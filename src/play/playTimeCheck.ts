/**
 * Play-time check (GLOSSARY, spec #183, #190).
 *
 * The health check runs when a Source is about to be played, never before the
 * stream list is sent (the list-time Smart and Fixed checks were deleted in
 * #191): the list goes out at once, unchecked, with the Best entry on top when
 * Ultimate Fallback is on. Ultimate Fallback's engine is the Best entry's
 * engine; a list entry is checked when it is clicked (`prepareStream`),
 * whatever the fallback setting. KaijuFlow never hands the Backend an
 * Unchecked Source: a Source this check did not find healthy is not handed over.
 */

import { config as globalConfig } from '../config/index.js';
import { getLatestVersions } from '../versionFetcher.js';
import { performHealthCheck } from '../health/healthCheckPipeline.js';
import type { NntpConnectionPool } from '../health/nntpConnection.js';
import type { HealthCheckResult } from '../health/types.js';
import type { UsenetProvider } from '../types.js';
import { logStep } from '../utils/stepTiming.js';
import { sourceFailure } from '../backends/types.js';

/** The health-check providers switched on: the only ones a Play-time check asks. */
export function enabledHealthCheckProviders(): UsenetProvider[] {
  return (globalConfig.healthChecks?.providers ?? []).filter(p => p.enabled);
}

/** The Source to check. */
export interface SourceToCheck {
  nzbUrl: string;
  title?: string;
  indexerName?: string;
  /** Proxy exit IP hash from search time, checked when grabbing the NZB. */
  searchExitIp?: string;
  /** The episode selector AltMount is sent (#203): the check samples the file it picks. */
  episodePattern?: string;
}

/** True for a result the Backend may be handed (the statuses the health check calls healthy). */
export function isHealthy(result: HealthCheckResult): boolean {
  return result.status === 'verified' || result.status === 'verified_stored' || result.status === 'verified_archive';
}

/**
 * Check one Source before it is played: the health check with the pass rule
 * (ADR 0009, archive inspection always on). No setting turns it off; with no
 * enabled health-check provider nothing can be checked, so the answer is an
 * error and the Source is not played.
 * `pool`: share NNTP connections across the checks of one Best press.
 */
export async function checkSource(source: SourceToCheck, pool?: NntpConnectionPool): Promise<HealthCheckResult> {
  const t0 = Date.now();
  const providers = enabledHealthCheckProviders();
  const result: HealthCheckResult = providers.length === 0
    ? { status: 'error', message: 'No health-check provider: a Source is checked before it is played', playable: false }
    : await performHealthCheck(
      source.nzbUrl, providers, globalConfig.userAgents?.nzbDownload || getLatestVersions().chrome,
      { archiveInspection: true, sampleCount: globalConfig.ultimateFallback?.sampleCount ?? 3, episodePattern: source.episodePattern },
      pool, source.indexerName, source.searchExitIp,
    );
  logStep({ step: 'play_check', source: source.indexerName, title: source.title, ok: isHealthy(result), status: result.status, ms: Date.now() - t0 });
  return result;
}

/**
 * Check a Source the player clicked, right before it is handed to the Backend.
 * Returns when it is healthy. Throws a Source failure (it is marked dead) when the
 * check blocks it, and a plain error (not dead, ADR 0004) when the check could not
 * answer, for example the indexer or the news server did not.
 */
export async function requireHealthySource(source: SourceToCheck, logPrefix = ''): Promise<void> {
  const result = await checkSource(source);
  if (isHealthy(result)) {
    console.log(`${logPrefix}✅ Play-time check: healthy (${result.message})`);
    return;
  }
  console.log(`${logPrefix}❌ Play-time check: ${result.status} (${result.message}) — not handed to the Backend`);
  if (result.status === 'blocked') throw sourceFailure(`Play-time check: ${result.message}`);
  throw new Error(`Play-time check could not check the Source: ${result.message}`);
}
