// KaijuFlow finding 6: health checks never hold more Usenet connections at
// once than the total cap, across all checks and providers combined. The checks
// run in parallel on one shared pool, as Best checks its Sources (#190), through
// the Play-time check's call (checkSource), which a clicked list entry makes too.
// The cap is the setting (healthChecks.maxTotalConnections): nothing sets it
// before a check (#191's review, rule 4).
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { NntpConnectionPool } from '../../src/health/index.ts';
import { configData } from '../../src/config/index.ts';
import { checkSource } from '../../src/play/playTimeCheck.ts';
import { cacheNzbContent } from '../../src/health/nzbContentCache.ts';
import type { UsenetProvider } from '../../src/types.ts';

// --- Fake NNTP server shared by two providers; counts open connections ---
let open = 0;
let peak = 0;
const sockets = new Set<net.Socket>();

function startFakeNntp(missingIds: Set<string>): Promise<net.Server> {
  const server = net.createServer(sock => {
    open++;
    peak = Math.max(peak, open);
    sockets.add(sock);
    // A connection stops counting once the server handles QUIT or sees the client close it.
    let counted = true;
    const gone = () => { if (counted) { counted = false; open--; } sockets.delete(sock); };
    sock.on('end', gone);
    sock.on('close', gone);
    sock.on('error', () => {});
    sock.write('200 fake news ready\r\n');
    let buf = '';
    sock.on('data', d => {
      buf += d.toString();
      const lines = buf.split('\r\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('QUIT')) { gone(); sock.end('205 bye\r\n'); }
        else if (line.startsWith('AUTHINFO USER')) sock.write('381 more\r\n');
        else if (line.startsWith('AUTHINFO PASS')) sock.write('281 ok\r\n');
        else if (line.startsWith('STAT')) {
          const id = line.slice(line.indexOf('<') + 1, line.lastIndexOf('>'));
          // Slow replies so workers overlap and connections pile up.
          setTimeout(() => {
            if (!sock.destroyed) sock.write(missingIds.has(id) ? `430 no such article\r\n` : `223 0 <${id}>\r\n`);
          }, 40);
        }
      }
    });
  });
  return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function nzbXml(name: string): string {
  const segs = [1, 2, 3, 4, 5]
    .map(n => `<segment bytes="500000" number="${n}">${name}-seg${n}@fake</segment>`)
    .join('');
  return `<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">` +
    `<file subject="&quot;${name}.mkv&quot; yEnc (1/5)"><segments>${segs}</segments></file></nzb>`;
}

// 8 Sources: odd ones are missing their last article on every provider.
const names = Array.from({ length: 8 }, (_, i) => `source${i}`);
const urls = names.map(n => `http://nzb.invalid/${n}.nzb`);
const missing = new Set(names.filter((_, i) => i % 2 === 1).map(n => `${n}-seg5@fake`));
const expectedPlayable = Object.fromEntries(urls.map((u, i) => [u, i % 2 === 0]));

const servers = await Promise.all([startFakeNntp(missing), startFakeNntp(missing)]);
const providers: UsenetProvider[] = servers.map((s, i) => ({
  id: `p${i}`,
  name: `Fake ${i}`,
  host: '127.0.0.1',
  port: (s.address() as net.AddressInfo).port,
  useTLS: false,
  username: 'user',
  password: 'pass',
  enabled: true,
  type: 'pool',
}));

const savedHealthChecks = configData.healthChecks;
after(() => {
  configData.healthChecks = savedHealthChecks;
  for (const s of sockets) s.destroy();
  for (const s of servers) s.close();
});

/** Check all 8 Sources at once on one shared pool, with the connection cap setting at `cap`. */
async function runChecks(cap: number) {
  for (let i = 0; i < names.length; i++) cacheNzbContent(urls[i], nzbXml(names[i]));
  configData.healthChecks = { ...savedHealthChecks, providers, maxTotalConnections: cap } as typeof savedHealthChecks;
  open = 0;
  peak = 0;
  const pool = new NntpConnectionPool();
  let results;
  try {
    results = await Promise.all(urls.map((u, i) => checkSource({ nzbUrl: u, title: names[i], indexerName: 'Parity' }, pool)));
  } finally {
    pool.destroyAll();
  }
  // Let the server see the pool's sockets close.
  await new Promise(r => setTimeout(r, 50));
  const playable = Object.fromEntries(results.map((r, i) => [urls[i], r.playable]));
  return { playable, peak };
}

test('without a tight cap, 8 checks x 2 providers open far more than 3 connections', async () => {
  const { playable, peak } = await runChecks(100);
  assert.deepEqual(playable, expectedPlayable);
  assert.ok(peak > 3, `expected the uncapped run to exceed 3 connections, saw ${peak}`);
});

test('a cap of 3 holds across all checks and providers, with the same verdicts', async () => {
  const { playable, peak } = await runChecks(3);
  assert.ok(peak <= 3, `peak simultaneous connections was ${peak}, cap is 3`);
  assert.ok(peak >= 1);
  assert.deepEqual(playable, expectedPlayable);
});

test('a cap of 1 still gives the same verdicts, only slower', async () => {
  const { playable, peak } = await runChecks(1);
  assert.equal(peak, 1);
  assert.deepEqual(playable, expectedPlayable);
});

test('all connections are closed after capped checks', async () => {
  await runChecks(2);
  assert.equal(open, 0);
});
