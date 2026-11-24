/**
 * Search Orchestrator
 *
 * Runs index manager searches (Prowlarr, NZBHydra, or Newznab) and
 * EasyNews searches in parallel, returning combined raw results.
 */

import { config } from '../config/index.js';
import { UsenetSearcher } from '../parsers/usenetSearcher.js';
import { withBuffer, flushBuffer, withSubBuffer, slog, type LogEntry } from '../parsers/searchLogger.js';
import { trackQuery } from '../statsTracker.js';
import { resolveExternalId } from '../idResolver.js';
import { ProwlarrSearcher } from '../searchers/prowlarrSearcher.js';
import { NzbhydraSearcher } from '../searchers/nzbhydraSearcher.js';
import { EasynewsSearcher } from '../searchers/easynewsSearcher.js';
import { UsenetIndexer, type IndexerCaps } from '../types.js';
import { waysOf, idWaysOf, foundBy, mergeFound, logSearchLines, logStrictAlone, type AskedIndexer, type SearchWay } from './kaijuSearch.js';
import { withFlowTitle, withSearchIndexer, droppedBy, flowTitleOf, markSources } from '../parsers/searchFlow.js';
import { logStep, devSwitchOn } from '../utils/stepTiming.js';

// When SEARCH_TIMEOUT env is set, force it onto every Newznab indexer for this search cycle.
// Returns the original reference when no override is active — no allocation cost in the common path.
function applySearchTimeoutOverride(indexer: UsenetIndexer): UsenetIndexer {
  return config.searchTimeoutOverride !== undefined
    ? { ...indexer, timeoutEnabled: true, timeout: config.searchTimeoutOverride }
    : indexer;
}

export interface SearchContext {
  type: string;
  imdbId: string;
  title: string;
  year?: string;
  country?: string;
  season?: number;
  episode?: number;
  episodesInSeason?: number;
  /** Cumulative episode count across prior seasons. Feeds the absolute-numbering fallback. */
  priorSeasonsEpisodeCount?: number;
  /** Canonical absolute episode number from TVDB (when set). Tier-1 source for the absolute-numbering fallback. */
  absoluteEpisodeNumber?: number;
  /** Cumulative episode count across prior aired seasons from TVDB. Tier-2 source when canonical isn't set. */
  tvdbPriorSeasonsCount?: number;
  additionalTitles?: string[];
  isAnime: boolean;
  titleYear?: string;
  /** English aliases from TVDB whose normalized form is a strict substring of the canonical title and substantially shorter. Used as a zero-result UTS fallback for shows whose release groups publish under a shortened name. */
  searchAliases?: string[];
  /** Air date of the targeted episode in `YYYY-MM-DD` form. Triggers a date-formatted alias query (e.g. `<alias> 2024.05.21`) instead of `<alias> SxxExx` when set, for shows whose releases are date-named rather than season/episode-numbered. */
  episodeAired?: string;
  /** Other TMDB/TVDB names of the title the search does not ask by (TVDB's aliases, TMDB's alternative titles): a
   *  release that fits one is kept and sure (Search Flow's extra proof, #286). */
  knownNames?: string[];
  /** The title's runtime in seconds (TMDB for a film, TVDB for an episode): a maybe whose own runtime fits it is sure
   *  (Search Flow's extra proof, #286). */
  runtime?: number;
  // Pre-resolved IDs from anime database (when request came from anime ID prefix)
  animeResolvedIds?: { tmdbId?: string; tvdbId?: string };
  // Numeric TVDB id parsed from the Stremio request when it arrived via the
  // `tvdb:` prefix. Seeds resolvedIds.tvdb directly so indexer searches use
  // tvdbid= without needing an IMDB id to drive resolveExternalId.
  tvdbIdFromRequest?: number;
}

/**
 * Search via the configured index manager (Prowlarr, NZBHydra, or Newznab).
 */
export function indexManagerSearch(ctx: SearchContext): Promise<any[]> {
  const title = flowTitleOf(ctx);
  const dev = devSwitchOn();
  return withFlowTitle(title, async () => {
    const asked: AskedIndexer[] = [];
    const results = await askIndexManager(ctx, asked);
    if (dev) logSearchLines(searchLog(ctx), asked, markSources(results, title), droppedBy(), managerName());
    return results;
  }, dev);
}

/**
 * Kaiju Search (#285): the indexers' and EasyNews's search at once, both inside the title's Search Flow. With the dev
 * switch on, a `search` line when the strict rule alone would have left nothing of what both found.
 */
export async function kaijuSearch(ctx: SearchContext): Promise<{ indexer: any[]; easynews: any[] }> {
  const [indexer, easynews] = await Promise.all([indexManagerSearch(ctx), easynewsSearch(ctx)]);
  if (devSwitchOn()) logStrictAlone(searchLog(ctx), markSources([...indexer, ...easynews], flowTitleOf(ctx)));
  return { indexer, easynews };
}

/** A dev `search` step line for this title (names and numbers only). */
const searchLog = (ctx: SearchContext) => (fields: Record<string, unknown>) => logStep({ step: 'search', ms: 0, title: ctx.title, ...fields });

