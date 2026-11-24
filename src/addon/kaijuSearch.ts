/**
 * Kaiju Search (GLOSSARY: Kaiju Search; spec #279, #285): every indexer is asked by ID and by name at once, and the
 * answers are merged so each Source is listed once.
 *
 * - **By ID**: with every ID the indexer's caps list for the kind of title (a film: IMDb, TMDB, TVDB; a show: IMDb,
 *   TVDB, TVmaze), one query per ID. An indexer whose caps are unknown (never fetched) is asked by IMDb, the ID every
 *   Newznab indexer has answered by default.
 * - **By name**: the title's name and its other names (the searchers' name queries, packs and fallbacks).
 *
 * There is no setting: the per-indexer search methods were removed (an old config loses them,
 * `src/config/deletedSettingsMigration.ts`). No limit handling is added for asking twice (spec #279, Q29).
 */

import type { IndexerCaps } from '../types.js';

/** A way of asking an indexer: by one of its IDs, or by name (`text`, the searchers' own word for it). */
export type SearchWay = 'imdb' | 'tmdb' | 'tvdb' | 'tvmaze' | 'text';
/** Which way found a Source: by an ID, by name, or both. */
export type FoundBy = 'id' | 'name';

const ID_PARAMS: Record<'movie' | 'tv', [string, SearchWay][]> = {
  movie: [['imdbid', 'imdb'], ['tmdbid', 'tmdb'], ['tvdbid', 'tvdb']],
  tv: [['imdbid', 'imdb'], ['tvdbid', 'tvdb'], ['tvmazeid', 'tvmaze']],
};

/** The ID ways an indexer is asked for a kind of title, from its caps (IMDb when its caps are unknown). */
export function idWaysOf(kind: 'movie' | 'tv', caps: IndexerCaps | undefined): SearchWay[] {
  const params = (kind === 'movie' ? caps?.movieSearchParams : caps?.tvSearchParams)?.map(p => p.toLowerCase());
  if (!params || params.length === 0) return ['imdb'];
  return ID_PARAMS[kind].filter(([param]) => params.includes(param)).map(([, way]) => way);
}

/** Every way an indexer is asked: its ID ways, then by name. */
export function waysOf(kind: 'movie' | 'tv', caps: IndexerCaps | undefined): SearchWay[] {
  return [...idWaysOf(kind, caps), 'text'];
}

/** Mark results as found one way (the ID and name searches tag what they return). */
export function foundBy<T extends object>(results: T[], way: FoundBy): (T & { foundBy: FoundBy[] })[] {
  return results.map(r => ({ ...r, foundBy: [way] }));
}

/**
 * Merge the answers of every way: a Source (one indexer's release, known by its NZB link) found more than once is
 * listed once, at its first place, with every way that found it (`foundBy`, `id` before `name`). A result no way
 * tagged was found by name (a pack or fallback query).
 */
export function mergeFound<T extends { link?: string; title?: string; size?: number; indexerName?: string; foundBy?: FoundBy[] }>(
  results: T[],
): (T & { foundBy: FoundBy[] })[] {
  const byKey = new Map<string, T & { foundBy: FoundBy[] }>();
  for (const r of results) {
    const key = `${r.indexerName ?? ''}\u0000${r.link || `${r.title}\u0000${r.size}`}`;
    const ways = r.foundBy ?? ['name'];
    const seen = byKey.get(key);
    if (!seen) { byKey.set(key, { ...r, foundBy: [...ways] }); continue; }
    for (const w of ways) if (!seen.foundBy.includes(w)) seen.foundBy.push(w);
    seen.foundBy.sort((a, b) => (a === b ? 0 : a === 'id' ? -1 : 1));
  }
  return [...byKey.values()];
}
