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
 */

import * as net from 'net';
import * as tls from 'tls';

type NntpSocket = net.Socket | tls.TLSSocket;
type NntpProvider = { host: string; port: number; useTLS: boolean; username: string; password: string };

/** Default total health-check connections, shared by all workers and providers. */
export const DEFAULT_HEALTH_CHECK_CONNECTION_CAP = 8;

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
    this.cap = Number.isFinite(n) && n >= 1 ? n : DEFAULT_HEALTH_CHECK_CONNECTION_CAP;
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

const limiter = new ConnectionLimiter();

/** Set the total health-check connection cap (the "max total connections" setting). */
export function setHealthCheckConnectionCap(cap: number): void {
  limiter.setCap(cap);
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
      ? tls.connect({ host: provider.host, port: provider.port, rejectUnauthorized: false })
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
        reject(error);
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

  private key(provider: { host: string; port: number; username: string }): string {
    return `${provider.host}:${provider.port}:${provider.username}`;
  }

  async acquire(provider: NntpProvider): Promise<NntpSocket> {
    const k = this.key(provider);
    const stack = this.pools.get(k);
    while (stack && stack.length > 0) {
      const socket = stack.pop()!;
      this.unregisterIdle.get(socket)?.();
      this.unregisterIdle.delete(socket);
      // Verify the socket is still alive
      if (!socket.destroyed && socket.writable) {
        return socket;
      }
      // Socket is dead, try the next one or create new
      try { socket.destroy(); } catch {}
    }
    return connectToUsenet(provider);
  }

  release(provider: { host: string; port: number; username: string }, socket: NntpSocket): void {
    // Someone is waiting for a slot under the cap: close instead of parking.
    if (socket.destroyed || !socket.writable || limiter.hasWaiters) {
      try { socket.destroy(); } catch {}
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
      try { socket.destroy(); } catch {}
    }));
  }

  destroyAll(): void {
    for (const unregister of this.unregisterIdle.values()) unregister();
    this.unregisterIdle.clear();
    for (const [, stack] of this.pools) {
      for (const socket of stack) {
        try { socket.destroy(); } catch {}
      }
    }
    this.pools.clear();
  }
}
