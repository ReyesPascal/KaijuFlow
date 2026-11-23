/**
 * Stream Handler
 * Main stream preparation pipeline with 302 redirect to WebDAV proxy.
 * Handles NZB submission -> job polling -> video discovery -> redirect,
 * with automatic fallback on failure and self-redirect to reset Stremio's timer.
 */

import { Request, Response as ExpressResponse } from 'express';
import { config as globalConfig } from '../config/index.js';
import { pipeline } from 'stream';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import { getActiveBackend, isSourceFailure, type Backend, type BackendSource } from '../backends/index.js';
import { getOrCreateStream, isPreparing, evictReadyByVideoPath, setPrepareFn, cleanupExpiredCache, isVideoPathBroken, markVideoPathBroken, clearVideoPathBroken, type PlaySource } from './streamCache.js';
import { recall, keyOf } from './sourceMemory.js';
import { logPlayed, logPlayFailed } from '../utils/stepTiming.js';
import { getFallbackGroup } from './fallbackManager.js';
import { getDeliveryLog, WebDav404Error, isUltimateFallbackActive } from './utils.js';
import { episodeOf, episodeForTile, playContextOfTile, type PlayContext } from './playContext.js';
import { claimSession, getSessionPromise, getSessionBackups, ultimateFallbackFromCandidates, walkFoundNothing, type UfBackupStream } from './ultimateFallback.js';
import { requireHealthySource } from './playTimeCheck.js';
import { encodeTileEnvelope, parseTilePayload } from './redirectHelpers.js';
import { serveVideo, type InlineProxy } from './delivery.js';
import { keepAlive } from './keepAlive.js';
import { ProxyCircuitAbortError } from '../proxy.js';
import { resolveBaseUrl } from '../utils/urlHelpers.js';
import type { StreamData, FallbackCandidate } from './types.js';

const pipelineAsync = promisify(pipeline);

// Register prepareStream into the cache to break the circular import
// (streamCache needs to call prepareStream, but importing it directly would create a cycle)
setPrepareFn(prepareStream);

// ============================================================================
// Streaming Log Throttle
// ============================================================================
// During fallback processing, the same stream title may trigger multiple
// self-redirects and fallback attempts. Track request counts per stream
// and emit a compact summary every STREAM_LOG_INTERVAL_MS to avoid
// flooding the console with repetitive log lines.

const STREAM_LOG_INTERVAL_MS = 30_000;   // 30 seconds
const STREAM_LOG_STATE_TTL_MS = 3_600_000; // 1 hour — evict stale entries to prevent unbounded growth
// KaijuFlow (AUDIT.md finding 5): on a fresh play request, stop waiting for the
// first source after this long and try the next one. The first source is NOT
// cancelled or marked dead: it keeps preparing in the stream cache, so it is
// ready next time. Only applies when Ultimate Fallback gives a next candidate.
// PTP 1.0.2.1 gives up on a source at ~42 s (30 s soft + 12 s hard), so 25 s
// leaves room for the backup. 0 disables.
// The one exception to "the next Source is prepared only when the one being
// played fails" (#192, owner's decision on #192, 2026-11-20: keep it): a first
// Source still loading after 25 s gets the next one beside it, and whichever is
// ready first plays.
const FIRST_SOURCE_SWITCH_MS = (() => {
  const raw = process.env.PLAY_FIRST_SOURCE_SWITCH_MS;
  const n = raw === undefined || raw === '' ? NaN : Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : 25_000;
})();
const DEDUP_CACHE_TTL_MS = 600_000;      // 10 min — covers a typical play session's seeks/probes without library-check overhead; eviction mid-session self-heals via the broken-path marker + live videoPathExists gate
const LOBBY_LOG_THROTTLE_MS = 15_000; // Suppress repeat "Lobby: serving" lines for one video within this window (matches /stream hit throttle)
// Self-redirects (keepAlive.ts) carry inside the `t` envelope:
//   rc — redirect count: how many self-redirects have occurred (prevents infinite loops)
//   ci — candidate index: which fallback candidate to resume at (avoids restarting from 0)

interface StreamLogState {
  requests: number;
  disconnects: number;
  lastLogAt: number;
  /** True once the first request for this title has been logged in full */
  seenFirst: boolean;
}

const streamLogState = new Map<string, StreamLogState>();
const deadSkipLoggedGroups = new Map<string, number>(); // key → timestamp for TTL cleanup
const lobbyServeLogged = new Map<string, number>(); // videoPath → when the lobby last said it serves it

// Delivery log lives in utils.ts to avoid circular dep between streamCache and streamHandler.
const lastDeliveryLog = getDeliveryLog();

/**
 * Returns true if this request should be logged in detail.
 * Otherwise increments counters and periodically emits a summary line.
 */
