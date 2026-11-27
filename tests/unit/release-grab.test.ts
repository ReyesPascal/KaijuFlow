// The Walk's grab of a Release (#300, grabRelease) on a fake indexer: which failure is whose (spec #298's review, P5;
// owner, 2026-11-27). A bad NZB is the upload's fault: the whole Release is bad, and no other indexer is asked for it.
// A link the indexer took down (a 404, or an error payload with code 300) is that indexer's Source alone: the
// Release's Source on the next indexer is fetched. A refusal (429) names the indexer, and the Source stays alive.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { grabRelease, ReleaseGrabError } from '../../src/play/releaseGrab.ts';
import { recall } from '../../src/play/sourceMemory.ts';
import { isSourceFailure } from '../../src/backends/types.ts';
import { captureLogs } from './capture-logs.ts';

const VALID_NZB = `<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><file subject="&quot;a.mkv&quot;"><segments><segment bytes="1" number="1">a@fake</segment></segments></file></nzb>`;

// Fake indexer: the path picks the reply; every request is noted.
const asked: string[] = [];
const indexer = http.createServer((req, res) => {
  const path = req.url ?? '';
  asked.push(path);
  if (path.startsWith('/ok')) { res.writeHead(200, { 'Content-Type': 'application/x-nzb' }); res.end(VALID_NZB); return; }
  if (path.startsWith('/bad')) { res.writeHead(200, { 'Content-Type': 'application/x-nzb' }); res.end('<html>not an nzb</html>'); return; }
  if (path.startsWith('/429')) { res.writeHead(429); res.end('Too Many Requests'); return; }
  if (path.startsWith('/300')) { res.writeHead(200, { 'Content-Type': 'application/xml' }); res.end('<?xml version="1.0"?><error code="300" description="No such item"/>'); return; }
  res.writeHead(404); res.end();
});
await new Promise<void>(r => indexer.listen(0, '127.0.0.1', () => r()));
const base = `http://127.0.0.1:${(indexer.address() as { port: number }).port}`;
after(() => indexer.close());

let n = 0;
const run = Math.random().toString(36).slice(2, 8); // KaijuFlow's stats and dead marks outlive a test run
/** A Release on two indexers, A's Source answering `first` and B's `second` (paths of the fake). Each Release's
 *  indexers are new to KaijuFlow's stats (A1, B1, then A2, B2, ..., named for this run too), with no NZB download
 *  measured yet, so A's NZB is fetched first. */
function release(first: string, second: string) {
  const title = `Release.Grab.Test.${++n}.2026.1080p.WEB-DL-GRP`;
  const sources = [
    { nzbUrl: `${base}${first}?n=${n}&i=a`, title, indexerName: `A${run}-${n}`, size: 1000 },
    { nzbUrl: `${base}${second}?n=${n}&i=b`, title, indexerName: `B${run}-${n}`, size: 1000 },
  ];
  return { ...sources[0], sources };
}

async function grab(rel: ReturnType<typeof release>) {
  let out: Awaited<ReturnType<typeof grabRelease>> | undefined, err: unknown;
  await captureLogs(async () => { try { out = await grabRelease(rel); } catch (e) { err = e; } });
  return { out, err };
}

test('a bad NZB is the Release\'s: no other indexer is asked, and the grab fails as a bad Release', async () => {
  const rel = release('/bad', '/ok');
  const { out, err } = await grab(rel);
  assert.equal(out, undefined);
  assert.ok(err instanceof ReleaseGrabError, String(err));
  assert.equal(isSourceFailure(err), true, 'a bad Release: its caller marks it dead on every indexer');
  assert.deepEqual(err.refused, []);
  assert.equal(asked.filter(p => p.includes(`n=${n}&i=b`)).length, 0, 'B is never asked for the bad upload');
});

for (const gone of ['/404', '/300']) {
  test(`a link the first indexer took down (${gone.slice(1)}) is that Source's alone: the other indexer's plays`, async () => {
    const rel = release(gone, '/ok');
    const { out, err } = await grab(rel);
    assert.equal(err, undefined, String(err));
    assert.equal(out?.source.indexerName, `B${run}-${n}`);
    assert.deepEqual(out?.refused, []);
    assert.ok(recall(rel.sources[0]).dead, 'A\'s Source is marked dead');
    assert.equal(recall(rel.sources[1]).dead, undefined, 'B\'s Source is not');
    assert.equal(recall(rel).dead, undefined, 'the Release is alive');
  });
}

test('a refusal names the indexer and leaves the Source alive; refused everywhere, the grab fails as no bad Release', async () => {
  const one = release('/429', '/ok');
  const { out } = await grab(one);
  assert.equal(out?.source.indexerName, `B${run}-${n}`);
  assert.deepEqual(out?.refused, [`A${run}-${n}`]);
  assert.equal(recall(one.sources[0]).dead, undefined);

  const both = release('/429', '/429');
  const { err } = await grab(both);
  assert.ok(err instanceof ReleaseGrabError, String(err));
  assert.deepEqual(err.refused, [`A${run}-${n}`, `B${run}-${n}`]);
  assert.equal(isSourceFailure(err), false);
});
