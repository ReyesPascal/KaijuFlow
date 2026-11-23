/**
 * Ultimate-Fallback: Best's sessions and the adapter that runs Best's Walk (walk.ts, GLOSSARY: Walk).
 *
 * The Walk decides; this file runs its decisions: the library pre-check (the Backend's findPrepared, no NZB download),
 * the NZB grab, the Play-time check (playTimeCheck.ts) and the hand-off to the Backend (prepare, probe), and tells the
 * Walk what each answered. It also keeps Best's sessions (the promise a press of Best waits on), the Head start and
 * the claim a press makes on it. Runs only when the Backend has the ultimateFallback capability (AltMount: since #190).
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
import { NntpConnectionPool } from '../health/nntpConnection.js';
import { isDeadNzbByUrl, getCacheKey, setReadyCacheEntry, setDeadNzbEntry, addDeadNzbByUrl, saveCacheToDisk, logPrepareStart } from './streamCache.js';
import { logPlayFailed } from '../utils/stepTiming.js';
import { prefetchNzb } from '../backends/nzbGrab.js';
import { getActiveBackend, PrepareCancelledError } from '../backends/index.js';
import { sourceFailure } from '../backends/types.js';
import { selectTimeoutMs, formatTimeoutSeconds, type TimeoutSet } from './timeoutDefaults.js';
import type { FallbackCandidate, StreamData } from './types.js';
import type { UltimateFallbackConfig } from '../types.js';
import { formatBytes } from '../parsers/metadataParsers.js';
import { checkSource, isHealthy, enabledHealthCheckProviders } from './playTimeCheck.js';
import { Walk, WALK_MAX_GRABS, type WalkDecision, type WalkEvent } from './walk.js';

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
  settings: UltimateFallbackConfig,
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
  ultimateFallbackFromCandidates(sessionKey, candidates, settings, cachePattern, filePattern, contentType, episodesInSeason)
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

/** A Walk that ended with no Source to play (the list ran out or the Walk hit its grabs): a press of Best shows the failure video. */
export function walkFoundNothing(err: unknown): boolean {
  return (err as { walkEnded?: boolean } | null)?.walkEnded === true;
}
const nothingToPlay = (message: string) => Object.assign(new Error(message), { walkEnded: true });

// ── The adapter: runs Best's Walk (walk.ts) against the NZB grab, the Play-time check and the Backend ──

/** What the adapter holds for one Source of the Walk: the Backend's job, what the check and the prepare found. */
interface SourceRun {
  nzoId?: string;
  cancelled?: boolean;
  containerType?: string;
  video?: StreamData;
  prepareError?: Error;
}

