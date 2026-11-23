/**
 * Stremio Addon — Main Entry Point
 *
 * Connects to Stremio and handles stream requests.
 *
 * What this does:
 *      manifest - Tells Stremio our addon capabilities
 *      defineStreamHandler - Called when user clicks "Watch"
 *      Parses IMDB ID and season/episode from request
 *      Searches all indexers in parallel with Promise.all()
 *      Sorts results by quality (best first)
 *      Returns NZB links as externalUrl (user's download client handles them)
 *      Caches results to avoid hitting API rate limits
 *
 * Key concept:
 *      externalUrl - means "open this URL externally" - user's NZB client will catch it
 *      notWebReady: true - tells Stremio it can't play in the web player
 */

import { createRequire } from 'node:module';
import { addonBuilder } from 'stremio-addon-sdk';

const _require = createRequire(import.meta.url);
const { version: APP_VERSION } = _require('../../package.json');
import NodeCache from 'node-cache';
import { withStepRef } from '../utils/stepTiming.js';
import { config } from '../config/index.js';
import { clearFallbackGroups, clearTimeoutEntries, headStart, listAsked, isUltimateFallbackActive, clearResolvedSessions } from '../play/index.js';
import { sessionKeyOf, makePlayContext, episodeOf, type PlayContext } from '../play/playContext.js';
import { resolveTitle, type ResolvedTitleInfo } from './titleResolver.js';
import { indexManagerSearch, easynewsSearch, type SearchContext } from './searchOrchestrator.js';
import { deduplicateAndPreFilter, applyUserFilters } from './resultProcessor.js';
import { verifiedMarks } from './verifiedMarks.js';
import { buildStreams } from './streamBuilder.js';
import { isDeadNzbByUrl, isDeadNzb, getDeadCacheKey } from '../play/streamCache.js';
import { requestContext } from '../requestContext.js';
import { parseAnimeId, resolveAnimeId } from '../anime/animeIdResolver.js';
import { isDatabaseLoaded } from '../anime/animeDatabase.js';
import { resolveEpisodeCountFromTvdbId, resolveTmdbExternalIds } from '../idResolver.js';
import { getSelfUrl } from '../utils/selfUrl.js';

// Create cache for search results
// Use stdTTL: 0 (no expiry) and manage TTL per-entry via cache.set() so runtime changes take effect
const cache = new NodeCache({ stdTTL: 0 });

export function clearSearchCache(): void {
  cache.flushAll();
  clearFallbackGroups();
  clearTimeoutEntries();
  clearResolvedSessions();
}

// Define addon manifest - tells Stremio what we support
const manifest = {
  id: 'com.usenetultimate.addon',
  version: APP_VERSION,
  name: 'Usenet Ultimate',
  description: 'Search Usenet indexers and EasyNews for media content. Supports Newznab, Prowlarr, and NZBHydra with NZB health checking, quality-based sorting, and direct streaming via AltMount or EasyNews.',
  logo: '/pwa-512x512.png',
  resources: ['stream'],           // We only provide streams
  types: ['movie', 'series'],      // Support movies and TV shows
  catalogs: [],                    // No catalogs (don't show in discover)
  idPrefixes: ['tt', 'kitsu:', 'mal:', 'anilist:', 'anidb:', 'tvdb:', 'tmdb:'],
  behaviorHints: {
    configurable: true,            // We have a config UI
    configurationRequired: false,  // But it's optional
  },
};

const builder = addonBuilder(manifest);

/**
 * Build the manifest-scoped search cache key. Manifest-scoping prevents
 * cross-manifest cache collisions in multi-tenant deployments.
 */
export function buildSearchCacheKey(manifestKey: string, type: string, id: string, cfg: typeof config): string {
  const easynewsSuffix = cfg.easynewsEnabled ? ':en' : '';
  const packsSuffix = cfg.searchConfig?.includeSeasonPacks ? ':packs' : '';
  // Bake the alias-fallback flag into the key so toggling it invalidates
  // any cached zero-result entry whose outcome depended on the flag's state.
  const aliasFbSuffix = cfg.searchConfig?.aliasTitleFallback === false ? ':noaf' : '';
  if (cfg.indexManager === 'prowlarr' || cfg.indexManager === 'nzbhydra') {
    const syncedEnabled = (cfg.syncedIndexers || []).filter(i => i.enabledForSearch);
    const syncedFingerprint = syncedEnabled
      .map(i => `${i.id}:${type === 'movie' ? i.movieSearchMethod : i.tvSearchMethod}`)
      .join(',');
    return `${manifestKey}:stream:${type}:${id}:${cfg.indexManager}:${syncedFingerprint}${packsSuffix}${easynewsSuffix}${aliasFbSuffix}`;
  }
  const enabledIndexers = cfg.indexers.filter(i => i.enabled);
  const methodsFingerprint = enabledIndexers
    .map(i => `${i.name}:${type === 'movie' ? (i.movieSearchMethod || ['imdb']).join('+') : (i.tvSearchMethod || ['imdb']).join('+')}`)
    .join(',');
  return `${manifestKey}:stream:${type}:${id}:${methodsFingerprint}${packsSuffix}${easynewsSuffix}${aliasFbSuffix}`;
}

