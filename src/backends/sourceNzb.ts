/**
 * Shared grab-then-hand-to-Backend step (spec #42, ticket #43).
 *
 * Every Backend's prepare gets the chosen Source's NZB here, never by calling
 * grabNzb itself. Today the step only grabs (cache, proxy exit-IP check,
 * validation, grab tracking; ADR 0003). It is the single place where
 * Unscramble (ADR 0005) plugs in, after the grab, so the NZB cache shared
 * with health checks keeps the original.
 */

import { grabNzb } from '../nzbdav/nzbdavApi.js';
import type { BackendSource } from './types.js';

export interface SourceNzb {
  /** The NZB text to upload to the Backend. */
  nzb: string;
  /** Prepare budget left for the Backend after this step, in ms. 0 = no limit. */
  remainingMs: number;
}

/**
 * Grab the Source's NZB for upload. `budgetMs` is what's left of the prepare
 * budget (0 = no limit); the result says how much of it the Backend still has
 * after the step's own work past the grab.
 * Throws Source failures from the grab, as before.
 */
export async function grabSourceNzb(
  source: BackendSource,
  opts: { budgetMs?: number; logPrefix?: string } = {},
): Promise<SourceNzb> {
  const { budgetMs = 0, logPrefix = '' } = opts;
  // The grab keeps its own download timeout and, as before this step existed,
  // its time doesn't come out of the Backend's wait.
  const nzb = await grabNzb(source.nzbUrl, source.title, undefined, logPrefix, source.indexerName, source.searchExitIp);
  // Work after the grab (Unscramble, #44) comes out of the budget.
  const afterGrab = Date.now();
  const remainingMs = budgetMs > 0 ? Math.max(1, budgetMs - (Date.now() - afterGrab)) : 0;
  return { nzb, remainingMs };
}
