// The one drop list of deleted settings (spec #183), kept apart from migrations.ts so it
// can be tested without loading a config from disk. Startup drops them from an old
// config; a save drops them from what a page loaded before the deletion still sends.

/** Settings deleted from each section, and the ticket that deleted them. */
const DELETED: Record<string, string[]> = {
  // The list-time Smart and Fixed checks (#191): the health check runs only at play time. The on/off switch,
  // the mode, its batch and budget, the list's own sample count and archive switch, hiding blocked results,
  // the worker count and the per-indexer choice. The providers, the connection cap and TLS stay.
  // Auto-queue (#226, replaced by the Head start).
  healthChecks: ['enabled', 'mode', 'archiveInspection', 'sampleCount', 'nzbsToInspect', 'inspectionMethod',
    'smartBatchSize', 'smartAdditionalRuns', 'smartMinHealthy', 'hideBlocked', 'maxConnections', 'healthCheckIndexers',
    'autoQueueMode'],
  // Backups (#192): only the Source being played is prepared, the next only when it fails. The list entry's attempts
  // cap (#228): a failed list entry walks on through the whole list, as the cap's default did.
  ultimateFallback: ['desiredBackups', 'backupProcessingLimit', 'maxAttempts'],
  // The old global search methods (Kaiju Search, #285: every indexer is asked by ID and by name at once).
  // The priority dedup (#299: an upload on several indexers is one Release).
  searchConfig: ['movieSearchMethod', 'tvSearchMethod', 'useTextSearchForAnime', 'indexerPriorityDedup'],
};

/** Settings deleted from every indexer entry (direct `indexers` and synced `syncedIndexers`), and why. */
const DELETED_PER_INDEXER: Record<'indexers' | 'syncedIndexers', string[]> = {
  // The per-indexer search methods (Kaiju Search, #285).
  indexers: ['movieSearchMethod', 'tvSearchMethod', 'animeMovieSearchMethod', 'animeTvSearchMethod'],
  // The per-indexer list-time check choice (#191), and the search methods (#285).
  syncedIndexers: ['enabledForHealthCheck', 'movieSearchMethod', 'tvSearchMethod', 'animeMovieSearchMethod', 'animeTvSearchMethod'],
};

/** Top-level settings deleted: the legacy text-search switch the search methods came from (#285), and the priority
 *  dedup's order of indexers (#299). */
const DELETED_TOP = ['useTextSearch', 'indexerPriority'];

/** Env vars of the deleted settings: set, they are ignored (startup says so). */
export const DELETED_ENV = ['HEALTH_CHECK_ENABLED', 'ULTIMATE_FALLBACK_DESIRED_BACKUPS', 'ULTIMATE_FALLBACK_BACKUP_PROCESSING_LIMIT',
  'ULTIMATE_FALLBACK_MAX_ATTEMPTS'];

/** Drop every deleted setting from a config (or from the sections a save sends). True when anything changed. */
export function dropDeletedSettings(c: Record<string, unknown>): boolean {
  let changed = false;
  for (const [section, keys] of Object.entries(DELETED)) {
    const s = c[section] as Record<string, unknown> | undefined;
    if (!s || typeof s !== 'object') continue;
    for (const k of keys) if (k in s) { delete s[k]; changed = true; }
  }
  for (const [list, keys] of Object.entries(DELETED_PER_INDEXER)) {
    const entries = c[list];
    if (!Array.isArray(entries)) continue;
    for (const e of entries as Record<string, unknown>[]) {
      if (!e || typeof e !== 'object') continue;
      for (const k of keys) if (k in e) { delete e[k]; changed = true; }
    }
  }
  for (const k of DELETED_TOP) if (k in c) { delete c[k]; changed = true; }
  return changed;
}
