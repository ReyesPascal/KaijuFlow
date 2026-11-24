// Process trace (#249): what the whole process did while a piece of work ran (CPU, GC, event loop, heap).
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setFlagsFromString } from 'node:v8';
import { runInNewContext } from 'node:vm';
import { startProcessTrace } from '../../src/utils/processTrace.ts';

const busy = (ms: number) => { const end = Date.now() + ms; while (Date.now() < end) { /* hold the loop */ } };

test('a trace around work that holds the loop shows its CPU, the loop delay and a busy loop', async () => {
  const end = startProcessTrace();
  await new Promise(r => setTimeout(r, 10)); // let the delay histogram take a sample before the loop is held
  busy(80);
  await new Promise(r => setTimeout(r, 10));
  const t = end();
  assert.ok(t.cpu_ms >= 60, `cpu_ms ${t.cpu_ms}`);
  assert.ok(t.loop_max_ms >= 60, `loop_max_ms ${t.loop_max_ms}`);
  assert.ok(t.elu >= 0.5 && t.elu <= 1, `elu ${t.elu}`);
  assert.ok(t.heap_mb > 0);
});

test('a trace around idle waiting shows next to no CPU and no loop delay', async () => {
  const end = startProcessTrace();
  await new Promise(r => setTimeout(r, 60));
  const t = end();
  assert.ok(t.cpu_ms < 30, `cpu_ms ${t.cpu_ms}`);
  assert.ok(t.loop_max_ms < 30, `loop_max_ms ${t.loop_max_ms}`);
  assert.ok(t.elu < 0.5, `elu ${t.elu}`);
});

test('garbage collection during the work is counted, and only in the trace it fell in', async () => {
  setFlagsFromString('--expose-gc');
  const gc = runInNewContext('gc') as () => void;
  const before = startProcessTrace()();
  assert.equal(before.gc_n, 0, 'a trace with no collection counts none');
  const end = startProcessTrace();
  gc(); gc();
  await new Promise(r => setImmediate(r)); // a trace ends one turn after its work (processTrace.ts)
  const t = end();
  assert.ok(t.gc_n >= 2, `gc_n ${t.gc_n}`);
  assert.ok(t.gc_ms >= 0);
});
