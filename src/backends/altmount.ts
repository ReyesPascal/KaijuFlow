/**
 * AltMount Backend (spec #16). #18: settings and reachability check.
 * #19: movie Sources. The selected NZB goes to AltMount's stream route
 * (POST /api/nzb/streams, as an uploaded file); its answer names the media's virtual path,
 * which is the media identity (`videoPath`) everywhere in KaijuFlow. Media is
 * fetched from AltMount's file route with the download key kept server side.
 * Not yet: TV episode selection, library reuse, cancel.
 */

import { config as globalConfig } from '../config/index.js';
import { createHash } from 'node:crypto';
import { grabNzb } from '../nzbdav/nzbdavApi.js';
import { nzbdavError } from '../nzbdav/utils.js';
import { PrepareCancelledError, isSourceFailure, type Backend, type BackendStatus, type MediaRequest, type PreparedVideo } from './types.js';

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
    if (res.status === 401 || res.status === 403) {
      return fail(502, 'AltMount rejected the API key - check the key');
    }
    const text = (await res.text().catch(() => '')).slice(0, 300);
    if (res.status === 404 || res.status === 503 || /stremio|integration|disabled/i.test(text)) {
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

interface StreamsEntry { url?: string; _queue_item_id?: string | number; _queue_status?: string; _cached?: boolean }

/** Virtual path of the media, taken from the `path` of the URL AltMount returned. */
function virtualPathOf(entryUrl: string, base: string): string | null {
  try {
    const p = new URL(entryUrl, base).searchParams.get('path');
    return p ? (p.startsWith('/') ? p : '/' + p) : null;
  } catch {
    return null;
  }
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

  return {
    id: 'altmount',
    label: 'AltMount',

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
      const waitSec = timeoutMs > 0 ? Math.max(1, Math.ceil(timeoutMs / 1000)) : Math.max(1, settings.prepareTimeoutSec ?? 300);
      // KaijuFlow grabs the NZB itself (proxy exit-IP check, validation, grab
      // tracking), exactly as for NzbDAV, and uploads it to AltMount.
      const nzb = await grabNzb(source.nzbUrl, source.title, undefined, logPrefix, source.indexerName, source.searchExitIp);
      if (isCancelled?.()) throw new PrepareCancelledError();
      const form = new FormData();
      form.append('file', new Blob([nzb], { type: 'application/x-nzb' }), `${source.title}.nzb`);
      form.append('category', settings.category || 'kaijuflow');
      form.append('timeout', String(waitSec));
      console.log(`${logPrefix}  \u{1F4E4} Sending Source to AltMount (waits up to ${waitSec}s)`);
      let res: Response;
      try {
        res = await fetch(new URL('/api/nzb/streams', baseUrl()), {
          method: 'POST',
          headers: { 'X-Api-Key': settings.apiKey },
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
        throw nzbdavError(`AltMount did not finish preparing within ${waitSec}s`, true, false);
      }
      if (res.status === 400 || res.status === 422) {
        throw nzbdavError(`AltMount rejected the Source (${res.status}): ${text}`, false, true);
      }
      if (!res.ok) {
        throw new Error(`AltMount returned status ${res.status}: ${text}`);
      }
      let streams: StreamsEntry[] = [];
      try { streams = (JSON.parse(raw) as { streams?: StreamsEntry[] }).streams ?? []; } catch { /* no streams */ }
      const entry = streams.find(s => s.url && virtualPathOf(s.url, baseUrl()));
      if (!entry?.url) throw nzbdavError('AltMount returned no playable file for this Source', false, true);
      const nzoId = String(entry._queue_item_id ?? '');
      onJob?.(nzoId);
      console.log(`${logPrefix}  \u2705 AltMount prepared the Source (${entry._cached ? 'reused' : entry._queue_status || 'ready'})`);
      return { nzoId, videoPath: virtualPathOf(entry.url, baseUrl())!, videoSize: 0 };
    },

    // GET the first byte (HEAD isn't proof the file is readable). A cached
    // entry skipped AltMount's own byte probe, so this always runs.
    async probe(video, opts = {}) {
      const { logPrefix = '' } = opts;
      const { url, headers } = mediaRequest(video.videoPath);
      let attempt = 0;
      while (attempt < PROBE_MAX_ATTEMPTS) {
        try {
          const resp = await fetch(url, { headers: { ...headers, Range: 'bytes=0-0' }, signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) });
          await resp.body?.cancel().catch(() => {});
          if (resp.status === 404 || resp.status === 410) {
            throw nzbdavError(`Video file not servable (${resp.status}): ${video.videoPath}`, false, true);
          }
          if (resp.status === 206 || resp.status === 200) return;
          console.warn(`${logPrefix}  \u26A0\uFE0F AltMount probe returned ${resp.status}`);
        } catch (err) {
          if (isSourceFailure(err)) throw err;
          console.warn(`${logPrefix}  \u26A0\uFE0F AltMount probe attempt ${attempt + 1}/${PROBE_MAX_ATTEMPTS} failed: ${(err as Error).message}`);
        }
        attempt++;
        if (attempt < PROBE_MAX_ATTEMPTS) await new Promise(r => setTimeout(r, PROBE_RETRY_DELAY_MS));
      }
      throw nzbdavError(`Video file not servable (probe failed after ${attempt} attempts): ${video.videoPath}`, false, true);
    },

    // Best effort and a no-op for now: AltMount cancels need a login, not the API key.
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
