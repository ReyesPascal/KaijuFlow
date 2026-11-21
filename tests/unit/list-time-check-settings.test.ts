// #191: the list-time Smart and Fixed checks are deleted; an old config that holds
// their settings still loads, and loses them. The whole path (config on disk →
// startup migration → /api/config) is INT-BACKEND-SETTING-001.
import test from 'node:test';
import assert from 'node:assert/strict';
import { dropListTimeCheckSettings } from '../../src/config/listTimeCheckMigration.ts';

const provider = { id: 'p1', name: 'News', host: 'news.example', port: 563, useTLS: true, username: 'u', password: 'p', enabled: true, type: 'pool' };

test('the list-time check settings are dropped; providers, the connection cap, TLS and auto-queue stay', () => {
  const c: Record<string, unknown> = {
    cacheTTL: 9000,
    healthChecks: {
      enabled: true, mode: 'full', archiveInspection: false, sampleCount: 7, nzbsToInspect: 6,
      inspectionMethod: 'smart', smartBatchSize: 3, smartAdditionalRuns: 1, smartMinHealthy: 1,
      hideBlocked: true, maxConnections: 12, healthCheckIndexers: { Ninja: false },
      providers: [provider], maxTotalConnections: 8, verifyTlsCertificates: true, autoQueueMode: 'top',
    },
    syncedIndexers: [{ name: 'Ninja', enabledForSearch: true, enabledForHealthCheck: false }],
  };
  assert.equal(dropListTimeCheckSettings(c), true);
  assert.deepEqual(c, {
    cacheTTL: 9000,
    healthChecks: { providers: [provider], maxTotalConnections: 8, verifyTlsCertificates: true, autoQueueMode: 'top' },
    syncedIndexers: [{ name: 'Ninja', enabledForSearch: true }],
  });
});

test('a config without them is left as it is', () => {
  const c: Record<string, unknown> = { cacheTTL: 9000, healthChecks: { providers: [provider], autoQueueMode: 'off' } };
  assert.equal(dropListTimeCheckSettings(c), false);
  assert.deepEqual(c, { cacheTTL: 9000, healthChecks: { providers: [provider], autoQueueMode: 'off' } });
  assert.equal(dropListTimeCheckSettings({}), false);
});
