// Unscramble one at a time (#119, ADR 0005): several Sources can be prepared
// at once, so at most one Unscramble reads first articles at a time,
// process-wide, first come first served. Each gets its own time limit from
// the start of its turn; the prepare budget still covers the wait.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { unscrambleNzb } from '../../src/archive/unscramble.ts';
import { configData } from '../../src/config/index.ts';
import { cacheNzbContent } from '../../src/health/nzbContentCache.ts';
import { grabSourceNzb } from '../../src/backends/sourceNzb.ts';
import { parseStepLine } from '../../src/utils/stepTiming.ts';
import { scrambledRarSet, startFakeNntp } from '../integration/parity/fake-nntp.mjs';
import { captureLogs } from './capture-logs.ts';

const servers: Array<{ close(): Promise<void> }> = [];
const savedHealthChecks = configData.healthChecks;
after(async () => {
  configData.healthChecks = savedHealthChecks;
  for (const s of servers) await s.close();
});

async function news(opts: Parameters<typeof startFakeNntp>[0]) {
  const n = await startFakeNntp(opts);
  servers.push(n);
  return n;
}

const sevenZip = Buffer.concat([Buffer.from([0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c]), Buffer.alloc(64)]);

test('three sets prepared at once: the first one started is Unscrambled inside its limit, the next gets its own full limit after its wait', async () => {
  // Inception's three picks from the 2026-11-13 baseline, at test scale: every
  // read takes 40 ms on a shared 12-connection cap. Alone, the 210-part set
  // takes about 0.75 s and the 197-part set about 0.7 s; sharing the
  // connections, both would need about 1.5 s. The limit is 1.2 s (15 s in a prepare).
  const LIMIT_MS = 1200;
  const top = scrambledRarSet({ base: 'top', parts: 210, startAt: 1, width: 3, seed: 3 });
  const second = scrambledRarSet({ base: 'second', parts: 197, startAt: 1, width: 3, seed: 4 });
  const notRar = scrambledRarSet({ base: 'third', parts: 545, startAt: 1, width: 3, firstArticle: () => sevenZip });
  const n = await news({ articles: new Map([...top.articles, ...second.articles, ...notRar.articles]), delayMs: 40 });
  configData.healthChecks = { ...savedHealthChecks, maxTotalConnections: 12 } as typeof savedHealthChecks;

  const [a, b, c] = await Promise.all([top, second, notRar].map(set => unscrambleNzb(set.nzb, [n.provider()], LIMIT_MS, { connections: 12 })));

  assert.equal(a.changed, true, `the top pick should be Unscrambled, got ${a.reason} after ${a.ms} ms`);
  assert.ok(a.waitMs < 100, `the first one started does not wait for another Unscramble; waited ${a.waitMs} ms`);
  assert.ok(a.ms < LIMIT_MS * 0.8, `the top pick took ${a.ms} ms of its ${LIMIT_MS} ms`);
  assert.equal(b.changed, true, `the second pick should be Unscrambled, got ${b.reason} after ${b.ms} ms (waited ${b.waitMs} ms)`);
  assert.ok(b.waitMs >= a.ms * 0.8, `the second pick waits for the top pick's turn; waited ${b.waitMs} ms, top took ${a.ms} ms`);
  assert.ok(b.ms > LIMIT_MS, `the wait doesn't count against the limit: ${b.ms} ms in all, ${b.waitMs} ms of it waiting`);
  assert.equal(c.reason, 'not-rar5');
  assert.ok(c.waitMs >= b.ms - b.waitMs, 'the third waits for the second too, first come first served');
  assert.ok(n.state.peak <= 12, `peak ${n.state.peak} connections, cap 12`);
});

let n = 0;
/** A prepare's Source whose NZB is already in the health-check cache (no indexer call). */
function cachedSource(nzb: string) {
  const nzbUrl = `http://indexer.invalid/queue/${++n}`;
  cacheNzbContent(nzbUrl, nzb);
  return { nzbUrl, title: `Queue Test ${n}`, indexerName: 'Parity' };
}
const unscrambleStep = (logs: string) => logs.split('\n').map(l => parseStepLine(l)).find(r => r?.step === 'unscramble');