/** The index manager a query to several indexers at once went to. */
const managerName = () => (config.indexManager === 'prowlarr' ? 'Prowlarr' : config.indexManager === 'nzbhydra' ? 'NZBHydra' : 'Newznab');

/** The ID ways an indexer is asked this time: those its caps list that the title has (IMDb needs a tt id). */
function idsAsked(kind: 'movie' | 'tv', caps: IndexerCaps | undefined, imdbId: string, resolvedIds: Map<string, unknown>): SearchWay[] {
  return idWaysOf(kind, caps).filter(w => (w === 'imdb' ? imdbId.startsWith('tt') : !!resolvedIds.get(w)));
}

/** Kaiju Search over the configured index manager, inside the title's Search Flow (`withFlowTitle`). `asked` gets
 *  every indexer asked and the IDs it was asked by. */
async function askIndexManager(ctx: SearchContext, asked: AskedIndexer[]): Promise<any[]> {
  const kind = ctx.type === 'movie' ? 'movie' as const : 'tv' as const;
  const { type, imdbId, title, year, country, season, episode, episodesInSeason, priorSeasonsEpisodeCount, absoluteEpisodeNumber, tvdbPriorSeasonsCount, additionalTitles, isAnime, titleYear, searchAliases, episodeAired, animeResolvedIds, tvdbIdFromRequest } = ctx;

  if (config.indexManager === 'prowlarr' && config.prowlarrUrl && config.prowlarrApiKey) {
    // === PROWLARR MODE ===
    const enabledSynced = (config.syncedIndexers || []).filter(i => i.enabledForSearch);
    if (enabledSynced.length === 0) {
      console.log('⚠️  No synced Prowlarr indexers enabled for search');
      return [];
    }

    // Kaiju Search (#285): every synced indexer is asked by the IDs its capabilities list, and by name.
    const neededMethods = new Set<string>();
    for (const indexer of enabledSynced) for (const m of waysOf(kind, indexer.capabilities)) neededMethods.add(m);
    console.log('');
    console.log('═══ Search Setup ' + '═'.repeat(46));
    console.log(`📋 Kaiju Search (Prowlarr): ${[...neededMethods].join(', ')} across ${enabledSynced.length} indexer(s)`);
    for (const indexer of enabledSynced) console.log(`   ${indexer.name}: ${waysOf(kind, indexer.capabilities).join(', ')}`);

    // Resolve external IDs needed by indexers — seed from anime database if available
    const resolvedIds = new Map<string, { idParam: string; idValue: string } | null>();
    if (animeResolvedIds?.tmdbId) resolvedIds.set('tmdb', { idParam: 'tmdbid', idValue: animeResolvedIds.tmdbId });
    if (animeResolvedIds?.tvdbId) resolvedIds.set('tvdb', { idParam: 'tvdbid', idValue: animeResolvedIds.tvdbId });
    if (tvdbIdFromRequest && !resolvedIds.has('tvdb')) {
      resolvedIds.set('tvdb', { idParam: 'tvdbid', idValue: String(tvdbIdFromRequest) });
    }
    await Promise.all([...neededMethods]
      .filter(m => m !== 'imdb' && m !== 'text' && !resolvedIds.has(m))
      .map(async (method) => {
        const result = await resolveExternalId(imdbId, type as 'movie' | 'series', method as 'tmdb' | 'tvdb' | 'tvmaze');
        if (!result) console.warn(`⚠️  Failed to resolve ${method} ID for ${imdbId}`);
        resolvedIds.set(method, result);
      }));

    for (const i of enabledSynced) asked.push({ source: i.name, ids: idsAsked(kind, i.capabilities, imdbId, resolvedIds) });
    const startTime = Date.now();
    const timeoutEnabled = config.searchTimeoutOverride !== undefined ? true : config.prowlarrTimeoutEnabled;
    const timeoutSeconds = config.searchTimeoutOverride ?? config.prowlarrTimeout;
    const searcher = new ProwlarrSearcher(
      config.prowlarrUrl, config.prowlarrApiKey, enabledSynced,
      timeoutEnabled, timeoutSeconds,
    );

    try {
      const { result: results, lines } = await withBuffer(async (): Promise<any[]> => {
        if (type === 'movie') {
          return await searcher.searchMovie(imdbId, title, year, country, resolvedIds, additionalTitles, titleYear, isAnime, searchAliases);
        } else if (type === 'series' && season !== undefined && episode !== undefined) {
          return await searcher.searchTVShow(imdbId, title, season, episode, episodesInSeason, year, country, resolvedIds, additionalTitles, titleYear, isAnime, searchAliases, episodeAired, priorSeasonsEpisodeCount, absoluteEpisodeNumber, tvdbPriorSeasonsCount);
        }
        return [];
      });
      flushBuffer(lines, 'Prowlarr');
      const merged = mergeFound(results);

      const responseTime = Date.now() - startTime;
      const indexerCounts = new Map<string, number>();
      for (const r of results) {
        indexerCounts.set(r.indexerName, (indexerCounts.get(r.indexerName) || 0) + 1);
      }
      for (const [name, count] of indexerCounts) {
        trackQuery(name, true, responseTime, count);
      }
      return merged;
    } catch (error) {
      const responseTime = Date.now() - startTime;
      trackQuery('Prowlarr', false, responseTime, 0, error instanceof Error ? error.message : 'Unknown error');
      console.error(`❌ Error searching via Prowlarr:`, error);
      return [];
    }

  } else if (config.indexManager === 'nzbhydra' && config.nzbhydraUrl && config.nzbhydraApiKey) {
    // === NZBHYDRA MODE ===
    const enabledSynced = (config.syncedIndexers || []).filter(i => i.enabledForSearch);
    if (enabledSynced.length === 0) {
      console.log('⚠️  No synced NZBHydra indexers enabled for search');
      return [];
    }

    // Kaiju Search (#285): every synced indexer is asked by the IDs its capabilities list, and by name.
    const neededMethods = new Set<string>();
    for (const indexer of enabledSynced) for (const m of waysOf(kind, indexer.capabilities)) neededMethods.add(m);
    console.log('');
    console.log('═══ Search Setup ' + '═'.repeat(46));
    console.log(`📋 Kaiju Search (NZBHydra): ${[...neededMethods].join(', ')} across ${enabledSynced.length} indexer(s)`);
    for (const indexer of enabledSynced) console.log(`   ${indexer.name}: ${waysOf(kind, indexer.capabilities).join(', ')}`);

    // Resolve external IDs needed by indexers — seed from anime database if available
    const resolvedIds = new Map<string, { idParam: string; idValue: string } | null>();
    if (animeResolvedIds?.tmdbId) resolvedIds.set('tmdb', { idParam: 'tmdbid', idValue: animeResolvedIds.tmdbId });
    if (animeResolvedIds?.tvdbId) resolvedIds.set('tvdb', { idParam: 'tvdbid', idValue: animeResolvedIds.tvdbId });
    if (tvdbIdFromRequest && !resolvedIds.has('tvdb')) {
      resolvedIds.set('tvdb', { idParam: 'tvdbid', idValue: String(tvdbIdFromRequest) });
    }
    await Promise.all([...neededMethods]
      .filter(m => m !== 'imdb' && m !== 'text' && !resolvedIds.has(m))
      .map(async (method) => {
        const result = await resolveExternalId(imdbId, type as 'movie' | 'series', method as 'tmdb' | 'tvdb' | 'tvmaze');
        if (!result) console.warn(`⚠️  Failed to resolve ${method} ID for ${imdbId}`);
        resolvedIds.set(method, result);
      }));

    for (const i of enabledSynced) asked.push({ source: i.name, ids: idsAsked(kind, i.capabilities, imdbId, resolvedIds) });
    const startTime = Date.now();
    const nzbhydraTimeoutEnabled = config.searchTimeoutOverride !== undefined ? true : config.nzbhydraTimeoutEnabled;
    const nzbhydraTimeoutSeconds = config.searchTimeoutOverride ?? config.nzbhydraTimeout;
    const searcher = new NzbhydraSearcher(
      config.nzbhydraUrl, config.nzbhydraApiKey, enabledSynced,
      config.nzbhydraUsername, config.nzbhydraPassword,
      nzbhydraTimeoutEnabled, nzbhydraTimeoutSeconds,
    );

    try {
      const { result: results, lines } = await withBuffer(async (): Promise<any[]> => {
        if (type === 'movie') {
          return await searcher.searchMovie(imdbId, title, year, country, resolvedIds, additionalTitles, titleYear, isAnime, searchAliases);
        } else if (type === 'series' && season !== undefined && episode !== undefined) {
          return await searcher.searchTVShow(imdbId, title, season, episode, episodesInSeason, year, country, resolvedIds, additionalTitles, titleYear, isAnime, searchAliases, episodeAired, priorSeasonsEpisodeCount, absoluteEpisodeNumber, tvdbPriorSeasonsCount);
        }
        return [];
      });
      flushBuffer(lines, 'NZBHydra');
      const merged = mergeFound(results);

      const responseTime = Date.now() - startTime;
      const indexerCounts = new Map<string, number>();
      for (const r of results) {
        indexerCounts.set(r.indexerName, (indexerCounts.get(r.indexerName) || 0) + 1);
      }
      for (const [name, count] of indexerCounts) {
        trackQuery(name, true, responseTime, count);
      }
      return merged;
    } catch (error) {
      const responseTime = Date.now() - startTime;
      trackQuery('NZBHydra', false, responseTime, 0, error instanceof Error ? error.message : 'Unknown error');
      console.error(`❌ Error searching via NZBHydra:`, error);
      return [];
    }

  } else {
    // === NEWZNAB MODE ===
    const enabledIndexers = config.indexers.filter(i => i.enabled);
    const waysFor = (i: typeof enabledIndexers[number]) => waysOf(kind, i.caps);

    // The ways needed across all enabled indexers: the IDs their caps list, and by name.
    const neededMethods = new Set<string>();
    for (const indexer of enabledIndexers) for (const m of waysFor(indexer)) neededMethods.add(m);
    console.log('');
    console.log('═══ Search Setup ' + '═'.repeat(46));
    console.log(`📋 Kaiju Search (Newznab): ${[...neededMethods].join(', ')} across ${enabledIndexers.length} indexer(s)`);
    for (const indexer of enabledIndexers) console.log(`   ${indexer.name}: ${waysFor(indexer).join(', ')}`);
    if (isAnime && neededMethods.has('text') && additionalTitles?.length) {
      console.log(`🎌 Anime dual-title search: "${title}" + ${additionalTitles.map(t => `"${t}"`).join(', ')}`);
    }

    // Resolve external IDs needed by indexers — seed from anime database if available
    const resolvedIds = new Map<string, { idParam: string; idValue: string } | null>();
    if (animeResolvedIds?.tmdbId) resolvedIds.set('tmdb', { idParam: 'tmdbid', idValue: animeResolvedIds.tmdbId });
    if (animeResolvedIds?.tvdbId) resolvedIds.set('tvdb', { idParam: 'tvdbid', idValue: animeResolvedIds.tvdbId });
    if (tvdbIdFromRequest && !resolvedIds.has('tvdb')) {
      resolvedIds.set('tvdb', { idParam: 'tvdbid', idValue: String(tvdbIdFromRequest) });
    }
    await Promise.all([...neededMethods]
      .filter(m => m !== 'imdb' && m !== 'text' && !resolvedIds.has(m))
      .map(async (method) => {
        const result = await resolveExternalId(imdbId, type as 'movie' | 'series', method as 'tmdb' | 'tvdb' | 'tvmaze');
        if (!result) {
          console.warn(`⚠️  Failed to resolve ${method} ID for ${imdbId}`);
        }
        resolvedIds.set(method, result);
      }));

    for (const i of enabledIndexers) asked.push({ source: i.name, ids: idsAsked(kind, i.caps, imdbId, resolvedIds) });

    // Indexers that timed out during the main search pass. Scoped to this single
    // indexManagerSearch invocation so the text-fallback and alt-title retries can
    // skip them and avoid stacking a second timeout wait on an already-slow backend.
    const timedOutIndexers = new Set<string>();

    // Per-indexer log accumulator. Each phase (main pass, parallel-alt, alias
    // fallback, absolute fallback, alt-title retry) appends its lines into this
    // map keyed by indexer name. A single flush at the end of the Newznab branch
    // produces ONE `═══ <indexer> ═══` cluster per indexer containing every phase
    // that fired, matching the single-cluster shape used by Prowlarr/NZBHydra/EasyNews.
    const indexerLines = new Map<string, LogEntry[]>();
    const accumulate = (name: string, lines: LogEntry[]) => {
      const existing = indexerLines.get(name) ?? [];
      existing.push(...lines);
      indexerLines.set(name, existing);
    };

    if (isAnime && !!additionalTitles?.length && enabledIndexers.length > 0) {
      console.log(`🎌 Newznab anime dual-title fan-out: querying primary + ${additionalTitles!.length} alt(s)`);
    }

    // Search across all enabled indexers, each with its own methods and resolved IDs
    const searchPromises = enabledIndexers
      .map(async (indexer) => {
        const startTime = Date.now();
        const methodArr = waysFor(indexer);

        const searcher = new UsenetSearcher(applySearchTimeoutOverride(indexer));

        const { result, lines } = await withBuffer(async (): Promise<any[]> => {
          try {
            const tasks: Promise<any[]>[] = [];
            for (let i = 0; i < methodArr.length; i++) {
              const method = methodArr[i];
              const externalId = (method !== 'imdb' && method !== 'text')
                ? resolvedIds.get(method) ?? null
                : null;

              const way = method === 'text' ? 'name' : 'id';
              if (type === 'movie') {
                tasks.push(withSubBuffer(`movie ${method} search`, () => searcher.searchMovie(imdbId, title, year, country, externalId || undefined, method, additionalTitles, titleYear)).then(r => foundBy(r, way)));
              } else if (type === 'series' && season !== undefined && episode !== undefined) {
                tasks.push(withSubBuffer(`TV ${method} search S${season}E${episode}`, () => searcher.searchTVShow(imdbId, title, season, episode, episodesInSeason, year, country, externalId || undefined, method, additionalTitles, titleYear, { includePacks: false })).then(r => foundBy(r, way)));
              }

              if (method === 'text' && isAnime && additionalTitles?.length) {
                for (const altTitle of additionalTitles) {
                  if (type === 'movie') {
                    tasks.push(withSubBuffer(`movie text search [alt: "${altTitle}"]`, () => searcher.searchMovie(imdbId, altTitle, year, country, undefined, 'text', additionalTitles, titleYear)));
                  } else if (type === 'series' && season !== undefined && episode !== undefined) {
                    tasks.push(withSubBuffer(`TV text search [alt: "${altTitle}"]`, () => searcher.searchTVShow(imdbId, altTitle, season, episode, episodesInSeason, year, country, undefined, 'text', additionalTitles, titleYear, { includePacks: false })));
                  }
                }
              }
            }

            if (type === 'series' && season !== undefined) {
              // Mirror the gates inside searchTVShowPacks so the sub-buffer header doesn't print when no pack feature will run.
              const includeMultiSeasonPacks = config.searchConfig?.includeMultiSeasonPacks ?? true;
              const includeSeasonPacks = config.searchConfig?.includeSeasonPacks ?? config.includeSeasonPacks;
              const anyPackFeatureEnabled =
                (includeMultiSeasonPacks && (season > 1 || !!episodesInSeason))
                || (!!includeSeasonPacks && !!episodesInSeason);
              if (anyPackFeatureEnabled) {
                tasks.push(withSubBuffer('Pack queries', () => searcher.searchTVShowPacks(title, season, episodesInSeason, year, country, additionalTitles, titleYear)));
              }
            }

            const allMethodResults = (await Promise.all(tasks)).flat();

            if (searcher.timedOut) timedOutIndexers.add(indexer.name);
            const responseTime = Date.now() - startTime;
            trackQuery(indexer.name, true, responseTime, allMethodResults.length);

            return allMethodResults.map(r => ({ ...r, indexerName: indexer.name }));
          } catch (error) {
            if (searcher.timedOut) timedOutIndexers.add(indexer.name);
            const responseTime = Date.now() - startTime;
            trackQuery(indexer.name, false, responseTime, 0, error instanceof Error ? error.message : 'Unknown error');
            console.error(`❌ Error searching ${indexer.name}:`, error);
            return [];
          }
        });
        return { result, lines, indexerName: indexer.name };
      });

    // Parallel alt-title search: when the user toggle is on, fire each
    // additional title as a text search concurrently with the primary pass
    // instead of waiting for a zero-result fallback. UTS-only by intent;
    // anime is excluded because its inner loop above already runs Kitsu +
    // Cinemeta in parallel via the per-indexer text path.
    const parallelAltEnabled = config.searchConfig?.parallelAlternateTitleSearch === true
      && !!additionalTitles?.length
      && !isAnime;
    if (parallelAltEnabled && enabledIndexers.length > 0) {
      slog(type === 'movie'
        ? `🔀 Newznab parallel alt-title movie search: querying primary + ${additionalTitles!.length} alt(s) concurrently`
        : `🔀 Newznab parallel alt-title search: querying primary + ${additionalTitles!.length} alt(s) concurrently`);
    }
    const altSearchPromises = parallelAltEnabled
      ? enabledIndexers.flatMap(indexer => additionalTitles!.map(async (altTitle) => {
          const startTime = Date.now();
          const searcher = new UsenetSearcher(applySearchTimeoutOverride(indexer));
          const { result, lines } = await withBuffer(async (): Promise<any[]> => {
            try {
              let altResults: any[] = [];
              if (type === 'movie') {
                altResults = await searcher.searchMovie(imdbId, altTitle, year, country, undefined, 'text', undefined, titleYear);
              } else if (type === 'series' && season !== undefined && episode !== undefined) {
                altResults = await searcher.searchTVShow(imdbId, altTitle, season, episode, episodesInSeason, year, country, undefined, 'text', undefined, titleYear);
              }
              if (searcher.timedOut) timedOutIndexers.add(indexer.name);
              const responseTime = Date.now() - startTime;
              trackQuery(indexer.name, true, responseTime, altResults.length);
              return altResults.map(r => ({ ...r, indexerName: indexer.name }));
            } catch (error) {
              if (searcher.timedOut) timedOutIndexers.add(indexer.name);
              const responseTime = Date.now() - startTime;
              trackQuery(indexer.name, false, responseTime, 0, error instanceof Error ? error.message : 'Unknown error');
              console.error(`❌ Error in parallel alt-title search for ${indexer.name} ("${altTitle}"):`, error);
              return [];
            }
          });
          return { result, lines, indexerName: indexer.name };
        }))
      : [];

    const mainResults = await Promise.all(searchPromises);
    for (const r of mainResults) accumulate(r.indexerName, r.lines);
    const altResults = await Promise.all(altSearchPromises);
    for (const r of altResults) accumulate(r.indexerName, r.lines);

    let results = [...mainResults.flatMap(r => r.result), ...altResults.flatMap(r => r.result)];

    // Alias title fallback: when the primary pass
    // returned zero, retry once per substring-shortcut English alias from
    // TVDB. Each alias is the indexer query AND its own filter target, so
    // results that match the alias but not the canonical title are kept.
    // Mirrors the per-alt shape of the parallel-alt block above. Skipped for
    // anime (anime has its own Kitsu/Cinemeta fan-out path).
    if (
      results.length === 0
      && !isAnime
      && config.searchConfig?.aliasTitleFallback !== false
      && !!searchAliases?.length
    ) {
      const retryIndexers = enabledIndexers.filter(i => !timedOutIndexers.has(i.name));
      if (retryIndexers.length === 0 && enabledIndexers.length > 0) {
        slog(`⚠️  Every indexer timed out in the main search, skipping alias-title fallback`);
      }
      if (retryIndexers.length > 0) {
        // When TVDB has an aired date for the targeted episode, use the
        // date-numbered query format (alias YYYY.MM.DD) so daily/talk shows
        // whose releases are dated rather than SxxExx-numbered are reachable.
        // Falls back to seasonal SxxExx when no aired date is known.
        const useDateScheme = type === 'series' && typeof episodeAired === 'string' && /^\d{4}-\d{2}-\d{2}/.test(episodeAired);
        const aliasPromises = retryIndexers.map(async (indexer) => {
          const { result, lines } = await withBuffer(async (): Promise<any[]> => {
            const subResults = await Promise.all(searchAliases!.map(alias =>
              withSubBuffer(`Alias fallback: "${alias}"`, async () => {
                const startTime = Date.now();
                const searcher = new UsenetSearcher(applySearchTimeoutOverride(indexer));
                try {
                  let fbResults: any[] = [];
                  if (type === 'movie') {
                    fbResults = await searcher.searchMovie(imdbId, alias, year, country, undefined, 'text', undefined, titleYear);
                  } else if (type === 'series' && season !== undefined && episode !== undefined) {
                    const tvOptions = useDateScheme
                      ? { numberingScheme: 'date' as const, airedDate: episodeAired }
                      : undefined;
                    fbResults = await searcher.searchTVShow(imdbId, alias, season, episode, episodesInSeason, year, country, undefined, 'text', undefined, titleYear, tvOptions);
                  }
                  if (searcher.timedOut) timedOutIndexers.add(indexer.name);
                  const responseTime = Date.now() - startTime;
                  trackQuery(indexer.name, true, responseTime, fbResults.length);
                  return fbResults.map(r => ({ ...r, indexerName: indexer.name }));
                } catch (error) {
                  if (searcher.timedOut) timedOutIndexers.add(indexer.name);
                  const responseTime = Date.now() - startTime;
                  trackQuery(indexer.name, false, responseTime, 0, error instanceof Error ? error.message : 'Unknown error');
                  slog(`❌ Error in alias fallback for ${indexer.name} ("${alias}"): ${error instanceof Error ? error.message : 'Unknown error'}`);
                  return [];
                }
              })
            ));
            return subResults.flat();
          });
          return { result, lines, indexerName: indexer.name };
        });
        const aliasResults = await Promise.all(aliasPromises);
        for (const r of aliasResults) accumulate(r.indexerName, r.lines);
        results = aliasResults.flatMap(r => r.result);
      }
    }

    // Absolute-episode fallback: covers indexers that file releases under
    // continuous absolute numbering (Title E31) rather than Title S03E07.
    // When combined results are zero after the main pass + standard
    // text-fallback, retry every non-timed-out indexer with E{absolute}.
    // By this point each has already had a UTS attempt (either configured
    // or via the L315 fallback above), so all are valid retry targets.
    // UTS-only — ID methods don't use the SxxExx vs E{n} distinction.
    // Downstream isTextSearchMatch still requires the resolved title to
    // appear in the result, so non-matching releases get filtered.
    if (
      results.length === 0
      && type === 'series'
      && season !== undefined
      && episode !== undefined
      && config.searchConfig?.absoluteEpisodeFallback !== false
    ) {
      const retryIndexers = enabledIndexers.filter(i => !timedOutIndexers.has(i.name));
      if (retryIndexers.length === 0 && enabledIndexers.length > 0) {
        slog(`⚠️  Every indexer timed out in the main search, skipping absolute-episode fallback`);
      }
      if (retryIndexers.length > 0) {
        // Three-tier source chain: TVDB canonical → TVDB cumulative → Cinemeta cumulative → per-season E{episode}.
        // Tiers 1 and 2 come from the same eager TVDB call during title resolve, so picking between them is free.
        let absoluteEp: number;
        if (typeof absoluteEpisodeNumber === 'number') {
          absoluteEp = absoluteEpisodeNumber;
        } else if (typeof tvdbPriorSeasonsCount === 'number') {
          absoluteEp = tvdbPriorSeasonsCount + episode;
        } else if (priorSeasonsEpisodeCount !== undefined) {
          absoluteEp = priorSeasonsEpisodeCount + episode;
        } else {
          console.warn(`⚠️  Absolute episode fallback: priorSeasonsEpisodeCount unavailable (Cinemeta gap), using per-season E${episode}`);
          absoluteEp = episode;
        }
        // When parallel mode is on, fan the absolute pass over primary + alts
        // upfront — the standard alt-title retry below is gated off in that
        // mode, so this is the only place alts get an E{absolute} probe.
        const titlesToRetry = (parallelAltEnabled && additionalTitles?.length)
          ? [title, ...additionalTitles]
          : [title];
        const fallbackPromises = retryIndexers.map(async (indexer) => {
          const { result, lines } = await withBuffer(async (): Promise<any[]> => {
            const subResults = await Promise.all(titlesToRetry.map(t =>
              withSubBuffer(`Absolute fallback: "${t} E${absoluteEp}"`, async () => {
                const startTime = Date.now();
                const searcher = new UsenetSearcher(applySearchTimeoutOverride(indexer));
                try {
                  // Pass additionalTitles only for primary pass — alt passes filter
                  // strictly against the alt to avoid loose cross-title matches.
                  const altsForFilter = t === title ? additionalTitles : undefined;
                  const fbResults = await searcher.searchTVShow(
                    imdbId, t, season, episode, episodesInSeason, year, country,
                    undefined, 'text', altsForFilter, titleYear,
                    { numberingScheme: 'absolute', absoluteEp }
                  );
                  if (searcher.timedOut) timedOutIndexers.add(indexer.name);
                  const responseTime = Date.now() - startTime;
                  trackQuery(indexer.name, true, responseTime, fbResults.length);
                  return fbResults.map(result => ({ ...result, indexerName: indexer.name }));
                } catch (error) {
                  if (searcher.timedOut) timedOutIndexers.add(indexer.name);
                  const responseTime = Date.now() - startTime;
                  trackQuery(indexer.name, false, responseTime, 0, error instanceof Error ? error.message : 'Unknown error');
                  slog(`❌ Error in absolute episode fallback for ${indexer.name} ("${t}"): ${error instanceof Error ? error.message : 'Unknown error'}`);
                  return [];
                }
              })
            ));
            return subResults.flat();
          });
          return { result, lines, indexerName: indexer.name };
        });
        const fallbackResults = await Promise.all(fallbackPromises);
        for (const r of fallbackResults) accumulate(r.indexerName, r.lines);
        results = fallbackResults.flatMap(r => r.result);
      }
    }

    // Alternative-title retry: if still 0 results and alternative titles exist, retry with each.
    // Skip indexers that have timed out at any prior point in this cycle.
    // Skipped entirely in parallel-alt mode — those alts already fired upfront.
    if (results.length === 0 && additionalTitles?.length && enabledIndexers.length > 0 && !parallelAltEnabled) {
      const altIndexers = enabledIndexers.filter(i => !timedOutIndexers.has(i.name));
      if (altIndexers.length === 0 && enabledIndexers.length > 0) {
        slog(`⚠️  Every indexer timed out in the main search, skipping alt-title retry`);
      }
      for (const altTitle of additionalTitles) {
        if (altIndexers.length === 0) break;
        slog(`🔄 Newznab alt-title retry: "${altTitle}"`);
        const altPromises = altIndexers.map(async (indexer) => {
          const { result, lines } = await withBuffer(async (): Promise<any[]> => {
            return withSubBuffer(`Alt-title retry: "${altTitle}"`, async () => {
              const startTime = Date.now();
              const searcher = new UsenetSearcher(applySearchTimeoutOverride(indexer));
              try {
                let r: any[] = [];
                if (type === 'movie') {
                  r = await searcher.searchMovie(imdbId, altTitle, year, country, undefined, 'text', undefined, titleYear);
                } else if (type === 'series' && season !== undefined && episode !== undefined) {
                  r = await searcher.searchTVShow(imdbId, altTitle, season, episode, episodesInSeason, year, country, undefined, 'text', undefined, titleYear);
                }
                if (searcher.timedOut) timedOutIndexers.add(indexer.name);
                const responseTime = Date.now() - startTime;
                trackQuery(indexer.name, true, responseTime, r.length);
                return r.map(result => ({ ...result, indexerName: indexer.name }));
              } catch (error) {
                if (searcher.timedOut) timedOutIndexers.add(indexer.name);
                const responseTime = Date.now() - startTime;
                trackQuery(indexer.name, false, responseTime, 0, error instanceof Error ? error.message : 'Unknown error');
                slog(`❌ Error in alt-title retry for ${indexer.name}: ${error instanceof Error ? error.message : 'Unknown error'}`);
                return [];
              }
            });
          });
          return { result, lines, indexerName: indexer.name };
        });

        const altResultsList = await Promise.all(altPromises);
        for (const r of altResultsList) accumulate(r.indexerName, r.lines);
        let altResults = altResultsList.flatMap(r => r.result);

        // Absolute-episode fallback for the alt title — same rationale as the
        // primary-title fallback above. If the alt-title SxxExx came back
        // empty and we're searching a series with the toggle on, retry the
        // alt title with E{absolute}.
        if (
          altResults.length === 0
          && type === 'series'
          && season !== undefined
          && episode !== undefined
          && config.searchConfig?.absoluteEpisodeFallback !== false
        ) {
          // Same three-tier source chain as the primary-title block above. The
          // values are imdbId-scoped on titleResolve so alt-title iterations
          // share the same number — no extra TVDB call here.
          let absoluteEp: number;
          if (typeof absoluteEpisodeNumber === 'number') {
            absoluteEp = absoluteEpisodeNumber;
          } else if (typeof tvdbPriorSeasonsCount === 'number') {
            absoluteEp = tvdbPriorSeasonsCount + episode;
          } else if (priorSeasonsEpisodeCount !== undefined) {
            absoluteEp = priorSeasonsEpisodeCount + episode;
          } else {
            absoluteEp = episode;
          }
          const absoluteAltIndexers = altIndexers.filter(i => !timedOutIndexers.has(i.name));
          if (absoluteAltIndexers.length > 0) {
            const absPromises = absoluteAltIndexers.map(async (indexer) => {
              const { result, lines } = await withBuffer(async (): Promise<any[]> => {
                return withSubBuffer(`Alt-title absolute fallback: "${altTitle} E${absoluteEp}"`, async () => {
                  const startTime = Date.now();
                  const searcher = new UsenetSearcher(applySearchTimeoutOverride(indexer));
                  try {
                    const fbResults = await searcher.searchTVShow(
                      imdbId, altTitle, season, episode, episodesInSeason, year, country,
                      undefined, 'text', undefined, titleYear,
                      { numberingScheme: 'absolute', absoluteEp }
                    );
                    if (searcher.timedOut) timedOutIndexers.add(indexer.name);
                    const responseTime = Date.now() - startTime;
                    trackQuery(indexer.name, true, responseTime, fbResults.length);
                    return fbResults.map(result => ({ ...result, indexerName: indexer.name }));
                  } catch (error) {
                    if (searcher.timedOut) timedOutIndexers.add(indexer.name);
                    const responseTime = Date.now() - startTime;
                    trackQuery(indexer.name, false, responseTime, 0, error instanceof Error ? error.message : 'Unknown error');
                    slog(`❌ Error in absolute episode fallback (alt title) for ${indexer.name}: ${error instanceof Error ? error.message : 'Unknown error'}`);
                    return [];
                  }
                });
              });
              return { result, lines, indexerName: indexer.name };
            });
            const absResultsList = await Promise.all(absPromises);
            for (const r of absResultsList) accumulate(r.indexerName, r.lines);
            altResults = absResultsList.flatMap(r => r.result);
          }
        }

        if (altResults.length > 0) {
          results = altResults;
          break;
        }
      }
    }

    // Single end-of-search flush per indexer: every phase that fired for an
    // indexer (main pass + parallel-alt + alias + absolute + alt-title retry)
    // accumulated into one buffer and now renders as ONE `═══ <indexer> ═══`
    // cluster, matching Prowlarr/NZBHydra/EasyNews single-cluster shape.
    for (const [name, lines] of indexerLines) flushBuffer(lines, name);

    return mergeFound(results);
  }
}