export async function ultimateFallbackFromCandidates(
  sessionKey: string,
  candidates: FallbackCandidate[],
  settings: UltimateFallbackConfig,
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
  // The played Source's release name rides along, so a press can name what it plays (its `played` step line).
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
  const pool = providers.length > 0 ? new NntpConnectionPool() : undefined;

  try {
    // Opted-out indexers are not walked.
    const indexerMap = settings.healthCheckIndexers;
    const list = indexerMap ? candidates.filter(c => indexerMap[c.indexerName] !== false) : candidates;
    if (list.length === 0) {
      console.log(`${tag} No eligible candidates`);
      return;
    }

    const pipelineStart = Date.now();
    const seconds = () => ((Date.now() - pipelineStart) / 1000).toFixed(1);
    const activeSet: TimeoutSet = settings.preferenceMode === 'priority'
      ? { movies: settings.priorityMoviesTimeoutSeconds, tv: settings.priorityTvTimeoutSeconds, seasonPack: settings.prioritySeasonPackTimeoutSeconds }
      : { movies: settings.speedMoviesTimeoutSeconds, tv: settings.speedTvTimeoutSeconds, seasonPack: settings.speedSeasonPackTimeoutSeconds };
    console.log(`${tag} Starting — ${list.length} candidate(s), pool size ${settings.candidateCount}, list order, wait times: ${settings.preferenceMode} (movies=${formatTimeoutSeconds(activeSet.movies)}, tv=${formatTimeoutSeconds(activeSet.tv)}, pack=${formatTimeoutSeconds(activeSet.seasonPack)})`);

    // Library hits: the Sources the Backend already holds (no NZB download needed).
    const libraryTasks = list.flatMap((candidate, index) => isDeadNzbByUrl(candidate.nzbUrl) ? [] : [() =>
      backend.findPrepared(
        { nzbUrl: candidate.nzbUrl, title: candidate.title, contentType, episodePattern: filePattern, episodesInSeason },
        { logPrefix: `${tag} [lib #${index + 1}] `, quiet: true },
      ).then(data => ({ index, data }), () => ({ index, data: null as StreamData | null }))]);
    const hits = new Map<number, StreamData>();
    for (const r of await runWithConcurrency(libraryTasks, 4)) if (r.data) hits.set(r.index, r.data);
    if (controller.signal.aborted) return;

    const walk = new Walk({
      size: list.length,
      inFlight: Math.max(1, settings.candidateCount),
      isDead: index => isDeadNzbByUrl(list[index].nzbUrl),
      hits: new Map([...hits].map(([index, data]) => [index, data.videoPath])),
    });
    const runs = new Map<number, SourceRun>();
    const runOf = (index: number): SourceRun => { let r = runs.get(index); if (!r) runs.set(index, r = {}); return r; };
    const name = (index: number) => `#${index + 1} ${list[index].title}`;
    const readyKey = (c: FallbackCandidate) => getCacheKey(c.nzbUrl, c.title) + (cachePattern ? `:${cachePattern}` : '');
    let deadWrites = 0;

    let finish!: () => void;
    const finished = new Promise<void>(resolve => { finish = resolve; });
    const post = (event: WalkEvent) => {
      for (const d of walk.on(event)) run(d);
      if (walk.done) finish();
    };

    // The Backend prepare: submit (the grab's NZB), wait for the job, find the video, probe its first byte.
    const prepare = async (index: number): Promise<void> => {
      const c = list[index];
      const r = runOf(index);
      const logPrefix = `${tag} [prepare #${index + 1}] `;
      try {
        logPrepareStart(logPrefix, c.title);
        const video = await backend.prepare(
          { nzbUrl: c.nzbUrl, title: c.title, contentType, episodePattern: filePattern, episodesInSeason, isSeasonPack: c.isSeasonPack, indexerName: c.indexerName, searchExitIp: c.searchExitIp },
          {
            logPrefix,
            timeoutMs: selectTimeoutMs(activeSet, contentType, c.isSeasonPack === true),
            pollIntervalMs: 250,
            onJob: jobId => { r.nzoId = jobId; },
            isCancelled: () => r.cancelled === true,
          },
        );
        if (r.cancelled) return;
        await backend.probe(video, { logPrefix, title: c.title, source: c.indexerName });
        if (r.cancelled) return;
        setReadyCacheEntry(readyKey(c), video, c.indexerName);
        r.video = video;
        console.log(`${logPrefix}✅ Stream ready: ${c.title}`);
        post({ type: 'prepared', index, videoPath: video.videoPath });
      } catch (err) {
        if (err instanceof PrepareCancelledError || r.cancelled) return;
        if (r.nzoId) backend.cancel(r.nzoId, 'pipeline failure').catch(() => {});
        r.prepareError = err as Error;
        console.log(`${logPrefix}❌ Failed: ${(err as Error).message}`);
        console.log(`${tag} ❌ Prepare failed for ${name(index)}`);
        logPlayFailed(c.title, c.indexerName, err);
        post({ type: 'prepareFailed', index, badSource: (err as { isBadSource?: boolean })?.isBadSource === true });
      }
    };

    const run = (d: WalkDecision): void => {
      switch (d.type) {
        case 'grab': {
          const c = list[d.index];
          deferred.lastVettedUrl = c.nzbUrl;
          prefetchNzb(c.nzbUrl, `${tag} [grab #${d.index + 1}] `, true, c.title, c.indexerName, c.searchExitIp)
            .catch(() => false)
            .then(ok => {
              if (!ok) console.log(`${tag} ❌ Grab failed for ${name(d.index)}`);
              post({ type: ok ? 'grabbed' : 'grabFailed', index: d.index });
            });
          return;
        }
        case 'check':
          // The check samples the file AltMount is told to play (#203): the episode selector it is sent.
          checkSource({ ...list[d.index], episodePattern: filePattern }, pool)
            .then(result => {
              runOf(d.index).containerType = result.containerType;
              if (!isHealthy(result)) console.log(`${tag} ❌ #${d.index + 1} not healthy (${result.message}) — ${list[d.index].title}`);
              post({ type: 'checked', index: d.index, verdict: isHealthy(result) ? 'healthy' : result.status === 'blocked' ? 'blocked' : 'error', episodeOnly: result.episodeOnly === true });
            }, () => post({ type: 'checked', index: d.index, verdict: 'error' }));
          return;
        case 'prepare':
          console.log(`${tag} 🚀 Submitting ${name(d.index)} [${list[d.index].indexerName}] to the Backend`);
          void prepare(d.index);
          return;
        case 'cancel': {
          // Stopped: AltMount cannot stop an import it has begun, but KaijuFlow hands it nothing more.
          const r = runOf(d.index);
          r.cancelled = true;
          if (r.nzoId) backend.cancel(r.nzoId, 'stopped').catch(() => {});
          return;
        }
        case 'park':
          console.log(`${tag}   ⚠️ Library hit deferred (list order) — ${list[d.index].title.substring(0, 60)} [${list[d.index].indexerName}]`);
          return;
        case 'settle': {
          const c = list[d.index];
          if (d.via === 'library') {
            const data = hits.get(d.index)!;
            console.log(`${tag} 📚 Library hit — ${c.title} [${c.indexerName}]`);
            setReadyCacheEntry(readyKey(c), data, c.indexerName);
            sessionResolve(data, c.title);
            console.log(`${tag} ✅ Resolved via library in ${seconds()}s`);
          } else {
            console.log(`${tag} ✅ Resolved in ${seconds()}s — ${c.title} [${c.indexerName}]`);
            sessionResolve(runOf(d.index).video!, c.title);
          }
          return;
        }
        case 'backup': {
          const c = list[d.index];
          const data = hits.get(d.index)!;
          deferred.backupUrls!.add(c.nzbUrl);
          deferred.backupStreams!.push({ nzbUrl: c.nzbUrl, videoPath: data.videoPath, title: c.title, indexerName: c.indexerName, candidateIndex: d.index + 1 });
          setReadyCacheEntry(readyKey(c), data, c.indexerName);
          console.log(`${tag}   📦 #${d.index + 1} Backup ready (library hit, videoPath: ${data.videoPath}) — ${c.title.substring(0, 60)} [${c.indexerName}]`);
          return;
        }
        case 'ceiling':
          console.log(`${tag} 🛑 Walk stopped: ${d.grabs} grabs, the most one Walk makes — ending as if the list had run out`);
          return;
        case 'settleNone':
          if (d.end === 'stopped') return; // the session is settled as stopped below
          if (d.end === 'ran-out') console.log(`${tag} ❌ Exhausted all ${list.length} candidates`);
          console.log(`${tag} Pipeline ended without resolution (${seconds()}s)`);
          sessionReject(nothingToPlay('All candidates exhausted'));
          return;
        case 'markDead': {
          // ADR 0004: a bad Source is remembered dead, so no later play grabs it again.
          const c = list[d.index];
          if (d.cause === 'check') addDeadNzbByUrl(c.nzbUrl, c.title, c.indexerName, c.size);
          // A pack blocked on its wanted episode is remembered for that episode only, as a prepare failure is (#203).
          else if (d.cause === 'check-episode') setDeadNzbEntry(c.nzbUrl, c.title, sourceFailure('Health check: blocked', false, true), cachePattern, c.indexerName, c.size, c.isSeasonPack);
          else setDeadNzbEntry(c.nzbUrl, c.title, runOf(d.index).prepareError!, cachePattern, c.indexerName, runOf(d.index).video?.videoSize || c.size, c.isSeasonPack);
          deadWrites++;
          return;
        }
      }
    };

    // A stop (a newer list request's Head start, a settings change) ends the Walk at once.
    controller.signal.addEventListener('abort', () => post({ type: 'stop' }), { once: true });
    for (const d of walk.start()) run(d);
    if (walk.done) finish();
    await finished;

    // ── Summary ──────────────────────────────────────────────────
    const members = walk.snapshot();
    const healthy = members.filter(m => m.check === 'healthy').length;
    const dead = members.filter(m => m.grab === 'failed' || m.check === 'blocked' || m.check === 'error' || m.prepare === 'failed').length;
    const skipped = members.filter(m => m.library === 'duplicate' || m.library === 'mismatch').length;
    const divider = '┄'.repeat(120);
    console.log(`${tag} ${divider}`);
    console.log(`${tag}   ${members.length} checked · ${healthy} healthy · ${dead} dead · ${skipped} skipped · ${walk.grabCount} grabbed · ${seconds()}s`);
    console.log(`${tag}   ⚙️  pool: ${settings.candidateCount} · list order · only the Source played is prepared · at most ${WALK_MAX_GRABS} grabs`);
    console.log(`${tag} ${divider}`);
    for (const m of members) {
      const c = list[m.index];
      const r = runs.get(m.index);
      const status = m.library === 'played' ? 'primary (library)'
        : m.prepare === 'done' ? 'primary'
        : m.library === 'backup' ? 'backup (library)'
        : m.library === 'duplicate' ? 'duplicate'
        : m.library === 'mismatch' ? 'skipped (other container)'
        : m.prepare === 'cancelled' ? 'cancelled'
        : m.prepare === 'failed' ? 'prepare-failed'
        : m.grab === 'failed' ? 'grab-failed'
        : m.check === 'blocked' ? 'dead'
        : m.check === 'error' ? 'check-error'
        : m.check === 'healthy' ? 'standby'
        : 'unfinished';
      const ct = r?.containerType ? `[${r.containerType}${r.video?.videoSize ? ` · ${formatBytes(r.video.videoSize)}` : ''}] ` : '';
      console.log(`${tag}   #${m.index + 1} ${ct}${c.title.substring(0, 60)} [${c.indexerName}] → ${status}`);
    }
    if (deadWrites > 0) saveCacheToDisk();

  } catch (err) {
    if (!controller.signal.aborted) console.error(`${tag} Error:`, err);
    sessionReject(err instanceof Error ? err : new Error(String(err)));
  } finally {
    pool?.destroyAll();
    activeSessions.delete(sessionKey);
    claimedSessions.delete(sessionKey);
    // A run that ends with nothing to play settles its session whatever the way out (an early end such as every
    // Source remembered dead, or a stop), so a press waiting on it goes on at once. Settling twice does nothing.
    if (deferred.resolvedData === undefined) {
      sessionReject(controller.signal.aborted ? new Error('Ultimate-Fallback stopped') : nothingToPlay('Ultimate-Fallback found no Source to play'));
    }
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
