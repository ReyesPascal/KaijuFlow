// Deleted settings (spec #183): the list-time Smart and Fixed checks (#191), Auto-queue (#226), backups (#192) and the
// list entry's attempts cap (#228).
// An old config that holds them still loads, and loses them. The whole path (config on disk → startup migration →
// /api/config, and a save from an old page) is INT-BACKEND-SETTING-001.
import test from 'node:test';
import assert from 'node:assert/strict';
import { dropDeletedSettings } from '../../src/config/deletedSettingsMigration.ts';

const provider = { id: 'p1', name: 'News', host: 'news.example', port: 563, useTLS: true, username: 'u', password: 'p', enabled: true, type: 'pool' };

test('the deleted settings are dropped; providers, the connection cap, TLS and the other fallback settings stay', () => {
  const c: Record<string, unknown> = {
    cacheTTL: 9000,
    healthChecks: {
      enabled: true, mode: 'full', archiveInspection: false, sampleCount: 7, nzbsToInspect: 6,
      inspectionMethod: 'smart', smartBatchSize: 3, smartAdditionalRuns: 1, smartMinHealthy: 1,
      hideBlocked: true, maxConnections: 12, healthCheckIndexers: { Ninja: false },
      providers: [provider], maxTotalConnections: 8, verifyTlsCertificates: true, autoQueueMode: 'top',
    },
    ultimateFallback: { enabled: true, candidateCount: 3, desiredBackups: 1, backupProcessingLimit: 2, maxAttempts: 4 },
    syncedIndexers: [{ name: 'Ninja', enabledForSearch: true, enabledForHealthCheck: false }],
  };
  assert.equal(dropDeletedSettings(c), true);
  assert.deepEqual(c, {
    cacheTTL: 9000,
    healthChecks: { providers: [provider], maxTotalConnections: 8, verifyTlsCertificates: true },
    ultimateFallback: { enabled: true, candidateCount: 3 },
    syncedIndexers: [{ name: 'Ninja', enabledForSearch: true }],
  });
});

test('a config without them is left as it is', () => {
  const c: Record<string, unknown> = { cacheTTL: 9000, healthChecks: { providers: [provider] }, ultimateFallback: { enabled: true } };
  assert.equal(dropDeletedSettings(c), false);
  assert.deepEqual(c, { cacheTTL: 9000, healthChecks: { providers: [provider] }, ultimateFallback: { enabled: true } });
  assert.equal(dropDeletedSettings({}), false);
});

// Kaiju Search (#285): every indexer is asked by ID and by name at once, so the per-indexer movie and TV search
// method settings (and their anime twins, and the old global ones they came from) go from an old config.
test('the search method settings are dropped from every indexer and from the search settings; the rest stays', () => {
  const methods = { movieSearchMethod: ['text'], tvSearchMethod: ['imdb', 'text'], animeMovieSearchMethod: ['text'], animeTvSearchMethod: ['text'] };
  const caps = { movieSearchParams: ['q', 'imdbid'], tvSearchParams: ['q', 'tvdbid'] };
  const c: Record<string, unknown> = {
    useTextSearch: true,
    searchConfig: { movieSearchMethod: 'text', tvSearchMethod: 'imdb', useTextSearchForAnime: true, includeSeasonPacks: true },
    indexers: [{ name: 'NinjaCentral', url: 'https://ninja.example', apiKey: 'k', enabled: true, caps, ...methods }],
    syncedIndexers: [{ id: '1', name: 'Ninja', enabledForSearch: true, capabilities: caps, ...methods }],
  };
  assert.equal(dropDeletedSettings(c), true);
  assert.deepEqual(c, {
    searchConfig: { includeSeasonPacks: true },
    indexers: [{ name: 'NinjaCentral', url: 'https://ninja.example', apiKey: 'k', enabled: true, caps }],
    syncedIndexers: [{ id: '1', name: 'Ninja', enabledForSearch: true, capabilities: caps }],
  });
  assert.equal(dropDeletedSettings(c), false, 'a second startup finds nothing to drop');
});
