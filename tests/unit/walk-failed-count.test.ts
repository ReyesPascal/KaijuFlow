// The Walk's summary count (GLOSSARY: Walk): the adapter's summary line asks the Walk how many Sources it gave up on,
// rather than recomputing which members are finished.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Walk } from '../../src/play/walk.ts';

test('the Sources a Walk gave up on: a failed grab and a check that could not answer count, a prepare cut off by a stop does not', () => {
  const walk = new Walk({ size: 4, inFlight: 1, isDead: () => false, indexerOf: () => 'Parity', hits: new Map() });
  assert.deepEqual(walk.start(), [{ type: 'grab', index: 0 }]);
  assert.deepEqual(walk.on({ type: 'grabFailed', index: 0, badSource: true }).map(d => d.type), ['markDead', 'grab']);
  walk.on({ type: 'grabbed', index: 1 });
  assert.deepEqual(walk.on({ type: 'checked', index: 1, verdict: 'error' }), [{ type: 'grab', index: 2 }]);
  walk.on({ type: 'grabbed', index: 2 });
  assert.deepEqual(walk.on({ type: 'checked', index: 2, verdict: 'healthy' }), [{ type: 'prepare', index: 2 }]);
  assert.equal(walk.failedCount, 2, 'while #3 prepares');
  walk.on({ type: 'stop' });
  assert.equal(walk.failedCount, 2, 'the stopped prepare is not given up on');
});
