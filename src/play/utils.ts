/**
 * Stream handling shared utilities (episode patterns, media paths, delivery log,
 * dead-mark helpers).
 */

import { config as globalConfig } from '../config/index.js';
import { backendCapabilities } from '../backends/capabilities.js';

/**
 * Build an episode pattern regex for matching season/episode in filenames.
 * Used by stream resolution and auto-resolve to locate the correct episode
 * within a season pack or multi-episode release.
 */
export function buildEpisodePattern(season: number, episode: number, allowMultiEpisodeFiles: boolean): string {
  const s = season.toString().padStart(2, '0');
  const e = episode.toString().padStart(2, '0');
  return allowMultiEpisodeFiles
    ? `S${s}(?:[. _-]?E\\d+|-\\d{1,2})*(?:[. _-]?E${e}|-${e})(?!\\d)`
    : `S${s}[. _-]?E${e}(?!\\d|[. _-]?E\\d|-\\d)`;
}

/**
 * Build a date-pattern regex for daily/talk-show episode releases. Mirrors
 * the search-side date convention (separators `[. _-]?`, fixed digits derived
 * from the input). Returns undefined when the input is missing or doesn't
 * match `YYYY-MM-DD` form so callers can short the date pass without an
 * explicit guard. Word boundaries prevent partial-token matches.
 *
 * Used as a Pass-2 fallback when SxxExx-based library matching returns nothing
 * AND the search context has both an aired date and TVDB aliases (the same
 * gate the alias-fallback search uses).
 */
export function buildDateEpisodePattern(episodeAired: string | undefined): string | undefined {
  if (!episodeAired || !/^\d{4}-\d{2}-\d{2}/.test(episodeAired)) return undefined;
  const [y, m, d] = episodeAired.slice(0, 10).split('-');
  return `\\b${y}[. _-]?${m}[. _-]?${d}\\b`;
}

/**
 * Ultimate Fallback needs the Backend's ultimateFallback capability (off for AltMount until #190): until then it acts as
 * off even if the saved setting is enabled. Use instead of reading `ultimateFallback.enabled`.
 */
export function isUltimateFallbackActive(): boolean {
  return globalConfig.ultimateFallback?.enabled === true && backendCapabilities().ultimateFallback;
}

/**
 * Encode a raw WebDAV file path for use in URLs.
 * Splits on '/', filters out empty segments and traversal components,
 * and encodes each segment individually.
 */
export function encodeWebdavPath(rawPath: string): string {
  return '/' + rawPath
    .split('/')
    .filter(s => s && s !== '.' && s !== '..')
    .map(s => encodeURIComponent(s))
    .join('/');
}

// ── Delivery log ──────────────────────────────────────────────────────
// Tracks last logged delivery mode per video path to avoid repeating
// the same log line on every range request during active playback.
// Lives here (rather than streamHandler) to avoid a circular dependency
// between streamCache and streamHandler.

const lastDeliveryLog = new Map<string, { mode: 'pipe' | 'proxy' | 'direct'; at: number }>();

/** Get the delivery log map (used by streamHandler for dedup + TTL eviction) */
export function getDeliveryLog(): Map<string, { mode: 'pipe' | 'proxy' | 'direct'; at: number }> {
  return lastDeliveryLog;
}

/** Clear all delivery log entries (called from clearStreamCache) */
export function clearDeliveryLog(): void {
  lastDeliveryLog.clear();
}

/** Error message stored when an episode is only found in a combined multi-episode file */
export const MULTI_EPISODE_BLOCKED_ERROR = 'Episode only found in combined multi-episode file';

/**
 * Transport-layer error thrown when WebDAV returns an error status (404, 410, etc.)
 * for a video file. Carries the videoPath so callers can evict the stale cache entry.
 */
export class WebDav404Error extends Error {
  readonly videoPath: string;
  readonly statusCode: number;
  constructor(videoPath: string, statusCode: number = 404) {
    super(`WebDAV upstream returned ${statusCode} for video path`);
    this.name = 'WebDav404Error';
    this.videoPath = videoPath;
    this.statusCode = statusCode;
  }
}

/**
 * True for a dead-mark message written when the indexer did not hand over the
 * NZB (rate limit, server error, refused credentials, network error, download
 * timeout). Such a mark
 * says nothing about the Source (ADR 0004, #51); the dead cache drops it on
 * load. Bad-content messages (invalid NZB, indexer error payload) stay.
 */
export function isIndexerUnavailableMessage(message: string): boolean {
  return /^Failed to download NZB from .+: (429|401|403|5\d\d)\b/.test(message)
    || /^NZB download failed for /.test(message)
    || /^NZB download timed out after /.test(message);
}

/**
 * Split stored dead marks into the ones to keep and the ones an unavailable
 * indexer caused (429, 5xx, refused credentials, network error, timeout on the
 * NZB grab). Earlier builds wrote those as Source failures; they say nothing
 * about the Source, so they are dropped on load (ADR 0004, #51).
 */
export function pruneIndexerUnavailableMarks<T extends { error?: { message?: string } }>(
  stored: Record<string, T>,
): { kept: Record<string, T>; dropped: string[] } {
  const kept: Record<string, T> = {};
  const dropped: string[] = [];
  for (const [key, entry] of Object.entries(stored)) {
    if (isIndexerUnavailableMessage(entry.error?.message ?? '')) dropped.push(key);
    else kept[key] = entry;
  }
  return { kept, dropped };
}
