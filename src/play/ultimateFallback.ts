/**
 * Ultimate-Fallback
 *
 * Combines retry-on-failure with Health Checking for the fastest possible
 * NZB resolution. Runs four parallel layers simultaneously:
 *   1. Already-prepared pre-check (the Backend's findPrepared — no NZB download needed)
 *   2. Grab chain (NZB download from indexers)
 *   3. Health checks (NNTP article verification, streams per-candidate as grabs complete)
 *   4. Hand-off to the Backend (prepare, probe; cancel on a failed health check)
 * Runs only when the Backend has the ultimateFallback capability (AltMount: since #190). It is the Play-time
 * check's engine (playTimeCheck.ts): it hands the Backend only a Source its check found healthy, the first in
 * list order, checking candidateCount Sources at a time from the top down.
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { config as globalConfig } from '../config/index.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
import { NntpConnectionPool, setHealthCheckConnectionCap, DEFAULT_HEALTH_CHECK_CONNECTION_CAP } from '../health/nntpConnection.js';
import type { HealthCheckResult } from '../health/types.js';
import { isDeadNzbByUrl, getCacheKey, setReadyCacheEntry, setDeadNzbEntry, addDeadNzbByUrl, saveCacheToDisk, logPrepareStart } from './streamCache.js';
import { prefetchNzb } from '../backends/nzbGrab.js';
import { getActiveBackend, PrepareCancelledError } from '../backends/index.js';
import { selectTimeoutMs, formatTimeoutSeconds, type TimeoutSet } from './timeoutDefaults.js';
import type { FallbackCandidate, StreamData } from './types.js';
import type { UltimateFallbackConfig } from '../types.js';
import { formatBytes } from '../parsers/metadataParsers.js';
import { checkSource, isHealthy, enabledHealthCheckProviders } from './playTimeCheck.js';

// ── Types ────────────────────────────────────────────────────────────

type LibraryHit = { candidate: FallbackCandidate; index: number; data: StreamData };

interface CandidateState {
  candidate: FallbackCandidate;
  poolIndex: number;
  healthStatus: 'pending' | 'checking' | 'healthy' | 'dead' | 'error';
  grabStatus: 'pending' | 'grabbing' | 'done' | 'failed';
  healthPromise?: Promise<{ cs: CandidateState; result: HealthCheckResult }>;
  grabPromise?: Promise<{ cs: CandidateState; ok: boolean }>;
  prepareStatus: 'idle' | 'submitted' | 'completed' | 'failed' | 'skipped';
  nzoId?: string;
  cancelled?: boolean;
  containerType?: string;     // Video container (e.g. 'MKV') — from health check or library hit
  videoSize?: number;         // File size in bytes — known once primary/backup is resolved
  containerFallbackViaPrepare?: boolean; // submitted without pre-resolved container; derive from videoPath post-resolve
  duplicate?: boolean;         // Resolved to same videoPath as another candidate
  duplicateOf?: number;        // poolIndex of the original candidate this duplicates
  replaced?: boolean;          // Replacement already pulled for this dead candidate
  prepareDeadWritten?: boolean; // setDeadNzbEntry already wrote a specific Backend-failure entry — don't shadow it with a generic URL-only one at end-of-pipeline
  grabFailed?: boolean;        // Grab never produced an NZB (indexer/network/VPN transient) — don't persist to dead NZB DB
  backendFailed?: boolean;     // Prepare failed for a reason that is not the Source's (Backend unreachable, ADR 0004) — don't persist to dead NZB DB
  libraryHitDeferred?: LibraryHit; // Priority mode: library hit waiting for an earlier in-flight candidate to terminate
}

interface UltimateFallbackOptions {
  candidateCount: number;
  /** Picks the wait times only: Best hands over the first healthy Source in list order whatever it says (#190). */
  preferenceMode: 'priority' | 'speed';
  desiredBackups: number;
  backupProcessingLimit: number;
  priorityMoviesTimeoutSeconds: number;
  priorityTvTimeoutSeconds: number;
  prioritySeasonPackTimeoutSeconds: number;
  speedMoviesTimeoutSeconds: number;
  speedTvTimeoutSeconds: number;
  speedSeasonPackTimeoutSeconds: number;
  healthCheckIndexers?: Record<string, boolean>;
}

// ── Active session tracking ─────────────────────────────────────────

const activeSessions = new Map<string, AbortController>();

// UF-vetted backup metadata for in-session serving (no TTL coupling with fallback groups).
export interface UfBackupStream {
  nzbUrl: string;
  videoPath: string;
  title: string;
  indexerName: string;
  candidateIndex?: number; // 1-based position from the original ranking — surfaces in midstream-fallback log
}

// Session promises — lobby awaits these to get the resolved stream
interface DeferredStream {
  promise: Promise<StreamData>;
  resolve: (data: StreamData) => void;
  reject: (err: Error) => void;
  backupUrls?: Set<string>;   // NZB URLs of verified backups (for fallback loop prioritization)
  backupStreams?: UfBackupStream[]; // Parallel array with videoPaths — UF tile serves these directly when primary breaks
  lastVettedUrl?: string;      // Last NZB URL pulled into pool (for sequential resume point)
  resolvedData?: StreamData;   // Set on resolve so disk persistence can read settled state
  expiresAt?: number;          // Set on resolve; matches the in-memory cleanup timer
}
const sessionPromises = new Map<string, DeferredStream>();
const cleanupTimers = new Map<string, ReturnType<typeof setTimeout>>();

// Resolved sessions outlive the addon process via disk persistence so that
// a player reconnecting to /stream/ultimate-fallback?t=<envelope-with-sk>
// after an addon restart still finds its session and gets a 302 to
// /v?path=…. Mirrors the pattern in streamCache.ts (loadCacheFromDisk /
// saveCacheToDisk).
const SESSION_TTL_MS = 2 * 60 * 60 * 1000 + 30_000;
const UF_SESSIONS_FILE = path.join(__dirname, '..', '..', 'config', 'uf-sessions.json');
const UF_SESSIONS_SCHEMA_VERSION = 1;

interface SerializedSession {
  version: number;
  sessionKey: string;
  streamData: StreamData;
  backupStreams: UfBackupStream[];
  backupUrls: string[];
  lastVettedUrl?: string;
  expiresAt: number;
}

function loadSessionsFromDisk(): void {
  const now = Date.now();
  try {
    const raw = JSON.parse(fs.readFileSync(UF_SESSIONS_FILE, 'utf-8')) as SerializedSession[];
    for (const entry of raw) {
      if (entry.version !== UF_SESSIONS_SCHEMA_VERSION) {
        console.warn(`⚠️  Discarding UF session (schema v${entry.version} != v${UF_SESSIONS_SCHEMA_VERSION})`);
        continue;
      }
      if (entry.expiresAt > now) {
        const promise = Promise.resolve(entry.streamData);
        promise.catch(() => {});
        const deferred: DeferredStream = {
          promise,
          resolve: () => {},
          reject: () => {},
          backupUrls: new Set(entry.backupUrls ?? []),
          backupStreams: entry.backupStreams ?? [],
          lastVettedUrl: entry.lastVettedUrl,
          resolvedData: entry.streamData,
          expiresAt: entry.expiresAt,
        };
        sessionPromises.set(entry.sessionKey, deferred);
        const ms = entry.expiresAt - now;
        cleanupTimers.set(entry.sessionKey, setTimeout(() => {
          sessionPromises.delete(entry.sessionKey);
          cleanupTimers.delete(entry.sessionKey);
          saveSessionsToDisk();
        }, ms));
      }
    }
    if (sessionPromises.size) console.log(`💾 Loaded ${sessionPromises.size} UF session(s) from disk`);
  } catch {}
}

