// One-time drop of the list-time health-check settings (#191), kept apart from
// migrations.ts so it can be tested without loading a config from disk.

/**
 * The list-time Smart and Fixed checks were deleted (#191): the health check runs
 * only at play time. Their settings are dropped from an old config: the on/off
 * switch, the mode, its batch and budget, the list's own sample count and archive
 * switch, hiding blocked results, the worker count and the per-indexer choice.
 * The health-check providers, the connection cap, TLS and auto-queue stay. True
 * when anything changed.
 */
export function dropListTimeCheckSettings(c: Record<string, unknown>): boolean {
  let changed = false;
  const LIST_TIME = ['enabled', 'mode', 'archiveInspection', 'sampleCount', 'nzbsToInspect', 'inspectionMethod',
    'smartBatchSize', 'smartAdditionalRuns', 'smartMinHealthy', 'hideBlocked', 'maxConnections', 'healthCheckIndexers'];
  const hc = c.healthChecks as Record<string, unknown> | undefined;
  if (hc && typeof hc === 'object') {
    for (const k of LIST_TIME) if (k in hc) { delete hc[k]; changed = true; }
  }
  if (Array.isArray(c.syncedIndexers)) {
    for (const si of c.syncedIndexers as Record<string, unknown>[]) {
      if (si && typeof si === 'object' && 'enabledForHealthCheck' in si) { delete si.enabledForHealthCheck; changed = true; }
    }
  }
  return changed;
}
