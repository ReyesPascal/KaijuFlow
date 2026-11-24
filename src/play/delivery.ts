/**
 * Delivery (GLOSSARY: Delivery method): the one serve step of the play route.
 * The video and the request give the response, always with the Delivery method as it is now
 * (`playDeliveryMethod`, #248): proxy or pipe inline (Ultimate Fallback off) or by a 302 to the
 * `/v` video route (Ultimate Fallback on), or direct (a 302 to the Backend's file route).
 */

import type { Request, Response as ExpressResponse } from 'express';
import { config as globalConfig } from '../config/index.js';
import { getActiveBackend } from '../backends/index.js';
import { formatBytes } from '../parsers/metadataParsers.js';
import { resolveBaseUrl } from '../utils/urlHelpers.js';
import { getDeliveryLog, isUltimateFallbackActive } from './utils.js';

/** The play route's inline proxy (`proxyVideoStream` in routes/play.ts): serves videoPath on this response. */
export type InlineProxy = (req: Request, res: ExpressResponse, videoPath: string, usePipe: boolean) => Promise<void>;

/** The Delivery method as it is now. */
function deliveryMethod(): 'pipe' | 'proxy' | 'direct' {
  return globalConfig.playDeliveryMethod ?? 'proxy';
}

/**
 * Serve a prepared video on this request. The log line goes out once per video and method, so the
 * player's range probes and seeks do not repeat it.
 */
export async function serveVideo(
  req: Request,
  res: ExpressResponse,
  video: { videoPath: string; videoSize?: number },
  inlineProxy?: InlineProxy,
): Promise<void> {
  const mode = deliveryMethod();
  const lastDeliveryLog = getDeliveryLog();
  const last = lastDeliveryLog.get(video.videoPath);
  const log = !last || last.mode !== mode;
  if (log) lastDeliveryLog.set(video.videoPath, { mode, at: Date.now() });
  const size = video.videoSize ? ` (${formatBytes(video.videoSize)})` : '';

  if (mode === 'direct') {
    // The Backend's file route, its download key in the URL (desktop players).
    const directUrl = new URL(getActiveBackend().directUrl(video.videoPath));
    if (log) console.log(`  ⇗️ Direct passthrough: → ${directUrl.hostname}${directUrl.pathname}${size}`);
    res.redirect(302, directUrl.href);
    return;
  }

  const inline = !isUltimateFallbackActive() && inlineProxy;
  const label = mode === 'pipe' ? '🔗 Pipe' : '📡 Dual-Stage Proxy';
  if (log) console.log(`  ${label}${inline ? '' : ' 302'} streaming: ${video.videoPath}${size}`);
  if (inline) {
    // Inline: no redirect, the broadest player compatibility.
    await inlineProxy(req, res, video.videoPath, mode !== 'proxy');
    return;
  }
  // The /v route adds auth, buffering and transparent reconnect; `_fb` brings a broken video back to this request.
  const proxyUrl = new URL(`${resolveBaseUrl(req)}${req.baseUrl}/v`);
  proxyUrl.searchParams.set('path', video.videoPath);
  proxyUrl.searchParams.set('_fb', req.originalUrl);
  if (req.query._norange === '1') proxyUrl.searchParams.set('_norange', '1');
  res.redirect(302, proxyUrl.href);
}
