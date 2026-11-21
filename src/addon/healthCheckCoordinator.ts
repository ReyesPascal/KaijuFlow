/**
 * Stream-list helpers around the health check.
 *
 * The list-time health checks (Smart and Fixed) were deleted in #191: the
 * health check runs only at play time (src/play/playTimeCheck.ts). What is
 * left marks EasyNews/Zyclops results as verified and auto-queues to the Backend.
 */

import { config } from '../config/index.js';
import type { HealthCheckResult } from '../health/index.js';
import { requestContext } from '../requestContext.js';
import { buildStreamFilename } from '../parsers/metadataParsers.js';
import { getActiveBackend } from '../backends/index.js';
import { encodeTileEnvelope, toContentType } from '../play/redirectHelpers.js';
import { isUltimateFallbackActive } from '../play/utils.js';
import { getSelfUrl } from '../utils/selfUrl.js';

// Internal self-requests (auto-queue) hit loopback directly to avoid
// cross-origin redirect errors from reverse proxies / external BASE_URL.
// KaijuFlow: 127.0.0.1, not localhost (see utils/selfUrl.ts).
const SELF_URL = getSelfUrl();

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


/**
 * Auto-queue verified results to the Backend (prepare ahead of the click).
 * Mode 'top': queue only the first verified result.
 * Mode 'all': queue all verified results in order.
 * Reuses NZB content cached during health checks to avoid extra indexer grabs.
 */
export function autoQueueToBackend(
  allResults: any[],
  healthResults: Map<string, HealthCheckResult>,
  type: string,
  season?: number,
  episode?: number,
  episodesInSeason?: number,
): void {
  const mode = config.healthChecks?.autoQueueMode;
  // UF in on-results mode submits NZBs at search time itself; running auto-queue
  // would race on the same titles.
  // on-tile-selection defers UF's submit until click, so auto-queue is safe there.
  const ufSubmitsAtSearch = isUltimateFallbackActive()
    && config.ultimateFallback?.whenToResolve !== 'on-tile-selection';
  if (!mode || mode === 'off'
      || allResults.length === 0 || ufSubmitsAtSearch) {
    return;
  }

  // Packed into the tile envelope so the stream handler resolves the Backend
  // category correctly for auto-queued submits.
  const ty = toContentType(type);
  // Auto-queued tiles go through the stream route, so the active Backend prepares them.
  const backendLabel = getActiveBackend().label;

  const sendToBackend = (result: any, reason: string) => {
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
      const proxyUrl = `${SELF_URL}/${autoManifestKey}/play/stream/${encodeURIComponent(streamFilename || result.title || 'stream')}?t=${tileT}&auto=true`;
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
    // Deduplicate by title — the same release from different indexers would be prepared twice
    const seen = new Set<string>();
    const verified = allResults.filter(r => {
      if (!isEligible(r)) return false;
      if (seen.has(r.title)) return false;
      seen.add(r.title);
      return true;
    });
    if (verified.length > 0) {
      console.log(`🚀 Auto-queueing all ${verified.length} verified result(s) to ${backendLabel}`);
      // Serialize submissions — one hand-off to the Backend at a time
      (async () => {
        for (let i = 0; i < verified.length; i++) {
          sendToBackend(verified[i], `verified ${i + 1}/${verified.length}`);
          if (i < verified.length - 1) await new Promise(r => setTimeout(r, 250));
        }
      })();
    }
  } else {
    // mode === 'top'
    const firstVerified = allResults.find(isEligible);
    if (firstVerified) {
      sendToBackend(firstVerified, 'verified');
    }
  }
}
