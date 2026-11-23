/**
 * The stream list's verified marks.
 *
 * The list goes out unchecked (the list-time Smart and Fixed checks were deleted in
 * #191; a Source is checked when it is played, src/play/playTimeCheck.ts). The only
 * marks left are the ones a result brings from where it was found: EasyNews and
 * Zyclops results show as verified.
 */

import { config } from '../config/index.js';
import type { HealthCheckResult } from '../health/index.js';

/**
 * The verified marks of one list, by NZB link: EasyNews results (unless EasyNews
 * is set to be checked, in NZB mode) and Zyclops-verified results. Made afresh for
 * every list, so a settings change shows at once.
 */
export function verifiedMarks(allResults: any[]): Map<string, HealthCheckResult> {
  const marks = new Map<string, HealthCheckResult>();
  const checkEasynews = config.easynewsHealthCheck && config.easynewsMode === 'nzb';
  for (const r of allResults) {
    if (r.easynewsMeta && !checkEasynews && !marks.has(r.link)) {
      marks.set(r.link, { status: 'verified', message: 'EasyNews', playable: true });
    }
    if (r.zyclopsVerified && !marks.has(r.link)) {
      marks.set(r.link, { status: 'verified', message: 'Zyclops', playable: true });
    }
  }
  return marks;
}
