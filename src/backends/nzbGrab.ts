/**
 * NZB grab shared by every Backend (ADR 0003): the cached copy or an indexer
 * download through the proxy, then validation and grab tracking. The Backend's
 * prepare gets the NZB through grabSourceNzb (sourceNzb.ts); Best's Walk
 * grabs through walkGrab, which sorts failures the same way.
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
 * NZB text. Throws a Source failure (sourceFailure) only for bad content (an
 * invalid NZB body) or a link the indexer says is gone (404 and other 4xx, an
 * error payload with code 300). An indexer that is unavailable or refuses us
 * (429, 5xx, 401/403, an error payload with any other code, network error,
 * download timeout) throws a plain error, so the player gets
 * the failure video and the Source stays alive (ADR 0004, #51).
 * `stop`: cuts the download off when it aborts (a Walk that ended, GLOSSARY: Walk), with a plain error.
 * Backends don't call it: they go through grabSourceNzb (src/backends/sourceNzb.ts).
 */
export async function grabNzb(
  nzbUrl: string,
  title: string,
  budgetMs?: number,
  logPrefix = '',
  indexerName?: string,
  searchExitIp?: string,
  stop?: AbortSignal,
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
    const stopped = () => new Error(`NZB download stopped for ${indexerForLog}`);
    try {
      await verifyProxyCircuit(nzbUrl, 'nzb-grab', indexerName, searchExitIp, stop);
    } catch (err) {
      if (stop?.aborted) throw stopped();
      throw err;
    }
    if (stop?.aborted) throw stopped();
    const controller = new AbortController();
    const downloadTimeoutMs = remainingBudget();
    const timeout = setTimeout(() => controller.abort(), downloadTimeoutMs);
    const onStop = () => controller.abort();
    stop?.addEventListener('abort', onStop, { once: true });

    let nzbResponse: { ok: boolean; status: number; statusText: string; text: () => Promise<string> };
    try {
      nzbResponse = await proxyFetch(nzbUrl, {
        headers: { 'User-Agent': downloadUserAgent },
        signal: controller.signal,
      }, indexerName);
    } catch (err) {
      clearTimeout(timeout);
      stop?.removeEventListener('abort', onStop);
      if (stop?.aborted) throw stopped();
      // The indexer, not the Source, failed: no dead mark (ADR 0004).
      if ((err as Error).name === 'AbortError') {
        throw new Error(`NZB download timed out after ${Math.round(downloadTimeoutMs / 1000)}s for ${indexerForLog}`);
      }
      throw new Error(`NZB download failed for ${indexerForLog}: ${(err as Error).message}`);
    }
    clearTimeout(timeout);

    try {
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
    } catch (err) {
      if (stop?.aborted) throw stopped();
      throw err;
    } finally {
      stop?.removeEventListener('abort', onStop);
    }
    console.log(`${logPrefix}  \u2705 NZB downloaded (${nzbContent.length} bytes)`);
    freshlyDownloaded = true;
  }

  // Validate NZB content - must contain <nzb element
  if (!nzbContent.includes('<nzb') || !nzbContent.includes('</nzb>')) {
    // An error payload (200 with a Newznab <error>) is sorted by its code, as an HTTP answer is by its status
    // (ADR 0004): 300 (no such item) means the link is gone; every other code (1xx credentials, suspended or
    // privileges, 5xx request or download limit, ...) is the indexer refusing us, the Source kept.
    if (nzbContent.includes('<error')) {
      const errorMsg = nzbContent.match(/description="([^"]+)"/)?.[1] ?? 'Unknown indexer error';
      const code = nzbContent.match(/<error[^>]*\bcode="(\d+)"/)?.[1];
      if (code === '300') throw sourceFailure(`Indexer returned error: ${errorMsg}`);
      throw new Error(`Indexer ${indexerForLog} refused the grab: ${errorMsg} (code ${code ?? 'none'}; indexer unavailable, Source kept)`);
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
 * The Walk's grab (ADR 0004, "The walk's grabs"): grabNzb, keeping the NZB for the check and the prepare. It sorts
 * its answers as grabNzb does: a Source failure (sourceFailure, isBadSource) for a link the indexer says is gone or
 * bad content, a plain error for an indexer that refuses or cannot be reached.
 * `searchExitIp` carries the proxy exit IP that was live when this candidate's search ran; `stop` cuts the grab off.
 */
export async function walkGrab(nzbUrl: string, title: string, logPrefix = '', indexerName?: string, searchExitIp?: string, stop?: AbortSignal): Promise<void> {
  if (getCachedNzbContent(nzbUrl)) return;
  cacheNzbContent(nzbUrl, await grabNzb(nzbUrl, title, undefined, logPrefix, indexerName, searchExitIp, stop));
}