/**
 * Search EasyNews (runs in parallel with index manager search).
 */
export function easynewsSearch(ctx: SearchContext): Promise<any[]> {
  if (!config.easynewsEnabled || !config.easynewsUsername || !config.easynewsPassword) return Promise.resolve([]);
  const title = flowTitleOf(ctx);
  const dev = devSwitchOn();
  return withFlowTitle(title, () => withSearchIndexer('EasyNews', async () => {
    const results = await askEasynews(ctx);
    if (dev) logSearchLines(searchLog(ctx), [{ source: 'EasyNews', ids: [] }], markSources(results, title), droppedBy(), 'EasyNews');
    return results;
  }), dev);
}

async function askEasynews(ctx: SearchContext): Promise<any[]> {
  if (!config.easynewsEnabled || !config.easynewsUsername || !config.easynewsPassword) {
    return [];
  }

  const { type, title, year, country, season, episode, episodesInSeason, priorSeasonsEpisodeCount, absoluteEpisodeNumber, tvdbPriorSeasonsCount, additionalTitles, titleYear, searchAliases, episodeAired } = ctx;
  const easynewsStartTime = Date.now();
  const easynewsTimeoutEnabled = config.searchTimeoutOverride !== undefined ? true : config.easynewsTimeoutEnabled;
  const easynewsTimeoutSeconds = config.searchTimeoutOverride ?? config.easynewsTimeout;
  const searcher = new EasynewsSearcher(
    config.easynewsUsername,
    config.easynewsPassword,
    config.easynewsPagination ? config.easynewsMaxPages : 1,
    easynewsTimeoutEnabled, easynewsTimeoutSeconds,
  );

  try {
    const { result: results, lines } = await withBuffer(async (): Promise<any[]> => {
      let r: any[] = [];
      if (type === 'movie') {
        r = await searcher.searchMovie(title, year, country, additionalTitles, titleYear, searchAliases);
      } else if (type === 'series' && season !== undefined && episode !== undefined) {
        r = await searcher.searchTVShow(title, season, episode, episodesInSeason, year, country, additionalTitles, titleYear, priorSeasonsEpisodeCount, absoluteEpisodeNumber, tvdbPriorSeasonsCount, searchAliases, episodeAired);
      }
      return r;
    });
    flushBuffer(lines, 'EasyNews');

    const responseTime = Date.now() - easynewsStartTime;
    trackQuery('EasyNews', true, responseTime, results.length);
    return results;
  } catch (error) {
    const responseTime = Date.now() - easynewsStartTime;
    trackQuery('EasyNews', false, responseTime, 0, error instanceof Error ? error.message : 'Unknown error');
    console.error('❌ EasyNews search failed:', error);
    return [];
  }
}