function saveSessionsToDisk(): void {
  const data: SerializedSession[] = [];
  const now = Date.now();
  for (const [key, d] of sessionPromises) {
    if (d.resolvedData && d.expiresAt && d.expiresAt > now) {
      data.push({
        version: UF_SESSIONS_SCHEMA_VERSION,
        sessionKey: key,
        streamData: d.resolvedData,
        backupStreams: d.backupStreams ?? [],
        backupUrls: [...(d.backupUrls ?? [])],
        lastVettedUrl: d.lastVettedUrl,
        expiresAt: d.expiresAt,
      });
    }
  }
  try { fs.writeFileSync(UF_SESSIONS_FILE, JSON.stringify(data, null, 2)); } catch {}
}

loadSessionsFromDisk();

/** Get the session promise for a session key (used by stream handler lobby). */
export function getSessionPromise(sessionKey: string): Promise<StreamData> | null {
  return sessionPromises.get(sessionKey)?.promise ?? null;
}

/** Get backup URLs, vetted streams, and last vetted URL for a session key. Used by the
 *  fallback loop (backupUrls prioritization) and the UF tile gate (backupStreams direct serve). */
export function getSessionBackups(sessionKey: string): { backupUrls: Set<string>; backupStreams: UfBackupStream[]; lastVettedUrl?: string } | null {
  const deferred = sessionPromises.get(sessionKey);
  if (!deferred?.backupUrls?.size && !deferred?.backupStreams?.length) return null;
  return {
    backupUrls: deferred.backupUrls ?? new Set<string>(),
    backupStreams: deferred.backupStreams ?? [],
    lastVettedUrl: deferred.lastVettedUrl,
  };
}

/** Check if any Ultimate-Fallback sessions are active. */
export function hasAnySessions(): boolean {
  return activeSessions.size > 0;
}

/** Drop all resolved (non-in-flight) sessions. Wired into clearSearchCache so
 *  "start fresh" honors user intent — cached resolutions disappear with the
 *  underlying searches. In-flight sessions are skipped so someone currently
 *  mid-playback finishes their resolution. */
export function clearResolvedSessions(): void {
  let cleared = 0;
  for (const sessionKey of [...sessionPromises.keys()]) {
    if (activeSessions.has(sessionKey)) continue;
    const timer = cleanupTimers.get(sessionKey);
    if (timer) {
      clearTimeout(timer);
      cleanupTimers.delete(sessionKey);
    }
    sessionPromises.delete(sessionKey);
    cleared++;
  }
  if (cleared > 0) {
    console.log(`🧹 Cleared ${cleared} resolved UF session(s)`);
    saveSessionsToDisk();
  }
}

/** Cancel all running Ultimate-Fallback sessions (called on settings change). */
export function cancelAllUltimateFallbacks(): void {
  const activeCount = activeSessions.size;
  if (activeCount > 0) {
    console.warn(`👑 Cancelling ${activeCount} active Ultimate-Fallback session(s)`);
  }
  for (const [, controller] of activeSessions) {
    controller.abort();
  }
  activeSessions.clear();
  for (const [, timer] of cleanupTimers) {
    clearTimeout(timer);
  }
  cleanupTimers.clear();
  // Reject pending deferreds so awaiting lobbies wake. DO NOT delete from
  // sessionPromises — resolved entries are cached primary streams; deleting
  // them severs in-flight playback for clients still polling the lobby URL.
  // The per-session cleanup setTimeout in ultimateFallbackFromCandidates is
  // the sole deletion path. Rejecting an already-resolved promise is a no-op.
  for (const [, deferred] of sessionPromises) {
    deferred.reject(new Error('Ultimate-Fallback cancelled'));
  }
}

// ── Head start (#206) ───────────────────────────────────────────────

/** Sessions a press of Best is waiting on: a newer list request never stops them. Emptied as each session ends. */
const claimedSessions = new Set<string>();
/** The title of the newest list request's Head start, until a press of Best claims it. */
let headStartKey: string | null = null;

/**
 * Head start (GLOSSARY): a title's stream list was asked for, so Best's check and prepare begin now in the
 * background. Only the newest list request has one: the one before is stopped unless a press of Best is waiting
 * on it. A title whose Best already runs or is done keeps that session (a press joins it).
 */
export function headStart(
  sessionKey: string,
  candidates: FallbackCandidate[],
  options: UltimateFallbackOptions,
  cachePattern?: string,
  filePattern?: string,
  contentType?: string,
  episodesInSeason?: number,
): void {
  const before = headStartKey;
  headStartKey = sessionKey;
  if (before && before !== sessionKey && !claimedSessions.has(before)) {
    const controller = activeSessions.get(before);
    if (controller) {
      console.log(`👑 Ultimate-Fallback [${before}] Head start stopped: a newer list request [${sessionKey}] has it`);
      controller.abort();
    }
  }
  if (candidates.length === 0 || sessionPromises.has(sessionKey)) return;
  console.log(`👑 Ultimate-Fallback [${sessionKey}] Head start: checking Best's Sources before a press`);
  ultimateFallbackFromCandidates(sessionKey, candidates, options, cachePattern, filePattern, contentType, episodesInSeason)
    .catch(err => console.error('❌ Ultimate-Fallback error (Head start):', err));
}

/** A press of Best waits on this title's session: from now on it is a play, which no newer list request stops. */
export function claimSession(sessionKey: string): void {
  if (!activeSessions.has(sessionKey) || claimedSessions.has(sessionKey)) return;
  console.log(`👑 Ultimate-Fallback [${sessionKey}] Best pressed: a play now, no newer list request stops it`);
  claimedSessions.add(sessionKey);
  if (headStartKey === sessionKey) headStartKey = null;
}

// ── Helpers ──────────────────────────────────────────────────────────

/** Limit concurrency for a batch of async tasks. */
async function runWithConcurrency<T>(tasks: (() => Promise<T>)[], limit: number): Promise<T[]> {
  const results: T[] = [];
  const running = new Set<Promise<void>>();
  for (const task of tasks) {
    const p = task().then(r => { results.push(r); });
    running.add(p);
    p.finally(() => running.delete(p));
    if (running.size >= limit) await Promise.race(running);
  }
  await Promise.all(running);
  return results;
}

// ── Main pipeline ────────────────────────────────────────────────────

