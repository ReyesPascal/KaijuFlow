/**
 * The Source memory (GLOSSARY: Source memory, #247): the ready and the dead Sources KaijuFlow remembers, behind two
 * operations. `remember(outcome)` keeps what a play learned about a Source (its video is ready, or it is a bad Source,
 * ADR 0004); `recall(Source, play context)` says what is remembered of it for that play. The keys, the URL
 * normalising, a dead mark's scope (the Source's, or one episode's), the TTLs and the storage limit live here, and no
 * caller composes a key: the list entry, the Walk and the prepare all go through these two, so a Source remembered as
 * one play makes it is found again as another asks for it, for every episode, dated or not.
 *
 * Saved to `config/healthy-nzbs.json` (ready) and `config/dead-nzbs.json` (dead), in the layout earlier builds wrote,
 * so a saved memory loads across builds. A dead mark is keyed by the Source (ADR 0004).
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import type { StreamData } from './types.js';
import { BACKEND_ID } from '../backends/types.js';
import { config as globalConfig } from '../config/index.js';
import { episodeOf, type PlayContext } from './playContext.js';
import { pruneIndexerUnavailableMarks, MULTI_EPISODE_BLOCKED_ERROR } from './utils.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const READY_CACHE_FILE = path.join(__dirname, '..', '..', 'config', 'healthy-nzbs.json');
const DEAD_NZB_CACHE_FILE = path.join(__dirname, '..', '..', 'config', 'dead-nzbs.json');

/** A Source as the memory knows it: its link and release name, and what a dead mark records with it. */
export interface RememberedSource {
  nzbUrl: string;
  title: string;
  indexerName?: string;
  /** Video bytes when known, else the indexer's NZB bytes: shown with a dead mark. */
  size?: number;
  isSeasonPack?: boolean;
}

/** What a play learned about a Source. */
export type Outcome =
  /** The Backend made the Source's video for the play's episode and its first byte served. */
  | { source: RememberedSource; play?: PlayContext; ready: StreamData }
  /**
   * A bad Source (ADR 0004). With `everyEpisode` the mark is the Source's whatever is played of it (a link the indexer
   * says is gone, a check that blocked the whole Source). Otherwise it is the play's episode's, unless a season pack
   * fails whole before any episode of it was ever ready: then the pack is marked dead, so its siblings drop out of lists.
   */
  | { source: RememberedSource; play?: PlayContext; dead: Error; everyEpisode?: boolean };

/** What the memory holds for a Source as a play asks for it. */
export interface Recalled {
  /** The video the Backend made for it, for this play's episode. */
  ready?: StreamData;
  /** Why it is a bad Source, for every episode or for this play's. */
  dead?: Error;
}

// ── Keys ──────────────────────────────────────────────────────────────
// Ready: `<url>::<title>`, plus `:<episode pattern>` for an episode. Dead: `<url>`, plus `::<episode pattern>` for a
// mark of one episode. The episode pattern is the play's SxxExx (episodeOf), never the file pattern, which for a dated
// episode also names its aired date (#247: written under one and read under the other, a ready Source was never found).

/** Strip the volatile `link` query param from Prowlarr download URLs (`/{indexerId}/download?apikey=…&link=…`): a
 *  dynamic token that changes every search. Then collapse the `.nzb&` malformation some Newznab indexers emit. */
function normalizeUrl(url: string): string {
  let normalized = url;
  try {
    const parsed = new URL(url);
    if (parsed.pathname.match(/\/\d+\/download\/?$/)) {
      parsed.searchParams.delete('link');
      normalized = parsed.toString();
    }
  } catch { /* not a URL: kept as it is */ }
  return normalized.replace(/\.nzb&/, '.nzb?');
}

const episodePatternOf = (play: PlayContext | undefined): string | undefined => episodeOf(play).episodePattern;
const readyKey = (nzbUrl: string, title: string, episodePattern?: string): string =>
  `${normalizeUrl(nzbUrl)}::${title}` + (episodePattern ? `:${episodePattern}` : '');
