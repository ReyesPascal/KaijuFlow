/**
 * NNTP Connection Management
 *
 * Handles NNTP authentication, TLS/plain connections, timeout handling,
 * and connection pooling for reusing authenticated sockets within a batch.
 *
 * Every health-check connection takes a slot from one process-wide limit
 * (KaijuFlow finding 6), so health checks never hold more Usenet connections
 * than the cap across all workers, batches and providers combined. That
 * leaves the rest of the provider's connection limit for playback.
 *
 * TLS certificates are checked by default (finding 7). The "Verify TLS
 * Certificates" setting can turn the check off for a server the owner trusts.
 */

import * as net from 'net';
import * as tls from 'tls';

type NntpSocket = net.Socket | tls.TLSSocket;
type NntpProvider = { host: string; port: number; useTLS: boolean; username: string; password: string };

/** Default total health-check connections, shared by all workers and providers. */
export const DEFAULT_HEALTH_CHECK_CONNECTION_CAP = 8;
const MAX_HEALTH_CHECK_CONNECTION_CAP = 100;

/**
 * Counts open health-check connections against the cap. A slot is held from
 * just before connecting until the socket closes, including while the socket
 * sits idle in a pool. When a caller has to wait, one idle pooled socket is
 * closed to make room, so idle sockets never block an active check.
 */
class ConnectionLimiter {
  private cap = DEFAULT_HEALTH_CHECK_CONNECTION_CAP;
  private open = 0;
  private waiters: Array<() => void> = [];
  private idle = new Set<() => void>();

  setCap(cap: number): void {
    const n = Math.floor(cap);
    this.cap = Number.isFinite(n) && n >= 1
      ? Math.min(n, MAX_HEALTH_CHECK_CONNECTION_CAP)
      : DEFAULT_HEALTH_CHECK_CONNECTION_CAP;
    // Cap lowered: close idle pooled sockets now instead of waiting for them.
    let excess = this.open - this.cap;
    while (excess-- > 0 && this.idle.size > 0) this.evictOneIdle();
    while (this.open < this.cap && this.waiters.length > 0) {
      this.open++;
      this.waiters.shift()!();
    }
  }

  get hasWaiters(): boolean {
    return this.waiters.length > 0;
  }

  /** Wait for a slot. Returns a release function that is safe to call twice. */
  async acquire(): Promise<() => void> {
    this.setCap(readCap() ?? DEFAULT_HEALTH_CHECK_CONNECTION_CAP);
    if (this.open < this.cap) {
      this.open++;
    } else {
      await new Promise<void>(resolve => {
        this.waiters.push(resolve);
        this.evictOneIdle();
      });
    }
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.releaseSlot();
    };
  }

  /** Register an idle pooled socket that may be closed to free its slot. */
  registerIdle(evict: () => void): () => void {
    this.idle.add(evict);
    return () => { this.idle.delete(evict); };
  }

  private releaseSlot(): void {
    if (this.open <= this.cap && this.waiters.length > 0) {
      this.waiters.shift()!(); // hand the slot straight to the next waiter
    } else {
      this.open--;
    }
  }

  private evictOneIdle(): void {
    const evict = this.idle.values().next().value;
    if (evict) {
      this.idle.delete(evict);
      evict();
    }
  }
}

let readCap: () => number | undefined = () => DEFAULT_HEALTH_CHECK_CONNECTION_CAP;

/**
 * Bind the total health-check connection cap (the "Max Total Connections" setting,
 * `healthChecks.maxTotalConnections`, 1-100). The reader is called on every new
 * connection, a Play-time check's or Unscramble's alike, so the setting applies
 * to every one without a caller setting it first. Bound once, where the config loads.
 */
export function bindHealthCheckConnectionCap(read: () => number | undefined): void {
  readCap = read;
}

const limiter = new ConnectionLimiter();

let readVerifyTlsCertificates: () => boolean = () => true;

/**
 * Bind the "Verify TLS Certificates" setting (default on). The reader is
 * called on every new connection, so a changed setting applies right away.
 */
export function bindVerifyTlsCertificates(read: () => boolean): void {
  readVerifyTlsCertificates = read;
}