/** The engine's options from the Ultimate Fallback settings (both ways in: on search results, on a press of Best). */
export function ultimateFallbackOptions(ur: UltimateFallbackConfig): UltimateFallbackOptions {
  return {
    candidateCount: ur.candidateCount, preferenceMode: ur.preferenceMode, desiredBackups: ur.desiredBackups,
    backupProcessingLimit: ur.backupProcessingLimit, priorityMoviesTimeoutSeconds: ur.priorityMoviesTimeoutSeconds,
    priorityTvTimeoutSeconds: ur.priorityTvTimeoutSeconds, prioritySeasonPackTimeoutSeconds: ur.prioritySeasonPackTimeoutSeconds,
    speedMoviesTimeoutSeconds: ur.speedMoviesTimeoutSeconds, speedTvTimeoutSeconds: ur.speedTvTimeoutSeconds,
    speedSeasonPackTimeoutSeconds: ur.speedSeasonPackTimeoutSeconds, healthCheckIndexers: ur.healthCheckIndexers,
  };
}

export async function ultimateFallbackFromCandidates(
  sessionKey: string,
  candidates: FallbackCandidate[],
  options: UltimateFallbackOptions,
  cachePattern?: string,
  filePattern?: string,
  contentType?: string,
  episodesInSeason?: number,
): Promise<void> {
  if (activeSessions.has(sessionKey)) return;

  const controller = new AbortController();
  activeSessions.set(sessionKey, controller);
  const backend = getActiveBackend();

  // Create deferred promise — lobby awaits this to get the resolved stream
  let sessionResolveRaw!: (data: StreamData) => void;
  let sessionReject!: (err: Error) => void;
  const sessionPromise = new Promise<StreamData>((res, rej) => { sessionResolveRaw = res; sessionReject = rej; });
  sessionPromise.catch(() => {});
  const deferred: DeferredStream = { promise: sessionPromise, resolve: sessionResolveRaw, reject: sessionReject, backupUrls: new Set(), backupStreams: [] };
  // Wrap resolve to stamp the persistable fields and write to disk so the
  // session survives an addon restart.
  // The played Source's release name rides along, so a press can name what it plays (brain tools' played_source).
  const sessionResolve = (video: StreamData, sourceTitle: string) => {
    const data = { ...video, sourceTitle };
    deferred.resolvedData = data;
    deferred.expiresAt = Date.now() + SESSION_TTL_MS;
    sessionResolveRaw(data);
    saveSessionsToDisk();
  };
  deferred.resolve = data => sessionResolve(data, data.sourceTitle ?? '');
  sessionPromises.set(sessionKey, deferred);

  const tag = `👑 Ultimate-Fallback [${sessionKey}]`;
  // The Play-time check: every Source is checked before the Backend gets it, whatever the
  // health-check switches say (GLOSSARY: Unchecked Source). With no enabled provider every
  // check answers an error, so nothing is handed over and the play shows the failure video.
  const providers = enabledHealthCheckProviders();
  if (providers.length > 0) setHealthCheckConnectionCap(globalConfig.healthChecks?.maxTotalConnections ?? DEFAULT_HEALTH_CHECK_CONNECTION_CAP);
  const pool = providers.length > 0 ? new NntpConnectionPool() : undefined;

  try {
    // Filter out opted-out indexers
    let eligible = candidates;
    if (options.healthCheckIndexers) {
      const indexerMap = options.healthCheckIndexers;
      eligible = candidates.filter(c => indexerMap[c.indexerName] !== false);
    }

    const allCandidates = eligible;

    if (allCandidates.length === 0) {
      console.log(`${tag} No eligible candidates`);
      return;
    }

    const pipelineStart = Date.now();
    const activeSet: TimeoutSet = options.preferenceMode === 'priority'
      ? { movies: options.priorityMoviesTimeoutSeconds, tv: options.priorityTvTimeoutSeconds, seasonPack: options.prioritySeasonPackTimeoutSeconds }
      : { movies: options.speedMoviesTimeoutSeconds, tv: options.speedTvTimeoutSeconds, seasonPack: options.speedSeasonPackTimeoutSeconds };
    console.log(`${tag} Starting — ${allCandidates.length} candidate(s), pool size ${options.candidateCount}, list order, wait times: ${options.preferenceMode} (movies=${formatTimeoutSeconds(activeSet.movies)}, tv=${formatTimeoutSeconds(activeSet.tv)}, pack=${formatTimeoutSeconds(activeSet.seasonPack)})`);

    // ── Stage 1: Already-prepared pre-check on ALL candidates ────────────
    const libraryTasks = allCandidates
      .filter(c => !isDeadNzbByUrl(c.nzbUrl))
      .map((candidate, i) => () => {
        const probe = backend.findPrepared(
          { nzbUrl: candidate.nzbUrl, title: candidate.title, contentType, episodePattern: filePattern, episodesInSeason },
          { logPrefix: `${tag} [lib #${i + 1}] `, quiet: true },
        );
        return probe
          .then(data => ({ candidate, index: i, data }))
          .catch(() => ({ candidate, index: i, data: null as StreamData | null }));
      });

    const libraryResults = await runWithConcurrency(libraryTasks, 4);

    if (controller.signal.aborted) return;

    // Hoisted state — set by either library hit or event loop resolution
    let primaryResolved = false;
    let resolvedStreamData = null as StreamData | null;
    const resolvedVideoPaths = new Set<string>();
    const videoPathOwner = new Map<string, number>(); // videoPath → poolIndex of first resolver
    const resolvedTitles = new Set<string>(); // titles already resolved — prevents cross-indexer duplicate submissions
    let primaryPoolIndex = -1;
    let primaryFromLibrary = false;
    let requiredContainerType: string | undefined;
    let backupCount = 0;
    let libraryBackupCount = 0;
    const libraryResolvedUrls = new Set<string>(); // NZB URLs already resolved as library hits
    let evaluatedAfterPrimary = 0;
    let skippedMismatch = 0;
    let skippedUnknown = 0;
    let duplicateCount = 0;
    let failedBackupCount = 0;
    let backupLimitReached = false;
    let postPrimaryGrabs = 0;

    const hits: LibraryHit[] = libraryResults
      .filter((r): r is LibraryHit => r.data !== null)
      .sort((a, b) => a.index - b.index);
    const hitUrls = new Set(hits.map(h => h.candidate.nzbUrl));

    // Promote a library-matched pool member to primary (if no primary yet) or backup.
    // Caller decides whether to start a grab — promoted candidates never need one.
    const promoteLibraryCandidate = (cs: CandidateState): 'primary' | 'backup' | 'duplicate' | 'mismatch' | 'already-promoted' | 'deferred' | null => {
      const hit = hits.find(h => h.candidate.nzbUrl === cs.candidate.nzbUrl);
      if (!hit) return null;
      if (libraryResolvedUrls.has(cs.candidate.nzbUrl)) return 'already-promoted';
      const hitExt = path.extname(hit.data.videoPath).slice(1).toUpperCase();
      if (!primaryResolved) {
        // List order: don't let a library hit leapfrog earlier candidates whose
        // grabs/jobs are still in flight. Park it; pullReplacement re-checks on
        // every blocker-clear event and promotes once the path is clear.
        if (hasEarlierInFlight(cs.poolIndex)) {
          cs.libraryHitDeferred = hit;
          console.log(`${tag}   ⚠️ Library hit deferred (list order) — ${hit.candidate.title.substring(0, 60)} [${hit.candidate.indexerName}]`);
          return 'deferred';
        }
        const libElapsed = ((Date.now() - pipelineStart) / 1000).toFixed(1);
        console.log(`${tag} 📚 Library hit — ${hit.candidate.title} [${hit.candidate.indexerName}]`);
        const cacheKey = getCacheKey(hit.candidate.nzbUrl, hit.candidate.title) + (cachePattern ? `:${cachePattern}` : '');
        setReadyCacheEntry(cacheKey, hit.data, hit.candidate.indexerName);
        // Assign resolvedStreamData BEFORE sessionResolve so any awaiter observing
        // primaryResolved=true also sees resolvedStreamData populated.
        resolvedStreamData = hit.data;
        primaryResolved = true;
        primaryPoolIndex = cs.poolIndex;
        primaryFromLibrary = true;
        resolvedVideoPaths.add(hit.data.videoPath);
        videoPathOwner.set(hit.data.videoPath, cs.poolIndex);
        libraryResolvedUrls.add(hit.candidate.nzbUrl);
        resolvedTitles.add(hit.candidate.title);
        requiredContainerType = hitExt;
        cs.prepareStatus = 'skipped';
        cs.containerType = hitExt || undefined;
        cs.videoSize = hit.data.videoSize;
        sessionResolve(hit.data, hit.candidate.title);
        console.log(`${tag} 📦 Container locked: ${requiredContainerType || 'unknown'} (from library hit #${cs.poolIndex + 1}, videoPath: ${hit.data.videoPath})`);
        console.log(`${tag} ✅ Resolved via library in ${libElapsed}s`);
        return 'primary';
      }
      if (resolvedVideoPaths.has(hit.data.videoPath)) {
        cs.prepareStatus = 'skipped';
        cs.duplicate = true;
        cs.duplicateOf = videoPathOwner.get(hit.data.videoPath);
        if (hitExt) cs.containerType = hitExt;
        duplicateCount++;
        console.log(`${tag}   📦 #${cs.poolIndex + 1} Skipping (duplicate videoPath: ${hit.data.videoPath}) — ${cs.candidate.title.substring(0, 60)} [${cs.candidate.indexerName}]`);
        return 'duplicate';
      }
      if (requiredContainerType && hitExt && hitExt !== requiredContainerType) {
        cs.prepareStatus = 'skipped';
        cs.containerType = hitExt;
        skippedMismatch++;
        console.log(`${tag}   📦 #${cs.poolIndex + 1} Library hit skipped (${hitExt} ≠ ${requiredContainerType}) — ${cs.candidate.title.substring(0, 60)} [${cs.candidate.indexerName}]`);
        return 'mismatch';
      }
      resolvedVideoPaths.add(hit.data.videoPath);
      videoPathOwner.set(hit.data.videoPath, cs.poolIndex);
      libraryResolvedUrls.add(cs.candidate.nzbUrl);
      resolvedTitles.add(hit.candidate.title);
      deferred.backupUrls!.add(cs.candidate.nzbUrl);
      deferred.backupStreams!.push({ nzbUrl: cs.candidate.nzbUrl, videoPath: hit.data.videoPath, title: cs.candidate.title, indexerName: cs.candidate.indexerName, candidateIndex: cs.poolIndex + 1 });
      const cacheKey = getCacheKey(hit.candidate.nzbUrl, hit.candidate.title) + (cachePattern ? `:${cachePattern}` : '');
      setReadyCacheEntry(cacheKey, hit.data, hit.candidate.indexerName);
      cs.prepareStatus = 'skipped';
      cs.containerType = hitExt || undefined;
      cs.videoSize = hit.data.videoSize;
      backupCount++;
      libraryBackupCount++;
      console.log(`${tag}   📦 #${cs.poolIndex + 1} Backup ready (library hit, ${hitExt || 'unknown'}, videoPath: ${hit.data.videoPath}) — ${cs.candidate.title.substring(0, 60)} [${cs.candidate.indexerName}]`);
      return 'backup';
    };

    // ── Stage 2: Stream processing pipeline ─────────────────────
    const poolSize = Math.min(options.candidateCount, allCandidates.length);
    const activePool: CandidateState[] = [];
    let nextCandidateIdx = 0;

    const addToPool = (candidate: FallbackCandidate, idx: number): CandidateState => {
      const cs: CandidateState = {
        candidate,
        poolIndex: idx,
        healthStatus: 'pending',
        grabStatus: 'pending',
        prepareStatus: 'idle',
      };
      activePool.push(cs);
      return cs;
    };

    // List order: a library hit at poolIndex N must wait for any earlier
    // candidate still actively grabbing or preparing on the Backend to finish first.
    const hasEarlierInFlight = (poolIndex: number): boolean =>
      activePool.some(c =>
        c.poolIndex < poolIndex &&
        (c.grabStatus === 'grabbing' || c.prepareStatus === 'submitted')
      );

    for (let i = 0; i < poolSize && nextCandidateIdx < allCandidates.length; i++) {
      const c = allCandidates[nextCandidateIdx];
      if (isDeadNzbByUrl(c.nzbUrl)) { nextCandidateIdx++; i--; continue; }
      const cs = addToPool(c, nextCandidateIdx);
      deferred.lastVettedUrl = c.nzbUrl;
      if (hitUrls.has(c.nzbUrl)) promoteLibraryCandidate(cs);
      nextCandidateIdx++;
    }

    if (activePool.length === 0) {
      console.log(`${tag} All candidates are dead NZBs`);
      return;
    }

    if (primaryResolved) {
      console.log(`${tag} Continuing pipeline for backup candidates after library hit`);
    } else {
      console.log(`${tag} No library hits in pool — launching grab chain + health checks + Backend prepare`);
      if (hits.length > 0) {
        console.log(`${tag} ⚠️ Found ${hits.length} library hit(s), none in initial pool — pool may snake toward them or post-drain sweep will pick up the rest`);
      }
    }

    const startGrab = (cs: CandidateState) => {
      cs.grabStatus = 'grabbing';
      cs.grabPromise = prefetchNzb(cs.candidate.nzbUrl, `${tag} [grab #${cs.poolIndex + 1}] `, true, cs.candidate.title, cs.candidate.indexerName, cs.candidate.searchExitIp)
        .then(ok => { cs.grabStatus = ok ? 'done' : 'failed'; return { cs, ok }; })
        .catch(() => { cs.grabStatus = 'failed'; return { cs, ok: false }; });
    };

    const startHealthCheck = (cs: CandidateState) => {
      cs.healthStatus = 'checking';
      cs.healthPromise = checkSource(cs.candidate, pool).then(result => {
        cs.healthStatus = isHealthy(result) ? 'healthy' : result.status === 'blocked' ? 'dead' : 'error';
        cs.containerType = result.containerType;
        if (!isHealthy(result)) console.log(`${tag} ❌ #${cs.poolIndex + 1} not healthy (${result.message}) — ${cs.candidate.title}`);
        return { cs, result };
      }).catch(err => {
        cs.healthStatus = 'error';
        return { cs, result: { status: 'error' as const, message: (err as Error).message, playable: false } };
      });
    };

    // Direct Backend prepare — we own the lifecycle for cancellation control
    const startPrepare = async (cs: CandidateState): Promise<StreamData | null> => {
      cs.prepareStatus = 'submitted';
      const logPrefix = `${tag} [prepare #${cs.poolIndex + 1}] `;
      try {
        // Cancel checkpoint: before HTTP starts
        if (cs.cancelled) { cs.prepareStatus = 'failed'; return null; }

        logPrepareStart(logPrefix, cs.candidate.title);
        // Steps 1-3: submit (uses cached XML from grab chain), wait for the
        // job (per-mode, per-content-type budget), find the video. Cancel
        // checkpoints between steps: the health check may fail meanwhile.
        const video = await backend.prepare(
          { nzbUrl: cs.candidate.nzbUrl, title: cs.candidate.title, contentType, episodePattern: filePattern, episodesInSeason, isSeasonPack: cs.candidate.isSeasonPack, indexerName: cs.candidate.indexerName, searchExitIp: cs.candidate.searchExitIp },
          {
            logPrefix,
            timeoutMs: selectTimeoutMs(activeSet, contentType, cs.candidate.isSeasonPack === true),
            pollIntervalMs: 250,
            onJob: jobId => { cs.nzoId = jobId; },
            isCancelled: () => cs.cancelled === true,
          },
        );
        // Cancel checkpoint: health check may have failed during video discovery
        if (cs.cancelled) { cs.prepareStatus = 'failed'; return null; }

        // Step 4: Probe video is servable
        await backend.probe(video, { logPrefix, title: cs.candidate.title, source: cs.candidate.indexerName });

        // Step 5: Write to readyCache so stream handler can deliver
        const cacheKey = getCacheKey(cs.candidate.nzbUrl, cs.candidate.title) + (cachePattern ? `:${cachePattern}` : '');
        setReadyCacheEntry(cacheKey, video, cs.candidate.indexerName);

        cs.prepareStatus = 'completed';
        console.log(`${logPrefix}✅ Stream ready: ${cs.candidate.title}`);
        return video;
      } catch (err) {
        if (err instanceof PrepareCancelledError) { cs.prepareStatus = 'failed'; return null; }
        // Skip logging/cancelling if the event loop already cancelled this candidate
        if (cs.cancelled) return null;
        if (cs.nzoId) backend.cancel(cs.nzoId, 'pipeline failure').catch(() => {});
        if ((err as any)?.isBadSource) {
          setDeadNzbEntry(cs.candidate.nzbUrl, cs.candidate.title, err as Error, cachePattern, cs.candidate.indexerName, cs.videoSize || cs.candidate.size, cs.candidate.isSeasonPack);
          cs.prepareDeadWritten = true;
        } else {
          cs.backendFailed = true;
        }
        cs.prepareStatus = 'failed';
        console.log(`${logPrefix}❌ Failed: ${(err as Error).message}`);
        return null;
      }
    };

    const pullReplacement = (): CandidateState | null => {
      // A candidate may have been parked with a deferred library hit while an
      // earlier candidate was in flight. Re-evaluate now — the caller fired this
      // from a blocker-clearing transition.
      if (!primaryResolved) {
        const parked = activePool
          .filter(c => c.libraryHitDeferred)
          .sort((a, b) => a.poolIndex - b.poolIndex);
        for (const cs of parked) {
          cs.libraryHitDeferred = undefined;
          const result = promoteLibraryCandidate(cs);
          if (result === 'primary') return null;
          // 'deferred' means still blocked — promoteLibraryCandidate re-set the field.
        }
      }
      if (backupLimitReached) return null;
      // Also check live counts. The flag flips top-of-loop but pullReplacement
      // is called inline from the completion handlers — without this, a fresh
      // candidate gets grabbed between backupCount incrementing and the next
      // iteration's drain signal.
      if (primaryResolved) {
        // No backups wanted — block any post-primary grab. Catches the
        // inline-call race where `backupLimitReached` hasn't been set yet
        // by the top of the loop. Already-grabbed candidates are not handed
        // to the Backend either (selectNext, #192). Free library hits are
        // picked up by the post-drain sweep below regardless.
        if (options.desiredBackups === 0) return null;
        if (options.desiredBackups > 0 && backupCount >= options.desiredBackups) return null;
        // Cap NEW post-primary grabs only. Pre-primary refills (added before
        // primary resolved while still searching) are free and flow through
        // as backups via selectNext. Library hits don't charge either.
        if (options.backupProcessingLimit > 0 && postPrimaryGrabs >= options.backupProcessingLimit) {
          return null;
        }
      }
      // No attempts cap before the primary: Best checks until one is healthy or the list runs out (#190).
      while (nextCandidateIdx < allCandidates.length) {
        const c = allCandidates[nextCandidateIdx];
        nextCandidateIdx++;
        if (isDeadNzbByUrl(c.nzbUrl)) continue;
        const cs = addToPool(c, nextCandidateIdx - 1);
        if (primaryResolved && !hitUrls.has(c.nzbUrl)) postPrimaryGrabs++;
        deferred.lastVettedUrl = c.nzbUrl;
        if (hitUrls.has(c.nzbUrl)) {
          promoteLibraryCandidate(cs);
        } else {
          startGrab(cs);
        }
        return cs;
      }
      return null;
    };

    // Only a Source the check found healthy is handed to the Backend, never one still being checked:
    // the first healthy Source in list order, waiting while an earlier one is still grabbed or checked.
    const selectNext = (): CandidateState | null => {
      // Prepare only the Source being played (#192): with no backups wanted, the healthy Sources
      // checked alongside the played one are not handed to the Backend; the next is prepared only
      // when the one being prepared fails.
      if (primaryResolved && options.desiredBackups === 0) return null;
      for (const cs of activePool) {
        if (cs.prepareStatus !== 'idle') continue;
        if (cs.healthStatus === 'dead' || cs.healthStatus === 'error') continue;
        if (cs.healthStatus !== 'healthy') return null;
        return cs;
      }
      return null;
    };

    for (const cs of activePool) { if (cs.prepareStatus === 'idle') startGrab(cs); }

    // ── Event loop (continues after primary for backup pre-caching) ──
    let activePrepareCs: CandidateState | null = null;
    let preparePromise: Promise<StreamData | null> | null = null;
    // A stop (a newer list request's Head start, a settings change) wakes the loop at once.
    const stopped = new Promise<void>(resolve => controller.signal.addEventListener('abort', () => resolve(), { once: true }));

    while (!controller.signal.aborted) {
      // Backup limit checks
      if (primaryResolved) {
        if (options.desiredBackups === 0 && !backupLimitReached) {
          backupLimitReached = true;
          console.log(`${tag} 📦 No replacement grabs (desiredBackups=0) — draining; free library hits still captured`);
        } else if (options.desiredBackups > 0 && backupCount >= options.desiredBackups && !backupLimitReached) {
          backupLimitReached = true;
          console.log(`${tag} 📦 Desired backups reached (${backupCount}/${options.desiredBackups}) — draining pool`);
        }
        if (options.backupProcessingLimit > 0 && !backupLimitReached && postPrimaryGrabs >= options.backupProcessingLimit) {
          backupLimitReached = true;
          console.log(`${tag} 📦 Backup processing limit reached (${postPrimaryGrabs}/${options.backupProcessingLimit}) — draining pool`);
        }
      }

      const pending: Promise<unknown>[] = [];
      for (const cs of activePool) {
        if (cs.grabPromise && cs.grabStatus === 'grabbing') pending.push(cs.grabPromise);
        if (cs.healthPromise && cs.healthStatus === 'checking') pending.push(cs.healthPromise);
      }
      if (preparePromise) pending.push(preparePromise);
      if (pending.length === 0 && !selectNext()) {
        // Pool drained — try pulling more candidates before exiting.
        // pullReplacement self-gates on backupLimitReached/desiredBackups/BPL,
        // so it returns null when budget or candidates are exhausted. This
        // matters especially when the initial pool was fully resolved by
        // library hits (status='skipped') and no grabs were ever started.
        if (!backupLimitReached) {
          const pulled = pullReplacement();
          if (pulled) {
            console.log(`${tag} Pool drained — pulled replacement to satisfy desiredBackups`);
            continue;
          }
        }
        break;
      }

      if (pending.length > 0) await Promise.race([...pending, stopped]);
      if (controller.signal.aborted) break;

      // Process grab completions → start health checks
      for (const cs of activePool) {
        if (cs.grabStatus === 'done' && cs.healthStatus === 'pending') startHealthCheck(cs);
        if (cs.grabStatus === 'failed' && cs.healthStatus === 'pending') {
          cs.healthStatus = 'dead';
          cs.grabFailed = true;
          console.log(`${tag} ❌ Grab failed for #${cs.poolIndex + 1} ${cs.candidate.title}`);
          pullReplacement();
        }
      }

      // Process health check completions — cancel the active prepare if its candidate is dead, pull replacements for idle dead candidates
      for (const cs of activePool) {
        if (cs.healthStatus !== 'dead' && cs.healthStatus !== 'error') continue;
        if (cs === activePrepareCs && cs.prepareStatus === 'submitted') {
          console.log(`${tag} 🗑️ Health check failed for the candidate being prepared #${cs.poolIndex + 1} — cancelling job`);
          cs.cancelled = true;
          // Flip status synchronously so hasEarlierInFlight in the same tick (via pullReplacement
          // below) doesn't see this candidate as still in-flight and re-defer parked library hits.
          cs.prepareStatus = 'failed';
          if (cs.nzoId) backend.cancel(cs.nzoId, 'health check failed').catch(() => {});
          preparePromise?.catch(() => {});
          activePrepareCs = null;
          preparePromise = null;
          pullReplacement();
        } else if (cs.prepareStatus === 'idle' && !cs.replaced) {
          cs.replaced = true;
          pullReplacement();
        }
      }

      // Check prepare completion — primary vs backup
      if (activePrepareCs?.prepareStatus === 'completed' && resolvedStreamData) {
        if (!primaryResolved) {
          // ── Primary resolution ──
          primaryResolved = true;
          primaryPoolIndex = activePrepareCs.poolIndex;
          requiredContainerType = path.extname(resolvedStreamData.videoPath).slice(1).toUpperCase();
          resolvedVideoPaths.add(resolvedStreamData.videoPath);
          videoPathOwner.set(resolvedStreamData.videoPath, activePrepareCs.poolIndex);
          resolvedTitles.add(activePrepareCs.candidate.title);
          activePrepareCs.videoSize = resolvedStreamData.videoSize;
          const elapsed = ((Date.now() - pipelineStart) / 1000).toFixed(1);
          console.log(`${tag} ✅ Resolved in ${elapsed}s — ${activePrepareCs.candidate.title} [${activePrepareCs.candidate.indexerName}]`);
          sessionResolve(resolvedStreamData, activePrepareCs.candidate.title);
          if (requiredContainerType) {
            console.log(`${tag} 📦 Container locked: ${requiredContainerType} (from primary #${activePrepareCs.poolIndex + 1}, videoPath: ${resolvedStreamData.videoPath})`);
          } else {
            console.log(`${tag} 📦 Primary videoPath has no file extension (${resolvedStreamData.videoPath}) — submitting all healthy backups without container filtering`);
          }
        } else {
          // ── Backup completion ──
          const videoPath = resolvedStreamData.videoPath;
          const resolvedExt = path.extname(videoPath).slice(1).toUpperCase();
          if (resolvedVideoPaths.has(videoPath)) {
            duplicateCount++;
            activePrepareCs.duplicate = true;
            activePrepareCs.duplicateOf = videoPathOwner.get(videoPath);
            console.log(`${tag}   📦 #${activePrepareCs.poolIndex + 1} Skipping (duplicate videoPath: ${videoPath}) — ${activePrepareCs.candidate.title.substring(0, 60)} [${activePrepareCs.candidate.indexerName}]`);
          } else if (activePrepareCs.containerFallbackViaPrepare && requiredContainerType && (!resolvedExt || resolvedExt !== requiredContainerType)) {
            // Fallback-resolved backup has wrong (or empty) container vs primary. Discard.
            activePrepareCs.prepareStatus = 'skipped';
            if (resolvedExt) activePrepareCs.containerType = resolvedExt;
            skippedMismatch++;
            console.log(`${tag}   📦 #${activePrepareCs.poolIndex + 1} Fallback container mismatch (${resolvedExt || 'no ext'} ≠ ${requiredContainerType}) — ${activePrepareCs.candidate.title.substring(0, 60)} [${activePrepareCs.candidate.indexerName}]`);
          } else {
            resolvedVideoPaths.add(videoPath);
            videoPathOwner.set(videoPath, activePrepareCs.poolIndex);
            resolvedTitles.add(activePrepareCs.candidate.title);
            deferred.backupUrls!.add(activePrepareCs.candidate.nzbUrl);
            deferred.backupStreams!.push({ nzbUrl: activePrepareCs.candidate.nzbUrl, videoPath, title: activePrepareCs.candidate.title, indexerName: activePrepareCs.candidate.indexerName, candidateIndex: activePrepareCs.poolIndex + 1 });
            backupCount++;
            if (!activePrepareCs.containerType) activePrepareCs.containerType = resolvedExt || undefined;
            activePrepareCs.videoSize = resolvedStreamData.videoSize;
            const via = activePrepareCs.containerFallbackViaPrepare ? 'via fallback, ' : '';
            const ct = activePrepareCs.containerType || 'unknown';
            console.log(`${tag}   📦 #${activePrepareCs.poolIndex + 1} Backup submitted (${via}${ct}, videoPath: ${videoPath}) — ${activePrepareCs.candidate.title.substring(0, 60)} [${activePrepareCs.candidate.indexerName}]`);
          }
        }
        pullReplacement();
        activePrepareCs = null;
        preparePromise = null;
        resolvedStreamData = null;
      }
      if (activePrepareCs?.prepareStatus === 'failed') {
        if (primaryResolved) {
          failedBackupCount++;
          console.log(`${tag}   📦 #${activePrepareCs.poolIndex + 1} Backup failed — ${activePrepareCs.candidate.title.substring(0, 60)} [${activePrepareCs.candidate.indexerName}]`);
        } else {
          console.log(`${tag} ❌ Prepare failed for #${activePrepareCs.poolIndex + 1} ${activePrepareCs.candidate.title}`);
        }
        activePrepareCs.healthStatus = 'dead';
        pullReplacement();
        activePrepareCs = null;
        preparePromise = null;
      }

      // Hand the next candidate to the Backend if none is being prepared
      if (!activePrepareCs || activePrepareCs.prepareStatus !== 'submitted') {
        const next = selectNext();
        if (next) {
          // Skip cross-indexer duplicates (same release title already resolved)
          if (primaryResolved && resolvedTitles.has(next.candidate.title)) {
            next.prepareStatus = 'skipped';
            next.duplicate = true;
            duplicateCount++;
            console.log(`${tag}   📦 #${next.poolIndex + 1} Skipping (duplicate title) — ${next.candidate.title.substring(0, 60)} [${next.candidate.indexerName}]`);
            pullReplacement();
            continue;
          }

          // Container match gate (only for backups after primary)
          if (primaryResolved && requiredContainerType) {
            evaluatedAfterPrimary++;
            if (!next.containerType) {
              // Archive inspection couldn't determine the container. Health check
              // already grabbed the segments — fall through to the Backend and derive
              // the container from the extracted videoPath post-resolve.
              next.containerFallbackViaPrepare = true;
              console.log(`${tag}   📦 #${next.poolIndex + 1} Container fallback via the Backend — ${next.candidate.title.substring(0, 60)} [${next.candidate.indexerName}]`);
            } else if (next.containerType !== requiredContainerType) {
              next.prepareStatus = 'skipped';
              skippedMismatch++;
              console.log(`${tag}   📦 #${next.poolIndex + 1} Skipping (${next.containerType} ≠ ${requiredContainerType}) — ${next.candidate.title.substring(0, 60)} [${next.candidate.indexerName}]`);
              pullReplacement();
              continue;
            } else {
              console.log(`${tag}   📦 #${next.poolIndex + 1} Backup match (${next.containerType}) — ${next.candidate.title.substring(0, 60)} [${next.candidate.indexerName}]`);
            }
          }
          console.log(`${tag} 🚀 Submitting #${next.poolIndex + 1} ${next.candidate.title} [${next.candidate.indexerName}] to the Backend`);
          activePrepareCs = next;
          preparePromise = startPrepare(next).then(data => { resolvedStreamData = data; return data; });
        }
      }

      // Check if all candidates are exhausted
      const allProcessed = activePool.every(cs =>
        cs.healthStatus === 'dead' || cs.healthStatus === 'error' ||
        cs.prepareStatus === 'failed' || cs.prepareStatus === 'completed' || cs.prepareStatus === 'skipped'
      );
      if (allProcessed && nextCandidateIdx >= allCandidates.length) {
        if (!primaryResolved) {
          console.log(`${tag} ❌ Exhausted all ${allCandidates.length} candidates`);
        } else if (options.desiredBackups > 0) {
          const pipelineBackups = backupCount - libraryBackupCount;
          if (pipelineBackups < options.desiredBackups) {
            console.log(`${tag} 📦 Exhausted all candidates — ${pipelineBackups}/${options.desiredBackups} backups found`);
          } else {
            console.log(`${tag} 📦 Desired backups reached (${pipelineBackups}/${options.desiredBackups}) — stopping`);
          }
        }
        break;
      }
    }

    // Stopped: a Source not yet handed over is not handed over (AltMount cannot stop an import it has begun).
    if (controller.signal.aborted && activePrepareCs?.prepareStatus === 'submitted') {
      activePrepareCs.cancelled = true;
      activePrepareCs.prepareStatus = 'failed';
      preparePromise?.catch(() => {});
      if (activePrepareCs.nzoId) backend.cancel(activePrepareCs.nzoId, 'stopped').catch(() => {});
    }

    // ── Post-drain library sweep ─────────────────────────────────
    // Library hits cost no NNTP grab, so the sweep is always exhaustive when
    // primary resolved. desiredBackups is treated as a target for grabbed
    // backups; free library hits are added on top of the target rather than
    // counting against it. More mid-stream fallback protection at zero cost.
    if (primaryResolved) {
      for (const hit of hits) {
        if (libraryResolvedUrls.has(hit.candidate.nzbUrl)) continue;
        if (hit.index === primaryPoolIndex) continue;
        if (resolvedVideoPaths.has(hit.data.videoPath)) continue;
        const hitExt = path.extname(hit.data.videoPath).slice(1).toUpperCase();
        if (requiredContainerType && hitExt && hitExt !== requiredContainerType) continue;
        resolvedVideoPaths.add(hit.data.videoPath);
        videoPathOwner.set(hit.data.videoPath, hit.index);
        libraryResolvedUrls.add(hit.candidate.nzbUrl);
        resolvedTitles.add(hit.candidate.title);
        deferred.backupUrls!.add(hit.candidate.nzbUrl);
        deferred.backupStreams!.push({ nzbUrl: hit.candidate.nzbUrl, videoPath: hit.data.videoPath, title: hit.candidate.title, indexerName: hit.candidate.indexerName, candidateIndex: hit.index + 1 });
        deferred.lastVettedUrl = hit.candidate.nzbUrl;
        const cacheKey = getCacheKey(hit.candidate.nzbUrl, hit.candidate.title) + (cachePattern ? `:${cachePattern}` : '');
        setReadyCacheEntry(cacheKey, hit.data, hit.candidate.indexerName);
        backupCount++;
        libraryBackupCount++;
        console.log(`${tag}   📦 #${hit.index + 1} Backup ready (library post-drain, ${hitExt || 'unknown'}, videoPath: ${hit.data.videoPath}) — ${hit.candidate.title.substring(0, 60)} [${hit.candidate.indexerName}]`);
      }
    }

    // ── Summary ──────────────────────────────────────────────────
    const totalElapsed = ((Date.now() - pipelineStart) / 1000).toFixed(1);
    if (!primaryResolved) {
      console.log(`${tag} Pipeline ended without resolution (${totalElapsed}s)`);
      sessionReject(new Error('All candidates exhausted'));
    }
    const healthy = activePool.filter(cs => cs.healthStatus === 'healthy').length;
    const dead = activePool.filter(cs => cs.healthStatus === 'dead' || cs.healthStatus === 'error' || cs.prepareStatus === 'failed').length;
    const skipped = activePool.filter(cs => cs.prepareStatus === 'skipped').length;
    const divider = '┄'.repeat(120);
    const settingsLine = [
      `pool: ${options.candidateCount}`,
      'list order',
      `desiredBackups: ${options.desiredBackups === 0 ? 'Off' : options.desiredBackups}`,
      `backupProcessingLimit: ${options.backupProcessingLimit === 0 ? 'all' : `${postPrimaryGrabs}/${options.backupProcessingLimit}`}`,
    ].join(' · ');
    console.log(`${tag} ${divider}`);
    console.log(`${tag}   ${activePool.length} checked · ${healthy} healthy · ${dead} dead · ${skipped} skipped · ${totalElapsed}s`);
    console.log(`${tag}   ⚙️  ${settingsLine}`);
    console.log(`${tag} ${divider}`);

    // Render candidates with the primary pinned on top, then remaining rows
    // in priority (poolIndex) order — matches the fallback chain below the
    // active stream.
    type SummaryRow = { poolIndex: number; isPrimary: boolean; line: string };
    const rows: SummaryRow[] = [];

    if (primaryResolved && primaryPoolIndex >= 0) {
      const primaryCs = activePool.find(cs => cs.poolIndex === primaryPoolIndex);
      if (primaryCs) {
        const primarySize = primaryCs.videoSize ? ` · ${formatBytes(primaryCs.videoSize)}` : '';
        rows.push({
          poolIndex: primaryPoolIndex,
          isPrimary: true,
          line: `${tag}   👑 #${primaryPoolIndex + 1} [${requiredContainerType || '?'}${primarySize}] ${primaryCs.candidate.title.substring(0, 60)} [${primaryCs.candidate.indexerName}] → primary${primaryFromLibrary ? ' (library)' : ''}`,
        });
      }
    }

    // Active-pool entries render first (richer status/icon). Track what's rendered
    // so library hits covering the same poolIndex aren't printed twice.
    const poolIndicesRendered = new Set<number>(rows.map(r => r.poolIndex));
    for (const cs of activePool) {
      if (cs.poolIndex === primaryPoolIndex) continue;
      if (cs.healthStatus === 'pending' && cs.prepareStatus === 'idle') continue;
      const isLibraryBackup = cs.prepareStatus === 'skipped' && libraryResolvedUrls.has(cs.candidate.nzbUrl);
      const icon = isLibraryBackup ? '📚' : cs.duplicate ? '🔁' : cs.prepareStatus === 'completed' ? '✅' : cs.prepareStatus === 'skipped' ? '⏭️' : cs.prepareStatus === 'failed' ? '❌' : cs.healthStatus === 'healthy' ? '💚' : cs.healthStatus === 'dead' ? '❌' : '⏳';
      const dupRef = cs.duplicate ? (cs.duplicateOf !== undefined ? ` (#${cs.duplicateOf + 1})` : '') : '';
      const sizeStr = cs.videoSize ? ` · ${formatBytes(cs.videoSize)}` : '';
      const ct = cs.containerType ? `[${cs.containerType}${sizeStr}] ` : '';
      const skippedLabel = cs.containerType && requiredContainerType && cs.containerType !== requiredContainerType
        ? `skipped (${cs.containerType} ≠ ${requiredContainerType})`
        : `skipped (${cs.containerType || 'unknown'})`;
      const status = isLibraryBackup ? 'backup (library)' : cs.duplicate ? `duplicate${dupRef}` : cs.prepareStatus === 'completed' ? 'backup' : cs.prepareStatus === 'skipped' ? skippedLabel : cs.cancelled ? 'cancelled' : cs.prepareStatus === 'failed' ? 'prepare-failed' : cs.grabFailed ? 'grab-failed' : cs.healthStatus === 'dead' ? 'dead' : 'standby';
      rows.push({
        poolIndex: cs.poolIndex,
        isPrimary: false,
        line: `${tag}   ${icon} #${cs.poolIndex + 1} ${ct}${cs.candidate.title.substring(0, 60)} [${cs.candidate.indexerName}] → ${status}`,
      });
      poolIndicesRendered.add(cs.poolIndex);
    }

    // Out-of-pool library hits promoted post-drain (after event loop budget exhausted)
    for (const hit of hits) {
      if (hit.index === primaryPoolIndex) continue;
      if (poolIndicesRendered.has(hit.index)) continue;
      if (!libraryResolvedUrls.has(hit.candidate.nzbUrl)) continue;
      const ext = path.extname(hit.data.videoPath).slice(1).toUpperCase();
      const hitSize = hit.data.videoSize ? ` · ${formatBytes(hit.data.videoSize)}` : '';
      rows.push({
        poolIndex: hit.index,
        isPrimary: false,
        line: `${tag}   📚 #${hit.index + 1} [${ext || '?'}${hitSize}] ${hit.candidate.title.substring(0, 60)} [${hit.candidate.indexerName}] → backup (library post-drain)`,
      });
    }

    rows.sort((a, b) => {
      if (a.isPrimary !== b.isPrimary) return a.isPrimary ? -1 : 1;
      return a.poolIndex - b.poolIndex;
    });
    for (const r of rows) console.log(r.line);

    // Backup summary (only if primary resolved)
    if (primaryResolved) {
      const pipelineBackups = backupCount - libraryBackupCount;
      const sourceBreakdown = libraryBackupCount > 0 && pipelineBackups > 0
        ? ` (${pipelineBackups} pipeline + ${libraryBackupCount} library)`
        : libraryBackupCount > 0 ? ' (library)' : '';
      console.log(`${tag} ${divider}`);
      console.log(`${tag}   📦 Backups: ${backupCount}${options.desiredBackups > 0 ? `/${options.desiredBackups}` : ''}${sourceBreakdown} · ${evaluatedAfterPrimary} evaluated · ${skippedMismatch} mismatch · ${skippedUnknown} unknown · ${duplicateCount} duplicate · ${failedBackupCount} failed`);
      console.log(`${tag} ${divider}`);
    }

    // Write dead candidates to the dead NZB DB so the fallback loop skips them.
    // Skip candidates whose prepare step already wrote a specific failure entry via setDeadNzbEntry
    // (preserves granular errors for selective clears like clearMultiEpisodeDeadEntries /
    // clearTimeoutDeadEntries). Also skip grab-failed candidates — grab failures are transient
    // indexer/network/VPN issues, not NZB-liveness signals, and should never be persisted.
    let deadWrites = 0;
    for (const cs of activePool) {
      if (cs.healthStatus === 'dead' && !cs.prepareDeadWritten && !cs.grabFailed && !cs.backendFailed) {
        addDeadNzbByUrl(cs.candidate.nzbUrl, cs.candidate.title, cs.candidate.indexerName, cs.candidate.size);
        deadWrites++;
      }
    }
    if (deadWrites > 0) saveCacheToDisk();

  } catch (err) {
    if (!controller.signal.aborted) console.error(`${tag} Error:`, err);
    sessionReject(err instanceof Error ? err : new Error(String(err)));
  } finally {
    pool?.destroyAll();
    activeSessions.delete(sessionKey);
    claimedSessions.delete(sessionKey);
    // Persist end-of-pipeline state — captures final backup arrays + lastVettedUrl
    // so a UF tile click after addon restart can serve from the vetted backups.
    saveSessionsToDisk();
    // A session that found nothing to play is dropped at once, so the next press of Best checks again
    // (dead Sources stay remembered and are skipped).
    if (deferred.resolvedData === undefined && sessionPromises.get(sessionKey) === deferred) {
      sessionPromises.delete(sessionKey);
      saveSessionsToDisk();
    } else {
      // Keep session promise available for SESSION_TTL_MS so auto-play / binge watching can find it after episodes finish
      const timer = setTimeout(() => {
        sessionPromises.delete(sessionKey);
        cleanupTimers.delete(sessionKey);
        saveSessionsToDisk();
      }, SESSION_TTL_MS);
      cleanupTimers.set(sessionKey, timer);
    }
  }
}
