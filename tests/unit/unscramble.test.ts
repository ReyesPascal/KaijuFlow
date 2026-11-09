// Unscramble (#44, spec #42, ADR 0005): a Scrambled RAR set is renamed to
// <name>.partNN.rar in real RAR5 volume order, read from each part's first
// article on the health-check providers. Main path; the "upload unchanged"
// cases are #45. Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { unscrambleNzb } from '../../src/archive/unscramble.ts';
import { scrambledRarSet, startFakeNntp } from '../integration/parity/fake-nntp.mjs';

type Part = { name: string; volume: number; firstId: string };
const servers: Array<{ close(): Promise<void> }> = [];
after(async () => { for (const s of servers) await s.close(); });

/** The original NZB with only the part names swapped for the expected ones. */
function expectedNzb(nzb: string, parts: Part[], base: string, width: number): string {
  let out = nzb;
  for (const p of parts) out = out.replace(`&quot;${p.name}&quot;`, `&quot;${base}.part${String(p.volume + 1).padStart(width, '0')}.rar&quot;`);
  return out;
}

test('a shuffled set starting at .10 is renamed in real volume order', async () => {
  const base = 'a1b2c3d4e5f6';
  const set = scrambledRarSet({ base, parts: 12, startAt: 10 });
  // The fixture really is scrambled: the name order is not the volume order.
  assert.notDeepEqual(set.parts.map((p: Part) => p.volume), [...Array(12).keys()]);
  const news = await startFakeNntp({ articles: set.articles });
  servers.push(news);

  const r = await unscrambleNzb(set.nzb, [news.provider()], 15000);

  assert.equal(r.changed, true, `expected a rename, got reason ${r.reason}`);
  assert.equal(r.parts, 12);
  assert.ok(r.ms >= 0 && r.ms < 15000);
  // Only the names change: segments, ids, sizes, nfo/par2 and <head> are byte-for-byte the same.
  assert.equal(r.nzb, expectedNzb(set.nzb, set.parts, base, 2));
  // Volume 0 (the first volume, no number in its header) is part01.
  const first = set.parts.find((p: Part) => p.volume === 0)!;
  assert.ok(r.nzb.includes(`segment bytes="750000" number="1">${first.firstId}</segment>`));
  // One read per part, the first article only.
  assert.deepEqual([...news.state.reads].sort(), set.parts.map((p: Part) => p.firstId).sort());
});

test('a set shuffled without a gap is still renamed', async () => {
  const base = 'nogap';
  const set = scrambledRarSet({ base, parts: 5, startAt: 1, width: 3, seed: 11 });
  assert.notDeepEqual(set.parts.map((p: Part) => p.volume), [...Array(5).keys()]);
  const news = await startFakeNntp({ articles: set.articles });
  servers.push(news);

  const r = await unscrambleNzb(set.nzb, [news.provider()], 15000);

  assert.equal(r.changed, true, `expected a rename, got reason ${r.reason}`);
  assert.equal(r.parts, 5);
  assert.equal(r.nzb, expectedNzb(set.nzb, set.parts, base, 2));
});

test('names are zero-padded to the part count', async () => {
  const base = 'wide';
  const set = scrambledRarSet({ base, parts: 103, startAt: 0, seed: 5 });
  const news = await startFakeNntp({ articles: set.articles });
  servers.push(news);

  const r = await unscrambleNzb(set.nzb, [news.provider()], 15000);

  assert.equal(r.changed, true, `expected a rename, got reason ${r.reason}`);
  assert.ok(r.nzb.includes('&quot;wide.part001.rar&quot;') && r.nzb.includes('&quot;wide.part103.rar&quot;'));
  assert.equal(r.nzb, expectedNzb(set.nzb, set.parts, base, 3));
});

test('a non-RAR number-named split next to a Scrambled RAR set is left alone, the RAR set is still renamed', async () => {
  const rar = scrambledRarSet({ base: 'movie', parts: 4, startAt: 10, tag: 'rar' });
  const sevenZip = Buffer.concat([Buffer.from([0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c]), Buffer.alloc(64)]);
  const split = scrambledRarSet({ base: 'extras.7z', parts: 3, startAt: 1, width: 3, tag: '7z', firstArticle: () => sevenZip });
  const splitFiles = [...split.nzb.matchAll(/<file [\s\S]*?<\/file>/g)].map(m => m[0]).join('\n');
  const nzb = rar.nzb.replace('</nzb>', `${splitFiles}\n</nzb>`);
  const news = await startFakeNntp({ articles: new Map([...rar.articles, ...split.articles]) });
  servers.push(news);

  const r = await unscrambleNzb(nzb, [news.provider()], 15000);

  assert.equal(r.changed, true, `expected a rename, got reason ${r.reason}`);
  assert.equal(r.nzb, expectedNzb(nzb, rar.parts, 'movie', 2));
});