function shouldLogStreamRequest(title: string, event: 'request' | 'disconnect'): boolean {
  const now = Date.now();
  let state = streamLogState.get(title);

  if (!state) {
    state = { requests: 0, disconnects: 0, lastLogAt: now, seenFirst: false };
    streamLogState.set(title, state);
  }

  if (event === 'request') state.requests++;
  if (event === 'disconnect') state.disconnects++;

  // Always log the first request in full
  if (!state.seenFirst) {
    state.seenFirst = true;
    state.lastLogAt = now;
    state.requests = 0;
    state.disconnects = 0;
    return true;
  }

  // Emit a summary line every interval
  if (now - state.lastLogAt >= STREAM_LOG_INTERVAL_MS) {
    const reqs = state.requests;
    const discs = state.disconnects;
    state.requests = 0;
    state.disconnects = 0;
    state.lastLogAt = now;
    if (reqs > 0 || discs > 0) {
      console.log(`  \u{1F4CA} Streaming ${title}: ${reqs} request${reqs !== 1 ? 's' : ''}, ${discs} disconnect${discs !== 1 ? 's' : ''} in last ${STREAM_LOG_INTERVAL_MS / 1000}s`);
    }
    // Evict stale entries to prevent unbounded map growth
    for (const [key, s] of streamLogState) {
      if (now - s.lastLogAt > STREAM_LOG_STATE_TTL_MS) streamLogState.delete(key);
    }
    for (const [key, entry] of lastDeliveryLog) {
      if (now - entry.at > STREAM_LOG_STATE_TTL_MS) lastDeliveryLog.delete(key);
    }
    for (const [key, ts] of deadSkipLoggedGroups) {
      if (now - ts > STREAM_LOG_STATE_TTL_MS) deadSkipLoggedGroups.delete(key);
    }
    for (const [key, ts] of lobbyServeLogged) {
      if (now - ts > STREAM_LOG_STATE_TTL_MS) lobbyServeLogged.delete(key);
    }
    return false;
  }

  return false;
}

/**
 * Check if an error represents a client disconnect (seek, stop, navigation).
 * These are normal during video playback and should not be treated as failures.
 */
function isClientDisconnect(error: unknown): boolean {
  const err = error as NodeJS.ErrnoException & { code?: string; message?: string };
  const code = err?.code || '';
  const message = err?.message || '';
  return code === 'ERR_STREAM_PREMATURE_CLOSE'
    || code === 'ECONNABORTED'
    || code === 'ERR_CANCELED'
    || code === 'ECONNRESET'
    || message === 'aborted'
    || message.includes('aborted');
}

// ── Stremio request dedup ────────────────────────────────────────────
// Caches successful deliveries for 10 min to deduplicate Stremio's rapid
// sequential requests (catalog browse → detail → play → range) and to
// short-circuit seeks in inline-proxy mode so they skip library check.
// Completely outside the cache pipeline — doesn't interfere with library checks.

// It holds the video, not the Delivery method: every request is served with the method as it is now (#248).
interface CachedDelivery { streamData: StreamData; timestamp: number; played: FallbackCandidate }
const recentDeliveries = new Map<string, CachedDelivery>();

function cleanupRecentDeliveries(): void {
  const now = Date.now();
  for (const [key, entry] of recentDeliveries) {
    if (now - entry.timestamp > DEDUP_CACHE_TTL_MS) recentDeliveries.delete(key);
  }
}

/** Entries (address and `t` payload) whose `played` line went out in the last 15 s: one line per press, not per Range
 *  probe or seek. Each list's entries have their own payload, so every press from a new list writes its line. */
const playedLogged = new Set<string>();
const PLAYED_LOG_TTL_MS = 15_000;

/** The press's `played` step line (#242): this Source's video is served now. */
function logPlayedOnce(req: Request, source: { title: string; indexerName?: string }): void {
  const entry = `${req.params.filename ?? '-'}::${typeof req.query.t === 'string' ? req.query.t : ''}::${source.title}`;
  if (playedLogged.has(entry)) return;
  playedLogged.add(entry);
  setTimeout(() => playedLogged.delete(entry), PLAYED_LOG_TTL_MS).unref?.();
  logPlayed(source.title, source.indexerName);
}

/** The lobby's line for a press of Best it serves, once per video in LOBBY_LOG_THROTTLE_MS (range probes and seeks repeat it). */
function logLobbyServe(sessionKey: string, videoPath: string): void {
  const now = Date.now();
  const last = lobbyServeLogged.get(videoPath);
  if (last !== undefined && now - last < LOBBY_LOG_THROTTLE_MS) return;
  lobbyServeLogged.set(videoPath, now);
  console.log(last === undefined ? `👑 Lobby: serving Ultimate-Fallback result for ${sessionKey}` : `👑 Lobby: cached resolve served (sk=${sessionKey})`);
}

// ============================================================================
// Stream Preparation Pipeline
// ============================================================================

/**
 * Complete stream preparation pipeline:
 * 0. Already prepared on the Backend, or remembered ready (and its first byte still served)?
 * 1. Play-time check (when on): only a healthy Source goes on
 * 2. Hand the Source to the Backend and wait for its video
 * 3. Probe the first byte
 */
