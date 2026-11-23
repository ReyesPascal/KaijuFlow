// The Source memory (GLOSSARY: Source memory, #247): ready and dead Sources remembered and recalled through its two
// operations, remember(outcome) and recall(Source, play context). No caller composes a key, so a Source remembered
// as one play makes it is found again as another play asks for it, for every episode, dated or not.
// Real config and Source memory; nothing else runs.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const load = p => import(root + '/dist/' + p + '.js');
const report = { id: 'INT-SOURCE-MEMORY-001', boundaries: ['Source memory only: no Backend, indexer or player'], results: [] };
const scenario = async (id, fn) => {
  try { await fn(); report.results.push({ id, status: 'pass' }); }
  catch (e) { report.results.push({ id, status: 'fail', error: String(e?.stack || e) }); }
};
try {
  await load('config/index');
  const { remember, recall } = await load('play/sourceMemory');
  const { makePlayContext } = await load('play/playContext');
  const witcher = (episode = 1) => makePlayContext({ manifestKey: 'synthetic-manifest', type: 'series', imdbId: 'tt5180504', season: 1, episode, aired: '2019-12-20', episodesInSeason: 8 });
  const video = (name) => ({ nzoId: 'altmount-job', videoPath: `/tv/The.Witcher/${name}.mkv`, videoSize: 4096 });

  await scenario('a-ready-source-for-a-dated-episode-is-recalled', () => {
    const source = { nzbUrl: 'http://127.0.0.1:1/api?t=get&id=witcher-s01e01', title: 'The.Witcher.S01E01.1080p.WEB.H264-GRP', indexerName: 'Parity' };
    remember({ source, play: witcher(), ready: video('s01e01') }); // as the Walk remembers it
    assert.deepEqual(recall(source, witcher()).ready, video('s01e01')); // as a play asks for it
  });

  report.status = report.results.every(r => r.status === 'pass') ? 'pass' : 'fail';
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
process.exit(report.status === 'pass' ? 0 : 1);
