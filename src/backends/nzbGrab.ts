/**
 * NZB grab shared by every Backend (ADR 0003): the cached copy or an indexer
 * download through the proxy, then validation and grab tracking. The Backend's
 * prepare gets the NZB through grabSourceNzb (sourceNzb.ts); Ultimate
 * Fallback prefetches through prefetchNzb.
 */

import { config as globalConfig } from '../config/index.js';
import { getLatestVersions } from '../versionFetcher.js';
import { proxyFetch, verifyProxyCircuit } from '../proxy.js';
import { getCachedNzbContent, cacheNzbContent } from '../health/nzbContentCache.js';
import { trackGrab } from '../statsTracker.js';
import { sourceFailure } from './types.js';

/**
 * NZB grab shared by every Backend: cached copy or indexer download through
 * the proxy (exit-IP check), content validation and grab tracking. Returns the
 * NZB text. Throws a Source failure (sourceFailure) only for bad content: an
 * invalid NZB body, an indexer error payload, or a link the indexer says is
 * gone. An indexer that is unavailable or refuses us (429, 5xx, 401/403,
 * network error, download timeout) throws a plain error, so the player gets
 * the failure video and the Source stays alive (ADR 0004, #51).
 * Backends don't call it: they go through grabSourceNzb (src/backends/sourceNzb.ts).
 */
export async function grabNzb(
  nzbUrl: string,
  title: string,
  budgetMs?: number,
  logPrefix = '',
  indexerName?: string,
  searchExitIp?: string,
): Promise<string> {
  const budgetStart = Date.now();
  const remainingBudget = () => budgetMs ? Math.max(1000, budgetMs - (Date.now() - budgetStart)) : 30000;
  const indexerForLog = indexerName?.trim() || '(unknown)';
  // Check if NZB was already downloaded during health checks
  let nzbContent = getCachedNzbContent(nzbUrl);
  let freshlyDownloaded = false;
  if (nzbContent) {
    console.log(`${logPrefix}  \u{1F4BE} Using cached NZB from health check (${nzbContent.length} bytes)`);
  } else {
    // Download NZB from indexer with timeout
    const downloadUserAgent = globalConfig.userAgents?.nzbDownload || getLatestVersions().chrome;
    console.log(`${logPrefix}  \u{1F4E5} Downloading NZB from indexer: ${nzbUrl.substring(0, 80)}...`);
    await verifyProxyCircuit(nzbUrl, 'nzb-grab', indexerName, searchExitIp);

    const controller = new AbortController();
    const downloadTimeoutMs = remainingBudget();
    const timeout = setTimeout(() => controller.abort(), downloadTimeoutMs);

    let nzbResponse: { ok: boolean; status: number; statusText: string; text: () => Promise<string> };
    try {
      nzbResponse = await proxyFetch(nzbUrl, {
        headers: { 'User-Agent': downloadUserAgent },
        signal: controller.signal,
      }, indexerName);
    } catch (err) {
      clearTimeout(timeout);
      // The indexer, not the Source, failed: no dead mark (ADR 0004).
      if ((err as Error).name === 'AbortError') {
        throw new Error(`NZB download timed out after ${Math.round(downloadTimeoutMs / 1000)}s for ${indexerForLog}`);
      }
      throw new Error(`NZB download failed for ${indexerForLog}: ${(err as Error).message}`);
    }
    clearTimeout(timeout);

    if (!nzbResponse.ok) {
      const status = `${nzbResponse.status} ${nzbResponse.statusText}`.trim();
      const message = `Failed to download NZB from ${indexerForLog}: ${status}`;
      // Rate limit, server error or refused credentials: the indexer is unavailable to us,
      // the Source is not bad (ADR 0004, #51). Any other 4xx (404, 410) means the link is gone.
      if (nzbResponse.status === 429 || nzbResponse.status >= 500) throw new Error(`${message} (indexer unavailable, Source kept)`);
      if (nzbResponse.status === 401 || nzbResponse.status === 403) throw new Error(`${message} (indexer refused us, check its API key; Source kept)`);
      throw sourceFailure(message);
    }

    nzbContent = await nzbResponse.text();
    console.log(`${logPrefix}  \u2705 NZB downloaded (${nzbContent.length} bytes)`);
    freshlyDownloaded = true;
  }

  // Validate NZB content - must contain <nzb element
  if (!nzbContent.includes('<nzb') || !nzbContent.includes('</nzb>')) {
    // Check if it's an error response from the indexer
    if (nzbContent.includes('<error')) {
      const errorMatch = nzbContent.match(/description="([^"]+)"/);
      const errorMsg = errorMatch ? errorMatch[1] : 'Unknown indexer error';
      throw sourceFailure(`Indexer returned error: ${errorMsg}`);
    }
    throw sourceFailure(`Invalid NZB content received (${nzbContent.length} bytes)`);
  }

  // Single grab-tracking chokepoint. Cache hits skip this; invalid NZBs throw above.
  // EasyNews is tracked one layer up in the /nzb route, because its real indexer
  // fetch happens inside that route's POST to easynews.com, not in this
  // proxyFetch (which just loops back to the local handler).
  if (freshlyDownloaded && indexerForLog.toLowerCase() !== 'easynews') {
    trackGrab(indexerForLog, title);
  }

  return nzbContent;
}