/** TLS options for an NNTP connection, with certificate checking per the setting. */
export function tlsConnectOptions(host: string, port: number): tls.ConnectionOptions {
  return { host, port, rejectUnauthorized: readVerifyTlsCertificates() };
}

/**
 * Turn an invalid-certificate error into one that says what failed and names
 * the setting that controls it. Other errors are returned unchanged.
 */
export function describeTlsError(err: Error, host: string, port: number): Error {
  if (!isCertificateError(err)) return err;
  return new Error(
    `TLS certificate check failed for ${host}:${port}: ${err.message}. ` +
    `Fix the server's certificate, or turn off "Verify TLS Certificates" in Health Checks settings if you trust this server.`,
    { cause: err },
  );
}

const CERTIFICATE_ERROR_CODES = new Set([
  'DEPTH_ZERO_SELF_SIGNED_CERT',
  'SELF_SIGNED_CERT_IN_CHAIN',
  'UNABLE_TO_VERIFY_LEAF_SIGNATURE',
  'UNABLE_TO_GET_ISSUER_CERT',
  'UNABLE_TO_GET_ISSUER_CERT_LOCALLY',
  'CERT_HAS_EXPIRED',
  'CERT_NOT_YET_VALID',
  'CERT_UNTRUSTED',
  'CERT_REVOKED',
  'CERT_SIGNATURE_FAILURE',
  'ERR_TLS_CERT_ALTNAME_INVALID',
]);

function isCertificateError(err: unknown): boolean {
  const code = (err as NodeJS.ErrnoException | undefined)?.code;
  return typeof code === 'string' && CERTIFICATE_ERROR_CODES.has(code);
}

/**
 * Connect to Usenet and authenticate. Waits for a slot under the total
 * health-check connection cap; the slot is freed when the socket closes.
 */
export async function connectToUsenet(provider: NntpProvider): Promise<NntpSocket> {
  const release = await limiter.acquire();
  let socket: NntpSocket;
  try {
    socket = await openAuthenticatedSocket(provider);
  } catch (err) {
    release();
    throw err;
  }
  if (socket.destroyed) release();
  else socket.once('close', release);
  return socket;
}

/**
 * Close a healthy connection politely: send QUIT and our FIN, then wait for
 * the server to close its side. The slot is freed on 'close', which only
 * fires after the server has seen us go, so the provider never counts the
 * old and the next connection at the same time. Falls back to destroy.
 */
export function closeGracefully(socket: NntpSocket, timeoutMs = 2000): void {
  if (socket.destroyed) return;
  if (!socket.writable) {
    socket.destroy();
    return;
  }
  const timer = setTimeout(() => socket.destroy(), timeoutMs);
  timer.unref?.();
  socket.once('close', () => clearTimeout(timer));
  socket.on('error', () => socket.destroy());
  socket.resume(); // drain the server's QUIT reply so its FIN is read
  socket.end('QUIT\r\n');
}

function openAuthenticatedSocket(provider: NntpProvider): Promise<NntpSocket> {
  return new Promise((resolve, reject) => {
    let resolved = false;

    const timeout = setTimeout(() => {
      if (!resolved && socket) {
        resolved = true;
        socket.destroy();
        reject(new Error('Connection timeout'));
      }
    }, 10000);

    let buffer = '';

    const socket = provider.useTLS
      ? tls.connect(tlsConnectOptions(provider.host, provider.port))
      : net.connect({ host: provider.host, port: provider.port });
    socket.setNoDelay(true);

    const cleanup = () => {
      clearTimeout(timeout);
      socket.removeListener('data', dataHandler);
      socket.removeListener('error', errorHandler);
      socket.removeListener('close', closeHandler);
      socket.removeListener('end', endHandler);
    };

    const dataHandler = (data: Buffer) => {
      buffer += data.toString();
      const lines = buffer.split('\r\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        // Server greeting
        if (line.startsWith('200') || line.startsWith('201')) {
          if (provider.username && provider.password) {
            socket.write(`AUTHINFO USER ${provider.username}\r\n`);
          } else {
            if (!resolved) {
              resolved = true;
              cleanup();
              resolve(socket);
            }
          }
        }
        // Username accepted
        else if (line.startsWith('381')) {
          socket.write(`AUTHINFO PASS ${provider.password}\r\n`);
        }
        // Authentication successful
        else if (line.startsWith('281')) {
          if (!resolved) {
            resolved = true;
            cleanup();
            resolve(socket);
          }
        }
        // Authentication failed
        else if (line.startsWith('481') || line.startsWith('482')) {
          if (!resolved) {
            resolved = true;
            cleanup();
            socket.destroy();
            reject(new Error('Authentication failed'));
          }
        }
      }
    };

    const errorHandler = (error: Error) => {
      if (!resolved) {
        resolved = true;
        clearTimeout(timeout);
        reject(describeTlsError(error, provider.host, provider.port));
      }
    };

    const closeHandler = () => {
      if (!resolved) {
        resolved = true;
        clearTimeout(timeout);
        socket.destroy();
        reject(new Error('Connection closed by server'));
      }
    };

    const endHandler = () => {
      closeHandler();
    };

    socket.on('data', dataHandler);
    socket.on('error', errorHandler);
    socket.on('close', closeHandler);
    socket.on('end', endHandler);
  });
}

