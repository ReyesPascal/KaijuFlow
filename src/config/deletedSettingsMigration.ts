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
};

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
  // The per-indexer list-time check choice (#191).
  if (Array.isArray(c.syncedIndexers)) {
    for (const si of c.syncedIndexers as Record<string, unknown>[]) {
      if (si && typeof si === 'object' && 'enabledForHealthCheck' in si) { delete si.enabledForHealthCheck; changed = true; }
    }
  }
  return changed;
}
