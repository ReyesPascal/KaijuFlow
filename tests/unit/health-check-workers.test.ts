// #131: the number of Sources health-checked at once comes from
// healthChecks.maxConnections, not from the batch size.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { healthCheckWorkerCount } from '../../src/addon/healthCheckCoordinator.ts';

test('worker count is healthChecks.maxConnections', () => {
  assert.equal(healthCheckWorkerCount({ maxConnections: 2 }), 2);
  assert.equal(healthCheckWorkerCount({ maxConnections: 20 }), 20);
});

test('worker count falls back to the settings default of 12 when unset', () => {
  assert.equal(healthCheckWorkerCount({}), 12);
  assert.equal(healthCheckWorkerCount(undefined), 12);
});
