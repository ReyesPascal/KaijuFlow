/**
 * Health Check Coordinator
 *
 * Orchestrates NZB health checking in two modes:
 *   - Smart: batch-based, stops when a healthy result is found
 *   - Fixed: checks a fixed number of top results
 *
 * Also handles auto-marking EasyNews/Zyclops results as verified,
 * filtering blocked results, and auto-queuing to the Backend.
 */

import { config } from '../config/index.js';
import { getLatestVersions } from '../versionFetcher.js';
import { performBatchHealthChecks, setHealthCheckConnectionCap, type HealthCheckResult, type HealthCheckOptions } from '../health/index.js';
import { requestContext } from '../requestContext.js';
import { buildStreamFilename } from '../parsers/metadataParsers.js';
import { getActiveBackend } from '../backends/index.js';
import { isDeadNzbByUrl, addDeadNzbByUrl, saveCacheToDisk } from '../nzbdav/streamCache.js';
import { encodeTileEnvelope, toContentType } from '../nzbdav/redirectHelpers.js';
import { isUltimateFallbackActive } from '../nzbdav/utils.js';
import { getSelfUrl } from '../utils/selfUrl.js';

// Internal self-requests (auto-queue) hit loopback directly to avoid
// cross-origin redirect errors from reverse proxies / external BASE_URL.
// KaijuFlow: 127.0.0.1, not localhost (see utils/selfUrl.ts).
const SELF_URL = getSelfUrl();

/**
 * Number of Sources health-checked at once: `healthChecks.maxConnections`.
 * Callers still cap it by the number of Sources in the batch.
 */
export function healthCheckWorkerCount(healthChecks: { maxConnections?: number } | undefined): number {
  return healthChecks?.maxConnections || 12;
}

export interface HealthCheckContext {
  allResults: any[];
  type: string;
  season?: number;
  episode?: number;
  episodesInSeason?: number;
  episodeAired?: string;
  preExistingHealth?: Map<string, HealthCheckResult>;
}

/**
 * Run health checks on the provided results and return a map of link → HealthCheckResult.
 * Also mutates allResults in-place to filter blocked results when hideBlocked is enabled.
 * Returns the (potentially filtered) allResults alongside the health map.
 */
