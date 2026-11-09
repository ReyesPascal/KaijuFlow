/**
 * NzbDAV Backend: today's NzbDAV flow behind the Backend slot, unchanged.
 * SAB-style upload, job polling, WebDAV video discovery, library lookup and
 * the first-byte probe. This is the only module outside src/nzbdav/ that
 * calls NzbDAV code.
 */

import { config as globalConfig } from '../config/index.js';
import { getLatestVersions } from '../versionFetcher.js';
import { submitNzb, waitForJobCompletion, cancelJob } from '../nzbdav/nzbdavApi.js';
import { checkNzbLibrary, checkLibraryVideoPath, waitForVideoFile, videoPathExists } from '../nzbdav/videoDiscovery.js';
import { searchLibrary } from '../nzbdav/librarySearch.js';
import { encodeWebdavPath, nzbdavError } from '../nzbdav/utils.js';
import type { NZBDavConfig } from '../nzbdav/types.js';
import { NZBDAV_CAPABILITIES } from './capabilities.js';
import { PrepareCancelledError, isSourceFailure, type Backend, type BackendStatus, type MediaRequest } from './types.js';

const PROBE_TIMEOUT_MS = 10_000;
const PROBE_RETRY_BASE_MS = 2_000;
const PROBE_MAX_RETRIES = 2;
const TEST_CONNECTION_TIMEOUT_MS = 15_000;

export function createNzbdavBackend(config: NZBDavConfig): Backend {
  const mediaUrl = (mediaPath: string) =>
    new URL(`${(config.webdavUrl || config.url || '').replace(/\/+$/, '')}${encodeWebdavPath(mediaPath)}`);

  const mediaRequest = (mediaPath: string): MediaRequest => {
    const headers: Record<string, string> = {};
    if (config.webdavUser && config.webdavPassword) {
      headers['Authorization'] = basicAuth(config.webdavUser, config.webdavPassword);
    }
    return { url: mediaUrl(mediaPath), headers };
  };

  const cancel = (jobId: string, reason?: string) => cancelJob(jobId, config, reason);

  return {
    id: 'nzbdav',
    label: 'NzbDAV',
    capabilities: NZBDAV_CAPABILITIES,

    library: { search: ctx => searchLibrary(ctx, config) },

    findPrepared(source, opts = {}) {
      const { logPrefix = '', quiet = false } = opts;
      return source.knownMediaPath
        ? checkLibraryVideoPath(source.knownMediaPath, source.knownSize ?? 0, config, logPrefix, quiet)
        : checkNzbLibrary(source.title, config, source.episodePattern, source.contentType, source.episodesInSeason, logPrefix, quiet);
    },

    stillPrepared(mediaPath) {
      return videoPathExists(mediaPath, config);
    },

    async prepare(source, opts = {}) {
      const { logPrefix = '', timeoutMs = 0, pollIntervalMs, onJob, isCancelled } = opts;
      // Grab tracking lives inside submitNzb after content validation, so
      // cache hits (precached by health checks) do not double-count.
      const nzoId = await submitNzb(source.nzbUrl, source.title, config, source.contentType, undefined, logPrefix, source.indexerName, source.searchExitIp);
      onJob?.(nzoId);
      if (isCancelled?.()) {
        cancel(nzoId, 'health check failed (late cancel)').catch(() => {});
        throw new PrepareCancelledError();
      }
      await waitForJobCompletion(nzoId, config, timeoutMs, pollIntervalMs, source.contentType, logPrefix);
      if (isCancelled?.()) throw new PrepareCancelledError();
      const video = await waitForVideoFile(nzoId, source.title, config, source.episodePattern, source.contentType, source.episodesInSeason, logPrefix);
      return { nzoId, videoPath: video.path, videoSize: video.size };
    },

    // GET the first byte. HEAD isn't reliable: NzbDAV answers 200 for HEAD
    // even when content is gone. Large files can take a moment to become
    // servable after the job completes, so retry once with a delay.
    async probe(video, opts = {}) {
      const { logPrefix = '' } = opts;
      const { url, headers } = mediaRequest(video.videoPath);
      const probeHeaders = { ...headers, 'Range': 'bytes=0-0' };
      let attempt = 0;
      while (attempt < PROBE_MAX_RETRIES) {
        try {
          const resp = await fetch(url, { headers: probeHeaders, signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) });
          await resp.body?.cancel().catch(() => {});
          if (resp.status === 404 || resp.status === 410) {
            throw nzbdavError(`Video file not servable (${resp.status}): ${video.videoPath}`, false, true);
          }
          if (resp.status === 206 || resp.status === 200) return;
          attempt++;
          console.warn(`${logPrefix}  ⚠️ Probe returned ${resp.status} — retrying (${attempt}/${PROBE_MAX_RETRIES})...`);
        } catch (err) {
          if (isSourceFailure(err)) throw err;
          attempt++;
          if (attempt >= PROBE_MAX_RETRIES) {
            console.warn(`${logPrefix}  ⚠️ Probe failed after ${attempt} attempts: ${(err as Error).message}`);
            break;
          }
          console.warn(`${logPrefix}  ⚠️ Probe attempt ${attempt}/${PROBE_MAX_RETRIES} failed (${(err as Error).message}) — retrying in ${Math.round(PROBE_RETRY_BASE_MS / 1000)}s`);
        }
        if (attempt < PROBE_MAX_RETRIES) {
          await new Promise(r => setTimeout(r, Math.min(PROBE_RETRY_BASE_MS * Math.pow(2, attempt - 1), 10_000)));
        }
      }
      throw nzbdavError(`Video file not servable (probe failed after ${attempt} attempts): ${video.videoPath}`, false, true);
    },

    cancel,

    mediaRequest,

    directUrl(mediaPath) {
      const url = mediaUrl(mediaPath);
      if (config.webdavUser) {
        url.username = config.webdavUser;
        url.password = config.webdavPassword || '';
      }
      return url.href;
    },

    status(settings) {
      return testNzbdavConnection((settings ?? {
        url: config.url, apiKey: config.apiKey, webdavUrl: config.webdavUrl,
        webdavUser: config.webdavUser, webdavPassword: config.webdavPassword, moviesCategory: config.moviesCategory,
      }) as NzbdavConnectionSettings);
    },
  };
}

