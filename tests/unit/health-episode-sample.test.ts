// #203: for an episode, the Play-time check samples the file AltMount will be
// asked to play, chosen with the same episode selector KaijuFlow sends AltMount,
// not the first video file of the NZB. Goes through the Play-time check's call
// (checkSource) on NZBs captured on Brain (tests/fixtures/nzbs)
// and the fake news server.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { configData } from '../../src/config/index.ts';
import { checkSource } from '../../src/play/playTimeCheck.ts';
import { buildEpisodePattern } from '../../src/play/utils.ts';
import { capturedNzbWithNews, nzbWithNews } from './health-nzb.ts';

const savedHealthChecks = configData.healthChecks;
after(() => { configData.healthChecks = savedHealthChecks; });

/** The Play-time check of a captured NZB, its fake news server the one health-check provider. */
async function check(fixture: string, { missing = [] as string[], episodePattern = undefined as string | undefined } = {}) {
  const { url, provider, state } = await capturedNzbWithNews(fixture, { missing });
  configData.healthChecks = { ...savedHealthChecks, providers: [provider] } as typeof savedHealthChecks;
  const result = await checkSource({ nzbUrl: url, title: fixture, indexerName: 'Parity', episodePattern });
  return { result, stats: state.stats };
}

// The Twilight Zone S02 by edge2020 (#189's warm-round Source): 8 obfuscated par2 files, then 29 loose episodes, S02E01 first.
const PACK = 'season-pack-loose-edge2020.nzb';
const S02E01 = 'The.Twilight.Zone.S02E01.';
const S02E06 = 'The.Twilight.Zone.S02E06.';
const wanted = (s: number, e: number) => buildEpisodePattern(s, e, false);

test('a loose-video season pack whose first episode is gone and whose wanted episode is complete is healthy', async () => {
  const { result } = await check(PACK, { missing: [S02E01], episodePattern: wanted(2, 6) });
  assert.equal(result.status, 'verified', result.message);
});

test('a loose-video season pack whose wanted episode is gone is blocked, though its first episode is complete', async () => {
  const { result } = await check(PACK, { missing: [S02E06], episodePattern: wanted(2, 6) });
  assert.equal(result.status, 'blocked');
  assert.match(result.message, /^Missing 3 of 3 segments/);
});

test('the multi-episode selector picks the same file', async () => {
  const { result } = await check(PACK, { missing: [S02E06], episodePattern: buildEpisodePattern(2, 6, true) });
  assert.equal(result.status, 'blocked');
});

test('a season pack with no file the selector picks is checked on its first video file, as before', async () => {
  assert.equal((await check(PACK, { missing: [S02E06], episodePattern: wanted(3, 6) })).result.status, 'verified');
  assert.equal((await check(PACK, { missing: [S02E01], episodePattern: wanted(3, 6) })).result.status, 'blocked');
});

// Thief (1981): 8 obfuscated par2 files listed first, the film last. Ted Lasso S01E01: the episode first, then par2 files.
for (const [what, fixture, video, episodePattern] of [
  ['a film', 'film-thief-1981.nzb', 'Thief.1981.', undefined],
  ['a single-episode NZB', 'episode-ted-lasso-s01e01.nzb', 'Ted.Lasso.S01E01.', wanted(1, 1)],
] as const) {
  test(`${what} is checked as before: verified when complete, blocked when its video is gone`, async () => {
    const ok = await check(fixture, { episodePattern });
    assert.equal(ok.result.status, 'verified', ok.result.message);
    assert.equal(ok.stats.length, 3, 'three segments of the video are sampled');
    const gone = await check(fixture, { missing: [video], episodePattern });
    assert.equal(gone.result.status, 'blocked');
  });
}

// What a blocked verdict is remembered for (#203's review): a check that sampled the wanted episode's file of a pack
// of loose videos speaks for that episode only, so the pack is remembered dead for that episode, not for the others.
test('a pack blocked on its wanted episode says its verdict holds for that episode only', async () => {
  const { result } = await check(PACK, { missing: [S02E06], episodePattern: wanted(2, 6) });
  assert.equal(result.status, 'blocked');
  assert.equal(result.episodeOnly, true);
});

test('a verdict on a film, a single episode or a pack checked on its first video holds for the whole NZB', async () => {
  for (const [fixture, missing, episodePattern] of [
    ['film-thief-1981.nzb', 'Thief.1981.', undefined],
    ['episode-ted-lasso-s01e01.nzb', 'Ted.Lasso.S01E01.', wanted(1, 1)],
    [PACK, S02E01, wanted(3, 6)],
  ] as const) {
    const { result } = await check(fixture, { missing: [missing], episodePattern });
    assert.equal(result.status, 'blocked', fixture);
    assert.notEqual(result.episodeOnly, true, fixture);
  }
});

test('a RAR season pack, sampled across its parts, is blocked for the whole NZB as before', async () => {
  const parts = [1, 2, 3].map(n => ({ name: `Show.S01.2160p.WEB-DL-GRP.part${n}.rar`, segs: 3 }));
  const { url, provider } = await nzbWithNews(parts, { served: false });
  configData.healthChecks = { ...savedHealthChecks, providers: [provider] } as typeof savedHealthChecks;
  const result = await checkSource({ nzbUrl: url, title: 'Show.S01', indexerName: 'Parity', episodePattern: wanted(1, 2) });
  assert.equal(result.status, 'blocked', result.message);
  assert.notEqual(result.episodeOnly, true);
});