export async function coordinateHealthChecks(
  ctx: HealthCheckContext
): Promise<{ healthResults: Map<string, HealthCheckResult>; filteredResults: any[] }> {
  let { allResults } = ctx;
  const healthResults = new Map<string, HealthCheckResult>();
  // Pre-populate with existing health data (from cached results) so smart mode
  // sees already-checked results and doesn't re-check them
  if (ctx.preExistingHealth) {
    for (const [key, val] of ctx.preExistingHealth) healthResults.set(key, val);
  }

  const enabledProviders = config.healthChecks?.providers?.filter(p => p.enabled) || [];
  if (!config.healthChecks?.enabled || enabledProviders.length === 0) {
    // No NNTP health checks — still auto-mark EasyNews/Zyclops
    autoMarkRemainingResults(allResults, healthResults);
    return { healthResults, filteredResults: allResults };
  }

  // Build health-check-enabled set based on index manager mode
  const isAggregatorMode = config.indexManager === 'prowlarr' || config.indexManager === 'nzbhydra';
  const healthCheckEnabledSet = new Set<string>();
  if (isAggregatorMode) {
    for (const si of config.syncedIndexers || []) {
      if (si.enabledForHealthCheck) healthCheckEnabledSet.add(si.name);
    }
  }
  const healthCheckIndexers = config.healthChecks?.healthCheckIndexers;
  const userAgent = config.userAgents?.nzbDownload || getLatestVersions().chrome;
  const healthCheckOpts: HealthCheckOptions = {
    archiveInspection: config.healthChecks?.archiveInspection ?? true,
    sampleCount: config.healthChecks?.sampleCount ?? 7,
  };
  const inspectionMethod = config.healthChecks.inspectionMethod || 'smart';
  setHealthCheckConnectionCap(config.healthChecks.maxTotalConnections);
  const maxConnections = healthCheckWorkerCount(config.healthChecks);

  // Check if EasyNews NZB results should be health-checked instead of auto-verified
  const shouldHealthCheckEasynews = config.easynewsHealthCheck && config.easynewsMode === 'nzb';

  // Build EasyNews link → NZB proxy URL mapping for health checks
  const easynewsLinkToNzbUrl = new Map<string, string>();
  const nzbUrlToEasynewsLink = new Map<string, string>();
  if (shouldHealthCheckEasynews) {
    const hcManifestKey = requestContext.getStore()?.manifestKey || '';
    for (const r of allResults) {
      if (r.easynewsMeta) {
        const meta = r.easynewsMeta;
        const nzbParams = new URLSearchParams({ hash: meta.hash, filename: meta.filename, ext: meta.ext });
        if (meta.sig) nzbParams.set('sig', meta.sig);
        const nzbUrl = `${SELF_URL}/${hcManifestKey}/easynews/nzb?${nzbParams.toString()}`;
        easynewsLinkToNzbUrl.set(r.link, nzbUrl);
        nzbUrlToEasynewsLink.set(nzbUrl, r.link);
      }
    }
  }

  // Helper: auto-mark EasyNews/Zyclops results as healthy and filter eligible results for NNTP check
  const processCandidate = (candidate: typeof allResults[0]) => {
    if (candidate.easynewsMeta) {
      if (shouldHealthCheckEasynews) {
        return true; // Eligible for NNTP health check
      }
      if (!healthResults.has(candidate.link)) {
        healthResults.set(candidate.link, { status: 'verified', message: 'EasyNews', playable: true });
      }
      return false; // Not eligible for NNTP check
    }
    if (candidate.zyclopsVerified) {
      if (!healthResults.has(candidate.link)) {
        healthResults.set(candidate.link, { status: 'verified', message: 'Zyclops', playable: true });
      }
      return false; // Already verified by Zyclops — not eligible for NNTP check
    }
    // Skip results that already have health data (from cached pre-existing results)
    if (healthResults.has(candidate.link)) return false;
    if (isAggregatorMode) return healthCheckEnabledSet.has(candidate.indexerName);
    return !healthCheckIndexers || healthCheckIndexers[candidate.indexerName] !== false;
  };

  // Helper: resolve NZB URL for health check (translates easynews:// links to proxy URLs)
  const resolveHealthCheckUrl = (r: typeof allResults[0]) => easynewsLinkToNzbUrl.get(r.link) || r.link;
  // Helper: reverse-map health check result URL back to original link
  const resolveOriginalLink = (url: string) => nzbUrlToEasynewsLink.get(url) || url;

  const isVerifiedStatus = (s: string) =>
    s === 'verified' || s === 'verified_stored' || s === 'verified_archive';

  if (inspectionMethod === 'smart') {
    // --- SMART: Stop on Healthy ---
    const batchSize = config.healthChecks.smartBatchSize || 3;
    const additionalRuns = config.healthChecks.smartAdditionalRuns ?? 1;
    const minHealthy = Math.max(1, config.healthChecks.smartMinHealthy ?? 1);
    const maxBatches = 1 + additionalRuns;

    let healthyCount = 0;

    for (let batch = 0; batch < maxBatches; batch++) {
      const batchStart = batch * batchSize;
      const batchCandidates = allResults.slice(batchStart, batchStart + batchSize);
      if (batchCandidates.length === 0) break;

      // Process EasyNews and filter eligible NZBs
      const toCheck = batchCandidates.filter(processCandidate);

      const easynewsCount = batchCandidates.filter(r => r.easynewsMeta).length;
      const zyclopsCount = batchCandidates.filter(r => r.zyclopsVerified).length;
      if (easynewsCount > 0 && !shouldHealthCheckEasynews) {
        console.log(`✅ Auto-verified ${easynewsCount} EasyNews result(s) in batch ${batch + 1}`);
      } else if (easynewsCount > 0) {
        console.log(`🔍 Including ${easynewsCount} EasyNews result(s) in health check batch ${batch + 1}`);
      }
      if (zyclopsCount > 0) {
        console.log(`🤖 Auto-verified ${zyclopsCount} Zyclops result(s) in batch ${batch + 1}`);
      }
      // NZB Database pre-check: skip NNTP for known-bad NZBs
      if (toCheck.length > 0) {
        let nzbDbHits = 0;
        for (const r of toCheck) {
          if (healthResults.has(r.link)) continue;
          const url = easynewsLinkToNzbUrl.get(r.link) || r.link;
          if (isDeadNzbByUrl(url)) {
            healthResults.set(r.link, { status: 'blocked', message: 'NZB Database: previously failed', playable: false });
            nzbDbHits++;
          }
        }
        if (nzbDbHits > 0) {
          console.log(`💾 ${nzbDbHits} result(s) found in NZB Database (batch ${batch + 1}), skipping NNTP`);
          const remaining = toCheck.filter(r => !healthResults.has(r.link));
          toCheck.length = 0;
          toCheck.push(...remaining);
        }
      }

      console.log(`🔍 Smart batch ${batch + 1}/${maxBatches}: checking ${toCheck.length} NZB(s) across ${enabledProviders.length} provider(s)...`);

      if (toCheck.length > 0) {
        const indexerByUrl = new Map<string, string>();
        const searchIpByUrl = new Map<string, string>();
        for (const r of toCheck) {
          const url = resolveHealthCheckUrl(r);
          if (r.indexerName) indexerByUrl.set(url, r.indexerName);
          if (r.searchExitIp) searchIpByUrl.set(url, r.searchExitIp);
        }
        const { results: batchResults, circuitAborted } = await performBatchHealthChecks(
          toCheck.map(resolveHealthCheckUrl),
          enabledProviders,
          userAgent,
          Math.min(maxConnections, toCheck.length),
          healthCheckOpts,
          indexerByUrl,
          searchIpByUrl
        );

        for (const [url, result] of batchResults.entries()) {
          healthResults.set(resolveOriginalLink(url), result);
        }

        // Log batch results
        for (const [nzbUrl, result] of batchResults.entries()) {
          const originalLink = resolveOriginalLink(nzbUrl);
          const resultTitle = allResults.find(r => r.link === originalLink)?.title || 'Unknown';
          const icon = isVerifiedStatus(result.status) ? '✅' : '🚫';
          console.log(`  ${icon} ${resultTitle.substring(0, 60)}...`);
        }

        if (circuitAborted) {
          console.warn(`🔒 Smart mode: proxy circuit aborted mid-batch, stopping further batches`);
          break;
        }
      }

      // Count healthy results accumulated so far
      healthyCount = 0;
      for (const r of allResults.slice(0, batchStart + batchCandidates.length)) {
        const health = healthResults.get(r.link);
        if (health && isVerifiedStatus(health.status)) {
          healthyCount++;
        }
      }

      if (healthyCount >= minHealthy) {
        console.log(`✅ Smart mode: found ${healthyCount} healthy result(s) by batch ${batch + 1} (min: ${minHealthy}), stopping.`);
        break;
      }

      if (batch < maxBatches - 1) {
        console.log(`⏳ Smart mode: ${healthyCount}/${minHealthy} healthy after batch ${batch + 1}, continuing...`);
      }
    }

    if (healthyCount === 0) {
      console.log(`⚠️ Smart mode: no healthy result found after checking`);
    } else if (healthyCount < minHealthy) {
      console.log(`⚠️ Smart mode: only found ${healthyCount}/${minHealthy} healthy result(s) after all batches`);
    }

  } else {
    // --- FIXED COUNT (default, existing behavior) ---
    const topN = allResults.slice(0, config.healthChecks.nzbsToInspect);

    // Process EasyNews and filter eligible NZBs
    const nonEasynewsToCheck = topN.filter(processCandidate);

    const easynewsCount = topN.filter(r => r.easynewsMeta).length;
    const zyclopsCount = topN.filter(r => r.zyclopsVerified).length;
    if (easynewsCount > 0 && !shouldHealthCheckEasynews) {
      console.log(`✅ Auto-verified ${easynewsCount} EasyNews result(s) in top ${topN.length}`);
    } else if (easynewsCount > 0) {
      console.log(`🔍 Including ${easynewsCount} EasyNews result(s) in health check`);
    }
    if (zyclopsCount > 0) {
      console.log(`🤖 Auto-verified ${zyclopsCount} Zyclops result(s) in top ${topN.length}`);
    }
    // NZB Database pre-check: skip NNTP for known-bad NZBs
    if (nonEasynewsToCheck.length > 0) {
      let nzbDbHits = 0;
      for (const r of nonEasynewsToCheck) {
        if (healthResults.has(r.link)) continue;
        const url = easynewsLinkToNzbUrl.get(r.link) || r.link;
        if (isDeadNzbByUrl(url)) {
          healthResults.set(r.link, { status: 'blocked', message: 'NZB Database: previously failed', playable: false });
          nzbDbHits++;
        }
      }
      if (nzbDbHits > 0) {
        console.log(`💾 ${nzbDbHits} result(s) found in NZB Database, skipping NNTP`);
        const remaining = nonEasynewsToCheck.filter(r => !healthResults.has(r.link));
        nonEasynewsToCheck.length = 0;
        nonEasynewsToCheck.push(...remaining);
      }
    }

    console.log(`🔍 Health checking ${nonEasynewsToCheck.length} result(s) across ${enabledProviders.length} provider(s)...`);

    if (nonEasynewsToCheck.length > 0) {
      const indexerByUrl = new Map<string, string>();
      const searchIpByUrl = new Map<string, string>();
      for (const r of nonEasynewsToCheck) {
        const url = resolveHealthCheckUrl(r);
        if (r.indexerName) indexerByUrl.set(url, r.indexerName);
        if (r.searchExitIp) searchIpByUrl.set(url, r.searchExitIp);
      }
      const { results: usenetResults, circuitAborted } = await performBatchHealthChecks(
        nonEasynewsToCheck.map(resolveHealthCheckUrl),
        enabledProviders,
        userAgent,
        Math.min(maxConnections, nonEasynewsToCheck.length),
        healthCheckOpts,
        indexerByUrl,
        searchIpByUrl
      );

      for (const [url, result] of usenetResults.entries()) {
        healthResults.set(resolveOriginalLink(url), result);
      }

      if (circuitAborted) {
        console.warn(`🔒 Health check aborted mid-batch: proxy circuit changed`);
      }
      console.log(`✅ Health check complete: ${usenetResults.size} results checked`);

      for (const [nzbUrl, result] of usenetResults.entries()) {
        const originalLink = resolveOriginalLink(nzbUrl);
        const resultTitle = allResults.find(r => r.link === originalLink)?.title || 'Unknown';
        const icon = isVerifiedStatus(result.status) ? '✅' : '🚫';
        console.log(`  ${icon} ${resultTitle.substring(0, 60)}...`);
      }
    }
  }

  // Also auto-mark any remaining EasyNews/Zyclops results (beyond top N) as healthy
  // Skip auto-marking EasyNews if health checks are enabled for them
  let remainingEasynews = 0;
  let remainingZyclops = 0;
  for (const r of allResults) {
    if (r.easynewsMeta && !shouldHealthCheckEasynews && !healthResults.has(r.link)) {
      healthResults.set(r.link, {
        status: 'verified',
        message: 'EasyNews',
        playable: true,
      });
      remainingEasynews++;
    }
    if (r.zyclopsVerified && !healthResults.has(r.link)) {
      healthResults.set(r.link, {
        status: 'verified',
        message: 'Zyclops',
        playable: true,
      });
      remainingZyclops++;
    }
  }
  if (remainingEasynews > 0) {
    console.log(`✅ Auto-verified ${remainingEasynews} remaining EasyNews result(s) beyond inspection window`);
  }
  if (remainingZyclops > 0) {
    console.log(`🤖 Auto-verified ${remainingZyclops} remaining Zyclops result(s) beyond inspection window`);
  }

  // Write blocked NNTP results to dead NZB cache
  let deadWrites = 0;
  for (const [link, result] of healthResults) {
    if (result.status === 'blocked' && result.message !== 'NZB Database: previously failed') {
      const url = easynewsLinkToNzbUrl.get(link) || link;
      const r = allResults.find(rs => rs.link === link);
      if (r?.title) { addDeadNzbByUrl(url, r.title, r.indexerName, r.size); deadWrites++; }
    }
  }
  if (deadWrites > 0) saveCacheToDisk();

  // Filter out blocked/error NZBs if hideBlocked is enabled
  if (config.healthChecks.hideBlocked) {
    const beforeCount = allResults.length;
    allResults = allResults.filter(r => {
      const health = healthResults.get(r.link);
      // Keep results that weren't checked or that aren't blocked/error
      return !health || (health.status !== 'blocked' && health.status !== 'error');
    });
    const filteredCount = beforeCount - allResults.length;
    if (filteredCount > 0) {
      console.log(`🚫 Filtered out ${filteredCount} blocked/error NZB(s)`);
    }
  }

  return { healthResults, filteredResults: allResults };
}