export async function prepareStream(playSource: PlaySource, play?: PlayContext, logPrefix = ''): Promise<StreamData> {
  const { nzbUrl, title, isSeasonPack, indexerName, searchExitIp } = playSource;
  const contentType = play?.type || undefined;
  // The Backend is sent the file pattern, which for a daily show also finds the file named by its aired date.
  const episodePattern = episodeOf(play).filePattern;
  const backend = getActiveBackend();
  const source: BackendSource = { nzbUrl, title, contentType, episodePattern, episodesInSeason: play?.episodesInSeason, isSeasonPack, indexerName, searchExitIp };
  const budgetStart = Date.now();

  console.log(`\n${logPrefix}\u{1F3AC} Preparing stream (${backend.label}): ${title}${episodePattern ? ` (selecting ${episodePattern})` : ''} [${contentType || 'unknown'}] \u23F1\uFE0F no limit`);

  // Step 0: Already prepared? Authoritative freshness signal for
  // already-downloaded content. Runs unconditionally: it's the primary defense
  // against re-submitting a Source whose video already exists on the Backend,
  // and against serving stale in-memory cache paths (readyCache) after the
  // Backend evicts content.
  const existing = await backend.findPrepared(source, { logPrefix });
  if (existing) {
    if (isVideoPathBroken(existing.videoPath)) {
      console.log(`${logPrefix}\u{1F6AB} Prepared video skipped (video path broken): ${existing.videoPath}`);
    } else {
      console.log(`${logPrefix}\u2705 Stream ready (${backend.label}, already prepared): ${title}\n`);
      return existing;
    }
  }

  // Reuse what the Backend already made for the Source (the Source memory) when it is still there.
  // The probe is the freshness check here (stillPrepared would send the same request).
  const { ready } = recall(playSource, play);
  if (ready && !isVideoPathBroken(ready.videoPath)) {
    try {
      await backend.probe(ready, { logPrefix, title, source: indexerName });
      console.log(`${logPrefix}\u2705 Stream ready (${backend.label}, reused): ${title}\n`);
      return ready;
    } catch (err) {
      markVideoPathBroken(ready.videoPath);
      if (!isSourceFailure(err)) throw err;
    }
  }

  // Steps 1-3: hand the Source to the Backend and wait for its video, with no time limit of KaijuFlow's
  // (AltMount's prepare timeout is the limit; keep-alive answers the player meanwhile).
  // Play-time check (#190): a Source is checked before the Backend gets it, never handed over unchecked.
  // It is the only health check since #191, so it runs whatever the fallback setting.
  await requireHealthySource(source, logPrefix);

  const video = await backend.prepare(source, { logPrefix });

  // Step 4: Verify the video is actually servable (first byte).
  try {
    await backend.probe(video, { logPrefix, title, source: indexerName });
  } catch (err) {
    markVideoPathBroken(video.videoPath);
    throw err;
  }

  const totalElapsed = Math.round((Date.now() - budgetStart) / 1000);
  console.log(`${logPrefix}\u2705 Stream ready (${backend.label}): ${title} (${totalElapsed}s total)\n`);

  clearVideoPathBroken(video.videoPath);
  return video;
}

// ============================================================================
// Failure Video
// ============================================================================

const FAILURE_VIDEO_PATH = path.resolve(
  fs.existsSync(path.resolve('ui/dist/nzb_failure_video.mp4'))
    ? 'ui/dist/nzb_failure_video.mp4'
    : 'ui/public/nzb_failure_video.mp4'
);

/**
 * Serve the failure video (a 3-hour static "Stream Unavailable" screen).
 * The extreme duration ensures Stremio never considers the episode "completed"
 * so it won't mark it as watched or auto-advance to the next episode.
 */
async function sendFailureVideo(req: Request, res: ExpressResponse): Promise<void> {
  try {
    const stat = fs.statSync(FAILURE_VIDEO_PATH);
    const fileSize = stat.size;

    res.setHeader('Content-Type', 'video/mp4');
    res.setHeader('Accept-Ranges', 'bytes');

    if (req.headers.range) {
      const match = req.headers.range.match(/bytes=(\d+)-(\d*)/);
      if (match) {
        const start = parseInt(match[1]);
        // Clients (ExoPlayer especially) probe ahead with ranges past EOF.
        // Out-of-range starts must answer 416, not throw on a negative
        // Content-Length. Clamp end when the requested upper bound exceeds
        // the file so 0-N requests with N >= fileSize still serve cleanly.
        if (start >= fileSize) {
          res.status(416);
          res.setHeader('Content-Range', `bytes */${fileSize}`);
          res.end();
          return;
        }
        const end = match[2] ? Math.min(parseInt(match[2]), fileSize - 1) : fileSize - 1;
        res.status(206);
        res.setHeader('Content-Range', `bytes ${start}-${end}/${fileSize}`);
        res.setHeader('Content-Length', end - start + 1);
        const readStream = fs.createReadStream(FAILURE_VIDEO_PATH, { start, end });
        try {
          await pipelineAsync(readStream, res);
        } catch (err) {
          if ((err as NodeJS.ErrnoException).code !== 'ERR_STREAM_PREMATURE_CLOSE') {
            console.error('\u274C Failure video stream error:', err);
          }
        }
        return;
      }
    }

    res.status(200);
    res.setHeader('Content-Length', fileSize);
    const readStream = fs.createReadStream(FAILURE_VIDEO_PATH);
    try {
      await pipelineAsync(readStream, res);
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== 'ERR_STREAM_PREMATURE_CLOSE') {
        console.error('\u274C Failure video stream error:', err);
      }
    }
  } catch (fileErr) {
    console.error('\u274C Failed to serve failure video:', fileErr);
    if (!res.headersSent) res.status(500).end();
  }
}

// ============================================================================
// Express Handler
// ============================================================================

/** Key for Stremio request dedup: the Backend, and the Source as the play asks for it (the Source memory's key). */
function dedupKey(backend: Backend, candidate: { nzbUrl: string; title: string }, play?: PlayContext): string {
  return `${backend.id}|${keyOf(candidate, play)}`;
}

/**
 * Express handler for /play/stream endpoint
 * Supports automatic fallback: if the chosen NZB fails, tries the next candidates
 * from the fallback group until one succeeds or all are exhausted.
 */
