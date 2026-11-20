// The shared grab step (#45, ADR 0005): Unscramble runs on the health-check
// providers after the grab, logs one line per prepare with the time taken,
// never throws for the Source, and uses the settings as they are.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { configData } from '../../src/config/index.ts';
import { cacheNzbContent } from '../../src/health/nzbContentCache.ts';
import { grabSourceNzb } from '../../src/backends/sourceNzb.ts';
import { scrambledRarSet, startFakeNntp } from '../integration/parity/fake-nntp.mjs';
import { captureLogs } from './capture-logs.ts';
import { archiveFixture } from './health-nzb.ts';
import { parseStepLine } from '../../src/utils/stepTiming.ts';

const servers: Array<{ close(): Promise<void> }> = [];
const savedHealthChecks = configData.healthChecks;
after(async () => {
  configData.healthChecks = savedHealthChecks;
  for (const s of servers) await s.close();
});

/** Point the health-check providers at the given list (the settings as the step reads them). */
const useProviders = (providers: unknown[]) => { configData.healthChecks = { ...savedHealthChecks, providers } as typeof savedHealthChecks; };

let n = 0;
/** A Source whose NZB is already in the health-check cache (no indexer call). */
function cachedSource(nzb: string) {
  const nzbUrl = `http://indexer.invalid/nzb/${++n}`;
  cacheNzbContent(nzbUrl, nzb);
  return { nzbUrl, title: `Step Test ${n}`, indexerName: 'Parity' };
}

test('a Scrambled RAR set is Unscrambled on the health-check providers and logged with parts and ms', async () => {
  const set = scrambledRarSet({ base: 'step', parts: 5 });
  const news = await startFakeNntp({ articles: set.articles });
  servers.push(news);
  useProviders([news.provider()]);
  let nzb = '';
  const logs = await captureLogs(async () => { ({ nzb } = await grabSourceNzb(cachedSource(set.nzb), { budgetMs: 60000 })); });
  assert.notEqual(nzb, set.nzb, 'the uploaded NZB should be the Unscrambled one');
  assert.ok(nzb.includes('&quot;step.part01.rar&quot;') && nzb.includes('&quot;step.part05.rar&quot;'));
  assert.match(logs, /Unscrambled RAR set: 5 parts .*\(\d+ ms\)/);
});

test('when Unscramble cannot finish, the original goes up and the reason and ms are logged', async () => {
  const set = scrambledRarSet({ base: 'stepmissing', parts: 5 });
  set.articles.delete(set.parts[0].firstId);
  const news = await startFakeNntp({ articles: set.articles });
  servers.push(news);
  useProviders([news.provider()]);
  let nzb = '';
  const logs = await captureLogs(async () => { ({ nzb } = await grabSourceNzb(cachedSource(set.nzb), { budgetMs: 60000 })); });
  assert.equal(nzb, set.nzb, 'the original NZB should be uploaded unchanged');
  assert.match(logs, /Unscramble skipped \(missing-article, 5 parts, \d+ ms\)/);
});

test('without a health-check provider, the original goes up and no-provider is logged', async () => {
  const set = scrambledRarSet({ base: 'stepnoprov', parts: 3 });
  useProviders([]);
  let nzb = '';
  const logs = await captureLogs(async () => { ({ nzb } = await grabSourceNzb(cachedSource(set.nzb), { budgetMs: 60000 })); });
  assert.equal(nzb, set.nzb);
  assert.match(logs, /Unscramble skipped \(no-provider, 3 parts, \d+ ms\)/);
});

test('Unscramble takes at most min(15 s, the budget) and what it used comes out of the budget', async () => {
  const set = scrambledRarSet({ base: 'stepslow', parts: 8 });
  const news = await startFakeNntp({ articles: set.articles, delayMs: 5000 });
  servers.push(news);
  useProviders([news.provider()]);
  const started = Date.now();
  let result = { nzb: '', remainingMs: 0 };
  const logs = await captureLogs(async () => { result = await grabSourceNzb(cachedSource(set.nzb), { budgetMs: 1000 }); });
  const took = Date.now() - started;
  assert.equal(result.nzb, set.nzb, 'the original NZB should be uploaded unchanged');
  assert.ok(took < 4000, `should stop at the 1 s budget, not wait out the 5 s server delay; took ${took} ms`);
  assert.ok(result.remainingMs >= 1 && result.remainingMs < 1000, `remaining budget ${result.remainingMs}`);
  assert.match(logs, /Unscramble skipped \(timeout, 8 parts, \d+ ms\)/);
});

