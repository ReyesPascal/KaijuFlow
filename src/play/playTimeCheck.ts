/**
 * Play-time check (GLOSSARY, spec #183, #190).
 *
 * The health check runs when a Source is about to be played, not before the
 * stream list is sent: the list goes out at once, unchecked, with the Best
 * entry on top. Ultimate Fallback's engine is its engine (the Best entry);
 * a list entry is checked when it is clicked (`prepareStream`). KaijuFlow
 * never hands the Backend an Unchecked Source: a Source this check did not
 * find healthy is not handed over.
 */

import { config as globalConfig } from '../config/index.js';
import { getLatestVersions } from '../versionFetcher.js';
import { performHealthCheck } from '../health/healthCheckPipeline.js';
import type { NntpConnectionPool } from '../health/nntpConnection.js';
import type { HealthCheckResult } from '../health/types.js';
import { logStep } from '../utils/stepTiming.js';
import { isUltimateFallbackActive } from './utils.js';

/** True when the Play-time check is on: Ultimate Fallback is on and the Backend can run it (AltMount since #190). */
export function isPlayTimeCheckOn(): boolean {
  return isUltimateFallbackActive();
}

/** The Source to check. */
export interface SourceToCheck {
  nzbUrl: string;
  title?: string;
  indexerName?: string;
  /** Proxy exit IP hash from search time, checked when grabbing the NZB. */
  searchExitIp?: string;
}

/** True for a result the Backend may be handed (the statuses the health check calls healthy). */
export function isHealthy(result: HealthCheckResult): boolean {
  return result.status === 'verified' || result.status === 'verified_stored' || result.status === 'verified_archive';
}

/**
 * Check one Source before it is played: the health check with the pass rule
 * (ADR 0009, archive inspection always on). It runs whatever the list-time
 * health-check switches say; with no enabled health-check provider nothing can
 * be checked, so the answer is an error and the Source is not played.
 * `pool`: share NNTP connections across the checks of one Best press.
 */
export async function checkSource(source: SourceToCheck, pool?: NntpConnectionPool): Promise<HealthCheckResult> {
  const t0 = Date.now();
  const providers = (globalConfig.healthChecks?.providers ?? []).filter(p => p.enabled);
  const result: HealthCheckResult = providers.length === 0
    ? { status: 'error', message: 'No health-check provider: a Source is checked before it is played', playable: false }
    : await performHealthCheck(
      source.nzbUrl, providers, globalConfig.userAgents?.nzbDownload || getLatestVersions().chrome,
      { archiveInspection: true, sampleCount: globalConfig.ultimateFallback?.sampleCount ?? 3 },
      pool, source.indexerName, source.searchExitIp,
    );
  logStep({ step: 'play_check', source: source.indexerName, title: source.title, ok: isHealthy(result), status: result.status, ms: Date.now() - t0 });
  return result;
}
