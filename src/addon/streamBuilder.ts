/**
 * Stream Builder
 *
 * Converts processed search results into Stremio Stream objects.
 * Handles URL construction for every kind of result:
 *   - Indexer results (play URL to the stream handler, with fallback groups)
 *   - EasyNews DDL (direct CDN resolve URL)
 *   - EasyNews NZB (routed through download client)
 *   - Native (external NZB link)
 *
 * Also handles fallback group creation and binge/auto-play group computation.
 */

import crypto from 'crypto';
import { config } from '../config/index.js';
import { parseQuality, parseCodec, parseSource, parseVisualTag, parseAudioTag, parseReleaseGroup, parseCleanTitle, parseYear, parseEdition, parseLanguage, resolutionToDisplay, formatBytes, formatAge, formatBitrate, parseDurationAttr, buildStreamFilename } from '../parsers/metadataParsers.js';
import type { Stream, AutoPlayConfig } from '../types.js';
import type { HealthCheckResult } from '../health/index.js';
import { requestContext } from '../requestContext.js';
import { createFallbackGroup, isUltimateFallbackActive, type FallbackCandidate } from '../play/index.js';
import { encodeTileEnvelope, toContentType } from '../play/redirectHelpers.js';
import { buildStreamDisplay } from './streamDisplay.js';
import { getSelfUrl } from '../utils/selfUrl.js';

// Ultimate Fallback tile name + path
const UF_TILE_BASE_NAME = '👑 Ultimate Fallback';
const UF_STREAM_PATH = 'ultimate-fallback';

/** Build the UF tile's display name + title based on the active preference mode.
 *  Brand goes in the `name` chip (left), mode + description in `title` (right detail). */
function ufTileDisplay(mode: 'speed' | 'priority' | undefined): { name: string; title: string } {
  if (mode === 'priority') {
    return { name: UF_TILE_BASE_NAME, title: '⚬ Priority Mode\n⚬ Auto-select highest-quality healthy stream' };
  }
  return { name: UF_TILE_BASE_NAME, title: '⚬ Speed Mode\n⚬ Auto-select fastest healthy stream' };
}


/** Resolve the base URL for stream/proxy URLs — uses the request's origin when available,
 *  falls back to BASE_URL env or loopback (127.0.0.1) for background tasks (auto-queue, health checks). */
function getBaseUrl(): string {
  return requestContext.getStore()?.baseUrl || process.env.BASE_URL || getSelfUrl(1337);
}

/** Get the path prefix for manifest-key routes (empty for legacy root, '/stremio' for prefixed path). */
function getPathPrefix(): string {
  return requestContext.getStore()?.pathPrefix || '';
}

export interface StreamBuildContext {
  allResults: any[];
  healthResults: Map<string, HealthCheckResult>;
  type: string;
  imdbId?: string;
  season?: number;
  episode?: number;
  episodesInSeason?: number;
  /** Aired date (YYYY-MM-DD) for daily/talk-show episodes. Packed into the
   *  per-tile envelope so the stream handler can fall back to a date-pattern
   *  match when SxxExx fails inside a season pack. */
  episodeAired?: string;
  now: number;
  runtime?: number;
}

export interface StreamBuildOutput {
  streams: Stream[];
  fallbackGroupId?: string;
  fallbackCandidates?: FallbackCandidate[];
}

/**
 * Build Stremio Stream objects from processed search results.
 */
