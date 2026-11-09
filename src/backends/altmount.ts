/**
 * AltMount Backend (spec #16). Step 2a (#18): settings and reachability check
 * only. Preparing, probing and delivery land with #19 onward; until then those
 * calls fail as "Backend not ready" (never a Source failure, so nothing is
 * marked dead).
 */

import { config as globalConfig } from '../config/index.js';
import type { Backend, BackendStatus } from './types.js';

const TEST_CONNECTION_TIMEOUT_MS = 15_000;

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

const notReady = () => new Error('AltMount Backend cannot prepare Sources yet');

export function createAltmountBackend(settings: AltmountSettings): Backend {
  return {
    id: 'altmount',
    label: 'AltMount',
    findPrepared: async () => null,
    stillPrepared: async () => false,
    prepare: async () => { throw notReady(); },
    probe: async () => { throw notReady(); },
    cancel: async () => {},
    mediaRequest: () => { throw notReady(); },
    directUrl: () => { throw notReady(); },
    status: async form => testAltmountConnection({
      url: (form?.altmountUrl as string | undefined) ?? settings.url,
      apiKey: (form?.altmountApiKey as string | undefined) ?? settings.apiKey,
      category: (form?.altmountCategory as string | undefined) ?? settings.category,
    }),
  };
}
