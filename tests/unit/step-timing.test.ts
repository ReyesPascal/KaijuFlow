// Step timing (#61): one structured line per step, one parseable format.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { logStep, timeStep, timeIndexerPage, withStepRef, parseStepLine, STEP_NAMES, logPlayFailed } from '../../src/utils/stepTiming.ts';
import { captureLogs } from './capture-logs.ts';

const stepLines = (logs: string) => logs.split('\n').filter(l => l.includes('[KF-STEP]'));

test('a step line carries tag, step, source, ms, ok and an end time, and parses back', async () => {
  const logs = await captureLogs(async () => { logStep({ step: 'nzb_fetch', source: 'NinjaCentral', ms: 412, title: 'Some.Movie.2024' }); });
  const lines = stepLines(logs);
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^\[KF-STEP\] \{"step":"nzb_fetch","source":"NinjaCentral","ms":412,"ok":true,/);
  const rec = parseStepLine(lines[0])!;
  assert.equal(rec.step, 'nzb_fetch');
  assert.equal(rec.source, 'NinjaCentral');
  assert.equal(rec.ms, 412);
  assert.equal(rec.title, 'Some.Movie.2024');
  assert.match(String(rec.t), /^\d{4}-\d{2}-\d{2}T/);
});

test('a title with quotes, newlines and unicode stays on one parseable line', async () => {
  const title = 'Odd "title"\nwith\ttabs é';
  const logs = await captureLogs(async () => { logStep({ step: 'upload', source: 'x', ms: 1, title }); });
  assert.equal(stepLines(logs).length, 1);
  assert.equal(parseStepLine(stepLines(logs)[0])!.title, title);
});

test('timeStep logs once per call, with the elapsed time, also when the work fails', async () => {
  const logs = await captureLogs(async () => {
    await timeStep({ step: 'indexer_page', source: 'A', page: 1 }, async () => { await new Promise(r => setTimeout(r, 30)); });
    await assert.rejects(timeStep({ step: 'indexer_page', source: 'A', page: 2 }, async () => { throw new Error('boom'); }), /boom/);
  });
  const recs = stepLines(logs).map(l => parseStepLine(l)!);
  assert.equal(recs.length, 2);
  assert.ok(recs[0].ms >= 25 && recs[0].ok === true && recs[0].page === 1);
  assert.equal(recs[1].ok, false);
  assert.equal(recs[1].page, 2);
});

test('the request reference set around a handler is added to every line inside it', async () => {
  const logs = await captureLogs(async () => {
    await withStepRef('tt0133093', async () => { logStep({ step: 'indexer_page', source: 'Idx', ms: 5, page: 1 }); });
    logStep({ step: 'indexer_page', source: 'Idx', ms: 6, page: 1 });
  });
  const recs = stepLines(logs).map(l => parseStepLine(l)!);
  assert.equal(recs[0].ref, 'tt0133093');
  assert.equal(recs[1].ref, undefined);
});

test('lines never carry an API key or a URL query', async () => {
  const logs = await captureLogs(async () => { logStep({ step: 'indexer_page', source: 'Idx', ms: 3 }); });
  assert.doesNotMatch(logs, /apikey|https?:\/\//i);
});

test('parseStepLine ignores other log lines, and the step names are the agreed ones (health_batch went with the list-time check, #191; the play\'s two events came with #242)', () => {
  assert.equal(parseStepLine('Searching x'), null);
  assert.deepEqual([...STEP_NAMES], ['indexer_page', 'play_check', 'nzb_fetch', 'unscramble', 'upload', 'import_wait', 'first_byte', 'played', 'play_failed']);
});

test('a play_failed line gives the reason without an address or a file path (#242)', async () => {
  const err = new Error('NZB fetch failed for https://indexer.example/api?t=get&id=1&apikey=abc123 after 2 tries: /movies/Film.2160p/Film.mkv');
  const logs = await captureLogs(async () => { logPlayFailed('Film.2160p-GRP', 'Idx', err); });
  const rec = parseStepLine(stepLines(logs)[0])!;
  assert.deepEqual([rec.step, rec.ok, rec.title, rec.source, rec.reason], ['play_failed', false, 'Film.2160p-GRP', 'Idx', 'NZB fetch failed for <url> after 2 tries']);
  assert.doesNotMatch(logs, /apikey|https?:\/\/|\/movies\//i);
});

test('timeIndexerPage writes an indexer_page line with source and page, and passes the result through', async () => {
  let result = '';
  const logs = await captureLogs(async () => { result = await timeIndexerPage('NinjaCentral', 2, async () => 'answer'); });
  assert.equal(result, 'answer');
  const rec = parseStepLine(stepLines(logs)[0])!;
  assert.equal(rec.step, 'indexer_page');
  assert.equal(rec.source, 'NinjaCentral');
  assert.equal(rec.page, 2);
  assert.equal(rec.ok, true);
});