export async function handleStream(
  req: Request,
  res: ExpressResponse,
  proxyFn?: InlineProxy,
): Promise<void> {
  const backend = getActiveBackend();
  // Express returns string[] for repeated query keys (`?t=a&t=b`). Take the
  // most recent so the decoder treats it as a single string. Catches
  // accidental client double-set; not expected on the happy path.
  if (Array.isArray(req.query.t)) {
    const arr = req.query.t as unknown[];
    req.query.t = arr[arr.length - 1] as any;
  }

  // Tile URL is a single base64url-JSON envelope under `?t=`. iOS / Infuse
  // handoff truncates URLs at the first `&`, so all tile state is packed
  // into one query param. The envelope schema differs per tile type
  // (regular result tile vs UF lobby tile) but the encoding mechanism is
  // uniform; `parseTilePayload` runs all per-field type guards in one place
  // and returns a typed object the handler destructures cleanly.
  let nzbUrl: string;
  let title: string;
  let indexerName: string;
  let fallbackGroupId: string | undefined;
  let contentType: string | undefined;
  // What this play is for (#246): the play context the list made, from its fallback group, or what the tile carries.
  let play: PlayContext | undefined;
  let tPackSessionKey: string | undefined;
  let tPackSp: string | undefined;
  let tPackUserPick = false;
  let tPackRc: number | undefined;
  let tPackCi: number | undefined;
  // Search-time exit IP sourced from the FBG candidate (if `idx` points to one)
  // or the envelope's `ip` field. Hydrates the sentinel candidate built below so
  // verifyProxyCircuit has a baseline when the FBG is missing (UF disabled, no
  // `fbg` in URL, or group TTL expired).
  let tPackSearchExitIp: string | undefined;
  const isUfTilePath = req.params.filename === 'ultimate-fallback';
  const payload = parseTilePayload(typeof req.query.t === 'string' ? req.query.t : undefined);
  fallbackGroupId = payload.fbg;
  tPackSessionKey = payload.sk;
  tPackRc = payload.rc;
  tPackCi = payload.ci;
  if (isUfTilePath) {
    // UF tile carries only sk + fbg (+ rc/ci on redirect). The lobby block
    // below uses sessionKey to find an existing UF session promise.
    nzbUrl = '';
    title = '';
    indexerName = '';
    play = fallbackGroupId ? getFallbackGroup(fallbackGroupId)?.context : undefined;
    contentType = play?.type;
  } else {
    // Regular result tile. fbg+idx points into the in-memory fallback group;
    // url/title/indexer ride along as fallbacks for when the group has been
    // evicted (TTL elapsed) so a single-shot resolution is still possible.
    const group = fallbackGroupId ? getFallbackGroup(fallbackGroupId) : undefined;
    const cand = payload.idx !== undefined && group ? group.candidates[payload.idx] : undefined;
    nzbUrl = cand?.nzbUrl ?? payload.url ?? '';
    title = cand?.title ?? payload.title ?? '';
    indexerName = cand?.indexerName ?? payload.indexer ?? '';
    play = group?.context ?? playContextOfTile(payload);
    contentType = group?.context.type ?? payload.ty;
    tPackSearchExitIp = cand?.searchExitIp ?? payload.ip;
    tPackSp = payload.seasonpack === 1 ? '1' : undefined;
    tPackUserPick = true;
  }
  const userPick = tPackUserPick;
  const sessionKey = tPackSessionKey;

  // UF tile clicks send only `sk` (no nzb/title) and rely on the lobby block below.
  // Regular requests must still provide nzb+title.
  const isUfTileRequest = !userPick && !!sessionKey && !nzbUrl && isUltimateFallbackActive();
  if (!isUfTileRequest && (!nzbUrl || !title)) {
    res.status(400).send('Missing required parameters: nzb, title');
    return;
  }

  const streamStartTime = Date.now();

  // The episode this play is for (e.g. "S02E05"), and for a daily show the file named by its aired date: the
  // file picker in a season pack matches either.
  const isSeasonPackRequest = (tPackSp ?? req.query.sp) === '1';

  // Build the list of candidates to try (primary first, then fallbacks).
  // Skip the initial candidate when nzbUrl/title are empty (UF tile request case):
  // a sentinel with empty fields would cause prepareStream to scan the library root
  // if it survived past the fbg-expansion block (e.g. when fbg is set but the group
  // has expired).
  const candidates: FallbackCandidate[] = [];
  if (nzbUrl && title) {
    candidates.push({ nzbUrl, title, indexerName, isSeasonPack: isSeasonPackRequest, searchExitIp: tPackSearchExitIp });
  }

  const fallbackEnabled = isUltimateFallbackActive();

  // Check whether this request should produce detailed logs.
  // During fallback processing, a single stream title may generate multiple
  // self-redirect requests. shouldLogStreamRequest returns true for the
  // first request and then emits a compact summary every 30 s.
  const verbose = shouldLogStreamRequest(title, 'request');

  if (fallbackGroupId && fallbackEnabled) {
    const group = getFallbackGroup(fallbackGroupId);
    if (group) {
      // Walk from clicked index through end of group, then wrap to top through
      // clicked-1 — every untried candidate gets a turn. Same wrap-from-clicked
      // walk for both userPickFallback='fallback-chain' and 'uf-lobby' modes.
      candidates.length = 0;
      const clickedIdx = group.candidates.findIndex(
        c => c.nzbUrl === nzbUrl && c.title === title
      );
      if (clickedIdx >= 0) {
        candidates.push(...group.candidates.slice(clickedIdx));
        candidates.push(...group.candidates.slice(0, clickedIdx));
      } else {
        // Clicked NZB not found in group — push sentinel (skip empty for UF tile
        // requests) + all group candidates so the chain still has something to walk.
        if (nzbUrl && title) candidates.push({ nzbUrl, title, indexerName, isSeasonPack: isSeasonPackRequest, searchExitIp: tPackSearchExitIp });
        candidates.push(...group.candidates);
      }
      if (verbose) console.log(`🔄 Fallback group loaded: ${candidates.length} candidates`);
    }
  }

  // A failed list entry walks on through the whole list (#190; its attempts cap was deleted in #228).
  const maxCandidates = fallbackEnabled ? candidates.length : 1;
  // rc/ci are read first from the in-`t` envelope (so they survive iOS handoff
  // truncation). safeNum guards against NaN leaking from a malformed in-`t`
  // value (parseTilePayload drops non-numbers, but defense-in-depth here).
  const safeNum = (n: number | undefined): number | undefined =>
    typeof n === 'number' && !Number.isNaN(n) && n >= 0 ? n : undefined;
  const redirectCount = safeNum(tPackRc) ?? 0;
  // The time this request may keep the player waiting, and its self-redirect (#248).
  const keep = keepAlive(req, redirectCount, streamStartTime);
  const candidateStart = maxCandidates > 0
    ? Math.min(Math.max(0, safeNum(tPackCi) ?? 0), maxCandidates - 1)
    : 0;
  if (redirectCount > 0 || candidateStart > 0) {
    console.log(`📦 Decoded rc=${redirectCount} ci=${candidateStart} from t-envelope`);
  }
  // Evict expired entries once before the loop
  cleanupExpiredCache();
  cleanupRecentDeliveries();

  // Stremio dedup: return cached delivery for subsequent requests on the same stream (within 10 min).
  // Catches seeks, probes, and dupes without re-running library check or re-submitting NZBs.
  // Only for fresh initial requests; self-redirects (ci > 0) bypass dedup to allow fallback retry.
  // Cache stores the *resolved* delivery (which may differ from the clicked NZB when fallback-chain
  // walked past the click), so we don't gate on the clicked NZB's dead state; the cache hit is
  // already a known-good resolution.
  const isFreshRequest = candidateStart === 0;
  if (isFreshRequest && candidates.length > 0 && !isUfTileRequest) {
    {
      const key = dedupKey(backend, candidates[0], play);
      const cached = recentDeliveries.get(key);
      if (cached
        && Date.now() - cached.timestamp < DEDUP_CACHE_TTL_MS
        && !isVideoPathBroken(cached.streamData.videoPath)
        && await backend.stillPrepared(cached.streamData.videoPath)) {
        // Serve dupes / seeks / probes using the cached videoPath — no re-prep,
        // no library check, no submission. If the file is gone we fall through
        // to a fresh candidate loop via the live videoPathExists gate above.
        if (verbose) console.log(`📦 Stream dedup hit (delivered ${Math.round((Date.now() - cached.timestamp) / 1000)}s ago)`);
        logPlayedOnce(req, cached.played);
        await serveVideo(req, res, cached.streamData, proxyFn);
        return;
      }
    }
  }

  // ── Ultimate-Fallback Lobby ─────────────────────────────────────────
  // When Ultimate-Fallback is active and the user didn't explicitly pick a
  // stream tile (user_pick=1), await its session promise instead of starting
  // our own Backend submission. Self-redirect keeps ExoPlayer alive.
  // Set when Best's Walk ended with no Source to play (GLOSSARY: Walk): the press then shows the failure video, it
  // does not walk the list a second time (#228).
  let walkFoundNoSource = false;
  if (!userPick && isUltimateFallbackActive() && sessionKey) {
    // No session for this title (no Head start: off, stopped by a newer list request, or a player that only
    // asks at play): Best starts here, so the await-flow below picks up the new session promise.
    if (!getSessionPromise(sessionKey)) {
      const group = fallbackGroupId ? getFallbackGroup(fallbackGroupId) : undefined;
      if (!group?.candidates?.length) {
        console.log(`👑 UF tile click but no fallback group (sk=${sessionKey}, fbg=${fallbackGroupId}) — falling through`);
      } else {
        console.log(`👑 UF fired on tile click [${sessionKey}]`);
        // Its Walk reads the list's play context, so it looks for the episode the Head start would have (#246).
        ultimateFallbackFromCandidates(group.context, group.candidates, globalConfig.ultimateFallback!).catch(err => console.error('❌ Ultimate-Fallback error (on-tile-selection):', err));
      }
    }
    const sessionPromise = getSessionPromise(sessionKey);
    // This press waits on the session: a newer list request no longer stops it (#206).
    claimSession(sessionKey);
    if (sessionPromise) {
      try {
        const waited = await keep.wait(sessionPromise);
        if (!waited.done) {
          // Still walking when this request's time is up: a self-redirect keeps the player waiting.
          keep.redirect(res);
          return;
        }
        const streamData = waited.value;

        // Verify the cached primary still exists on the Backend before serving. The broken-path marker short-circuits
        // when /v has just observed a 4xx/5xx (PROPFIND lies for evicted content
        // whose directory entry persists). Falls through to UF backups / fresh
        // resolution if either signal says the file is gone.
        if (isVideoPathBroken(streamData.videoPath) || !await backend.stillPrepared(streamData.videoPath)) {
          throw new Error('Primary path no longer available');
        }

        // Ultimate-Fallback resolved — deliver the stream
        logLobbyServe(sessionKey, streamData.videoPath);
        if (streamData.sourceTitle) {
          const fromGroup = fallbackGroupId ? getFallbackGroup(fallbackGroupId)?.candidates.find(c => c.title === streamData.sourceTitle) : undefined;
          logPlayedOnce(req, { title: streamData.sourceTitle, indexerName: fromGroup?.indexerName });
        }
        await serveVideo(req, res, streamData, proxyFn);
        return;
      } catch (err) {
        // Two reasons we land here:
        //   1. Primary path went dead mid-session — the UF tile block below
        //      iterates the session's vetted backups and serves the next one.
        //   2. Session promise rejected (all candidates exhausted) — no
        //      backups to fall back to; the single-attempt path below kicks in.
        // The "primary path no longer available" message already logged the
        // first case; only log here for the second.
        walkFoundNoSource = walkFoundNothing(err);
        if ((err as Error).message !== 'Primary path no longer available') {
          console.log(`👑 Lobby: session ended without resolution — falling through to single attempt`);
        }
      }
    }
  }

  // UF tile request (no nzb/title in URL). If the Lobby's primary is unavailable,
  // iterate the session's UF-vetted backup streams and serve the first whose
  // videoPath still exists on the Backend — no candidate loop, no re-submit, no TTL
  // coupling. /v's _fb param bounces back to this tile URL on mid-stream break,
  // which re-enters here and picks the next backup (previous now missing).
  if (isUfTileRequest) {
    const ufBackups = sessionKey ? getSessionBackups(sessionKey) : null;
    let usable: UfBackupStream | undefined;
    for (const b of ufBackups?.backupStreams ?? []) {
      if (isVideoPathBroken(b.videoPath)) continue;
      if (await backend.stillPrepared(b.videoPath)) { usable = b; break; }
    }
    if (usable) {
      const idxTag = usable.candidateIndex !== undefined ? `#${usable.candidateIndex} ` : '';
      console.log(`👑 Ultimate-Fallback [${sessionKey}] Primary path no longer available — falling back to backup: ${idxTag}${usable.title} [${usable.indexerName}]`);
      await serveVideo(req, res, usable, proxyFn);
      return;
    }
    if (walkFoundNoSource) {
      console.log(`👑 UF tile: Best's Walk found no Source to play (sk=${sessionKey}) — serving failure video`);
      await sendFailureVideo(req, res);
      return;
    }
    // Fall-through: after UF-vetted backups exhausted, redirect to the first
    // untried fallback-group candidate. Encoded as the canonical tile
    // envelope so the handler's user-pick path takes over (presence of
    // url/title/indexer in the payload implies user-pick); sequential
    // iteration walks the rest of the chain in one handleStream invocation,
    // skipping broken candidates via prepareStream's library-pre-check + dedup.
    const groupForFallthrough = fallbackGroupId ? getFallbackGroup(fallbackGroupId) : undefined;
    const triedUrls = ufBackups?.backupUrls ?? new Set<string>();
    const nextCandidate = (groupForFallthrough?.candidates ?? []).find(c => !triedUrls.has(c.nzbUrl));
    if (nextCandidate && groupForFallthrough) {
      const remaining = groupForFallthrough.candidates.filter(c => !triedUrls.has(c.nzbUrl)).length;
      const filename = encodeURIComponent(nextCandidate.title || 'stream');
      const fallthroughT = encodeTileEnvelope({
        url: nextCandidate.nzbUrl,
        title: nextCandidate.title,
        indexer: nextCandidate.indexerName,
        // Carry the resolved type so a UF-enabled install whose fallback group
        // is later evicted still files this candidate under the right category.
        ...(contentType === 'movie' || contentType === 'series' ? { ty: contentType } : {}),
        ...(fallbackGroupId ? { fbg: fallbackGroupId } : {}),
        ...(sessionKey ? { sk: sessionKey } : {}),
        ...(nextCandidate.isSeasonPack ? episodeForTile(groupForFallthrough.context) : {}),
      });
      const fallthroughUrl = new URL(`${resolveBaseUrl(req)}${req.baseUrl}/stream/${filename}?t=${fallthroughT}`);
      console.log(`👑 UF tile: ${ufBackups?.backupStreams?.length ?? 0} UF backup(s) exhausted — falling through to fallback group (${remaining} candidate(s) remaining)`);
      res.redirect(302, fallthroughUrl.href);
      return;
    }

    const backupCount = ufBackups?.backupStreams?.length ?? 0;
    const sessionExists = sessionKey ? getSessionPromise(sessionKey) !== null : false;
    if (backupCount > 0) {
      console.log(`👑 UF tile: ${backupCount} backup(s) checked but all broken — serving failure video`);
    } else if (sessionExists) {
      console.log(`👑 UF tile: session active but no backups produced (sk=${sessionKey}) — serving failure video`);
    } else {
      console.log(`👑 UF tile: no session for sk=${sessionKey} (expired or never triggered) — serving failure video`);
    }
    await sendFailureVideo(req, res);
    return;
  }

  const deadSkipKey = fallbackGroupId || nzbUrl;
  const logDeadSkips = !deadSkipLoggedGroups.has(deadSkipKey);

  // Build candidate order.
  // user_pick + UF enabled: honor the click, try only that NZB, fall into UF lobby on failure.
  // Otherwise (UF tile click / lobby fall-through): prefer UF's pre-vetted backups, then
  // resume sequential from after the last vetted URL.
  const ufLobbyAvailable = isUltimateFallbackActive();
  const sessionBackups = sessionKey ? getSessionBackups(sessionKey) : null;
  // What a failed list entry does: walk on down the list (the default, #190) or fall into the Best entry.
  const userPickMode = globalConfig.ultimateFallback?.userPickFallback ?? 'fallback-chain';
  if (userPick && redirectCount === 0) {
    console.log(`🎯 User-pick attempt: userPickFallback=${userPickMode}, sk=${sessionKey || 'none'}, fbg=${fallbackGroupId || 'none'}`);
  }
  const candidateOrder: number[] = [];
  if (userPick && ufLobbyAvailable && userPickMode !== 'fallback-chain') {
    candidateOrder.push(candidateStart);
  } else if (userPick && userPickMode === 'fallback-chain') {
    // Walk results from clicked through end. Skip the vetted-backup-priority
    // branch — sequential order is what the user opted into.
    for (let i = candidateStart; i < maxCandidates; i++) candidateOrder.push(i);
  } else if (sessionBackups?.backupUrls?.size && candidates.length > 0) {
    for (let i = candidateStart; i < maxCandidates; i++) {
      if (sessionBackups.backupUrls.has(candidates[i].nzbUrl)) candidateOrder.push(i);
    }
    const lastVettedIdx = sessionBackups.lastVettedUrl
      ? candidates.findIndex(c => c.nzbUrl === sessionBackups.lastVettedUrl)
      : -1;
    for (let i = Math.max(candidateStart, lastVettedIdx + 1); i < maxCandidates; i++) {
      if (!sessionBackups.backupUrls.has(candidates[i].nzbUrl)) candidateOrder.push(i);
    }
  } else {
    for (let i = candidateStart; i < maxCandidates; i++) candidateOrder.push(i);
  }

  /** Serve a Source's video, and remember the delivery for Stremio's next requests of the play (dedup). */
  const deliver = async (candidate: FallbackCandidate, streamData: StreamData): Promise<void> => {
    // A disconnected player got no video, so do not remember the delivery or say it played.
    if (req.socket.destroyed) return;
    // Cache delivery for Stremio request dedup (10 min TTL) — populated BEFORE
    // delivery so concurrent probes from Stremio land on the dedup path instead
    // of triggering another prep.
    // Key on candidates[0] (the URL the client requested) so subsequent client
    // requests for the same click hit dedup, even when fallback-chain walked
    // past the click and resolved a later candidate.
    const dedupCandidate = candidates[0] ?? candidate;
    recentDeliveries.set(dedupKey(backend, dedupCandidate, play), { streamData, timestamp: Date.now(), played: candidate });
    // Also key on the resolved candidate's URL so direct second-clicks of the
    // resolved tile (different click URL) also dedup.
    if (candidate !== dedupCandidate) {
      recentDeliveries.set(dedupKey(backend, candidate, play), { streamData, timestamp: Date.now(), played: candidate });
    }
    logPlayedOnce(req, candidate);
    await serveVideo(req, res, streamData, proxyFn);
  };

  // The first Source the first-Source switch left preparing (#192), to go back to if every later one fails.
  let warming: number | undefined;
  let circuitAborted = false;

  for (const i of candidateOrder) {
    // Stop processing if the client disconnected (user backed out)
    if (req.socket.destroyed) {
      console.log(`🔌 Client disconnected — stopping fallback loop at [${i + 1}/${maxCandidates}]`);
      return;
    }

    const candidate = candidates[i];

    // Skip candidates already known to be dead.
    if (recall(candidate, play).dead) {
      if (logDeadSkips) console.log(`\u23ED\uFE0F Source memory (dead, skipped) [${i + 1}/${maxCandidates}]: ${candidate.title}`);
      continue;
    }

    // Mark dead-skip logs as shown for this group so subsequent requests don't repeat
    if (logDeadSkips) deadSkipLoggedGroups.set(deadSkipKey, Date.now());

    // This request's time is up before the next Source starts: start it, so it is warming while the
    // player follows the self-redirect, which resumes at this Source (ci).
    if (keep.timeUp() && !req.socket.destroyed) {
      if (!isPreparing(candidate, play)) {
        getOrCreateStream(candidate, play, { verbose }).catch(() => {});
      }
      keep.redirect(res, i);
      return;
    }

    try {
      if (i > 0) {
        console.log(`🔄 Trying backup [${i + 1}/${maxCandidates}]: ${candidate.title} [${candidate.indexerName}]`);
      }

      // The first-Source switch (#192): on a play's first request, the first Source with a next one behind it
      // (candidateOrder holds one entry when the user's mode doesn't walk on) is waited for up to
      // FIRST_SOURCE_SWITCH_MS, then the next is tried; the first keeps preparing in the stream cache.
      const switchAtMs = redirectCount === 0 && FIRST_SOURCE_SWITCH_MS > 0 && i === candidateOrder[0] && candidateOrder.length > 1
        ? Math.max(0, FIRST_SOURCE_SWITCH_MS - (Date.now() - streamStartTime))
        : undefined;
      const waited = await keep.wait(getOrCreateStream(candidate, play, { verbose }), switchAtMs);
      if (!waited.done) {
        if (waited.timeUp) {
          // Still preparing when this request's time is up: a self-redirect resumes at this Source.
          if (!req.socket.destroyed) keep.redirect(res, i);
          return;
        }
        // Not a failure: leave it warming, don't mark it dead, try the next.
        console.log(`⏩ Still preparing after ${Math.round(FIRST_SOURCE_SWITCH_MS / 1000)}s, trying next source (kept warming) [${i + 1}/${maxCandidates}]: ${candidate.title}`);
        warming = i;
        continue;
      }
      const streamData = waited.value;

      if (i > 0) {
        console.log(`👑 Backup stream loaded [${i + 1}/${maxCandidates}]: ${candidate.title} [${candidate.indexerName}]`);
      }

      await deliver(candidate, streamData);
      return;

    } catch (error) {
      // Proxy circuit aborted (VPN IP changed / baseline unavailable / etc.) -
      // every remaining candidate in the local array carries the same stale
      // searchExitIp hash and would abort identically. Break the walk; the
      // natural fall-through serves the failure video.
      if (error instanceof ProxyCircuitAbortError) {
        console.error(`🔒 🚫 Proxy circuit aborted mid-stream, stopping candidate walk. ${error.message}`);
        circuitAborted = true;
        break;
      }
      if (isClientDisconnect(error)) {
        shouldLogStreamRequest(candidate.title, 'disconnect');
        return;
      }

      // WebDAV 404 during inline proxy — evict stale cache, loop continues to next candidate
      if (error instanceof WebDav404Error) {
        evictReadyByVideoPath((error as WebDav404Error).videoPath);
      }

      const err = error as Error;
      console.error(`\u274C Stream failed [${i + 1}/${maxCandidates}] ${candidate.title}: ${err.message}`);
      logPlayFailed(candidate.title, candidate.indexerName, err);

      // User-pick failure: fall straight into the UF lobby instead of walking the candidate chain.
      // The user explicitly chose this NZB; when it fails, UF's pre-vetted pool is the fallback.
      if (
        userPick
        && sessionKey
        && isUltimateFallbackActive()
        && userPickMode === 'uf-lobby'
        && keep.canRedirect()
        && !res.headersSent
      ) {
        // Site 4 of 6: build a fresh UF envelope so sk + fbg + rc all survive
        // iOS handoff (single `t` query param, no `&` after the path).
        const lobbyT = encodeTileEnvelope({
          sk: sessionKey,
          ...(fallbackGroupId ? { fbg: fallbackGroupId } : {}),
          rc: redirectCount + 1,
        });
        const lobbyUrl = new URL(`${resolveBaseUrl(req)}${req.baseUrl}/stream/ultimate-fallback?t=${lobbyT}`);
        console.log(`👑 User-pick failed — redirecting to UF lobby (rc=${redirectCount + 1})`);
        res.redirect(302, lobbyUrl.href);
        return;
      }
    }
  }

  // Every Source after the first-Source switch failed, while the first is still preparing (or became ready
  // meanwhile): go back to it instead of the failure video. Wait for it in this request's time, else a
  // self-redirect resumes at it.
  if ((candidateStart > 0 || warming !== undefined) && !circuitAborted && !res.headersSent && !req.socket.destroyed) {
    const first = candidates[0];
    const recalled = recall(first, play);
    if (!recalled.dead && (isPreparing(first, play) || (recalled.ready && !isVideoPathBroken(recalled.ready.videoPath)))) {
      console.log(`↩️ Every later Source failed: back to the first Source, still usable [1/${maxCandidates}]: ${first.title}`);
      try {
        const waited = await keep.wait(getOrCreateStream(first, play, { verbose }));
        if (!waited.done) {
          if (!req.socket.destroyed) keep.redirect(res, 0);
          return;
        }
        await deliver(first, waited.value);
        return;
      } catch (error) {
        if (isClientDisconnect(error)) return;
        console.error(`❌ Stream failed [1/${maxCandidates}] ${first.title}: ${(error as Error).message}`);
        logPlayFailed(first.title, first.indexerName, error);
      }
    }
  }

  // User-pick loop exhausted without serving (e.g. the clicked NZB was dead-cached and
  // `continue`d past the catch-block's lobby redirect). Fall into the UF lobby as the
  // final fallback before the failure video. Only fires when userPickFallback='uf-lobby'.
  if (
    userPick
    && sessionKey
    && isUltimateFallbackActive()
    && userPickMode === 'uf-lobby'
    && keep.canRedirect()
    && !res.headersSent
  ) {
    // Site 5 of 6: same fresh-envelope pattern as site 4.
    const lobbyT = encodeTileEnvelope({
      sk: sessionKey,
      ...(fallbackGroupId ? { fbg: fallbackGroupId } : {}),
      rc: redirectCount + 1,
    });
    const lobbyUrl = new URL(`${resolveBaseUrl(req)}${req.baseUrl}/stream/ultimate-fallback?t=${lobbyT}`);
    console.log(`👑 User-pick exhausted — redirecting to UF lobby (rc=${redirectCount + 1})`);
    res.redirect(302, lobbyUrl.href);
    return;
  }

  // All candidates exhausted -- serve the 3-hour failure video. The long duration
  // ensures Stremio never considers the episode "completed", so it won't mark it
  // as watched or auto-advance to the next episode. The user sees the
  // "Stream Unavailable" message and goes back to the stream list manually.
  console.error(`\u274C All ${maxCandidates} candidate(s) exhausted, serving failure video`);
  if (!res.headersSent) {
    await sendFailureVideo(req, res);
  }
}
