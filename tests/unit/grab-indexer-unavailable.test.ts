// #51 (ADR 0004): an indexer that doesn't hand over the NZB (429, 5xx, network
// error) is not a bad Source. The grab throws a plain error for those, so the
// player gets the failure video and the Source stays alive. Only bad NZB
// content (invalid body, indexer error payload) is a Source failure.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { grabNzb } from '../../src/nzbdav/nzbdavApi.ts';
import { isIndexerUnavailableMessage } from '../../src/nzbdav/utils.ts';
import { isSourceFailure } from '../../src/backends/types.ts';

const VALID_NZB = `<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><file subject="&quot;a.mkv&quot;"><segments><segment bytes="1" number="1">a@fake</segment></segments></file></nzb>`;

// Fake indexer: the path picks the reply.
const indexer = http.createServer((req, res) => {
  const path = req.url ?? '';
  if (path.startsWith('/ok')) { res.writeHead(200, { 'Content-Type': 'application/x-nzb' }); res.end(VALID_NZB); return; }
  if (path.startsWith('/429')) { res.writeHead(429, { 'Retry-After': '60' }); res.end('Too Many Requests'); return; }
  if (path.startsWith('/503')) { res.writeHead(503); res.end('maintenance'); return; }
  if (path.startsWith('/html')) { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end('<html>login please</html>'); return; }
  if (path.startsWith('/apierror')) { res.writeHead(200, { 'Content-Type': 'application/xml' }); res.end('<?xml version="1.0"?><error code="100" description="Incorrect user credentials"/>'); return; }
  res.writeHead(404); res.end();
});
await new Promise<void>(r => indexer.listen(0, '127.0.0.1', () => r()));
const base = `http://127.0.0.1:${(indexer.address() as { port: number }).port}`;
after(() => indexer.close());

let n = 0;
const grab = (path: string) => grabNzb(`${base}${path}?n=${++n}`, `Grab Test ${n}`, undefined, '', 'FakeIndexer');

async function failure(path: string): Promise<Error> {
  try { await grab(path); } catch (err) { return err as Error; }
  assert.fail(`${path} should have thrown`);
}

test('a good NZB comes back as text', async () => {
  assert.equal(await grab('/ok'), VALID_NZB);
});

test('indexer 429: a plain error, not a Source failure', async () => {
  const err = await failure('/429');
  assert.equal(isSourceFailure(err), false, err.message);
  assert.match(err.message, /FakeIndexer.*429/);
});

test('indexer 5xx: a plain error, not a Source failure', async () => {
  const err = await failure('/503');
  assert.equal(isSourceFailure(err), false, err.message);
  assert.match(err.message, /503/);
});

test('indexer unreachable: a plain error, not a Source failure', async () => {
  const closed = http.createServer();
  await new Promise<void>(r => closed.listen(0, '127.0.0.1', () => r()));
  const port = (closed.address() as { port: number }).port;
  await new Promise<void>(r => closed.close(() => r()));
  let err: Error | undefined;
  try { await grabNzb(`http://127.0.0.1:${port}/x.nzb`, 'Unreachable', undefined, '', 'FakeIndexer'); } catch (e) { err = e as Error; }
  assert.ok(err, 'should have thrown');
  assert.equal(isSourceFailure(err), false, err.message);
});

test('a body that is not an NZB is still a Source failure', async () => {
  const err = await failure('/html');
  assert.equal(isSourceFailure(err), true, err.message);
});

test('an indexer error payload is still a Source failure', async () => {
  const err = await failure('/apierror');
  assert.equal(isSourceFailure(err), true, err.message);
  assert.match(err.message, /Incorrect user credentials/);
});

test('stored dead marks from an unavailable indexer are recognised, bad-Source ones are not', () => {
  // Messages as written by earlier KaijuFlow/UU builds into dead-nzbs.json.
  for (const m of [
    'Failed to download NZB from altHUB: 429 Too Many Requests',
    'Failed to download NZB from NinjaCentral: 502 Bad Gateway',
    'NZB download failed for DrunkenSlug: fetch failed',
    'NZB download timed out after 30s for altHUB',
  ]) assert.equal(isIndexerUnavailableMessage(m), true, m);
  for (const m of [
    'Invalid NZB content received (1234 bytes)',
    'Indexer returned error: Incorrect user credentials',
    'Health check: blocked',
    'NZBDav download failed: Article with message-id x@y not found.',
    'AltMount could not process the Source: {"error":{"code":"INTERNAL_SERVER_ERROR"}}',
    'Failed to download NZB from altHUB: 404 Not Found',
  ]) assert.equal(isIndexerUnavailableMessage(m), false, m);
});
