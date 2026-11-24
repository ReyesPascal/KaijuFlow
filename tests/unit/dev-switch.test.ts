// The dev switch (#280, spec #279): one setting, `devDiagnostics`, off by default and on in the test copies only. Every
// diagnostic line goes behind it. With it off a step line is exactly today's; with it on, every line says so (`dev: true`),
// so evidence made without it is never read as complete. Driven through the loaded config, as the app sets it.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { configData, config } from '../../src/config/index.ts';
import { logStep, logPlayFailed, logPlayed, withStepRef } from '../../src/utils/stepTiming.ts';
import { captureLogs } from './capture-logs.ts';

const saved = configData.devDiagnostics;
after(() => { configData.devDiagnostics = saved; });

/** The step lines a few steps write, with the time field fixed so lines can be compared byte for byte. */
async function lines(): Promise<string[]> {
  const logs = await captureLogs(async () => {
    await withStepRef('tt0133093', async () => {
      logStep({ step: 'nzb_fetch', source: 'NinjaCentral', ms: 412, title: 'Some.Movie.2024' });
      logPlayFailed('Some.Movie.2024', 'NinjaCentral', new Error('AltMount could not process the Source'));
    });
  });
  return logs.split('\n').filter(l => l.includes('[KF-STEP]')).map(l => l.replace(/"t":"[^"]+"/, '"t":"T"'));
}

const TODAY = [
  '[KF-STEP] {"step":"nzb_fetch","source":"NinjaCentral","ms":412,"ok":true,"t":"T","ref":"tt0133093","title":"Some.Movie.2024"}',
  '[KF-STEP] {"step":"play_failed","source":"NinjaCentral","ms":0,"ok":false,"t":"T","ref":"tt0133093","title":"Some.Movie.2024","reason":"AltMount could not process the Source"}',
];

test('the dev switch is off by default: a config without it writes exactly today\'s step lines', async () => {
  delete configData.devDiagnostics;
  assert.equal(config.devDiagnostics, false);
  assert.deepEqual(await lines(), TODAY);
  configData.devDiagnostics = false;
  assert.deepEqual(await lines(), TODAY);
});

test('with the dev switch on, every step line records it, and nothing else changes', async () => {
  configData.devDiagnostics = true;
  assert.equal(config.devDiagnostics, true);
  assert.deepEqual(await lines(), TODAY.map(l => l.replace(/\}$/, ',"dev":true}')));
});

// Search Flow's extra proof (#286): the `played` line names the Source's mark and its video file, with the switch on only.
test('the played line carries Search Flow\'s mark and the video file played with the dev switch on, and nothing with it off', async () => {
  const played = async () => (await captureLogs(async () => {
    logPlayed('Joker 1080p WEB-DL DD5.1 H264 (2019) NL Subs', 'NinjaCentral', { flow: 'sure', proof: 'nzb video', video: 'Joker.2019.1080p.WEB-DL.DD5.1.H264.mkv' });
  })).split('\n').filter(l => l.includes('[KF-STEP]')).map(l => JSON.parse(l.slice(l.indexOf('{'))));
  configData.devDiagnostics = false;
  const [off] = await played();
  assert.deepEqual([off.flow, off.proof, off.video, off.dev], [undefined, undefined, undefined, undefined]);
  configData.devDiagnostics = true;
  const [on] = await played();
  assert.deepEqual([on.flow, on.proof, on.video, on.dev], ['sure', 'nzb video', 'Joker.2019.1080p.WEB-DL.DD5.1.H264.mkv', true]);
});
