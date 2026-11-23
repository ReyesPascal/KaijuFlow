// The Head start (#206): a config that saved the old default `whenToResolve: 'on-tile-selection'` gets the
// Head start once ('on-results'); a later choice of 'on-tile-selection' stays. The whole path (config on disk →
// startup migration → /api/config) is INT-BACKEND-SETTING-001.
import test from 'node:test';
import assert from 'node:assert/strict';
import { migrateToHeadStart } from '../../src/config/headStartMigration.ts';

test('an old config on the old default moves to the Head start, once', () => {
  const c: Record<string, unknown> = { ultimateFallback: { enabled: true, whenToResolve: 'on-tile-selection' } };
  assert.equal(migrateToHeadStart(c), true);
  assert.deepEqual(c, { ultimateFallback: { enabled: true, whenToResolve: 'on-results' }, headStartMigrated: true });
  (c.ultimateFallback as Record<string, unknown>).whenToResolve = 'on-tile-selection'; // the owner's later choice
  assert.equal(migrateToHeadStart(c), false);
  assert.equal((c.ultimateFallback as Record<string, unknown>).whenToResolve, 'on-tile-selection');
});

test('a config already on the Head start, or with no fallback settings, is only marked', () => {
  const on: Record<string, unknown> = { ultimateFallback: { whenToResolve: 'on-results' } };
  assert.equal(migrateToHeadStart(on), true);
  assert.deepEqual(on, { ultimateFallback: { whenToResolve: 'on-results' }, headStartMigrated: true });
  const none: Record<string, unknown> = {};
  assert.equal(migrateToHeadStart(none), true);
  assert.deepEqual(none, { headStartMigrated: true });
});
