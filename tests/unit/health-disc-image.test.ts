// #120: the health check blocks a Source whose only real content is a bare disc image.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { performHealthCheck } from '../../src/health/index.ts';
import { cacheNzbContent } from '../../src/health/nzbContentCache.ts';
import { rar5FirstArticle, startFakeNntp } from '../integration/parity/fake-nntp.mjs';

const servers: Array<{ close(): Promise<void> }> = [];
after(async () => { for (const s of servers) await s.close(); });

type F = { name: string; segs?: number; bytes?: number };
function nzb(files: F[], tag: string): string {
  const body = files.map(f => {
    const n = f.segs ?? 1;
    const segs = Array.from({ length: n }, (_, i) =>
      `<segment bytes="${f.bytes ?? 1000}" number="${i + 1}">${tag}-${f.name}-${i + 1}@fake</segment>`).join('');
    return `<file subject="&quot;${f.name}&quot; yEnc (1/${n})"><segments>${segs}</segments></file>`;
  }).join('');
  return `<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">${body}</nzb>`;
}

let n = 0;
/** Run the health check on an NZB with these files; `served` false leaves every article missing. */
async function check(files: F[], served = true) {
  const tag = `t${++n}`;
  const articles = new Map<string, Buffer>();
  if (served) {
    for (const f of files) {
      for (let i = 1; i <= (f.segs ?? 1); i++) {
        articles.set(`${tag}-${f.name}-${i}@fake`, /\.rar$/.test(f.name) ? rar5FirstArticle(0) : Buffer.alloc(100, 0x41));
      }
    }
  }
  const news = await startFakeNntp({ articles });
  servers.push(news);
  const url = `http://indexer.invalid/${tag}.nzb`;
  cacheNzbContent(url, nzb(files, tag));
  const result = await performHealthCheck(url, [news.provider()], 'test-agent', { archiveInspection: true, sampleCount: 3 });
  return { result, reads: news.state.reads };
}

const side = (): F[] => [
  { name: 'Movie.nfo' }, { name: 'Movie.url' },
  { name: 'Movie.par2' }, { name: 'Movie.vol000+01.par2' },
];

for (const ext of ['iso', 'IMG']) {
  test(`a bare .${ext} with nfo, url and par2 is blocked as Disc image with no segment reads`, async () => {
    const { result, reads } = await check([{ name: `Movie.${ext}`, segs: 5, bytes: 700000 }, ...side()]);
    assert.equal(result.status, 'blocked');
    assert.equal(result.message, 'Disc image');
    assert.equal(result.playable, false);
    assert.equal(reads.length, 0);
  });
}

test('an .mkv inside a RAR set is still accepted', async () => {
  const { result } = await check([
    { name: 'Movie.part01.rar', segs: 3, bytes: 700000 }, { name: 'Movie.part02.rar', segs: 3, bytes: 700000 }, ...side(),
  ]);
  assert.notEqual(result.message, 'Disc image');
  assert.match(result.status, /^verified/);
});

test('an .iso next to a recognized video file does not block it', async () => {
  const { result } = await check([{ name: 'Movie.mkv' }, { name: 'Extras.iso', segs: 5, bytes: 700000 }]);
  assert.match(result.status, /^verified/);
});

test('files named only by hash still fall back to sampling the largest file', async () => {
  const files = [{ name: 'a1b2c3d4e5f60718', segs: 4, bytes: 700000 }, { name: '9f8e7d6c5b4a3210' }];
  assert.match((await check(files)).result.status, /^verified/);
  // Sampled for real: with every article missing the Source is not verified.
  const missing = (await check(files, false)).result;
  assert.doesNotMatch(missing.status, /^verified/);
  assert.notEqual(missing.message, 'Disc image');
});