test('a plain Source is not logged as skipped', async () => {
  const nzb = `<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><file subject="&quot;Plain.2026.mkv&quot; yEnc (1/1)"><segments><segment bytes="1" number="1">p@fake</segment></segments></file></nzb>`;
  useProviders([]);
  let out = '';
  const logs = await captureLogs(async () => { ({ nzb: out } = await grabSourceNzb(cachedSource(nzb))); });
  assert.equal(out, nzb);
  assert.doesNotMatch(logs, /Unscrambl/);
});

// Step timing (#61): the grab and Unscramble each log one step line per prepare.
const stepRecs = (logs: string) => logs.split('\n').map(l => parseStepLine(l)).filter((r): r is NonNullable<typeof r> => r !== null);

test('the grab logs one nzb_fetch line and Unscramble one unscramble line with its answer', async () => {
  const set = scrambledRarSet({ base: 'steptime', parts: 5 });
  const news = await startFakeNntp({ articles: set.articles });
  servers.push(news);
  useProviders([news.provider()]);
  const logs = await captureLogs(async () => { await grabSourceNzb(cachedSource(set.nzb), { budgetMs: 60000 }); });
  const recs = stepRecs(logs);
  assert.deepEqual(recs.map(r => r.step), ['nzb_fetch', 'unscramble']);
  assert.equal(recs[0].source, 'Parity');
  assert.match(recs[0].title, /^Step Test \d+$/);
  assert.equal(recs[1].result, 'unscrambled');
  assert.equal(recs[1].parts, 5);
  assert.equal(typeof recs[1].ms, 'number');
});

test('a plain NZB logs unscramble with the not-scrambled answer; a skip logs its reason', async () => {
  const plain = `<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><file subject="&quot;Plain.2026.mkv&quot; yEnc (1/1)"><segments><segment bytes="1" number="1">p@fake</segment></segments></file></nzb>`;
  useProviders([]);
  let logs = await captureLogs(async () => { await grabSourceNzb(cachedSource(plain)); });
  assert.deepEqual(stepRecs(logs).filter(r => r.step === 'unscramble').map(r => r.result), ['not-scrambled']);
  const set = scrambledRarSet({ base: 'steptimenoprov', parts: 3 });
  logs = await captureLogs(async () => { await grabSourceNzb(cachedSource(set.nzb)); });
  assert.deepEqual(stepRecs(logs).filter(r => r.step === 'unscramble').map(r => r.result), ['no-provider']);
});

test('a 7z set goes up as it is, its step line says not-scrambled, and no article is read (#193)', async () => {
  const set = scrambledRarSet({ base: 'Xq7Lm2Pz9Rb4Vn8Kw3Ty5uhaF.7z', parts: 4, startAt: 1, width: 3, firstArticle: (v: number) => archiveFixture(`stored-split.7z.00${v + 1}`) });
  const news = await startFakeNntp({ articles: set.articles });
  servers.push(news);
  useProviders([news.provider()]);
  let nzb = '';
  const logs = await captureLogs(async () => { ({ nzb } = await grabSourceNzb(cachedSource(set.nzb), { budgetMs: 60000 })); });
  assert.equal(nzb, set.nzb, 'the original NZB should be uploaded unchanged');
  assert.deepEqual(stepRecs(logs).filter(r => r.step === 'unscramble').map(r => [r.result, r.parts]), [['not-scrambled', 0]]);
  assert.equal(news.state.reads.length, 0, 'no first article should be read');
  assert.doesNotMatch(logs, /Unscramble skipped/);
});