export function buildStreams(ctx: StreamBuildContext): StreamBuildOutput {
  const { allResults, healthResults, type, imdbId, season, episode, episodesInSeason, episodeAired, now, runtime } = ctx;
  // Normalize once and pack into every NZB tile envelope so the stream handler
  // can resolve the Backend category (Movies vs TV) even when no in-memory
  // fallback group exists (Ultimate Fallback disabled, evicted, or post-restart).
  const ty = toContentType(type);
  // sessionKey includes manifestKey so concurrent requests from different Stremio installations
  // don't share UF session state (avoids cross-tenant state leaks on multi-user deployments).
  const streamManifestKey = requestContext.getStore()?.manifestKey || '';
  const sessionKey = imdbId ? `${streamManifestKey}:${type}:${imdbId}:${season ?? ''}:${episode ?? ''}` : '';

  // Build auto-play / binge group settings
  const autoPlay: AutoPlayConfig = config.autoPlay || { enabled: true, method: 'firstFile' as const, attributes: ['resolution', 'quality', 'edition'] as ('resolution' | 'quality' | 'edition')[] };

  // Create the fallback group (auto-retry next NZB on failure)
  let fallbackGroupId: string | undefined;
  let fallbackCandidates: FallbackCandidate[] | undefined;
  if (isUltimateFallbackActive() && allResults.length > 0) {
    fallbackGroupId = crypto.randomUUID().slice(0, 12);

    fallbackCandidates = allResults
      .filter(r => {
        // Include all results that go through the Backend (skip EasyNews DDL)
        if (r.easynewsMeta && config.easynewsMode !== 'nzb') return false;
        return true;
      })
      .map(r => {
        let nzbUrl = r.link;
        // For EasyNews NZB mode, construct the proxy URL
        if (r.easynewsMeta && config.easynewsMode === 'nzb') {
          const meta = r.easynewsMeta;
          const nzbParams = new URLSearchParams({
            hash: meta.hash, filename: meta.filename, ext: meta.ext,
          });
          if (meta.sig) nzbParams.set('sig', meta.sig);
          nzbUrl = `${getBaseUrl()}${getPathPrefix()}/${streamManifestKey}/easynews/nzb?${nzbParams.toString()}`;
        }
        return { nzbUrl, title: r.title, indexerName: r.indexerName, size: r.size, isSeasonPack: r.isSeasonPack || false, searchExitIp: r.searchExitIp };
      });

    createFallbackGroup(
      fallbackGroupId,
      fallbackCandidates,
      type,
      season?.toString(),
      episode?.toString(),
      episodesInSeason,
    );
    console.log(`🔄 Created fallback group ${fallbackGroupId} with ${fallbackCandidates.length} candidates`);
  }

  const streams: Stream[] = [];

  for (let streamIndex = 0; streamIndex < allResults.length; streamIndex++) {
    const result = allResults[streamIndex];
    const resolution = parseQuality(result.title);
    const resolutionDisplay = resolutionToDisplay(resolution);
    const quality = parseSource(result.title);
    const parsedCleanTitle = parseCleanTitle(result.title);
    const year = type === 'movie' ? parseYear(result.title) : undefined;
    const cleanTitle = year ? `${parsedCleanTitle} (${year})` : parsedCleanTitle;
    const streamFilename = buildStreamFilename(result.title, type, season, episode);
    const encode = parseCodec(result.title);
    const visualTag = parseVisualTag(result.title);
    const audioTag = parseAudioTag(result.title);
    const size = formatBytes(result.size);
    const releaseGroup = parseReleaseGroup(result.title);
    const edition = parseEdition(result.title);
    const language = parseLanguage(result.title);
    const indexer = result.indexerName;

    // Calculate age from pubDate
    const age = formatAge(result.pubDate, now);

    // Calculate bitrate from size + duration (EasyNews provides duration; Newznab may have runtime attribute)
    let durationSec: number | undefined = result.duration;
    if (!durationSec) {
      // Non-standard Newznab attributes — most indexers don't send these, but some may
      const runtimeAttr = result.attributes?.runtime || result.attributes?.duration;
      if (runtimeAttr) durationSec = parseDurationAttr(String(runtimeAttr));
    }
    if (!durationSec && runtime) {
      durationSec = runtime;
    }
    const bitrateSize = result.estimatedEpisodeSize ?? result.size;
    const bitrate = durationSec ? formatBitrate(bitrateSize, durationSec) : '';

    // Get health status if available
    const healthStatus = healthResults.get(result.link);
    let statusBadge = '';
    let providersLine = '';
    if (healthStatus) {
      const s = healthStatus.status;
      if (s === 'verified' || s === 'verified_stored' || s === 'verified_archive') {
        // Use distinct icons for special verification sources
        statusBadge = healthStatus.message === 'Zyclops' ? '🤖' : '✅';
      } else if (s === 'blocked') {
        statusBadge = '🚫';
      } else {
        statusBadge = '❌';
      }
      if (healthStatus.providersUsed?.length) {
        providersLine = `  📡 ${healthStatus.providersUsed.join(', ')}`;
      }
    }

    // Build display size string
    const displaySize = result.isSeasonPack && result.estimatedEpisodeSize
      ? `${formatBytes(result.estimatedEpisodeSize)}/ep (${size} pack)`
      : result.isSeasonPack
        ? `${size} (season pack)`
        : size;

    // Build stream name and title from display config (or legacy hardcoded format)
    const { name: streamName, title: streamTitle } = buildStreamDisplay(
      {
        resolutionDisplay, quality, cleanTitle, rawTitle: result.title, encode, displaySize,
        visualTag, audioTag, releaseGroup, indexer, statusBadge,
        providersLine, edition, language, age, bitrate, isSeasonPack: result.isSeasonPack || false,
      },
      config.streamDisplayConfig
    );

    // Compute bingeGroup for auto-play / binge watching
    let bingeGroup: string | undefined;
    if (autoPlay.enabled && type === 'series') {
      bingeGroup = 'usenetultimate';
      switch (autoPlay.method) {
        case 'matchingFile': {
          const attrs = (autoPlay.attributes || ['resolution', 'quality', 'releaseGroup']);
          const attrMap: Record<string, string> = {
            resolution, quality, encode, visualTag, audioTag, releaseGroup, indexer, edition,
          };
          const parts = attrs
            .map(a => attrMap[a])
            .filter(v => v && v !== 'Unknown' && v !== 'Standard');
          if (parts.length > 0) bingeGroup += `|${parts.join('|')}`;
          break;
        }
        case 'matchingIndex':
          bingeGroup += `|${streamIndex}`;
          break;
        // 'firstFile': all streams get the same bingeGroup (just 'usenetultimate')
      }
    }

    // For EasyNews results: DDL mode uses direct download resolve, NZB mode uses download client pipeline
    // Every other result gets a play URL that hands the Source to the Backend when the user clicks play
    if (result.easynewsMeta && config.easynewsMode === 'nzb') {
      // EasyNews NZB mode — route through download client like regular NZB results
      const meta = result.easynewsMeta;
      const nzbParams = new URLSearchParams({
        hash: meta.hash,
        filename: meta.filename,
        ext: meta.ext,
      });
      if (meta.sig) nzbParams.set('sig', meta.sig);
      const streamManifestKey = requestContext.getStore()?.manifestKey || '';
      const nzbProxyUrl = `${getBaseUrl()}${getPathPrefix()}/${streamManifestKey}/easynews/nzb?${nzbParams.toString()}`;

      // Same envelope shape as the regular indexer-result tile above. The
      // `url` field points at /easynews/nzb instead of a raw NZB URL, but
      // the stream handler treats it identically: fetch + hand to the Backend.
      const candidateIdx = fallbackCandidates
        ? fallbackCandidates.findIndex(c => c.nzbUrl === nzbProxyUrl && c.title === result.title)
        : -1;
      const needsEpisodeCtx = result.isSeasonPack && season !== undefined && episode !== undefined;
      const tileT = encodeTileEnvelope({
        ...(fallbackGroupId ? { fbg: fallbackGroupId } : {}),
        ...(candidateIdx >= 0 ? { idx: candidateIdx } : {}),
        ...(sessionKey ? { sk: sessionKey } : {}),
        ...(needsEpisodeCtx ? { season, episode, seasonpack: 1 as const, ...(episodesInSeason ? { epcount: episodesInSeason } : {}), ...(episodeAired ? { aired: episodeAired } : {}) } : {}),
        ty,
        url: nzbProxyUrl,
        title: result.title,
        indexer: result.indexerName || '',
        ...(result.searchExitIp ? { ip: result.searchExitIp } : {}),
      });
      const proxyUrl = `${getBaseUrl()}${getPathPrefix()}/${streamManifestKey}/play/stream/${encodeURIComponent(streamFilename || result.title || 'stream')}?t=${tileT}`;
      streams.push({
        name: streamName,
        title: streamTitle,
        url: proxyUrl,
        behaviorHints: {
          notWebReady: false,
          bingeGroup,
        },
      });
    } else if (result.easynewsMeta) {
      // EasyNews DDL mode — direct download/stream from EasyNews CDN
      const meta = result.easynewsMeta;
      const resolveParams = new URLSearchParams({
        hash: meta.hash,
        filename: meta.filename,
        ext: meta.ext,
        dlFarm: meta.dlFarm,
        dlPort: meta.dlPort,
        downURL: meta.downURL,
      });
      const streamManifestKey = requestContext.getStore()?.manifestKey || '';
      const resolveUrl = `${getBaseUrl()}${getPathPrefix()}/${streamManifestKey}/easynews/resolve?${resolveParams.toString()}`;

      streams.push({
        name: streamName,
        title: streamTitle,
        url: resolveUrl,
        behaviorHints: {
          notWebReady: false,  // CDN URL is directly streamable
          bingeGroup,
        },
      });
    } else {
      const streamManifestKey = requestContext.getStore()?.manifestKey || '';
      // Single-param tile URL. Infuse and other iOS external-player handoff
      // chains truncate everything after the first `&` in the URL they
      // receive, so all tile state is packed into one base64url-JSON envelope
      // under `t`. The handler reads `fbg`+`idx` to look up the candidate in
      // the in-memory fallback group; `url`/`title`/`indexer` ride along as
      // a single-shot fallback for when the group has been evicted.
      const candidateIdx = fallbackCandidates
        ? fallbackCandidates.findIndex(c => c.nzbUrl === result.link && c.title === result.title)
        : -1;
      const base = `${getBaseUrl()}${getPathPrefix()}/${streamManifestKey}/play/stream/${encodeURIComponent(streamFilename || result.title || 'stream')}`;
      const needsEpisodeCtx = result.isSeasonPack && season !== undefined && episode !== undefined;
      const tileT = encodeTileEnvelope({
        ...(fallbackGroupId ? { fbg: fallbackGroupId } : {}),
        ...(candidateIdx >= 0 ? { idx: candidateIdx } : {}),
        ...(sessionKey ? { sk: sessionKey } : {}),
        ...(needsEpisodeCtx ? { season, episode, seasonpack: 1 as const, ...(episodesInSeason ? { epcount: episodesInSeason } : {}), ...(episodeAired ? { aired: episodeAired } : {}) } : {}),
        ty,
        url: result.link,
        title: result.title,
        indexer: result.indexerName || '',
        ...(result.searchExitIp ? { ip: result.searchExitIp } : {}),
      });
      streams.push({
        name: streamName,
        title: streamTitle,
        url: `${base}?t=${tileT}`,
        behaviorHints: { notWebReady: false, bingeGroup },
      });
    }
  }

  // Prepend synthetic Ultimate Fallback tile so users can opt into the UF lobby explicitly.
  // The sessionKey gate skips item pages
  // that don't have an imdbId (shouldn't happen in practice, but defensive). streams.length
  // gate suppresses the tile when there are no search results, so a lone UF tile cannot
  // obscure results from other Stremio addons.
  if (
    streams.length > 0
    && isUltimateFallbackActive()
    && sessionKey
  ) {
    // Pack sk + fbg into a single base64url-encoded JSON envelope so the URL
    // carries no `&`. iOS / Infuse handoff truncates URLs at the first `&`,
    // which previously dropped fbg from the request once a second param was
    // added (commit d5d9a42). When auto-resolve-on-search is off, no session
    // is pre-populated for the sk and the lobby cannot fall back to a cached
    // resolution; the truncated fbg leaves UF unable to look up the group at
    // all.
    const ufT = encodeTileEnvelope({
      sk: sessionKey,
      ...(fallbackGroupId ? { fbg: fallbackGroupId } : {}),
    });
    const ufUrl = `${getBaseUrl()}${getPathPrefix()}/${streamManifestKey}/play/stream/${UF_STREAM_PATH}?t=${ufT}`;
    // bingeGroup matches regular tiles so cross-episode auto-play can continue via UF.
    const ufBingeGroup = autoPlay.enabled && autoPlay.method === 'firstFile' ? 'usenetultimate' : undefined;
    const ufDisplay = ufTileDisplay(config.ultimateFallback?.preferenceMode);
    streams.unshift({
      name: ufDisplay.name,
      title: ufDisplay.title,
      url: ufUrl,
      behaviorHints: {
        notWebReady: false,
        bingeGroup: ufBingeGroup,
      },
    });
  }

  return { streams, fallbackGroupId, fallbackCandidates };
}