test('a prepare whose budget runs out while it waits uploads the original, logs timeout and wait_ms, and reads nothing', async () => {
  const busy = scrambledRarSet({ base: 'busy', parts: 4 });
  const busyNews = await news({ articles: busy.articles, delayMs: 3000 });
  const set = scrambledRarSet({ base: 'waiter', parts: 5 });
  const waiterNews = await news({ articles: set.articles });
  configData.healthChecks = { ...savedHealthChecks, providers: [waiterNews.provider()] } as typeof savedHealthChecks;
  // Another Source's Unscramble holds the turn for 2 s.
  const holder = unscrambleNzb(busy.nzb, [busyNews.provider()], 2000);
  await new Promise(r => setTimeout(r, 50));

  let result = { nzb: '', remainingMs: 0 };
  const logs = await captureLogs(async () => { result = await grabSourceNzb(cachedSource(set.nzb), { budgetMs: 400 }); });

  assert.equal(result.nzb, set.nzb, 'the original NZB should be uploaded unchanged');
  assert.ok(result.remainingMs >= 1 && result.remainingMs < 400, `remaining budget ${result.remainingMs}`);
  assert.deepEqual(waiterNews.state.reads, [], 'no first article read');
  const step = unscrambleStep(logs);
  assert.equal(step?.result, 'timeout');
  assert.ok(typeof step?.wait_ms === 'number' && step.wait_ms >= 350, `wait_ms ${step?.wait_ms}`);
  assert.equal((await holder).reason, 'timeout');
});

test('an NZB with no number-named set does not wait for the turn', async () => {
  const busy = scrambledRarSet({ base: 'busy2', parts: 4 });
  const busyNews = await news({ articles: busy.articles, delayMs: 3000 });
  const holder = unscrambleNzb(busy.nzb, [busyNews.provider()], 1000);
  await new Promise(r => setTimeout(r, 50));
  const plain = `<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><file subject="&quot;Plain.2026.mkv&quot; yEnc (1/1)"><segments><segment bytes="1" number="1">p@fake</segment></segments></file></nzb>`;

  const r = await unscrambleNzb(plain, [busyNews.provider()], 15000);

  assert.equal(r.reason, 'not-scrambled');
  assert.ok(r.ms < 100 && r.waitMs === 0, `took ${r.ms} ms, waited ${r.waitMs} ms`);
  assert.equal((await holder).reason, 'timeout');
});

test('a stop cuts an Unscramble off mid-read and one still waiting for the turn: both come back stopped, the turn goes on', async () => {
  const reading = scrambledRarSet({ base: 'stopread', parts: 4 });
  const waiting = scrambledRarSet({ base: 'stopwait', parts: 4 });
  const after = scrambledRarSet({ base: 'stopafter', parts: 4 });
  const slow = await news({ articles: new Map([...reading.articles, ...waiting.articles]), delayMs: 3000 });
  const fast = await news({ articles: after.articles });
  const stop = new AbortController();
  const started = Date.now();
  const first = unscrambleNzb(reading.nzb, [slow.provider()], 10000, { stop: stop.signal });
  const second = unscrambleNzb(waiting.nzb, [slow.provider()], 10000, { stop: stop.signal });
  await new Promise(r => setTimeout(r, 100));
  stop.abort();
  const [a, b] = await Promise.all([first, second]);
  assert.equal(a.reason, 'stopped', 'the one reading');
  assert.equal(b.reason, 'stopped', 'the one waiting for its turn');
  assert.equal(a.nzb, reading.nzb, 'the original comes back');
  assert.ok(Date.now() - started < 1000, `both back at once, not after the 3 s reads (${Date.now() - started} ms)`);
  assert.deepEqual(waiting.parts.map(p => p.firstId).filter(id => (slow.state.reads as string[]).includes(id)), [], 'the waiting one read nothing');
  const next = await unscrambleNzb(after.nzb, [fast.provider()], 2000);
  assert.equal(next.changed, true, `the next Unscramble gets the turn (${next.reason})`);
  assert.ok(next.waitMs < 100, `and does not wait for the stopped ones (${next.waitMs} ms)`);
});