interface NzbdavConnectionSettings {
  url?: string;
  apiKey?: string;
  webdavUrl?: string;
  webdavUser?: string;
  webdavPassword?: string;
  moviesCategory?: string;
  /** Also send a tiny test NZB (only when the user asks, to avoid flooding NzbDAV). */
  sendTestNzb?: boolean;
}

const basicAuth = (user: string, password: string) => 'Basic ' + Buffer.from(`${user}:${password}`).toString('base64');
const nzbdavUserAgent = () => globalConfig.userAgents?.nzbdavOperations || getLatestVersions().chrome;

const fail = (httpStatus: number, message: string): BackendStatus => ({ ok: false, httpStatus, message });

/** NzbDAV + WebDAV reachability check, optionally with a test NZB upload. */
async function testNzbdavConnection(settings: NzbdavConnectionSettings): Promise<BackendStatus> {
  const { url, apiKey, webdavUrl, webdavUser, webdavPassword, moviesCategory } = settings;
  if (!url) return fail(400, 'NZBDav URL is required');
  try {
    const nzbdavHeaders: Record<string, string> = apiKey ? { 'X-Api-Key': apiKey, 'User-Agent': nzbdavUserAgent() } : { 'User-Agent': nzbdavUserAgent() };
    const nzbdavResponse = await fetch(new URL(url).toString(), {
      headers: nzbdavHeaders,
      signal: AbortSignal.timeout(TEST_CONNECTION_TIMEOUT_MS),
    });
    if (!nzbdavResponse.ok && nzbdavResponse.status !== 401) {
      return fail(502, `NZBDav server returned status ${nzbdavResponse.status}`);
    }

    if (webdavUrl) {
      const webdavUserAgent = globalConfig.userAgents?.webdavOperations || getLatestVersions().chrome;
      const webdavHeaders: Record<string, string> = webdavUser && webdavPassword ? {
        'Authorization': basicAuth(webdavUser, webdavPassword),
        'User-Agent': webdavUserAgent,
      } : { 'User-Agent': webdavUserAgent };
      const webdavResponse = await fetch(new URL(webdavUrl).toString(), {
        method: 'PROPFIND',
        headers: { ...webdavHeaders, 'Depth': '0' },
        signal: AbortSignal.timeout(TEST_CONNECTION_TIMEOUT_MS),
      });
      if (webdavResponse.status === 401 || webdavResponse.status === 403) {
        return fail(502, 'WebDAV authentication failed - check credentials');
      }
      // PROPFIND returns 207 Multi-Status on success
      if (!webdavResponse.ok && webdavResponse.status !== 207) {
        return fail(502, `WebDAV server returned status ${webdavResponse.status}`);
      }
    }

    if (settings.sendTestNzb) {
      const testNzb = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nzb PUBLIC "-//newzBin//DTD NZB 1.1//EN" "http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">
<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">
  <head>
    <meta type="title">Usenet Ultimate Test File</meta>
  </head>
  <file poster="test@usenet-ultimate" date="1738368000" subject="Usenet Ultimate Test [1/1] - test.txt (1 KB)">
    <groups>
      <group>alt.binaries.test</group>
    </groups>
    <segments>
      <segment bytes="1024" number="1">test@usenet-ultimate</segment>
    </segments>
  </file>
</nzb>`;
      const category = moviesCategory || 'Usenet-Ultimate-Movies';
      const nzbApiUrl = `${url.endsWith('/') ? url.slice(0, -1) : url}/api?mode=addfile&cat=${encodeURIComponent(category)}&nzbname=UsenetUltimate-Test${apiKey ? `&apikey=${apiKey}` : ''}`;
      const formData = new FormData();
      formData.append('nzbFile', new Blob([testNzb], { type: 'application/x-nzb' }), 'test.nzb');
      const submitUserAgent = nzbdavUserAgent();
      const redactedNzbApiUrl = apiKey ? nzbApiUrl.replace(apiKey, '[REDACTED]') : nzbApiUrl;
      console.log('\u{1F4E4} Request to test NZB submission:', { url: redactedNzbApiUrl, method: 'POST', headers: { 'Content-Type': 'multipart/form-data', 'User-Agent': submitUserAgent } });
      const testNzbResponse = await fetch(nzbApiUrl, {
        method: 'POST',
        body: formData,
        headers: { 'User-Agent': submitUserAgent },
        signal: AbortSignal.timeout(TEST_CONNECTION_TIMEOUT_MS),
      });
      if (!testNzbResponse.ok) {
        const errorText = await testNzbResponse.text();
        return fail(502, `NZB submission test failed: ${testNzbResponse.status} - ${errorText}`);
      }
      const testResult = await testNzbResponse.json();
      return { ok: true, httpStatus: 200, message: 'Connection successful! Test NZB accepted.', testPath: (testResult as any).path };
    }

    return { ok: true, httpStatus: 200, message: 'Connection successful!' };
  } catch (error) {
    return fail(500, `Connection failed: ${(error as Error).message}`);
  }
}
