// #203: for an episode, the Play-time check samples the file AltMount will be
// asked to play, chosen with the same episode selector KaijuFlow sends AltMount,
// not the first video file of the NZB. Goes through the Play-time check's call
// (checkSource) on NZBs captured on Brain (tests/fixtures/nzbs, review rule 2)
// and the fake news server.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { configData } from '../../src/config/index.ts';
import { checkSource } from '../../src/play/playTimeCheck.ts';
import { buildEpisodePattern } from '../../src/play/utils.ts';
import { capturedNzbWithNews } from './health-nzb.ts';

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
