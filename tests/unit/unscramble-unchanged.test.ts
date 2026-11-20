// Unscramble (#45, spec #42, ADR 0005): when it can't finish, the original NZB
// comes back with the reason; properly named and non-RAR Sources (a 7z set
// included, #193) cost no reads; the time limit and the health-check connection cap hold.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { unscrambleNzb } from '../../src/archive/unscramble.ts';
import { setHealthCheckConnectionCap, DEFAULT_HEALTH_CHECK_CONNECTION_CAP } from '../../src/health/nntpConnection.ts';
import { scrambledRarSet, startFakeNntp, rar5FirstArticle, rar4FirstArticle } from '../integration/parity/fake-nntp.mjs';
import { archiveFixture } from './health-nzb.ts';

const LIMIT_MS = 15000; // the spec's ceiling; these tests never get near it
const servers: Array<{ close(): Promise<void> }> = [];
after(async () => { for (const s of servers) await s.close(); });

async function news(opts: { articles?: Map<string, Buffer>; delayMs?: number } = {}) {
  const n = await startFakeNntp(opts);
  servers.push(n);
  return n;
}

/** An NZB with the given file names, one segment each. */
function nzbOf(names: string[]): string {
  return `<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">` +
    names.map((n, i) => `<file subject="&quot;${n}&quot; yEnc (1/1)"><segments><segment bytes="1000" number="1">plain-${i}@fake</segment></segments></file>`).join('') +
    `</nzb>`;
}

/** The result is the original NZB, unchanged, with this reason. */
function assertUnchanged(r: { nzb: string; changed: boolean; reason?: string }, nzb: string, reason: string, msg?: string) {
  assert.deepEqual({ nzb: r.nzb, changed: r.changed, reason: r.reason }, { nzb, changed: false, reason }, msg);
}

const until = async (ok: () => boolean, ms = 3000) => {
  const end = Date.now() + ms;
  while (!ok() && Date.now() < end) await new Promise(r => setTimeout(r, 20));
  return ok();
};

test('properly named RAR sets and non-RAR Sources come back unchanged with no reads', async () => {
  const n = await news();
  for (const names of [
    ['Movie.2026.nfo', 'Movie.2026.part01.rar', 'Movie.2026.part02.rar', 'Movie.2026.part03.rar'],
    ['Movie.2026.rar', 'Movie.2026.r00', 'Movie.2026.r01'],
    ['Movie.2026.mkv', 'Movie.2026.nfo', 'Movie.2026.vol00+01.par2'],
    ['Movie.2026.7z', 'Movie.2026.zip'],
  ]) {
    const nzb = nzbOf(names);
    const r = await unscrambleNzb(nzb, [n.provider()], LIMIT_MS);
    assert.deepEqual({ nzb: r.nzb, changed: r.changed, reason: r.reason, parts: r.parts }, { nzb, changed: false, reason: 'not-scrambled', parts: 0 }, names.join(','));
  }
  assert.equal(n.state.reads.length, 0, 'no first article should be read');
});

test('no enabled health-check provider: unchanged, no-provider, no reads', async () => {
  const set = scrambledRarSet({ base: 'noprov', parts: 4 });
  const n = await news({ articles: set.articles });
  for (const providers of [[], [{ ...n.provider(), enabled: false }]]) {
    const r = await unscrambleNzb(set.nzb, providers, LIMIT_MS);
    assert.deepEqual({ nzb: r.nzb, changed: r.changed, reason: r.reason, parts: r.parts }, { nzb: set.nzb, changed: false, reason: 'no-provider', parts: 4 });
  }
  assert.equal(n.state.reads.length, 0);
});

test('a missing first article: unchanged, missing-article', async () => {
  const set = scrambledRarSet({ base: 'missing', parts: 6 });
  set.articles.delete(set.parts[3].firstId);
  const n = await news({ articles: set.articles });
  const r = await unscrambleNzb(set.nzb, [n.provider()], LIMIT_MS);
  assertUnchanged(r, set.nzb, 'missing-article');
});

test('two parts claiming the same volume: unchanged, duplicate-volume', async () => {
  const set = scrambledRarSet({ base: 'dupe', parts: 4, firstArticle: (v: number) => rar5FirstArticle(v === 2 ? 1 : v) });
  const n = await news({ articles: set.articles });
  const r = await unscrambleNzb(set.nzb, [n.provider()], LIMIT_MS);
  assertUnchanged(r, set.nzb, 'duplicate-volume');
});