const deadKey = (nzbUrl: string, episodePattern?: string): string =>
  episodePattern ? `${normalizeUrl(nzbUrl)}::${episodePattern}` : normalizeUrl(nzbUrl);

/** A Source as a play asks for it, as one string: what the in-flight prepares and the Stremio dedup are keyed by,
 *  so they name a Source the way the memory does. */
export function keyOf(source: { nzbUrl: string; title: string }, play?: PlayContext): string {
  return readyKey(source.nzbUrl, source.title, episodePatternOf(play));
}

/** Matches the trailing episode-pattern suffix on a ready key: the SxxExx forms (":S04E08", ":S04[. _-]?E08",
 *  the multi-episode regex) and the chain-aware ":(?:…|date)" form. The latter contains literal colons from `(?:`
 *  groups, so it anchors on the suffix's start (`:(?:` or `:S\d\d` and a separator), not `:S\d\d` alone. */
const EPISODE_PATTERN_SUFFIX_RE = /:(?:\(\?:|S\d{2}(?:[. _\-\[(]|E\d))[\s\S]*$/;

/** The release name in a ready key. */
function titleOfKey(key: string): string {
  const separatorIdx = key.indexOf('::');
  if (separatorIdx === -1) return key;
  return key.substring(separatorIdx + 2).replace(EPISODE_PATTERN_SUFFIX_RE, '');
}

// ── State ─────────────────────────────────────────────────────────────

interface ReadyEntry { data: StreamData; indexerName?: string; createdAt: number; expiresAt: number; backend?: string }
interface DeadNzbEntry { title: string; indexerName?: string; size?: number; error: Error; createdAt: number; expiresAt: number }
const readyCache = new Map<string, ReadyEntry>();
const deadNzbCache = new Map<string, DeadNzbEntry>();

/** Ready entries only count when AltMount made them: saved entries another Backend made (#188), and untagged ones
 *  from before Backends existed, are never served (a stale link). */
const isActiveBackendEntry = (e: ReadyEntry): boolean => e.backend === BACKEND_ID;
const isTimeoutMark = (e: DeadNzbEntry): boolean => (e.error as { isTimeout?: boolean }).isTimeout === true;
const isEpisodeMark = (e: DeadNzbEntry): boolean => (e.error as { isEpisodeSpecific?: boolean }).isEpisodeSpecific === true;
/** A timed-out mark is kept only for this run when the owner turned off remembering timeouts. */
const hiddenTimeout = (e: DeadNzbEntry): boolean => isTimeoutMark(e) && globalConfig.playCacheTimeouts === false;

// ── TTLs and the storage limit ────────────────────────────────────────

/** In 'storage' mode entries never expire by time; the storage limit bounds them instead. */
export function getReadyTTLMs(): number {
  if (globalConfig.healthyNzbDbMode === 'storage') return Infinity;
  return (globalConfig.healthyNzbDbTTL ?? 259200) * 1000;
}
export function getDeadTTLMs(): number {
  if (globalConfig.deadNzbDbMode === 'storage') return Infinity;
  return (globalConfig.deadNzbDbTTL ?? 86400) * 1000;
}

function readySize(): number {
  let total = 0;
  for (const [key, value] of readyCache.entries()) total += key.length + JSON.stringify(value).length;
  return total;
}
/** Error properties are non-enumerable, so a dead entry is sized by its fields. */
function deadSize(): number {
  let total = 0;
  for (const [key, entry] of deadNzbCache.entries()) {
    total += key.length + (entry.title?.length ?? 0) + (entry.indexerName?.length ?? 0) + (entry.error.message?.length ?? 0) + 50;
  }
  return total;
}

/** FIFO-evict the oldest entries until the cache is under the given MB limit. */
function enforceStorageLimit(cache: Map<string, unknown>, sizeFn: () => number, maxMB: number): void {
  const maxBytes = maxMB * 1024 * 1024;
  while (sizeFn() > maxBytes && cache.size > 0) {
    const firstKey = cache.keys().next().value;
    if (firstKey !== undefined) cache.delete(firstKey);
    else break;
  }
}
const limitReady = () => {
  if (globalConfig.healthyNzbDbMode === 'storage') enforceStorageLimit(readyCache, readySize, globalConfig.healthyNzbDbMaxSizeMB ?? 50);
};
const limitDead = () => {
  if (globalConfig.deadNzbDbMode === 'storage') enforceStorageLimit(deadNzbCache, deadSize, globalConfig.deadNzbDbMaxSizeMB ?? 50);
};

// ── Disk ──────────────────────────────────────────────────────────────

interface SerializedDeadEntry {
  title?: string;
  indexerName?: string;
  size?: number;
  // isNzbdavFailure: the flag's name in dead marks saved before #200; read on load, never written.
  error: { message: string; isBadSource?: boolean; isNzbdavFailure?: boolean; isTimeout?: boolean; isEpisodeSpecific?: boolean };
  createdAt?: number;
  expiresAt: number;
}

/** A saved key with its URL part normalised as the keys are now. */
function normalizeSavedKey(key: string): string {
  const sepIdx = key.indexOf('::');
  return sepIdx === -1 ? normalizeUrl(key) : `${normalizeUrl(key.substring(0, sepIdx))}::${key.substring(sepIdx + 2)}`;
}

function loadFromDisk(): void {
  const now = Date.now();
  try {
    const raw = JSON.parse(fs.readFileSync(READY_CACHE_FILE, 'utf-8')) as Record<string, ReadyEntry>;
    for (const [key, entry] of Object.entries(raw)) {
      const expiresAt = entry.expiresAt || Infinity;
      if (expiresAt > now) readyCache.set(normalizeSavedKey(key), { ...entry, createdAt: entry.createdAt || now, expiresAt });
    }
    if (readyCache.size) console.log(`💾 Loaded ${readyCache.size} ready streams from disk`);
  } catch {}
  try {
    const stored = JSON.parse(fs.readFileSync(DEAD_NZB_CACHE_FILE, 'utf-8')) as Record<string, SerializedDeadEntry>;
    const { kept: raw, dropped } = pruneIndexerUnavailableMarks(stored);
    for (const [key, entry] of Object.entries(raw)) {
      const expiresAt = entry.expiresAt || Infinity;
      if (expiresAt <= now) continue;
      const error = new Error(entry.error.message);
      (error as any).isBadSource = entry.error.isBadSource ?? entry.error.isNzbdavFailure ?? false;
      (error as any).isTimeout = entry.error.isTimeout ?? false;
      // Writers before the episode scope stored episode-keyed marks with isEpisodeSpecific=false, which made them
      // bans of the whole Source: any of the stored flag, the key's shape or the old multi-episode message makes a
      // mark the episode's. `||` is required: ?? would stop at the false boolean.
      (error as any).isEpisodeSpecific = entry.error.isEpisodeSpecific === true || key.includes('::') || entry.error.message === MULTI_EPISODE_BLOCKED_ERROR;
      if (entry.title) {
        // Key is url or url::episodePattern, the title in the entry.
        deadNzbCache.set(normalizeSavedKey(key), { title: entry.title, indexerName: entry.indexerName, size: entry.size, error, createdAt: entry.createdAt || now, expiresAt });
      } else {
        // Oldest layout: key is url::title or url::title:episodePattern.
        const title = titleOfKey(key);
        const url = key.substring(0, key.indexOf('::'));
        const afterSep = key.substring(key.indexOf('::') + 2);
        const epMatch = afterSep.match(/:S\d+(?:[\[(. _-]|E\d)/);
        const episodePattern = epMatch ? afterSep.substring(epMatch.index! + 1) : undefined;
        deadNzbCache.set(deadKey(url, episodePattern), { title, indexerName: entry.indexerName, size: entry.size, error, createdAt: entry.createdAt || now, expiresAt });
      }
    }
    if (deadNzbCache.size) console.log(`💾 Loaded ${deadNzbCache.size} dead NZBs from disk`);
    if (dropped.length) {
      console.log(`🧹 Dropped ${dropped.length} dead mark(s) caused by an unavailable indexer, not a bad Source (ADR 0004)`);
      saveCacheToDisk();
    }
  } catch {}
}

export function saveCacheToDisk(): void {
  const now = Date.now();
  const readyData: Record<string, ReadyEntry> = {};
  for (const [key, entry] of readyCache.entries()) {
    if (entry.expiresAt > now) readyData[key] = { ...entry, expiresAt: Number.isFinite(entry.expiresAt) ? entry.expiresAt : 0 };
  }
  try { fs.writeFileSync(READY_CACHE_FILE, JSON.stringify(readyData, null, 2)); } catch {}

  const deadData: Record<string, SerializedDeadEntry> = {};
  for (const [key, entry] of deadNzbCache.entries()) {
    if (entry.expiresAt <= now || hiddenTimeout(entry)) continue;
    deadData[key] = {
      title: entry.title,
      indexerName: entry.indexerName,
      size: entry.size,
      error: {
        message: entry.error.message,
        isBadSource: (entry.error as any).isBadSource ?? false,
        isTimeout: (entry.error as any).isTimeout ?? false,
        isEpisodeSpecific: (entry.error as any).isEpisodeSpecific ?? false,
      },
      createdAt: entry.createdAt,
      expiresAt: Number.isFinite(entry.expiresAt) ? entry.expiresAt : 0,
    };
  }
  try { fs.writeFileSync(DEAD_NZB_CACHE_FILE, JSON.stringify(deadData, null, 2)); } catch {}
}

// ── remember / recall ─────────────────────────────────────────────────

/** Whether a season pack failing now fails whole: no episode of it was ever ready. */
function packNeverReady(nzbUrl: string, isSeasonPack?: boolean): boolean {
  if (!isSeasonPack) return false;
  const normalized = normalizeUrl(nzbUrl);
  for (const key of readyCache.keys()) {
    const sepIdx = key.indexOf('::');
    if (sepIdx !== -1 && key.substring(0, sepIdx) === normalized) return false;
  }
  return true;
}

function setDead(key: string, source: RememberedSource, error: Error): void {
  const createdAt = Date.now();
  // A timed-out play is remembered for this run only (the search cache's TTL) when the owner turned that off.
  const persist = !(error as { isTimeout?: boolean }).isTimeout || globalConfig.playCacheTimeouts !== false;
  const ttl = persist ? getDeadTTLMs() : (globalConfig.cacheTTL || 7200) * 1000;
  deadNzbCache.set(key, { title: source.title, indexerName: source.indexerName, size: source.size, error, createdAt, expiresAt: createdAt + ttl });
  if (!persist) return;
  limitDead();
  saveCacheToDisk();
}

/** Keep what a play learned about a Source. */
export function remember(outcome: Outcome): void {
  const { source, play } = outcome;
  const episodePattern = episodePatternOf(play);
  if ('ready' in outcome) {
    const createdAt = Date.now();
    readyCache.set(readyKey(source.nzbUrl, source.title, episodePattern),
      { data: outcome.ready, indexerName: source.indexerName, createdAt, expiresAt: createdAt + getReadyTTLMs(), backend: BACKEND_ID });
    limitReady();
    saveCacheToDisk();
    return;
  }
  const error = outcome.dead as Error & { isEpisodeSpecific?: boolean };
  const whole = outcome.everyEpisode === true
    || (error.isEpisodeSpecific !== true && packNeverReady(source.nzbUrl, source.isSeasonPack));
  if (!whole && episodePattern) error.isEpisodeSpecific = true; // the mark is this episode's (recall honours it)
  setDead(whole ? deadKey(source.nzbUrl) : deadKey(source.nzbUrl, episodePattern), source, error);
}

/** A live dead mark of the Source for every episode: its bare-URL mark, or a mark under an episode key that is not
 *  the episode's (a pack that failed whole). */
function deadForEveryEpisode(nzbUrl: string, now: number): DeadNzbEntry | undefined {
  const normalized = normalizeUrl(nzbUrl);
  const exact = deadNzbCache.get(normalized);
  if (exact && exact.expiresAt > now) return exact;
  for (const [key, entry] of deadNzbCache) {
    if (entry.expiresAt <= now || isEpisodeMark(entry)) continue;
    const sepIdx = key.indexOf('::');
    if (sepIdx !== -1 && normalizeUrl(key.substring(0, sepIdx)) === normalized) return entry;
  }
  return undefined;
}

/** What is remembered of a Source as a play asks for it. */
export function recall(source: { nzbUrl: string; title: string }, play?: PlayContext): Recalled {
  const now = Date.now();
  const episodePattern = episodePatternOf(play);
  const ready = readyCache.get(readyKey(source.nzbUrl, source.title, episodePattern));
  const episodeMark = episodePattern ? deadNzbCache.get(deadKey(source.nzbUrl, episodePattern)) : undefined;
  const dead = (episodeMark && episodeMark.expiresAt > now ? episodeMark : undefined) ?? deadForEveryEpisode(source.nzbUrl, now);
  return {
    ...(ready && ready.expiresAt > now && isActiveBackendEntry(ready) ? { ready: ready.data } : {}),
    ...(dead ? { dead: dead.error } : {}),
  };
}

/** Whether anything is remembered of a Source for any episode (ready, or dead for every episode): the coarse check
 *  the grab counting uses, so one Source is counted once whatever episode is played of it. */
export function isRemembered(nzbUrl: string, title: string): boolean {
  const base = readyKey(nzbUrl, title);
  const now = Date.now();
  for (const [key, entry] of readyCache.entries()) {
    if ((key === base || key.startsWith(base + ':')) && entry.expiresAt > now && isActiveBackendEntry(entry)) return true;
  }
  const dead = deadNzbCache.get(normalizeUrl(nzbUrl));
  return dead !== undefined && dead.expiresAt > now;
}

/**
 * Forget the ready Source whose video is at `videoPath` (the Backend no longer serves it). With `markDead` (a 404:
 * the video is gone) it is also remembered dead, for its episode only, so the rest of a season pack still plays; a
 * passing error (5xx) only forgets it. Returns the forgotten entry's key, or null.
 */
export function evictReadyByVideoPath(videoPath: string, markDead: boolean = true): string | null {
  for (const [key, entry] of readyCache.entries()) {
    if (entry.data.videoPath !== videoPath) continue;
    readyCache.delete(key);
    const sepIdx = key.indexOf('::');
    if (markDead && sepIdx !== -1) {
      const nzbUrl = key.substring(0, sepIdx);
      const epMatch = key.match(EPISODE_PATTERN_SUFFIX_RE);
      const episodePattern = epMatch ? epMatch[0].substring(1) : undefined;
      const mark = deadKey(nzbUrl, episodePattern);
      if (!deadNzbCache.has(mark)) {
        const error = new Error('Video file no longer available (404)');
        (error as any).isBadSource = true;
        if (episodePattern) (error as any).isEpisodeSpecific = true;
        setDead(mark, { nzbUrl, title: titleOfKey(key), indexerName: entry.indexerName, size: entry.data.videoSize }, error);
      }
    }
    saveCacheToDisk();
    return key;
  }
  return null;
}

// ── Upkeep and the settings page ──────────────────────────────────────

/** Drop expired entries (saved again when any went). */
export function expireRemembered(): void {
  const now = Date.now();
  let removed = false;
  for (const [key, entry] of readyCache.entries()) if (entry.expiresAt < now) { readyCache.delete(key); removed = true; }
  for (const [key, entry] of deadNzbCache.entries()) if (entry.expiresAt < now) { deadNzbCache.delete(key); removed = true; }
  if (removed) saveCacheToDisk();
}

/** Give every entry the current TTL from now and apply the storage limit: called when a TTL or mode setting changes. */
export function recalculateTTLExpirations(): void {
  const now = Date.now();
  const readyTTL = getReadyTTLMs();
  for (const entry of readyCache.values()) { entry.createdAt = now; entry.expiresAt = now + readyTTL; }
  const deadTTL = getDeadTTLMs();
  for (const entry of deadNzbCache.values()) { entry.createdAt = now; entry.expiresAt = now + deadTTL; }
  expireRemembered();
  limitReady();
  limitDead();
  saveCacheToDisk();
}

/** Clear timed-out marks from memory only (a new search may find them playable). */
export function clearTimeoutEntries(): void {
  for (const [key, entry] of deadNzbCache) if (isTimeoutMark(entry)) deadNzbCache.delete(key);
}

function clearDeadWhere(pick: (e: DeadNzbEntry) => boolean, what: string): number {
  let count = 0;
  for (const [key, entry] of deadNzbCache) if (pick(entry)) { deadNzbCache.delete(key); count++; }
  if (count) {
    console.log(`\u{1F9F9} Cleared ${count} ${what}`);
    saveCacheToDisk();
  }
  return count;
}

export function clearReadyCache(): number {
  const count = readyCache.size;
  readyCache.clear();
  if (count) {
    console.log(`\u{1F9F9} Cleared ${count} successful stream cache entries`);
    saveCacheToDisk();
  }
  return count;
}
export const clearFailedCache = (): number => clearDeadWhere(() => true, 'dead NZB cache entries');
/** Marks of an episode only available in a combined multi-episode file. */
export const clearMultiEpisodeDeadEntries = (): number => clearDeadWhere(e => e.error.message === MULTI_EPISODE_BLOCKED_ERROR, 'multi-episode dead NZB entries');
export const clearTimeoutDeadEntries = (): number => clearDeadWhere(isTimeoutMark, 'timed-out dead NZB entries');

/** Forget one entry by the key the settings page shows. */
export function forgetEntry(key: string): boolean {
  const deleted = readyCache.delete(key) || deadNzbCache.delete(key);
  if (deleted) saveCacheToDisk();
  return deleted;
}

/** The entries, for the settings page. */
export function getCacheEntries(): {
  ready: { key: string; title: string; indexerName?: string; videoPath: string; videoSize: number; createdAt: number; expiresAt: number }[];
  failed: { key: string; title: string; indexerName?: string; size?: number; error: string; episodePattern?: string; createdAt: number; expiresAt: number }[];
} {
  const now = Date.now();
  const ready = [];
  for (const [key, entry] of readyCache.entries()) {
    if (entry.expiresAt < now || !isActiveBackendEntry(entry)) continue;
    ready.push({ key, title: titleOfKey(key), indexerName: entry.indexerName, videoPath: entry.data.videoPath, videoSize: entry.data.videoSize, createdAt: entry.createdAt, expiresAt: entry.expiresAt });
  }
  const failed = [];
  for (const [key, entry] of deadNzbCache.entries()) {
    if (entry.expiresAt < now || hiddenTimeout(entry)) continue;
    const sepIdx = key.indexOf('::');
    let episodePattern: string | undefined;
    if (sepIdx !== -1 && isEpisodeMark(entry)) {
      const raw = key.substring(sepIdx + 2);
      const m = raw.match(/S(\d+).*?E(\d+)/);
      episodePattern = m ? `S${m[1]}E${m[2]}` : raw;
    }
    failed.push({ key, title: entry.title, indexerName: entry.indexerName, size: entry.size, error: entry.error.message, episodePattern, createdAt: entry.createdAt, expiresAt: entry.expiresAt });
  }
  return { ready, failed };
}

/** Counts and sizes, for the settings page. */
export function memoryStats(): { ready: number; failed: number; readySizeMB: number; deadSizeMB: number } {
  const now = Date.now();
  let ready = 0;
  for (const entry of readyCache.values()) if (entry.expiresAt > now && isActiveBackendEntry(entry)) ready++;
  let failed = 0;
  for (const entry of deadNzbCache.values()) if (entry.expiresAt > now && !hiddenTimeout(entry)) failed++;
  const mb = (bytes: number) => Math.round(bytes / 1024 / 1024 * 100) / 100;
  return { ready, failed, readySizeMB: mb(readySize()), deadSizeMB: mb(deadSize()) };
}

loadFromDisk();
recalculateTTLExpirations();
