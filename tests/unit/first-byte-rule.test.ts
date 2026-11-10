import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import { createAltmountBackend, offeredPathsOf } from '../../src/backends/altmount.js';
import { isSourceFailure } from '../../src/backends/types.js';
import { firstByteFailureLine, kindOfStatus, kindOfFetchError } from '../../src/backends/firstByte.js';

test('the first-byte rule by status', () => {
  assert.equal(kindOfStatus(404), 'gone');
  assert.equal(kindOfStatus(410), 'gone');
  assert.equal(kindOfStatus(400), 'keep-source');
  assert.equal(kindOfStatus(500), 'other');
  assert.equal(kindOfStatus(503), 'other');
});

test('a timeout keeps today\'s handling, a dropped connection does not', () => {
  assert.equal(kindOfFetchError(Object.assign(new Error('t'), { name: 'TimeoutError' })), 'other');
  assert.equal(kindOfFetchError(new TypeError('fetch failed')), 'keep-source');
});

test('the log line names status, path asked for and the files offered, no address or key', () => {
  const line = firstByteFailureLine('[x] ', 'status 400', '/complete/Oppenheimer.2023.mkv', ['/complete/Oppenheimer.2023.mkv/movie.mkv', '/complete/readme.nfo']);
  assert.match(line, /status 400/);
  assert.match(line, /asked for \/complete\/Oppenheimer\.2023\.mkv;/);
  assert.match(line, /offered: movie\.mkv, readme\.nfo/);
  assert.doesNotMatch(line, /http|download_key|apikey/i);
});

test('AltMount offered paths come from the reply', () => {
  const base = 'http://altmount:8080';
  const raw = JSON.stringify({ streams: [{ url: `${base}/api/files/stream?path=${encodeURIComponent('/a/b.mkv')}&download_key=k` }] });
  assert.deepEqual(offeredPathsOf(raw, base), ['/a/b.mkv']);
  assert.deepEqual(offeredPathsOf('oops', base), []);
});

async function probeWith(handler: http.RequestListener) {
  const server = http.createServer(handler);
  await new Promise<void>(r => server.listen(0, '127.0.0.1', r));
  const logs: string[] = [];
  const warn = console.warn;
  console.warn = (...a: unknown[]) => { logs.push(a.join(' ')); };
  try {
    const backend = createAltmountBackend({ url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, apiKey: 'k' });
    let error: unknown = null;
    await backend.probe({ nzoId: '1', videoPath: '/m/Movie.mkv', videoSize: 0, offered: ['/m/Movie.mkv'] }, { logPrefix: '[t] ' }).catch(e => { error = e; });
    return { error, logs };
  } finally {
    console.warn = warn;
    server.closeAllConnections();
    server.close();
  }
}

test('400 at the first byte: not a Source failure, one line logged', async () => {
  const { error, logs } = await probeWith((_req, res) => { res.writeHead(400); res.end(); });
  assert.ok(error instanceof Error && !isSourceFailure(error));
  assert.equal(logs.filter(l => l.includes('First byte failed')).length, 1);
  assert.ok(logs.some(l => l.includes('status 400') && l.includes('asked for /m/Movie.mkv') && l.includes('offered: Movie.mkv')));
});

test('dropped connection at the first byte: not a Source failure', async () => {
  const { error } = await probeWith((req) => { req.destroy(); });
  assert.ok(error instanceof Error && !isSourceFailure(error));
});

test('404 at the first byte: a Source failure', async () => {
  const { error } = await probeWith((_req, res) => { res.writeHead(404); res.end(); });
  assert.ok(isSourceFailure(error));
});

test('500 at the first byte: today\'s handling, a Source failure after the retries', async () => {
  const { error } = await probeWith((_req, res) => { res.writeHead(500); res.end(); });
  assert.ok(isSourceFailure(error));
});
