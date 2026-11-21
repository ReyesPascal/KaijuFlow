/**
 * Stream-list helpers around the health check.
 *
 * The list-time health checks (Smart and Fixed) were deleted in #191: the
 * health check runs only at play time (src/play/playTimeCheck.ts). What is
 * left marks EasyNews/Zyclops results as verified (Auto-queue was deleted in #226).
 */

import { config } from '../config/index.js';
import type { HealthCheckResult } from '../health/index.js';

/** Auto-mark EasyNews and Zyclops results as verified (they are not health-checked on the list). */
export function autoMarkRemainingResults(
  allResults: any[],
  healthResults: Map<string, HealthCheckResult>,
): void {
  const skipEasynewsAutoMark = config.easynewsHealthCheck && config.easynewsMode === 'nzb';
  for (const r of allResults) {
    if (r.easynewsMeta && !skipEasynewsAutoMark && !healthResults.has(r.link)) {
      healthResults.set(r.link, { status: 'verified', message: 'EasyNews', playable: true });
    }
    if (r.zyclopsVerified && !healthResults.has(r.link)) {
      healthResults.set(r.link, { status: 'verified', message: 'Zyclops', playable: true });
    }
  }
}