/**
 * Resolve title metadata and assemble the SearchContext used by all downstream
 * searchers (indexer, EasyNews).
 *
 * Anime via Kitsu/MAL/AniList/AniDB without IMDB mappings uses a synthetic
 * titleInfo (no Cinemeta lookup) and only augments via TVDB when a TVDB ID is
 * provided directly. See the inline comments in the anime branch for the
 * Cinemeta-cumulative caveat.
 */
async function resolveTitleAndBuildSearchCtx(args: {
  type: string;
  imdbId: string;
  season: number | undefined;
  episode: number | undefined;
  animeId: ReturnType<typeof parseAnimeId>;
  animeResolved: ReturnType<typeof resolveAnimeId>;
  tvdbIdFromRequest?: number;
}): Promise<{ titleInfo: ResolvedTitleInfo; searchCtx: SearchContext }> {
  const { type, imdbId, season, episode, animeId, animeResolved, tvdbIdFromRequest } = args;

  let titleInfo: ResolvedTitleInfo;
  if (animeResolved && !animeResolved.imdbId && animeResolved.title) {
    titleInfo = {
      title: animeResolved.title,
      cinemetaTitle: animeResolved.title,
      year: animeResolved.year,
      country: 'Japan',
      genres: ['Animation'],
      isAnime: true,
      episodesInSeason: undefined,
      priorSeasonsEpisodeCount: undefined,
      absoluteEpisodeNumber: undefined,
      tvdbPriorSeasonsCount: undefined,
      additionalTitles: undefined,
      runtime: undefined,
      episodeName: undefined,
      hasRemake: undefined,
      titleYear: undefined,
    };
    // Synthetic path has no imdbId, so resolveTitle's eager TVDB call doesn't
    // fire. When animeResolved gives us a TVDB ID directly, fetch the same
    // series data so anime via Kitsu/MAL/AniList/AniDB without IMDB mappings
    // gets full feature parity (absolute-fallback chain, bitrate display,
    // season-pack episode-size estimation). Cinemeta cumulative tier is
    // structurally unavailable on this path (no imdbId to query).
    if (animeResolved.tvdbId && season !== undefined) {
      const tvdbIdNum = parseInt(animeResolved.tvdbId, 10);
      if (Number.isFinite(tvdbIdNum) && tvdbIdNum > 0) {
        const tvdbResult = await resolveEpisodeCountFromTvdbId(tvdbIdNum, season, episode);
        if (tvdbResult) {
          titleInfo.episodesInSeason = tvdbResult.count;
          if (tvdbResult.runtime) titleInfo.runtime = tvdbResult.runtime;
          if (tvdbResult.episodeName) titleInfo.episodeName = tvdbResult.episodeName;
          if (tvdbResult.absoluteNumber) titleInfo.absoluteEpisodeNumber = tvdbResult.absoluteNumber;
          if (tvdbResult.priorSeasonsCount !== undefined) titleInfo.tvdbPriorSeasonsCount = tvdbResult.priorSeasonsCount;
        }
      }
    }
  } else {
    titleInfo = await resolveTitle(type, imdbId, season, episode, tvdbIdFromRequest);
    if (animeId) {
      titleInfo.isAnime = true;
    }
  }

  const searchCtx: SearchContext = {
    type, imdbId,
    title: titleInfo.title,
    year: titleInfo.year,
    country: titleInfo.country,
    season, episode,
    episodesInSeason: titleInfo.episodesInSeason,
    priorSeasonsEpisodeCount: titleInfo.priorSeasonsEpisodeCount,
    absoluteEpisodeNumber: titleInfo.absoluteEpisodeNumber,
    tvdbPriorSeasonsCount: titleInfo.tvdbPriorSeasonsCount,
    additionalTitles: titleInfo.additionalTitles,
    isAnime: titleInfo.isAnime,
    titleYear: titleInfo.titleYear,
    searchAliases: titleInfo.searchAliases,
    episodeAired: titleInfo.episodeAired,
    animeResolvedIds: animeResolved ? { tmdbId: animeResolved.tmdbId, tvdbId: animeResolved.tvdbId } : undefined,
    tvdbIdFromRequest,
  };

  return { titleInfo, searchCtx };
}