/**
 * Auto-mark EasyNews and Zyclops results as verified (even without NNTP health checks).
 * Called both when health checks are disabled and as a final pass after health checks.
 */
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


/**
 * Auto-queue verified results to the Backend (prepare ahead of the click).
 * Mode 'top': queue only the first verified result.
 * Mode 'all': queue all verified results in order.
 * Reuses NZB content cached during health checks to avoid extra indexer grabs.
 */
export function autoQueueToNzbdav(
  allResults: any[],
  healthResults: Map<string, HealthCheckResult>,
  type: string,
  season?: number,
  episode?: number,
  episodesInSeason?: number,
): void {
  const mode = config.healthChecks?.autoQueueMode;
  // UF in on-results mode submits NZBs at search time itself; running auto-queue
  // would race on the same titles (NzbDAV has had 500s on concurrent inserts).
  // on-tile-selection defers UF's submit until click, so auto-queue is safe there.
  const ufSubmitsAtSearch = isUltimateFallbackActive()
    && config.ultimateFallback?.whenToResolve !== 'on-tile-selection';
  if (!config.healthChecks?.enabled || !mode || mode === 'off' || config.streamingMode !== 'nzbdav'
      || allResults.length === 0 || ufSubmitsAtSearch) {
    return;
  }

  // Packed into the tile envelope so the stream handler resolves the nzbdav
  // category correctly for auto-queued submits.
  const ty = toContentType(type);
  // Auto-queued tiles go through the stream route, so the active Backend prepares them.
  const backendLabel = getActiveBackend().label;

  const sendToNzbdav = (result: any, reason: string) => {
    try {
      console.log(`🚀 Auto-queueing (${reason}): ${result.title}`);
      const autoManifestKey = requestContext.getStore()?.manifestKey || '';

      // For EasyNews NZB mode, construct the NZB proxy URL instead of using easynews:// link
      let nzbUrl = result.link;
      if (result.easynewsMeta && config.easynewsMode === 'nzb') {
        const meta = result.easynewsMeta;
        const nzbParams = new URLSearchParams({
          hash: meta.hash,
          filename: meta.filename,
          ext: meta.ext,
        });
        if (meta.sig) nzbParams.set('sig', meta.sig);
        nzbUrl = `${SELF_URL}/${autoManifestKey}/easynews/nzb?${nzbParams.toString()}`;
      }

      const streamFilename = buildStreamFilename(result.title, type, season, episode);
      const includeSeasonPack = result.isSeasonPack && season !== undefined && episode !== undefined;
      const tileT = encodeTileEnvelope({
        ty,
        url: nzbUrl,
        title: result.title,
        indexer: result.indexerName,
        ...(includeSeasonPack ? {
          season,
          episode,
          seasonpack: 1 as const,
          ...(episodesInSeason ? { epcount: episodesInSeason } : {}),
        } : {}),
      });
      const proxyUrl = `${SELF_URL}/${autoManifestKey}/nzbdav/stream/${encodeURIComponent(streamFilename || result.title || 'stream')}?t=${tileT}&auto=true`;
      fetch(proxyUrl).catch(err => console.error('❌ Auto-queue failed:', err));
    } catch (error) {
      console.error(`❌ Auto-queue to ${backendLabel} failed:`, error);
    }
  };

  // Find verified results (skip EasyNews in DDL mode — not NZBs)
  const isVerifiedStatus = (s: string | undefined) =>
    s === 'verified' || s === 'verified_stored' || s === 'verified_archive';

  const isEligible = (r: any) => {
    if (r.easynewsMeta && config.easynewsMode !== 'nzb') return false;
    const health = healthResults.get(r.link);
    return !!health && isVerifiedStatus(health.status);
  };

  if (mode === 'all') {
    // Deduplicate by title — same release from different indexers causes NZBDav DB conflicts
    const seen = new Set<string>();
    const verified = allResults.filter(r => {
      if (!isEligible(r)) return false;
      if (seen.has(r.title)) return false;
      seen.add(r.title);
      return true;
    });
    if (verified.length > 0) {
      console.log(`🚀 Auto-queueing all ${verified.length} verified result(s) to ${backendLabel}`);
      // Serialize submissions — NZBDav's database chokes on concurrent inserts
      (async () => {
        for (let i = 0; i < verified.length; i++) {
          sendToNzbdav(verified[i], `verified ${i + 1}/${verified.length}`);
          if (i < verified.length - 1) await new Promise(r => setTimeout(r, 250));
        }
      })();
    }
  } else {
    // mode === 'top'
    const firstVerified = allResults.find(isEligible);
    if (firstVerified) {
      sendToNzbdav(firstVerified, 'verified');
    }
  }
}