/**
 * Pre-fetch an NZB from the indexer and cache it for later submission.
 * Best-effort, never throws. Returns true if the NZB is cached and ready.
 * `searchExitIp` carries the proxy exit IP that was live when this candidate's
 * search ran, used to gate the prefetch against an intervening IP rotation.
 */
export async function prefetchNzb(nzbUrl: string, logPrefix = '', quiet = false, title?: string, indexerName?: string, searchExitIp?: string): Promise<boolean> {
  // Already cached (from health check or earlier prefetch)
  if (getCachedNzbContent(nzbUrl)) return true;

  try {
    const downloadUserAgent = globalConfig.userAgents?.nzbDownload || getLatestVersions().chrome;
    if (!quiet) console.log(`${logPrefix}  📥 Prefetching NZB: ${nzbUrl.substring(0, 80)}...`);
    await verifyProxyCircuit(nzbUrl, 'nzb-prefetch', indexerName, searchExitIp);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30_000);

    let nzbResponse: { ok: boolean; status: number; statusText: string; text: () => Promise<string> };
    try {
      nzbResponse = await proxyFetch(nzbUrl, {
        headers: { 'User-Agent': downloadUserAgent },
        signal: controller.signal,
      }, indexerName);
    } catch (err) {
      clearTimeout(timeout);
      if (!quiet) console.warn(`${logPrefix}  ⚠️ Prefetch failed: ${(err as Error).message}`);
      return false;
    }
    clearTimeout(timeout);

    if (!nzbResponse.ok) {
      if (!quiet) console.warn(`${logPrefix}  ⚠️ Prefetch failed: ${nzbResponse.status} ${nzbResponse.statusText}`);
      return false;
    }

    const nzbContent = await nzbResponse.text();

    // Validate NZB XML
    if (!nzbContent.includes('<nzb') || !nzbContent.includes('</nzb>')) {
      if (nzbContent.includes('<error')) {
        const errorMatch = nzbContent.match(/description="([^"]+)"/);
        if (!quiet) console.warn(`${logPrefix}  ⚠️ Prefetch: indexer error — ${errorMatch ? errorMatch[1] : 'unknown'}`);
      } else {
        if (!quiet) console.warn(`${logPrefix}  ⚠️ Prefetch: invalid NZB content (${nzbContent.length} bytes)`);
      }
      return false;
    }

    cacheNzbContent(nzbUrl, nzbContent);
    if (!quiet) console.log(`${logPrefix}  ✅ Prefetched NZB (${nzbContent.length} bytes)`);

    // The indexer fetch just succeeded. Track here so UF-driven prefetches count
    // even when the subsequent grabNzb call hits cache. EasyNews skips for
    // the same reason as grabNzb: its real fetch happens in the /nzb route.
    if (title) {
      const tracked = indexerName?.trim() || '(unknown)';
      if (tracked.toLowerCase() !== 'easynews') {
        trackGrab(tracked, title);
      }
    }

    return true;
  } catch (err) {
    if (!quiet) console.warn(`${logPrefix}  ⚠️ Prefetch error: ${(err as Error).message}`);
    return false;
  }
}
