/**
 * Kaiju Search (GLOSSARY: Kaiju Search; spec #279, #285): every indexer is asked by ID and by name at once, and the
 * answers are merged so each Source is listed once.
 *
 * - **By ID**: with every ID the indexer's caps list for the kind of title (a film: IMDb, TMDB, TVDB; a show: IMDb,
 *   TVDB, TVmaze), one query per ID. An indexer whose caps are unknown (never fetched) is asked by IMDb, the ID every
 *   Newznab indexer has answered by default; one whose caps list no ID for the kind is asked by name only (caps marked
 *   read, `src/config/capsMigration.ts`: an empty list saved before then meant unknown, so it is still asked by IMDb).
 * - **By name**: the title's name and its other names (the searchers' name queries, packs and fallbacks).
 *
 * There is no setting: the per-indexer search methods were removed (an old config loses them,
 * `src/config/deletedSettingsMigration.ts`). No limit handling is added for asking twice (spec #279, Q29).
 */

import type { IndexerCaps } from '../types.js';
import { indexerContentKey } from './dedup.js';
import { asRead } from '../config/capsMigration.js';

/** A way of asking an indexer: by one of its IDs, or by name (`text`, the searchers' own word for it). */
export type SearchWay = 'imdb' | 'tmdb' | 'tvdb' | 'tvmaze' | 'text';
/** Which way found a Source: by an ID, by name, or both. */
export type FoundBy = 'id' | 'name';

const ID_PARAMS: Record<'movie' | 'tv', [string, SearchWay][]> = {
  movie: [['imdbid', 'imdb'], ['tmdbid', 'tmdb'], ['tvdbid', 'tvdb']],
  tv: [['imdbid', 'imdb'], ['tvdbid', 'tvdb'], ['tvmazeid', 'tvmaze']],
};

/** The ID ways an indexer is asked for a kind of title, from its caps: IMDb when its caps are unknown (never fetched);
 *  none when they were fetched and list no ID for the kind (`available="no"`): it said it cannot search by ID. */
export function idWaysOf(kind: 'movie' | 'tv', saved: IndexerCaps | undefined): SearchWay[] {
  const caps = asRead(saved); // caps saved before they were marked read: an empty list meant unknown
  const params = (kind === 'movie' ? caps?.movieSearchParams : caps?.tvSearchParams)?.map(p => p.toLowerCase());
  if (!params) return ['imdb'];
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
 * Merge the answers of every way: a Source (one indexer's release) found more than once is listed once, at its first
 * place, with every way that found it (`foundBy`, `id` before `name`). It is known by its NZB link or by its name, size
 * and post date (`indexerContentKey`): Prowlarr's ID and name searches hand out different links for one release. A
 * result no way tagged was found by name (a pack or fallback query).
 */
export function mergeFound<T extends { link?: string; title?: string; size?: number; pubDate?: string; indexerName?: string; foundBy?: FoundBy[] }>(
  results: T[],
): (T & { foundBy: FoundBy[] })[] {
  const out: (T & { foundBy: FoundBy[] })[] = [];
  const byKey = new Map<string, T & { foundBy: FoundBy[] }>();
  for (const r of results) {
    const keys = [indexerContentKey(r), ...(r.link ? [`${r.indexerName ?? ''}\u0000${r.link}`] : [])];
    const ways = r.foundBy ?? ['name'];
    const seen = keys.map(k => byKey.get(k)).find(Boolean);
    if (!seen) {
      const entry = { ...r, foundBy: [...ways] };
      out.push(entry);
      for (const k of keys) byKey.set(k, entry);
      continue;
    }
    for (const k of keys) if (!byKey.has(k)) byKey.set(k, seen);
    for (const w of ways) if (!seen.foundBy.includes(w)) seen.foundBy.push(w);
    seen.foundBy.sort((a, b) => (a === b ? 0 : a === 'id' ? -1 : 1));
  }
  return out;
}

// --------------------------------------------------------------------------- the dev switch's search lines (#285)

/** One indexer as a search asked it: its name, and the IDs it was asked by (none when it was asked by name only). */
export interface AskedIndexer { source: string; ids: SearchWay[] }

type Marked = { title: string; flow: 'sure' | 'maybe'; flowWhy: string; proof?: string; indexerName?: string; foundBy?: FoundBy[] };

/** A result as its search line names it: a sure one extra proof made sure says which proof (#286). */
const entry = (r: Marked) => ({ release: r.title, flow: r.flow, ...(r.proof ? { proof: r.proof } : {}), why: r.flowWhy });

/**
 * Write a `search` step line per indexer and way of asking (dev switch only; the caller checks it): the way (`id`,
 * `name`), what it was asked (`asked`: the IDs, or `name`), how many results came back that way (`count`, the kept
 * ones and those Search Flow dropped), how many stayed (`kept`, `sure`, `maybe`) and each result with its Search Flow
 * mark and why (`results`, the dropped ones last). `marked` is the search's merged results marked by Search Flow;
 * `dropped` what each indexer's name filter dropped (`droppedBy`; key '' is a query to several indexers at once, put
 * on a name line of `several`, the index manager). Names and numbers only: no URL or key.
 */
export function logSearchLines(
  log: (fields: Record<string, unknown>) => void,
  asked: AskedIndexer[], marked: Marked[], dropped: Map<string, Map<string, string>>, several: string,
): void {
  for (const { source, ids } of asked) {
    const mine = marked.filter(r => r.indexerName === source);
    if (ids.length > 0) line(log, source, 'id', ids, mine.filter(r => r.foundBy?.includes('id')), new Map());
    line(log, source, 'name', ['name'], mine.filter(r => r.foundBy?.includes('name') ?? true), dropped.get(source) ?? new Map());
  }
  const shared = dropped.get('');
  if (shared && shared.size > 0) line(log, several, 'name', ['name'], [], shared);
}

function line(log: (fields: Record<string, unknown>) => void, source: string, way: FoundBy, asked: string[], kept: Marked[], dropped: Map<string, string>): void {
  const keptNames = new Set(kept.map(r => r.title));
  const gone = [...dropped].filter(([release]) => !keptNames.has(release)).map(([release, why]) => ({ release, flow: 'dropped', why }));
  log({
    source, way, asked, count: kept.length + gone.length, kept: kept.length,
    sure: kept.filter(r => r.flow === 'sure').length, maybe: kept.filter(r => r.flow === 'maybe').length,
    results: [...kept.map(entry), ...gone],
  });
}

/** Write a `search` line when the strict rule alone would have left nothing: the search kept Sources and the strict
 *  rule passes none of them (a Source extra proof made sure is not the strict rule's, #286; dev switch only, the
 *  caller checks it). `sure` counts the Sources extra proof made sure. */
export function logStrictAlone(log: (fields: Record<string, unknown>) => void, marked: Marked[]): void {
  if (marked.length === 0 || marked.some(r => r.flow === 'sure' && !r.proof)) return;
  const sure = marked.filter(r => r.flow === 'sure').length;
  log({ strict_alone: 'nothing', kept: marked.length, sure, maybe: marked.length - sure });
}
