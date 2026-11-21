// Play-time check (#190, GLOSSARY): a clicked list entry is checked right before it is handed to the
// Backend. requireHealthySource is what prepareStream calls; each check writes one play_check step line
// (tools/brain/docs/formats.md), which the brain tools read. ADR 0004: only a Source the check blocks is dead.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { configData } from '../../src/config/index.ts';
import { requireHealthySource } from '../../src/play/playTimeCheck.ts';
import { parseStepLine } from '../../src/utils/stepTiming.ts';
import { captureLogs } from './capture-logs.ts';
import { nzbWithNews } from './health-nzb.ts';

const saved = configData.healthChecks;
after(() => { configData.healthChecks = saved; });

const useProviders = (providers: unknown[]) => { configData.healthChecks = { ...saved, providers } as typeof saved; };
type StepRecord = NonNullable<ReturnType<typeof parseStepLine>>;
const playChecks = (logs: string) => logs.split('\n').map(parseStepLine).filter((r): r is StepRecord => r?.step === 'play_check');

/** requireHealthySource's answer and the console lines it wrote. */
async function check(nzbUrl: string, title: string) {
  let error: (Error & { isBadSource?: boolean }) | undefined;
  const logs = await captureLogs(async () => {
    try { await requireHealthySource({ nzbUrl, title, indexerName: 'Parity' }); } catch (e) { error = e as Error; }
  });
  return { error, steps: playChecks(logs) };
}

test('a healthy Source goes on, and its check writes one play_check line', async () => {
  const { url, provider } = await nzbWithNews([{ name: 'Movie.mkv', segs: 3 }]);
  useProviders([provider]);
  const { error, steps } = await check(url, 'Healthy.Movie.2026');
  assert.equal(error, undefined);
  assert.equal(steps.length, 1);
  assert.deepEqual({ ...steps[0], ms: 0, t: '' },
    { step: 'play_check', source: 'Parity', ms: 0, ok: true, t: '', title: 'Healthy.Movie.2026', status: 'verified' });
});

test('a Source the check blocks is a Source failure (dead)', async () => {
  const { url, provider } = await nzbWithNews([{ name: 'Movie.mkv', segs: 3 }], { served: false });
  useProviders([provider]);
  const { error, steps } = await check(url, 'Dead.Movie.2026');
  assert.equal(error?.isBadSource, true);
  assert.match(error!.message, /^Play-time check: Missing/);
  assert.deepEqual([steps[0].ok, steps[0].status], [false, 'blocked']);
});

test('a check that cannot answer (the NZB cannot be fetched) is a plain error: the Source is not dead', async () => {
  const { provider } = await nzbWithNews([{ name: 'Movie.mkv' }]);
  useProviders([provider]);
  const { error, steps } = await check('http://indexer.invalid/never-cached.nzb', 'Unreachable.Movie.2026');
  assert.ok(error);
  assert.notEqual(error.isBadSource, true);
  assert.match(error.message, /^Play-time check could not check the Source/);
  assert.deepEqual([steps[0].ok, steps[0].status], [false, 'error']);
});

test('with no enabled health-check provider nothing is handed over, and the Source is not dead', async () => {
  const { url, provider } = await nzbWithNews([{ name: 'Movie.mkv', segs: 3 }]);
  useProviders([{ ...provider, enabled: false }]);
  const { error, steps } = await check(url, 'Unchecked.Movie.2026');
  assert.ok(error);
  assert.notEqual(error.isBadSource, true);
  assert.match(error.message, /No health-check provider/);
  assert.deepEqual([steps[0].ok, steps[0].status, steps[0].title], [false, 'error', 'Unchecked.Movie.2026']);
});
