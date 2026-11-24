/**
 * Stream Cache: the prepares under way, shared so concurrent requests for the same Source and episode wait on one
 * promise, and the video paths that just failed to serve. What a prepare ends in is kept by the Source memory
 * (`sourceMemory.ts`, #247): ready, or dead for a bad Source; this module keys its prepares the way the memory does.
 */

import type { StreamData } from './types.js';
import type { PlayContext } from './playContext.js';
import { isSourceFailure } from '../backends/types.js';
import { isBadGrab } from '../backends/nzbGrab.js';
import type { WalkLimits } from './walk.js';
import { config as globalConfig } from '../config/index.js';
import { clearFallbackGroups } from './fallbackManager.js';
import { clearDeliveryLog } from './utils.js';
import { remember, recall, keyOf, isRemembered, expireRemembered, forgetEntry, memoryStats, type RememberedSource } from './sourceMemory.js';

export {
  saveCacheToDisk, evictReadyByVideoPath, recalculateTTLExpirations, clearTimeoutEntries, clearReadyCache, forgetDeadSources,
  clearMultiEpisodeDeadEntries, clearTimeoutDeadEntries, getCacheEntries,
} from './sourceMemory.js';

/** A Source as a play prepares it. */
export interface PlaySource extends RememberedSource {
  /** Proxy exit IP captured at search time, checked again when the NZB is grabbed. */
  searchExitIp?: string;
}

/** Prepares under way: in-flight promises that end in the Source memory, ready or dead. */
interface Pending { promise: Promise<StreamData>; expiresAt: number; source: string }
const pendingCache = new Map<string, Pending>();

// ============================================================================
// Broken Video Path Tracking
// ============================================================================
// Video paths whose byte fetch returned 4xx/5xx during streaming.
// Prevents re-serving a path whose content has gone. 60s TTL covers a single user retry session;
// fresh-submission probe success calls clearVideoPathBroken so legitimately
// re-grabbed paths aren't blocked by TTL.

const BROKEN_VIDEO_PATH_TTL_MS = 60_000;
const brokenVideoPaths = new Map<string, number>(); // videoPath → expiresAt

/** Mark a video path as broken (WebDAV 4xx/5xx during streaming or probe). */
export function markVideoPathBroken(videoPath: string): void {
  brokenVideoPaths.set(videoPath, Date.now() + BROKEN_VIDEO_PATH_TTL_MS);
}

/** Check if a video path is currently marked as broken. Auto-evicts expired entries on read. */
export function isVideoPathBroken(videoPath: string): boolean {
  const expiresAt = brokenVideoPaths.get(videoPath);
  if (expiresAt === undefined) return false;
  if (Date.now() >= expiresAt) {
    brokenVideoPaths.delete(videoPath);
    return false;
  }
  return true;
}

/** Drop the broken marker for a path — called after a fresh-submission probe succeeds. */
export function clearVideoPathBroken(videoPath: string): void {
  brokenVideoPaths.delete(videoPath);
}

/** Injected stream preparation function (set by streamHandler to break circular dep) */
type PrepareFn = (source: PlaySource, play: PlayContext | undefined, logPrefix: string, walk?: WalkLimits) => Promise<StreamData>;
let prepareFn: PrepareFn | null = null;

/** The console line that says a Source goes to the Backend now, the same for every prepare (a clicked list entry,
 *  Best). For people reading the log: the brain tools read the `played` and `play_failed` step lines (#242). */
export function logPrepareStart(logPrefix: string, title: string): void {
  console.log(`${logPrefix}\u{1F195} Starting new stream preparation: ${title}`);
}

export function setPrepareFn(fn: PrepareFn): void {
  prepareFn = fn;
}

export function cleanupExpiredCache(): void {
  const now = Date.now();
  for (const [key, entry] of pendingCache.entries()) {
    if (entry.expiresAt < now) pendingCache.delete(key);
  }
  expireRemembered();
  for (const [path, expiresAt] of brokenVideoPaths) {
    if (now >= expiresAt) brokenVideoPaths.delete(path);
  }
}

/** Whether a prepare of this Source for this play is under way. */
export function isPreparing(source: { nzbUrl: string; title: string }, play?: PlayContext): boolean {
  const pending = pendingCache.get(keyOf(source, play));
  return pending !== undefined && pending.expiresAt > Date.now();
}

