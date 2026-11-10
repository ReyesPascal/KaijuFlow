/**
 * AltMount Backend (spec #16). #18: settings and reachability check.
 * #19: movie Sources. The selected NZB goes to AltMount's stream route
 * (POST /api/nzb/streams, as an uploaded file); its answer names the media's virtual path,
 * which is the media identity (`videoPath`) everywhere in KaijuFlow. Media is
 * fetched from AltMount's file route with the download key kept server side.
 * #21: TV. Season and episode go to AltMount as form fields, so a season pack
 * plays the requested episode.
 * Not yet: library reuse, cancel.
 */

import { config as globalConfig } from '../config/index.js';
import { createHash } from 'node:crypto';
import { ALTMOUNT_CAPABILITIES } from './capabilities.js';
import { kindOfStatus, kindOfFetchError, firstByteKeptError, logFirstByteFailure, type FirstByteKind } from './firstByte.js';
import { grabSourceNzb } from './sourceNzb.js';
import { timeStep } from '../utils/stepTiming.js';
import { VIDEO_EXTENSIONS } from '../health/fileClassifier.js';
import { PrepareCancelledError, isSourceFailure, sourceFailure, type Backend, type BackendStatus, type MediaRequest, type PreparedVideo } from './types.js';

const TEST_CONNECTION_TIMEOUT_MS = 15_000;
const PROBE_TIMEOUT_MS = 10_000;
const PROBE_RETRY_DELAY_MS = 2_000;
const PROBE_MAX_ATTEMPTS = 2;
/** Extra time past AltMount's own wait before KaijuFlow gives up on the HTTP call. */
const SUBMIT_GRACE_MS = 30_000;

export interface AltmountSettings {
  url?: string;
  apiKey?: string;
  category?: string;
  prepareTimeoutSec?: number;
}

/** Saved AltMount settings. */
export function buildAltmountSettings(): AltmountSettings {
  return {
    url: globalConfig.altmountUrl,
    apiKey: globalConfig.altmountApiKey,
    category: globalConfig.altmountCategory,
    prepareTimeoutSec: globalConfig.altmountPrepareTimeout,
  };
}

const fail = (httpStatus: number, message: string): BackendStatus => ({ ok: false, httpStatus, message });

/**
 * Reachability and setup check. Calls AltMount's stream route with the API key
 * and no NZB: a configured AltMount answers with a request error (400/422)
 * after it has accepted the key, so nothing is queued.
 */
async function testAltmountConnection(settings: AltmountSettings): Promise<BackendStatus> {
  const { url, apiKey, category } = settings;
  if (!url) return fail(400, 'AltMount URL is required');
  if (!apiKey) return fail(400, 'AltMount API key is required');
  let target: string;
  try {
    target = new URL('/api/nzb/streams', url).toString();
  } catch {
    return fail(400, 'AltMount URL is not a valid URL');
  }
  try {
    const form = new FormData();
    form.append('category', category || 'kaijuflow');
    const res = await fetch(target, {
      method: 'POST',
      headers: { 'X-Api-Key': apiKey },
      body: form,
      signal: AbortSignal.timeout(TEST_CONNECTION_TIMEOUT_MS),
    });
    // Handler order (AltMount v0.4.0): integration off -> 404, config not loaded -> 503,
    // bad key -> 401, no NZB in the request -> 400 (key accepted, nothing queued).
    if (res.status === 401 || res.status === 403) {
      return fail(502, 'AltMount rejected the API key - check the key');
    }
    if (res.status === 503) {
      return fail(502, 'AltMount not ready (configuration not loaded) - try again in a moment');
    }
    const text = (await res.text().catch(() => '')).slice(0, 300);
    if (res.status === 404 && /stremio integration is disabled/i.test(text)) {
      return fail(502, 'AltMount Stremio integration is turned off - enable it in AltMount settings');
    }
    if (res.status === 400 || res.status === 422 || res.ok) {
      return { ok: true, httpStatus: 200, message: 'Connection successful!' };
    }
    return fail(502, `AltMount returned status ${res.status}`);
  } catch (error) {
    return fail(500, `Connection failed: AltMount is not reachable (${(error as Error).message})`);
  }
}