/**
 * NNTP Connection Pool — reuses authenticated sockets within a batch
 * to avoid repeated TLS handshakes across multiple NZB health checks.
 */
export class NntpConnectionPool {
  private pools = new Map<string, NntpSocket[]>();
  private unregisterIdle = new Map<NntpSocket, () => void>();
  /** Sockets handed out and not yet given back. */
  private inUse = new Set<NntpSocket>();
  private isStopped = false;

  private key(provider: { host: string; port: number; username: string }): string {
    return `${provider.host}:${provider.port}:${provider.username}`;
  }

  /** stop() was called: the work this pool served was stopped, not answered. */
  get stopped(): boolean { return this.isStopped; }

  async acquire(provider: NntpProvider): Promise<NntpSocket> {
    if (this.stopped) throw new Error('Connection pool stopped');
    const k = this.key(provider);
    const stack = this.pools.get(k);
    while (stack && stack.length > 0) {
      const socket = stack.pop()!;
      this.unregisterIdle.get(socket)?.();
      this.unregisterIdle.delete(socket);
      // Verify the socket is still alive
      if (!socket.destroyed && socket.writable) {
        return this.handOut(socket);
      }
      // Socket is dead, try the next one or create new
      try { socket.destroy(); } catch {}
    }
    const socket = await connectToUsenet(provider);
    // Stopped while connecting: nobody is waiting for this one.
    if (this.stopped) { socket.destroy(); throw new Error('Connection pool stopped'); }
    return this.handOut(socket);
  }

  private handOut(socket: NntpSocket): NntpSocket {
    this.inUse.add(socket);
    socket.once('close', () => this.inUse.delete(socket));
    return socket;
  }

  /**
   * Stop the work this pool serves (a Walk that ended, GLOSSARY: Walk): close every connection now, the ones mid-read
   * too, and open no more. A read under way fails; its caller's answer is not wanted.
   */
  stop(): void {
    if (this.stopped) return;
    this.isStopped = true;
    for (const socket of this.inUse) socket.destroy();
    this.inUse.clear();
    this.destroyAll();
  }

  release(provider: { host: string; port: number; username: string }, socket: NntpSocket): void {
    this.inUse.delete(socket);
    // Someone is waiting for a slot under the cap: close instead of parking.
    if (socket.destroyed || !socket.writable || this.isStopped) {
      try { socket.destroy(); } catch {}
      return;
    }
    if (limiter.hasWaiters) {
      closeGracefully(socket);
      return;
    }
    const k = this.key(provider);
    let stack = this.pools.get(k);
    if (!stack) {
      stack = [];
      this.pools.set(k, stack);
    }
    stack.push(socket);
    const parked = stack;
    this.unregisterIdle.set(socket, limiter.registerIdle(() => {
      this.unregisterIdle.delete(socket);
      const i = parked.indexOf(socket);
      if (i >= 0) parked.splice(i, 1);
      closeGracefully(socket);
    }));
  }

  destroyAll(): void {
    for (const unregister of this.unregisterIdle.values()) unregister();
    this.unregisterIdle.clear();
    for (const [, stack] of this.pools) {
      for (const socket of stack) {
        closeGracefully(socket);
      }
    }
    this.pools.clear();
  }
}