/**
 * Prepare a Source for a play, sharing a prepare already under way. A Source remembered dead for the play is not
 * prepared (its error is thrown); what the prepare ends in is remembered: ready, or dead when it is a bad Source.
 * `walk`: the limits of the walk the prepare is part of (a clicked list entry's walk-on, #255), for its grab.
 */
export async function getOrCreateStream(
  source: PlaySource,
  play: PlayContext | undefined,
  { verbose = true, logPrefix = '', walk }: { verbose?: boolean; logPrefix?: string; walk?: WalkLimits } = {},
): Promise<StreamData> {
  cleanupExpiredCache();
  const { title } = source;
  const cacheKey = keyOf(source, play);

  // The ready Source is not recalled here: `prepareStream` reuses it only after its first-byte probe passes.
  const { dead } = recall(source, play);
  if (dead) {
    if (verbose) console.log(`${logPrefix}❌ Source memory (dead): ${title} - ${dead.message}`);
    throw dead;
  }

  // Check pending cache — share the in-flight promise
  const pending = pendingCache.get(cacheKey);
  if (pending) {
    if (pending.expiresAt <= Date.now()) {
      if (verbose) console.log(`${logPrefix}⏳ Prepare under way expired, starting again: ${title}`);
      pendingCache.delete(cacheKey);
    } else {
      if (verbose) console.log(`${logPrefix}⏳ Prepare under way, joined: ${title}`);
      return pending.promise;
    }
  }

  if (!prepareFn) throw new Error('Stream cache not initialised: prepareFn not set');

  // Create new preparation task
  if (verbose) logPrepareStart(logPrefix, title);

  const promise = prepareFn(source, play, logPrefix, walk);

  // Set as pending with a TTL — if the promise hangs, the entry expires and
  // subsequent requests can retry instead of hanging forever.  When UF is
  // off (no budget), the promise handlers (.then/.catch) clean up the entry so
  // no TTL-based expiry is needed.
  const ur = globalConfig.ultimateFallback;
  const maxTimeout = ur?.enabled === true
    ? Math.max(
        ur.priorityMoviesTimeoutSeconds, ur.priorityTvTimeoutSeconds, ur.prioritySeasonPackTimeoutSeconds,
        ur.speedMoviesTimeoutSeconds, ur.speedTvTimeoutSeconds, ur.speedSeasonPackTimeoutSeconds,
      )
    : 0;
  const pendingTTLMs = maxTimeout > 0 ? (maxTimeout + 30) * 1000 : Infinity;
  pendingCache.set(cacheKey, { promise, expiresAt: Date.now() + pendingTTLMs, source: keyOf(source) });

  promise.then((data) => {
    pendingCache.delete(cacheKey);
    remember({ source, play, ready: data });
  }).catch((error) => {
    pendingCache.delete(cacheKey);
    // A link the indexer says is gone, or a bad NZB, is the Source's for every episode (GLOSSARY: Source memory).
    if (isSourceFailure(error)) remember({ source, play, dead: error, everyEpisode: isBadGrab(error) });
  });

  return promise;
}

/** Clear fallback state and delivery log */
export function clearStreamCache(): void {
  clearFallbackGroups();
  clearDeliveryLog();
  console.log('\u{1F9F9} Pending entries + fallback groups cleared');
}

/** Delete a single entry by key: a remembered one (ready or dead) or a prepare under way. */
export function deleteCacheEntry(cacheKey: string): boolean {
  return forgetEntry(cacheKey) || pendingCache.delete(cacheKey);
}

/**
 * Whether a Source is prepared, under way or dead, for any episode of it: the grab counting's check, so one NZB grab
 * is counted once even when different episodes of it are played.
 */
export function isStreamCached(nzbUrl: string, title: string): boolean {
  if (isRemembered(nzbUrl, title)) return true;
  const source = keyOf({ nzbUrl, title });
  const now = Date.now();
  for (const entry of pendingCache.values()) {
    if (entry.source === source && entry.expiresAt > now) return true;
  }
  return false;
}

export function getCacheStats(): {
  total: number; ready: number; pending: number; failed: number;
  readySizeMB: number; deadSizeMB: number;
} {
  const { ready, failed, readySizeMB, deadSizeMB } = memoryStats();
  const pending = pendingCache.size;
  return { total: ready + pending + failed, ready, pending, failed, readySizeMB, deadSizeMB };
}