// Stream handler - called when user wants to watch something
builder.defineStreamHandler(({ type, id }) => withStepRef(id, async () => {
  try {
    // Check if addon is disabled
    if (!config.addonEnabled) {
      console.log('⏸️  Addon is disabled — returning no streams');
      return { streams: [] };
    }

    // Parse the ID: check for anime ID prefixes first, then tvdb:, then IMDB
    const animeId = parseAnimeId(id);
    let imdbId: string;
    let season: number | undefined;
    let episode: number | undefined;
    let animeResolved: ReturnType<typeof resolveAnimeId> = null;
    let tvdbIdFromRequest: number | undefined;

    if (animeId) {
      // Anime ID (kitsu:, mal:, anilist:, anidb:)
      if (!isDatabaseLoaded()) {
        console.warn(`⚠️  Anime ID ${id} received but anime databases not loaded — returning empty`);
        return { streams: [] };
      }
      animeResolved = resolveAnimeId(animeId);
      if (!animeResolved || (!animeResolved.imdbId && !animeResolved.title)) {
        console.warn(`⚠️  Could not resolve anime ID ${id} — no mapping found`);
        return { streams: [] };
      }
      imdbId = animeResolved.imdbId || `${animeId.prefix}:${animeId.id}`;
      season = animeResolved.season;
      episode = animeResolved.episode;
    } else if (id.startsWith('tvdb:')) {
      // Direct TVDB ID: tvdb:NNN or tvdb:NNN:S:E (movies and series)
      const parts = id.split(':');
      const numericTvdb = parseInt(parts[1] ?? '', 10);
      if (!Number.isFinite(numericTvdb) || numericTvdb <= 0) {
        console.warn(`⚠️  Malformed tvdb ID: ${id}`);
        return { streams: [] };
      }
      if (!config.searchConfig?.tvdbApiKey) {
        console.warn(`⚠️  tvdb: prefix received but TVDB API key not configured, returning empty`);
        return { streams: [] };
      }
      tvdbIdFromRequest = numericTvdb;
      // Use !== undefined so '0' (TVDB specials season) survives the truthy check.
      season  = parts[2] !== undefined && parts[2] !== '' ? parseInt(parts[2], 10) : undefined;
      episode = parts[3] !== undefined && parts[3] !== '' ? parseInt(parts[3], 10) : undefined;
      // Synthetic content-id for cache/bypass/log key strings. Never passed to
      // IMDB-keyed external APIs; the title resolver branches on tvdbIdHint and
      // skips Cinemeta/TMDB on this path.
      imdbId = `tvdb:${numericTvdb}`;
    } else if (id.startsWith('tmdb:')) {
      // Direct TMDB id: tmdb:NNN[:S:E] (emitted by catalog addons that key on
      // tmdb ids). Indexers can't search TV by tmdb id, and movies resolve
      // better through the imdb pipeline, so look up the record's external ids
      // once and delegate: imdb when present (movies + most series), else tvdb
      // for series.
      const parts = id.split(':');
      const numericTmdb = parseInt(parts[1] ?? '', 10);
      if (!Number.isFinite(numericTmdb) || numericTmdb <= 0) {
        console.warn(`⚠️  Malformed tmdb ID: ${id}`);
        return { streams: [] };
      }
      if (!config.searchConfig?.tmdbApiKey) {
        console.warn(`⚠️  tmdb: prefix received but TMDB API key not configured, returning empty`);
        return { streams: [] };
      }
      // Use !== undefined so '0' (specials season) survives the truthy check.
      season  = parts[2] !== undefined && parts[2] !== '' ? parseInt(parts[2], 10) : undefined;
      episode = parts[3] !== undefined && parts[3] !== '' ? parseInt(parts[3], 10) : undefined;
      const ext = await resolveTmdbExternalIds(numericTmdb, type === 'series' ? 'series' : 'movie');
      if (ext?.imdbId) {
        imdbId = ext.imdbId;
        console.log(`🆔 tmdb:${numericTmdb} → imdb ${imdbId}, using IMDB pipeline`);
      } else if (type === 'series' && ext?.tvdbId) {
        tvdbIdFromRequest = ext.tvdbId;
        imdbId = `tvdb:${ext.tvdbId}`;
        console.log(`🆔 tmdb:${numericTmdb} → tvdb ${ext.tvdbId}, using TVDB pipeline`);
      } else {
        console.warn(`⚠️  tmdb:${numericTmdb}: no imdb/tvdb mapping resolved, returning empty`);
        return { streams: [] };
      }
    } else {
      // Standard IMDB ID: tt1234567 or tt1234567:1:1
      const parts = id.split(':');
      imdbId = parts[0];
      season = parts[1] ? parseInt(parts[1], 10) : undefined;
      episode = parts[2] ? parseInt(parts[2], 10) : undefined;
    }

    // Manifest-scoped cache key.
    const requestManifestKey = requestContext.getStore()?.manifestKey || '';
    const cacheKey = buildSearchCacheKey(requestManifestKey, type, id, config);

    // Best's session for this title. Another title's unfinished Walk ends here, before this list's search (#244).
    listAsked(sessionKeyOf(requestManifestKey, type, imdbId, season, episode));

    // === SHARED: Filter dead NZBs from raw results ===
    const filterDeadFromRaw = (results: any[], play: PlayContext) => {
      if (!config.filterDeadNzbs) return results;
      const SELF_URL = getSelfUrl(); // must match the EasyNews NZB URLs the play side marks dead
      const manifestKey = requestContext.getStore()?.manifestKey || '';
      const cachePattern = episodeOf(play).episodePattern;
      const isDead = (url: string) =>
        (cachePattern && isDeadNzb(getDeadCacheKey(url, cachePattern))) || isDeadNzbByUrl(url);
      const before = results.length;
      const removed: { title: string; indexer: string }[] = [];
      const filtered = results.filter(r => {
        let dead: boolean;
        if (r.easynewsMeta) {
          const meta = r.easynewsMeta;
          const nzbParams = new URLSearchParams({ hash: meta.hash, filename: meta.filename, ext: meta.ext });
          if (meta.sig) nzbParams.set('sig', meta.sig);
          dead = isDead(`${SELF_URL}/${manifestKey}/easynews/nzb?${nzbParams.toString()}`);
        } else {
          dead = isDead(r.link);
        }
        if (dead) removed.push({ title: r.title, indexer: r.indexerName || r.origin });
        return !dead;
      });
      if (filtered.length < before) {
        console.log(`🚫 Filtered ${before - filtered.length} dead NZB(s) from results (${filtered.length} remaining)`);
        for (const { title, indexer } of removed) console.log(`   ✂️  "${title}" [${indexer}]`);
      }
      return filtered;
    };

    // === SHARED: the Head start (#206): Best's check and prepare begin when the list is asked for ===
    const startHeadStart = (fallbackCandidates: any[] | undefined, play: PlayContext) => {
      // Head start (#206): the list goes out now; Best's check and prepare begin in the background.
      // On-tile-selection turns it off: UF waits for a press of Best (the lobby in streamHandler.ts).
      if (isUltimateFallbackActive() && config.ultimateFallback) {
        if (config.ultimateFallback.whenToResolve === 'on-tile-selection') return;
        headStart(play, fallbackCandidates ?? [], config.ultimateFallback);
      }
    };

    // === SHARED: Process from raw results → streams (filter, sort, build) ===
    const processFromRaw = async (rawResults: any[], deprioritizedPacks: any[], titleMeta: { episodesInSeason?: number; episodeAired?: string; now: number; runtime?: number }) => {
      // The play context (#246): made once here, stored with the list's fallback group, read by every play of it.
      const play = makePlayContext({
        manifestKey: requestManifestKey, type, imdbId, season, episode,
        aired: titleMeta.episodeAired, episodesInSeason: titleMeta.episodesInSeason,
      });

      // Filter dead NZBs from both main results AND deprioritized packs — yearless
      // season packs of remade shows take the deprioritized path (applyRemakeFilter)
      // and would otherwise bypass the dead-NZB DB.
      let allResults = filterDeadFromRaw(rawResults, play);
      const filteredDeprioritizedPacks = filterDeadFromRaw(deprioritizedPacks, play);

      // Apply current user filter/sort preferences (deprioritized packs appended after sort)
      allResults = applyUserFilters(allResults, type, titleMeta.now, titleMeta.runtime, filteredDeprioritizedPacks);

      // No health check here (#191): the list goes out at once, unchecked; each
      // Source is checked when it is about to be played (Play-time check, #190).
      // Only EasyNews and Zyclops results carry a verified mark, made afresh each time.

      // Build streams
      // Build streams (and the list's fallback group, written once)
      const { streams, fallbackCandidates } = buildStreams({
        allResults,
        healthResults: verifiedMarks(allResults),
        play,
        now: titleMeta.now,
        runtime: titleMeta.runtime,
      });

      return { streams, fallbackCandidates, play };
    };

    // Check cache first (cacheTTL of 0 means disabled)
    if (config.cacheEnabled && config.cacheTTL > 0) {
      const cached = cache.get<{ rawResults: any[]; deprioritizedPacks: any[]; _meta: { type: string; season?: number; episode?: number; episodesInSeason?: number; episodeAired?: string; runtime?: number } }>(cacheKey);
      if (cached) {
        console.log(`💾 Cache hit for ${type} ${imdbId}`);

        const now = Date.now();

        // Re-apply filters and sort, and build streams with current settings
        const { streams, fallbackCandidates, play } = await processFromRaw(
          cached.rawResults, cached.deprioritizedPacks || [],
          { episodesInSeason: cached._meta.episodesInSeason, episodeAired: cached._meta.episodeAired, now, runtime: cached._meta.runtime }
        );

        startHeadStart(fallbackCandidates, play);
        return { streams };
      }
    }

    {
      const searchHeader = `🔍 Searching for ${type} ${imdbId}${season !== undefined ? ` S${season}E${episode}` : ''} [${config.indexManager}]`;
      console.log('');
      console.log('');
      console.log('╔' + '═'.repeat(70));
      console.log(`║  ${searchHeader}`);
      console.log('╚' + '═'.repeat(70));
      console.log('');
    }
    console.log('═══ Title Resolution ' + '═'.repeat(42));

    // === STEP 1: TITLE RESOLUTION + STEP 2 SEARCH CONTEXT ===
    const { titleInfo, searchCtx } = await resolveTitleAndBuildSearchCtx({
      type, imdbId, season, episode, animeId, animeResolved, tvdbIdFromRequest,
    });

    const [indexManagerResults, easynewsResults] = await Promise.all([
      indexManagerSearch(searchCtx),
      easynewsSearch(searchCtx),
    ]);
    // Tag indexer/easynews results with origin so downstream code can route correctly.
    // (Searchers don't currently emit origin natively; we tag at orchestrator level.)
    const tagOrigin = (r: any, origin: 'indexer' | 'easynews'): any =>
      r.origin ? r : { ...r, origin };
    const allRawResults: any[] = [
      ...indexManagerResults.map(r => tagOrigin(r, 'indexer')),
      ...easynewsResults.map(r => tagOrigin(r, 'easynews')),
    ];
    console.log('');
    console.log('═══ Results Processing ' + '═'.repeat(40));
    console.log(`📊 Found ${allRawResults.length} total results (indexer: ${indexManagerResults.length}, easynews: ${easynewsResults.length})`);

    // === STEP 3: DEDUP + CONTENT-DEPENDENT PRE-FILTERING (cacheable) ===
    const { results: rawResults, deprioritizedPacks } = deduplicateAndPreFilter(allRawResults, titleInfo.hasRemake, titleInfo.episodeName, titleInfo.year, titleInfo.titleYear);

    // === STEP 4: FILTER, SORT, BUILD (user-preference-dependent; no health check, #191) ===
    const now = Date.now();
    const { streams, fallbackCandidates, play } = await processFromRaw(
      rawResults, deprioritizedPacks,
      { episodesInSeason: titleInfo.episodesInSeason, episodeAired: titleInfo.episodeAired, now, runtime: titleInfo.runtime }
    );

    // Cache raw results + deprioritized packs (filters, sorts and marks reapply on cache hits).
    const skipEmptyCache = config.searchConfig?.cacheEmptyResults === false && rawResults.length === 0;
    if (config.cacheEnabled && config.cacheTTL > 0 && !skipEmptyCache) {
      cache.set(cacheKey, {
        rawResults,
        deprioritizedPacks,
        _meta: { type, season, episode, episodesInSeason: titleInfo.episodesInSeason, episodeAired: titleInfo.episodeAired, runtime: titleInfo.runtime },
      }, config.cacheTTL);
    } else if (skipEmptyCache && config.cacheEnabled && config.cacheTTL > 0) {
      console.log(`⏭️  Skipping cache write — 0 results for ${type} ${imdbId}`);
    }

    startHeadStart(fallbackCandidates, play);

    return { streams };
  } catch (error) {
    console.error('❌ Stream handler error:', error);
    return { streams: [] };
  }
}));

export { manifest as addonManifest };
export default builder.getInterface();
