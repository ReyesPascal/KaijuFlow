// The Source memory (GLOSSARY: Source memory, #247): ready and dead Sources remembered and recalled through its two
// operations, remember(outcome) and recall(Source, play context). No caller composes a key, so a Source remembered
// as one play makes it is found again as another play asks for it, for every episode, dated or not.
// Real config and Source memory; nothing else runs. The saved files are written in the previous build's layout.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const load = p => import(root + '/dist/' + p + '.js');
const report = { id: 'INT-SOURCE-MEMORY-001', boundaries: ['Source memory only: no Backend, indexer or player', 'Saved ready and dead files written as the previous build wrote them'], results: [] };
const scenario = async (id, fn) => {
  try { await fn(); report.results.push({ id, status: 'pass' }); }
  catch (e) { report.results.push({ id, status: 'fail', error: String(e?.stack || e) }); }
};

// What the previous build saved (keys and entries as it wrote them): a ready episode under its SxxExx pattern, a ready
// movie whose Prowlarr link had its search token stripped, a Source dead for every episode and one dead for S01E01.
const hour = Date.now() + 3_600_000;
const S01E01 = 'S01(?:[. _-]?E\\d+|-\\d{1,2})*(?:[. _-]?E01|-01)(?!\\d)'; // the multi-episode pattern, the default
const saved = {
  episode: { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=saved-s01e01', title: 'The.Witcher.S01E01.2160p.NF.WEB-DL.H265-GRP' },
  movie: { nzbUrl: 'http://127.0.0.1:9696/5/download?file=Saved.Movie&link=search-token-1', title: 'Saved.Movie.2026.1080p.WEB-DL.H264-GRP' },
  dead: { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=saved-dead', title: 'The.Witcher.S01.1080p.WEB.H264-BAD' },
  deadEpisode: { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=saved-dead-e01', title: 'The.Witcher.S01.720p.WEB.H264-PACK' },
  // Round 2 review of #239, memory-2: marks an earlier build wrote when the indexer answered a grab with a refusal payload.
  refused: { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=saved-refused', title: 'Saved.Movie.2026.2160p.WEB-DL.H265-LIMIT' },
  refusedEpisode: { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=saved-refused-e01', title: 'The.Witcher.S01E01.1080p.WEB.H264-LIMIT' },
};
const savedVideo = name => ({ nzoId: 'altmount-job', videoPath: `/saved/${name}.mkv`, videoSize: 2048 });
fs.mkdirSync(root + '/config', { recursive: true });
fs.writeFileSync(root + '/config/healthy-nzbs.json', JSON.stringify({
  [`${saved.episode.nzbUrl}::${saved.episode.title}:${S01E01}`]: { data: savedVideo('episode'), indexerName: 'Saved', createdAt: Date.now(), expiresAt: hour, backend: 'altmount' },
  ['http://127.0.0.1:9696/5/download?file=Saved.Movie::' + saved.movie.title]: { data: savedVideo('movie'), indexerName: 'Saved', createdAt: Date.now(), expiresAt: hour, backend: 'altmount' },
}));
fs.writeFileSync(root + '/config/dead-nzbs.json', JSON.stringify({
  [saved.dead.nzbUrl]: { title: saved.dead.title, indexerName: 'Saved', error: { message: 'Health check: blocked', isBadSource: true, isTimeout: false, isEpisodeSpecific: false }, createdAt: Date.now(), expiresAt: hour },
  [`${saved.deadEpisode.nzbUrl}::${S01E01}`]: { title: saved.deadEpisode.title, indexerName: 'Saved', error: { message: 'Episode not in the pack', isBadSource: true, isTimeout: false, isEpisodeSpecific: true }, createdAt: Date.now(), expiresAt: hour },
  // expiresAt 0: saved in storage mode (the default), where a mark never expires by time.
  [saved.refused.nzbUrl]: { title: saved.refused.title, indexerName: 'Saved', error: { message: 'Indexer returned error: Request limit reached', isBadSource: true, isTimeout: false, isEpisodeSpecific: false }, createdAt: Date.now(), expiresAt: 0 },
  [`${saved.refusedEpisode.nzbUrl}::${S01E01}`]: { title: saved.refusedEpisode.title, indexerName: 'Saved', error: { message: 'Indexer returned error: Download limit reached', isBadSource: true, isTimeout: false, isEpisodeSpecific: true }, createdAt: Date.now(), expiresAt: 0 },
}));

try {
  const { configData } = await load('config/index');
  const { remember, recall } = await load('play/sourceMemory');
  const { makePlayContext } = await load('play/playContext');
  const { sourceFailure } = await load('backends/types');
  const witcher = (episode = 1) => makePlayContext({ manifestKey: 'synthetic-manifest', type: 'series', imdbId: 'tt5180504', season: 1, episode, aired: '2019-12-20', episodesInSeason: 8 });
  const movie = makePlayContext({ manifestKey: 'synthetic-manifest', type: 'movie', imdbId: 'tt0000247' });
  const video = (name) => ({ nzoId: 'altmount-job', videoPath: `/tv/The.Witcher/${name}.mkv`, videoSize: 4096 });

  await scenario('a-ready-source-for-a-dated-episode-is-recalled', () => {
    const source = { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=witcher-s01e01', title: 'The.Witcher.S01E01.1080p.WEB.H264-GRP', indexerName: 'Parity' };
    remember({ source, play: witcher(), ready: video('s01e01') }); // as the Walk remembers it
    assert.deepEqual(recall(source, witcher()).ready, video('s01e01')); // as a play asks for it
    assert.equal(recall(source, witcher(2)).ready, undefined, 'another episode is not this one');
  });

  await scenario('a-cache-saved-by-the-previous-build-loads', () => {
    assert.deepEqual(recall(saved.episode, witcher()).ready, savedVideo('episode'));
    assert.deepEqual(recall({ ...saved.movie, nzbUrl: saved.movie.nzbUrl.replace('search-token-1', 'search-token-2') }, movie).ready, savedVideo('movie'),
      'a Prowlarr link from a later search is the same Source');
    assert.equal(recall(saved.dead, witcher(5)).dead?.message, 'Health check: blocked', 'dead for every episode');
    assert.equal(recall(saved.deadEpisode, witcher()).dead?.message, 'Episode not in the pack');
    assert.equal(recall(saved.deadEpisode, witcher(2)).dead, undefined, 'dead for S01E01 only');
  });

  // Round 2 review of #239, memory-2: ADR 0004 sorts an error payload with any code but 300
  // as a refusal, the Source kept. A mark an earlier build wrote for one is dropped when the memory loads, so the
  // Source is back in lists and Walks.
  await scenario('a-dead-mark-an-earlier-build-wrote-for-a-refusal-payload-is-dropped-on-load', () => {
    assert.equal(recall(saved.refused, movie).dead, undefined, 'a request limit says nothing about the Source');
    assert.equal(recall(saved.refusedEpisode, witcher()).dead, undefined, 'nor does a download limit, for the episode it was played as');
  });

  await scenario('a-source-the-check-blocked-is-dead-for-every-episode', () => {
    const source = { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=blocked', title: 'The.Witcher.S01E01.720p.WEB.H264-BLK', indexerName: 'Parity' };
    remember({ source, play: witcher(), dead: sourceFailure('Health check: blocked'), everyEpisode: true });
    assert.equal(recall(source, witcher(3)).dead?.message, 'Health check: blocked');
    assert.equal(recall(source, movie).dead?.message, 'Health check: blocked', 'whatever plays it');
  });

  await scenario('a-failure-in-a-pack-that-played-is-dead-for-its-episode-only', () => {
    const pack = { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=pack-played', title: 'The.Witcher.S01.1080p.NF.WEB-DL.H264-PACK', indexerName: 'Parity', isSeasonPack: true };
    remember({ source: pack, play: witcher(1), ready: video('pack-e01') });
    remember({ source: pack, play: witcher(2), dead: sourceFailure('Import failed') });
    assert.equal(recall(pack, witcher(2)).dead?.message, 'Import failed');
    assert.equal(recall(pack, witcher(3)).dead, undefined, 'the rest of the pack still plays');
    assert.deepEqual(recall(pack, witcher(1)), { ready: video('pack-e01') });
  });

  await scenario('a-pack-that-fails-whole-first-is-dead-for-every-episode', () => {
    const pack = { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=pack-dead', title: 'The.Witcher.S01.2160p.WEB.H265-GONE', indexerName: 'Parity', isSeasonPack: true };
    remember({ source: pack, play: witcher(1), dead: sourceFailure('Import failed') });
    assert.equal(recall(pack, witcher(6)).dead?.message, 'Import failed');
  });

  // Last: the limit evicts the oldest entries, those of the scenarios above included.
  await scenario('ready-sources-the-walk-remembers-are-held-to-the-storage-limit', () => {
    const before = { mode: configData.healthyNzbDbMode, max: configData.healthyNzbDbMaxSizeMB };
    configData.healthyNzbDbMode = 'storage';
    configData.healthyNzbDbMaxSizeMB = 1;
    try {
      const big = i => ({ nzoId: `job-${i}`, videoPath: `/movies/Big.${i}/` + 'x'.repeat(400_000) + '.mkv', videoSize: 4096 });
      const sources = [0, 1, 2].map(i => ({ nzbUrl: `http://127.0.0.1:1/api?t=get&id=big-${i}`, title: `Big.Movie.${i}.2026.1080p.WEB-DL.H264-GRP`, indexerName: 'Parity' }));
      sources.forEach((source, i) => remember({ source, play: movie, ready: big(i) }));
      assert.equal(recall(sources[0], movie).ready, undefined, 'the oldest goes once the memory is over 1 MB');
      assert.deepEqual(recall(sources[2], movie).ready, big(2));
      const onDisk = fs.statSync(root + '/config/healthy-nzbs.json').size;
      assert.ok(onDisk < 1024 * 1024, `saved within the limit (${onDisk} bytes)`);
    } finally {
      Object.assign(configData, { healthyNzbDbMode: before.mode, healthyNzbDbMaxSizeMB: before.max });
    }
  });

  report.status = report.results.every(r => r.status === 'pass') ? 'pass' : 'fail';
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
process.exit(report.status === 'pass' ? 0 : 1);
