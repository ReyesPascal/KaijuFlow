/**
 * Shared grab-then-hand-to-Backend step (spec #42, ticket #43).
 *
 * Every Backend's prepare gets the chosen Source's NZB here, never by calling
 * grabNzb itself. The step grabs (cache, proxy exit-IP check, validation,
 * grab tracking; ADR 0003), then Unscrambles a Scrambled RAR set (ADR 0005,
 * #44). Unscramble runs after the grab, so the NZB cache shared with health
 * checks keeps the original. Every Backend gets the same NZB.
 */

import { config } from '../config/index.js';
import { grabNzb } from './nzbGrab.js';
import { unscrambleNzb } from '../archive/unscramble.js';
import { setHealthCheckConnectionCap, DEFAULT_HEALTH_CHECK_CONNECTION_CAP } from '../health/nntpConnection.js';
import { logStep, timeStep } from '../utils/stepTiming.js';
import type { BackendSource } from './types.js';

/** Most time one Unscramble may read, from the start of its turn (#119); the prepare budget still caps it. */
export const UNSCRAMBLE_TIME_LIMIT_MS = 15000;

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
  const nzb = await timeStep(
    { step: 'nzb_fetch', source: source.indexerName, title: source.title },
    () => grabNzb(source.nzbUrl, source.title, undefined, logPrefix, source.indexerName, source.searchExitIp),
  );
  // Work after the grab (Unscramble) comes out of the budget.
  const afterGrab = Date.now();
  const upload = await unscramble(nzb, budgetMs, logPrefix, source);
  const remainingMs = budgetMs > 0 ? Math.max(1, budgetMs - (Date.now() - afterGrab)) : 0;
  return { nzb: upload, remainingMs };
}

/**
 * Unscramble on the health-check providers, one Source at a time (#119): up to
 * 15 s from its turn, the wait and the reads both within the budget. Never throws.
 */
async function unscramble(nzb: string, budgetMs: number, logPrefix: string, source: BackendSource): Promise<string> {
  const t0 = Date.now();
  const step = { step: 'unscramble', source: source.indexerName, title: source.title } as const;
  try {
    const hc = config.healthChecks;
    const connections = hc?.maxTotalConnections ?? DEFAULT_HEALTH_CHECK_CONNECTION_CAP;
    const providers = hc?.providers ?? [];
    // Apply the owner's cap even if no health check has run since start (as Ultimate Fallback does).
    if (providers.some(p => p.enabled)) setHealthCheckConnectionCap(connections);
    const r = await unscrambleNzb(nzb, providers, UNSCRAMBLE_TIME_LIMIT_MS, { connections, budgetMs: budgetMs > 0 ? budgetMs : undefined });
    logStep({ ...step, ms: r.ms, wait_ms: r.waitMs, result: r.changed ? 'unscrambled' : r.reason, parts: r.parts });
    if (r.changed) console.log(`${logPrefix}  \u{1F9E9} Unscrambled RAR set: ${r.parts} parts renamed in volume order (${r.ms} ms)`);
    else if (r.reason !== 'not-scrambled') console.log(`${logPrefix}  \u{1F9E9} Unscramble skipped (${r.reason}, ${r.parts} parts, ${r.ms} ms): uploading the original NZB`);
    return r.nzb;
  } catch (err) {
    logStep({ ...step, ok: false, ms: Date.now() - t0, result: 'failed' });
    console.warn(`${logPrefix}  \u{1F9E9} Unscramble failed (${(err as Error).message}): uploading the original NZB`);
    return nzb;
  }
}
