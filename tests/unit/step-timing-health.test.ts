// Step timing (#61): each health-check batch logs one health_batch line.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { performBatchHealthChecks } from '../../src/health/batchProcessor.ts';
import { cacheNzbContent } from '../../src/health/nzbContentCache.ts';
import { parseStepLine } from '../../src/utils/stepTiming.ts';
import type { HealthCheckOptions } from '../../src/health/types.ts';
import { captureLogs } from './capture-logs.ts';

const NZB = `<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><file subject="&quot;Plain.2026.mkv&quot; yEnc (1/1)"><segments><segment bytes="1" number="1">p@fake</segment></segments></file></nzb>`;

// One sample keeps the fake batch fast. The real type only allows 3 or 7, so
// this deliberately passes a value the type refuses.
// @ts-expect-error sampleCount is 3 | 7 in HealthCheckOptions
const ONE_SAMPLE: HealthCheckOptions = { archiveInspection: false, sampleCount: 1 };

test('each batch logs one health_batch line with the count and the indexers it covered', async () => {
  const urls = ['http://idx.invalid/hb/1', 'http://idx.invalid/hb/2'];
  for (const u of urls) cacheNzbContent(u, NZB);
  const indexers = new Map([[urls[0], 'IdxA'], [urls[1], 'IdxB']]);
  const logs = await captureLogs(async () => {
    await performBatchHealthChecks(urls, [], 'test-agent', 2, ONE_SAMPLE, indexers);
    await performBatchHealthChecks([urls[0]], [], 'test-agent', 1, ONE_SAMPLE, indexers);
  });
  const recs = logs.split('\n').map(l => parseStepLine(l)).filter((r): r is NonNullable<typeof r> => r !== null);
  assert.equal(recs.length, 2, 'one line per batch');
  assert.equal(recs[0].step, 'health_batch');
  assert.equal(recs[0].count, 2);
  assert.deepEqual(recs[0].indexers, ['IdxA', 'IdxB']);
  assert.equal(recs[1].count, 1);
  assert.deepEqual(recs[1].indexers, ['IdxA']);
  assert.equal(typeof recs[0].ms, 'number');
});