/** AltMount's file route wants SHA-256 of the API key. It is a bearer credential: never log it or send it to a player. */
const downloadKey = (apiKey: string) => createHash('sha256').update(apiKey).digest('hex');

const configError = (what: string) => new Error(`AltMount ${what} is not set - check AltMount settings`);

/** AltMount 500 answers that say AltMount had a problem, not that the Source failed. */
const BACKEND_SIDE_500 = /failed to check queue status|queue item not found|failed to list output media files|failed to fetch completed item|progress broadcaster closed unexpectedly|failed to open uploaded file|failed to read uploaded file|failed to process nzb/i;

/**
 * Reply of `POST /api/nzb/streams` (pinned v0.4.0 StremioStreamsResponse).
 * `_queue_item_id`, `_queue_status` and `_cached` sit next to `streams`, not
 * inside each entry.
 */
interface StreamsReply { streams?: { url?: string }[]; _queue_item_id?: string | number; _queue_status?: string; _cached?: boolean }

/** Virtual path of the media, taken from the `path` of the URL AltMount returned. */
function virtualPathOf(entryUrl: string, base: string): string | null {
  try {
    const p = new URL(entryUrl, base).searchParams.get('path');
    return p ? (p.startsWith('/') ? p : '/' + p) : null;
  } catch {
    return null;
  }
}

/**
 * The media AltMount says is ready, from the raw reply body. Ready means the
 * reply is streamable or completed, or a reused completed item; the file is
 * the first entry whose URL carries a virtual path.
 */
export function readyMediaOf(raw: string, base: string): { queueId: string; videoPath: string; cached: boolean; status: string } | null {
  let reply: StreamsReply;
  try { reply = JSON.parse(raw) as StreamsReply; } catch { return null; }
  const ready = reply._cached === true || reply._queue_status === 'streamable' || reply._queue_status === 'completed';
  if (!ready) return null;
  for (const s of reply.streams ?? []) {
    const videoPath = s.url ? virtualPathOf(s.url, base) : null;
    if (videoPath) return { queueId: String(reply._queue_item_id ?? ''), videoPath, cached: reply._cached === true, status: reply._queue_status ?? '' };
  }
  return null;
}

/** Paths of every file AltMount offered in its reply, for the first-byte log line. */
export function offeredPathsOf(raw: string, base: string): string[] {
  try {
    const reply = JSON.parse(raw) as StreamsReply;
    return (reply.streams ?? []).map(s => (s.url ? virtualPathOf(s.url, base) : null)).filter((p): p is string => !!p);
  } catch {
    return [];
  }
}

/**
 * Season and episode numbers behind a Source's episode selection. The stream
 * route builds `episodePattern` from them (buildEpisodePattern, optionally
 * wrapped with a date alternative); read them back the same way the NzbDAV
 * file picker does: first S<digits>, first E<digits> (the chain-aware
 * pattern's `E\d+` has no digits, so it is skipped).
 */
export function seasonEpisodeOf(episodePattern?: string): { season: number; episode: number } | null {
  if (!episodePattern) return null;
  const s = /S(\d+)/i.exec(episodePattern)?.[1];
  const e = /E(\d+)/i.exec(episodePattern)?.[1];
  return s && e ? { season: parseInt(s, 10), episode: parseInt(e, 10) } : null;
}

/**
 * Name AltMount gets for the upload (its file name, without ".nzb"). AltMount
 * files a release under a folder named like the upload, and when that name ends
 * in a video extension its reply offers only the folder (answers 400 "Cannot
 * stream directory"; captured in #84). So a release name ending in .mkv, .mp4
 * and the like goes up without that extension. The NZB itself is unchanged.
 */
export function altmountUploadName(releaseName: string): string {
  const lower = releaseName.toLowerCase();
  const ext = VIDEO_EXTENSIONS.find(e => lower.endsWith(e));
  const stem = ext ? releaseName.slice(0, -ext.length) : releaseName;
  return stem || releaseName;
}

