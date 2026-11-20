import test from 'node:test';
import assert from 'node:assert/strict';
import { seasonEpisodeOf } from '../../src/backends/altmount.js';
import { buildEpisodePattern, buildDateEpisodePattern } from '../../src/play/utils.js';

test('season and episode are read back from the episode pattern', () => {
  for (const multi of [false, true]) {
    assert.deepEqual(seasonEpisodeOf(buildEpisodePattern(2, 5, multi)), { season: 2, episode: 5 });
    assert.deepEqual(seasonEpisodeOf(buildEpisodePattern(12, 103, multi)), { season: 12, episode: 103 });
  }
  const dated = `(?:${buildEpisodePattern(1, 3, true)}|${buildDateEpisodePattern('2026-01-02')})`;
  assert.deepEqual(seasonEpisodeOf(dated), { season: 1, episode: 3 });
});

test('no episode selection means no season/episode', () => {
  assert.equal(seasonEpisodeOf(undefined), null);
  assert.equal(seasonEpisodeOf(buildDateEpisodePattern('2026-01-02')), null);
});
