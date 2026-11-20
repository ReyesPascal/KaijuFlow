// #179, ADR 0008: KaijuFlow plays plain video only. Its health check blocks every
// NZB with no video file before sampling a segment: any archive, and files it
// cannot name. Goes through the batch call the health-check coordinator makes.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { performBatchHealthChecks } from '../../src/health/index.ts';
import { nzbWithNews, type F } from './health-nzb.ts';

/** Health-check one NZB the way the coordinator does (one batch); `served` false leaves every article missing. */
async function check(files: F[], opts: { served?: boolean; password?: string } = {}) {
  const { url, provider, state } = await nzbWithNews(files, opts);
  const { results } = await performBatchHealthChecks([url], [provider], 'test-agent', 3, { archiveInspection: true, sampleCount: 3 });
  return { result: results.get(url)!, reads: state.reads, stats: state.stats };
}

const side = (): F[] => [{ name: 'Movie.nfo' }, { name: 'Movie.par2' }, { name: 'Movie.vol000+01.par2' }];
const big = { segs: 4, bytes: 700000 };

const archives: Array<[string, F[], string?]> = [
  ['a stored RAR5 set', [{ name: 'Movie.2160p.part01.rar', ...big }, { name: 'Movie.2160p.part02.rar', ...big }]],
  ['an old-style RAR set (.rar, .r00)', [{ name: 'Movie.2160p.rar', ...big }, { name: 'Movie.2160p.r00', ...big }]],
  ['a compressed 7z set', [{ name: 'Movie.2160p.7z.001', ...big }, { name: 'Movie.2160p.7z.002', ...big }]],
  ['an encrypted 7z with its password in the NZB', [{ name: 'Movie.2160p.7z', ...big }], 'secret'],
  ['a ZIP', [{ name: 'Movie.2160p.zip', ...big }]],
  ['files named only by hash (obfuscated)', [{ name: 'a1b2c3d4e5f60718', ...big }, { name: '9f8e7d6c5b4a3210' }]],
];

for (const [what, files, password] of archives) {
  test(`${what} is blocked as an archive with no segment reads`, async () => {
    const { result, reads, stats } = await check([...files, ...side()], { password });
    assert.equal(result.status, 'blocked');
    assert.equal(result.message, 'Blocked: archive, not plain video');
    assert.equal(result.playable, false);
    assert.deepEqual(reads, [], 'no article body is read');
    assert.deepEqual(stats, [], 'no segment is sampled');
  });
}

test('files with no video or archive name are blocked as unknown with no segment reads', async () => {
  const { result, reads, stats } = await check([{ name: 'Movie.2160p.bin', ...big }, ...side()]);
  assert.equal(result.status, 'blocked');
  assert.equal(result.message, 'Blocked: unknown files, not plain video');
  assert.equal(result.playable, false);
  assert.deepEqual(reads, []);
  assert.deepEqual(stats, []);
});

test('a video sample next to an archive does not count as plain video', async () => {
  const { result } = await check([{ name: 'Movie.sample.mkv' }, { name: 'Movie.part01.rar', ...big }, ...side()]);
  assert.equal(result.message, 'Blocked: archive, not plain video');
});

test('a plain MKV is verified', async () => {
  const { result, stats } = await check([{ name: 'Movie.2160p.mkv', ...big }, ...side()]);
  assert.equal(result.status, 'verified');
  assert.equal(result.playable, true);
  assert.equal(result.containerType, 'MKV');
  assert.equal(stats.length, 3, 'three segments are sampled');
});

test('a plain MKV with missing articles is still blocked', async () => {
  const { result } = await check([{ name: 'Movie.2160p.mkv', ...big }, ...side()], { served: false });
  assert.equal(result.status, 'blocked');
  assert.match(result.message, /^Missing 3 of 3 segments/);
});