test('a real gap in the volume numbers: unchanged, volume-gap', async () => {
  const set = scrambledRarSet({ base: 'gap', parts: 4, firstArticle: (v: number) => rar5FirstArticle(v === 2 ? 9 : v) });
  const n = await news({ articles: set.articles });
  const r = await unscrambleNzb(set.nzb, [n.provider()], LIMIT_MS);
  assertUnchanged(r, set.nzb, 'volume-gap');
});

test('a RAR4 set: unchanged, not-rar5', async () => {
  const set = scrambledRarSet({ base: 'rar4', parts: 4, firstArticle: () => rar4FirstArticle() });
  const n = await news({ articles: set.articles });
  const r = await unscrambleNzb(set.nzb, [n.provider()], LIMIT_MS);
  assertUnchanged(r, set.nzb, 'not-rar5');
});

test('a 7z set (<name>.7z.001 ...): unchanged from its names alone, no reads', async () => {
  // Test 1's 7z sets were named like this (hash base, .7z, three-digit numbers)
  // and each cost about a second reading first articles to answer not-rar5 (#193).
  const set = scrambledRarSet({ base: 'Xq7Lm2Pz9Rb4Vn8Kw3Ty5uhaF.7z', parts: 4, startAt: 1, width: 3, firstArticle: (v: number) => archiveFixture(`stored-split.7z.00${v + 1}`) });
  const n = await news({ articles: set.articles });
  const r = await unscrambleNzb(set.nzb, [n.provider()], LIMIT_MS);
  assert.deepEqual({ nzb: r.nzb, changed: r.changed, reason: r.reason, parts: r.parts }, { nzb: set.nzb, changed: false, reason: 'not-scrambled', parts: 0 });
  assert.equal(n.state.reads.length, 0, 'no first article should be read');
});

test('a number-named set of real RAR5 volumes is still Unscrambled', async () => {
  const set = scrambledRarSet({ base: 'f0729944c1d2e3b4', parts: 4, startAt: 1, width: 3, firstArticle: (v: number) => archiveFixture(`rar5-stored.part${v + 1}.rar`) });
  const n = await news({ articles: set.articles });
  const r = await unscrambleNzb(set.nzb, [n.provider()], LIMIT_MS);
  assert.equal(r.changed, true, `expected a rename, got ${r.reason}`);
  for (const p of set.parts) assert.ok(r.nzb.includes(`&quot;f0729944c1d2e3b4.part0${p.volume + 1}.rar&quot;`), `${p.name} is volume ${p.volume}`);
  assert.equal(n.state.reads.length, 4, 'one first article per part');
});

test('an unreachable provider: unchanged, read-error, nothing thrown', async () => {
  const set = scrambledRarSet({ base: 'down', parts: 3 });
  const n = await news();
  await n.close();
  const r = await unscrambleNzb(set.nzb, [n.provider()], LIMIT_MS);
  assertUnchanged(r, set.nzb, 'read-error');
});

test('a slow server: unchanged within the time limit, reads stop and connections close', async () => {
  const set = scrambledRarSet({ base: 'slow', parts: 12 });
  const n = await news({ articles: set.articles, delayMs: 2000 });
  const started = Date.now();
  const r = await unscrambleNzb(set.nzb, [n.provider()], 300);
  const took = Date.now() - started;
  assert.deepEqual({ nzb: r.nzb, changed: r.changed, reason: r.reason, parts: r.parts }, { nzb: set.nzb, changed: false, reason: 'timeout', parts: 12 });
  assert.ok(took < 2000, `should give up near the 300 ms limit, not wait out the 2 s server delay; took ${took} ms`);
  assert.ok(r.ms <= took);
  const readsAtReturn = n.state.reads.length;
  assert.ok(readsAtReturn > 0 && readsAtReturn < 12, `reads in flight at the limit: ${readsAtReturn}`);
  assert.ok(await until(() => n.state.open === 0), `connections should close, ${n.state.open} still open`);
  await new Promise(r => setTimeout(r, 300));
  assert.equal(n.state.reads.length, readsAtReturn, 'no read should start after the limit');
});

test('the health-check connection cap is never exceeded', async () => {
  const set = scrambledRarSet({ base: 'cap', parts: 20, seed: 3 });
  const n = await news({ articles: set.articles, delayMs: 15 });
  setHealthCheckConnectionCap(3);
  try {
    const r = await unscrambleNzb(set.nzb, [n.provider()], LIMIT_MS, { connections: 8 });
    assert.equal(r.changed, true, `expected a rename, got ${r.reason}`);
    assert.ok(n.state.peak <= 3, `peak ${n.state.peak} connections, cap 3`);
    assert.equal(new Set(n.state.reads).size, 20, 'every part read once');
  } finally {
    setHealthCheckConnectionCap(DEFAULT_HEALTH_CHECK_CONNECTION_CAP);
  }
});