export function createAltmountBackend(settings: AltmountSettings): Backend {
  const baseUrl = () => {
    if (!settings.url) throw configError('URL');
    return settings.url;
  };

  const mediaRequest = (mediaPath: string): MediaRequest => {
    if (!settings.apiKey) throw configError('API key');
    const url = new URL('/api/files/stream', baseUrl());
    url.searchParams.set('path', mediaPath);
    url.searchParams.set('download_key', downloadKey(settings.apiKey));
    return { url, headers: {} };
  };

  // GET the first byte; the retries are part of the step.
  // 404/410: bad Source. 400 or a refused/dropped connection: Source kept (ADR 0004).
  const probeFirstByte = async (video: PreparedVideo, logPrefix: string): Promise<void> => {
    const { url, headers } = mediaRequest(video.videoPath);
    const offered = () => video.offered ?? [];
    let attempt = 0;
    let kind: FirstByteKind = 'other';
    let what = '';
    while (attempt < PROBE_MAX_ATTEMPTS) {
      try {
        const resp = await fetch(url, { headers: { ...headers, Range: 'bytes=0-0' }, signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) });
        await resp.body?.cancel().catch(() => {});
        if (resp.status === 206 || resp.status === 200) {
          const total = /^bytes 0-0\/(\d+)$/.exec(resp.headers.get('content-range') ?? '')?.[1];
          if (total && !video.videoSize) video.videoSize = parseInt(total, 10);
          return;
        }
        kind = kindOfStatus(resp.status);
        what = `status ${resp.status}`;
        if (kind === 'gone') {
          await logFirstByteFailure(logPrefix, what, video.videoPath, offered);
          throw sourceFailure(`Video file not servable (${resp.status}): ${video.videoPath}`, false, true);
        }
        console.warn(`${logPrefix}  ⚠️ AltMount probe returned ${resp.status}`);
      } catch (err) {
        if (isSourceFailure(err)) throw err;
        kind = kindOfFetchError(err);
        what = kind === 'keep-source' ? 'connection refused or dropped' : 'timed out';
        console.warn(`${logPrefix}  ⚠️ AltMount probe attempt ${attempt + 1}/${PROBE_MAX_ATTEMPTS} failed: ${(err as Error).message}`);
      }
      attempt++;
      if (attempt < PROBE_MAX_ATTEMPTS) await new Promise(r => setTimeout(r, PROBE_RETRY_DELAY_MS));
    }
    await logFirstByteFailure(logPrefix, what, video.videoPath, offered);
    if (kind === 'keep-source') throw firstByteKeptError(video.videoPath, what);
    throw sourceFailure(`Video file not servable (probe failed after ${attempt} attempts): ${video.videoPath}`, false, true);
  };

  return {
    id: 'altmount',
    label: 'AltMount',
    capabilities: ALTMOUNT_CAPABILITIES,

    // No search-time library for AltMount yet: always prepare.
    findPrepared: async () => null,

    async stillPrepared(mediaPath) {
      try {
        const { url, headers } = mediaRequest(mediaPath);
        const res = await fetch(url, { headers: { ...headers, Range: 'bytes=0-0' }, signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) });
        await res.body?.cancel().catch(() => {});
        return res.status === 200 || res.status === 206;
      } catch {
        return false;
      }
    },

    async prepare(source, opts = {}) {
      const { logPrefix = '', timeoutMs = 0, onJob, isCancelled } = opts;
      if (!settings.apiKey) throw configError('API key');
      const apiKey = settings.apiKey;
      // KaijuFlow grabs the NZB itself (proxy exit-IP check, validation, grab
      // tracking) through the shared step, exactly as for NzbDAV, and uploads it.
      const { nzb, remainingMs } = await grabSourceNzb(source, { budgetMs: timeoutMs, logPrefix });
      if (isCancelled?.()) throw new PrepareCancelledError();
      // The setting is the ceiling; a shorter attempt budget from the caller wins.
      const settingSec = Math.max(1, settings.prepareTimeoutSec ?? 300);
      const waitSec = remainingMs > 0 ? Math.min(settingSec, Math.max(1, Math.ceil(remainingMs / 1000))) : settingSec;
      const form = new FormData();
      form.append('file', new Blob([nzb], { type: 'application/x-nzb' }), `${altmountUploadName(source.title)}.nzb`);
      form.append('category', settings.category || 'kaijuflow');
      form.append('timeout', String(waitSec));
      const se = seasonEpisodeOf(source.episodePattern);
      if (se) {
        form.append('season', String(se.season));
        form.append('episode', String(se.episode));
      }
      console.log(`${logPrefix}  \u{1F4E4} Sending Source to AltMount (waits up to ${waitSec}s)`);
      // One request uploads the NZB and waits for AltMount's import, so one step covers both.
      const media = await timeStep({ step: 'import_wait', source: source.indexerName, title: source.title, includes_upload: true }, async () => {
        let res: Response;
        try {
          res = await fetch(new URL('/api/nzb/streams', baseUrl()), {
            method: 'POST',
            headers: { 'X-Api-Key': apiKey },
            body: form,
            signal: AbortSignal.timeout(waitSec * 1000 + SUBMIT_GRACE_MS),
          });
        } catch (err) {
          // Unreachable AltMount: not the Source's fault, so not a Source failure.
          throw new Error(`AltMount is not reachable (${(err as Error).message})`);
        }
        if (isCancelled?.()) {
          await res.body?.cancel().catch(() => {});
          throw new PrepareCancelledError();
        }
        const raw = await res.text().catch(() => '');
        const text = raw.slice(0, 300);
        if (res.status === 408) {
          // AltMount keeps working on it; KaijuFlow just stopped waiting.
          throw sourceFailure(`AltMount did not finish preparing within ${waitSec}s`, true, false);
        }
        if (res.status === 400 || res.status === 422) {
          throw sourceFailure(`AltMount rejected the Source (${res.status}): ${text}`, false, true);
        }
        // A failed queue item ("NZB processing failed", or its error message) is the
        // Source's fault. AltMount-side 500s (queue lookup, output listing, upload
        // handling, progress stream) are not.
        if (res.status === 500 && !BACKEND_SIDE_500.test(raw)) {
          throw sourceFailure(`AltMount could not process the Source: ${text}`, false, true);
        }
        if (!res.ok) {
          throw new Error(`AltMount returned status ${res.status}: ${text}`);
        }
        const ready = readyMediaOf(raw, baseUrl());
        if (!ready) throw sourceFailure('AltMount returned no ready file for this Source', false, true);
        return { ...ready, offered: offeredPathsOf(raw, baseUrl()) };
      }, ready => ({ job: ready.queueId }));
      onJob?.(media.queueId);
      console.log(`${logPrefix}  \u2705 AltMount prepared the Source (${media.cached ? 'reused' : media.status || 'ready'})`);
      return { nzoId: media.queueId, videoPath: media.videoPath, videoSize: 0, offered: media.offered };
    },

    // GET the first byte (HEAD isn't proof the file is readable). A cached
    // entry skipped AltMount's own byte probe, so this always runs.
    probe: (video, opts = {}) => timeStep(
      { step: 'first_byte', source: opts.source, title: opts.title, job: video.nzoId },
      () => probeFirstByte(video, opts.logPrefix ?? ''),
    ),

    // Deliberately a no-op (checked against pinned AltMount source, #3). The only
    // API-key route, SAB `mode=queue&name=delete`, just deletes the import_queue
    // row; it does not stop a running worker (sabnzbd_handlers.go:708,
    // queue_repository.go:54). The REST DELETE refuses processing jobs for that
    // reason, and a timed-out job is still processing. So it would be row
    // deletion under a live worker, not a cancel. Cancel is best effort anyway.
    cancel: async () => {},

    mediaRequest,

    directUrl(mediaPath) {
      return mediaRequest(mediaPath).url.href;
    },

    status: async form => testAltmountConnection({
      url: (form?.altmountUrl as string | undefined) ?? settings.url,
      apiKey: (form?.altmountApiKey as string | undefined) ?? settings.apiKey,
      category: (form?.altmountCategory as string | undefined) ?? settings.category,
    }),
  };
}
