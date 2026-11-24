/**
 * Search Flow (GLOSSARY: Search Flow; spec #279, #282): what a title's list keeps and how sure each Source is.
 *
 * - The loose rule, the inherited `isTextSearchMatch`, decides what stays: the searchers drop what neither it nor the
 *   strict rule fits (`nameKeeps`, #285), so a release the strict rule passes is never dropped.
 * - The strict rule, ported from the quick check's right-title rule (`tools/brain/quickcheck.py`, `right_title`,
 *   #278), only sorts, never removes: a Source that passes it is **sure**, one only the loose rule keeps is **maybe**.
 *   Results found by ID (which no name rule drops) are marked the same way.
 * - Best's Walk tries sure Sources before maybe ones (`sureFirst`, run by `ultimateFallbackFromCandidates`).
 *
 * The two copies of the strict rule (this one and the quick check's) are tested on one shared table of real release
 * names, `tests/fixtures/release-names/table.tsv`, so they cannot drift: change both or neither.
 */

import { AsyncLocalStorage } from 'node:async_hooks';
import { isTextSearchMatch } from './titleMatching.js';

/** A title as Search Flow judges a release against it. */
export interface FlowTitle {
  type: 'movie' | 'series';
  /** The title's name (a film's, or an episode's show). */
  name: string;
  /** Its other names (alternate, foreign, anime), tried when the name does not fit. */
  otherNames?: string[];
  /** A film's year (YYYY). For a show, its first year, which only the loose rule reads. */
  year?: string;
  season?: number;
  episode?: number;
  /** An episode's air date (YYYY-MM-DD): a daily show is known by it. */
  aired?: string;
  /** The loose rule's extras: the title's country (a country tag in a release) and a year in its TVDB name. */
  country?: string;
  titleYear?: string;
  /** The title's runtime in seconds (TMDB for a film, TVDB for an episode): a maybe whose own runtime fits it is sure
   *  (extra proof, #286). */
  runtime?: number;
  /** Other TMDB/TVDB names of the title the search does not ask by (TVDB's aliases, TMDB's alternative titles): a
   *  maybe that fits one is sure (extra proof, #286). */
  knownNames?: string[];
}

/** How sure a Source in the list is, and why. */
export interface FlowMark {
  flow: 'sure' | 'maybe';
  why: string;
}

/** Search Flow's answer for one release: kept and sure, kept and maybe, or dropped, with the reason. */
export type FlowVerdict = FlowMark | { flow: 'dropped'; why: string };

// --------------------------------------------------------------------------- the strict rule (quickcheck.right_title)

/** A name as lower-case words, accents, apostrophes and punctuation gone, `&` read as `and`. */
function words(text: string): string[] {
  const ascii = String(text ?? '').normalize('NFKD').replace(/[^\x00-\x7f]/g, '').toLowerCase();
  return ascii.replace(/['`]/g, '').replace(/&/g, ' and ').match(/[a-z0-9]+/g) ?? [];
}

/** Whether the words `needle` appear in `hay` one after another. */
function holds(hay: string[], needle: string[]): boolean {
  const n = needle.length;
  if (n === 0) return false;
  for (let i = 0; i + n <= hay.length; i++) if (needle.every((w, k) => hay[i + k] === w)) return true;
  return false;
}

/** Python's re.fullmatch: the whole of `s` matched (each pattern below is anchored). */
const full = (re: RegExp, s: string | undefined): RegExpExecArray | null => (s === undefined ? null : re.exec(s));
const EPISODES = /^s(\d{1,3})((?:e\d{1,4})+)$/; // S01E02, S01E01E02
const SEASON_THEN = /^s(\d{1,3})()$/; // S01 of S01.E02
const EPISODE = /^e\d{1,4}$/;
const CROSS = /^(\d{1,2})x(\d{1,3})$/; // 1x02
const SEASON = /^s(\d{1,3})$/;
const YEAR = /^(19|20)\d\d$/;
const MARKER = /^(?:s\d{1,3}(e\d{1,4})*|\d{1,2}x\d{1,3}|season)$/;
const TVDB_NUMBER = /^\d{5,}$/;
const VIDEO_TAG = /^(?:\d{3,4}p|4k)$/; // a resolution between a film's name and its year
const isDigits = (s: string | undefined) => s !== undefined && /^\d+$/.test(s);

/** The episodes ([season, episode]) and seasons a release name names: S01E02, S01E01E02, S01E01-E03, S01.E02 and
 *  1x02; a season pack's S01, S01-S03 or "Season 1". */
function markers(tokens: string[]): { episodes: [number, number][]; seasons: Set<number> } {
  const episodes = new Map<string, [number, number]>();
  const seasons = new Set<number>();
  const add = (s: number, e: number) => episodes.set(`${s}:${e}`, [s, e]);
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    const m = full(EPISODES, t) ?? (full(EPISODE, tokens[i + 1]) ? full(SEASON_THEN, t) : null);
    if (m) { // S01E02, S01E01E02, or S01.E02 (the season and the episode as two words)
      let nums = [...m[2].matchAll(/e(\d+)/g)].map(x => Number(x[1]));
      let j = i + 1;
      if (nums.length === 0) { nums = [Number(tokens[i + 1].slice(1))]; j = i + 2; } // S01.E02: the episode is the next word
      while (j < tokens.length && full(EPISODE, tokens[j])) { nums.push(Number(tokens[j].slice(1))); j++; } // S01E01-E03
      for (let n = Math.min(...nums); n <= Math.max(...nums); n++) add(Number(m[1]), n);
      continue;
    }
    const x = full(CROSS, t);
    if (x) { add(Number(x[1]), Number(x[2])); continue; }
    const s = full(SEASON, t);
    if (s) {
      const end = full(SEASON, tokens[i + 1]); // S01-S03
      for (let n = Number(s[1]); n <= (end ? Number(end[1]) : Number(s[1])); n++) seasons.add(n);
    } else if (t === 'season' && isDigits(tokens[i + 1])) {
      seasons.add(Number(tokens[i + 1]));
    }
  }
  return { episodes: [...episodes.values()], seasons };
}

// The words a release may put between an episode's show name and its marker, and between a film's name and its year:
// quickcheck.py's SHOW_TAGS and FILM_TAGS (each seen there in a real release name; see the reasons there).
const SHOW_TAGS = new Set(['us', 'uk', 'au', 'tv', 'complete']);
const FILM_TAGS = new Set(['imax', '3d', '2d', 'hsbs', '3dbd', 'uhd', 'multi', 'german', 'en', 'nl', 'eng', 'ukr', 'subs', 'anime',
  'se', 'ue', 'special', 'extended', 'collector', 'collectors', 's', 'edition', 'theatrical', 'cut', 'remastered']);
const UMLAUTS: Record<string, string> = { 'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss' };
const umlauts = (s: string) => s.replace(/[äöüÄÖÜß]/g, c => UMLAUTS[c]);

/** The positions in the release words just after each place the name's words stand, one after another. */
function after(rel: string[], name: string[]): number[] {
  const n = name.length;
  const out: number[] = [];
  if (n === 0) return out;
  for (let i = 0; i + n <= rel.length; i++) if (name.every((w, k) => rel[i + k] === w)) out.push(i + n);
  return out;
}

const yearOf = (word: string | undefined): number | undefined => (full(YEAR, word) ? Number(word) : undefined);

/** The year that dates a film whose name ends before word j, past any FILM_TAGS and resolutions. */
function filmYear(rel: string[], j: number): number | undefined {
  for (const w of rel.slice(j)) {
    const y = yearOf(w);
    if (y) return y;
    if (!(FILM_TAGS.has(w) || full(VIDEO_TAG, w))) return undefined;
  }
  return undefined;
}

/** Whether an episode, season or date marker starts at word j, past any SHOW_TAGS, years and TVDB numbers. */
function episodeStart(rel: string[], j: number): boolean {
  for (let k = j; k < rel.length; k++) {
    const w = rel[k];
    if (full(MARKER, w) || (yearOf(w) && k + 2 < rel.length && isDigits(rel[k + 1]) && isDigits(rel[k + 2]))) {
      return true;
    }
    if (!(yearOf(w) || SHOW_TAGS.has(w) || full(TVDB_NUMBER, w))) return false;
  }
  return false;
}

const two = (n: number) => String(n).padStart(2, '0');

/**
 * The strict rule: whether the release is the title, with why not. A film's name is followed by a year within one of
 * its year, past only edition, language and video tags; an episode's show name by its marker (its episode, its season
 * when the release is a season pack, or its air date), past only show tags, years and TVDB numbers. The title's other
 * names are tried when its name does not fit. Answers word for word as quickcheck.right_title does (`ok` and `why`);
 * `fits` says what fits when it passes; `against`, that the name says another year, season or episode (no extra proof
 * makes it sure, #286).
 */
export function strictMatch(release: string, title: FlowTitle): { ok: boolean; why: string; fits?: string; against?: true } {
  const rel = words(release);
  const { name } = title;
  let tried = [name, ...(title.otherNames ?? []).filter(Boolean)];
  tried = [...tried, ...tried.filter(n => umlauts(n) !== n).map(umlauts)]; // Einzelgänger as released: Einzelgaenger
  const spots = tried.flatMap(n => after(rel, words(n)));
  if (spots.length === 0) return { ok: false, why: `the name "${name}" is not in it` };
  if (title.type === 'movie') {
    const year = /^\d{4}/.test(title.year ?? '') ? Number(title.year!.slice(0, 4)) : undefined;
    const years = spots.map(j => filmYear(rel, j)).filter((y): y is number => y !== undefined);
    if (years.length === 0) return { ok: false, why: `the name "${name}" is not followed by a year${year ? ` (${year} wanted)` : ''}` };
    if (year && !years.some(y => Math.abs(y - year) <= 1)) return { ok: false, why: `its year is ${years[0]}, not ${year}`, against: true };
    return { ok: true, why: '', fits: 'the name and year fit' };
  }
  const { season, episode, aired } = title;
  if (season === undefined || episode === undefined) return { ok: false, why: `the label "${name}" names no episode` };
  if (!spots.some(j => episodeStart(rel, j))) return { ok: false, why: `the name "${name}" is not followed by a season or episode` };
  if (aired && /^\d{4}-\d\d-\d\d$/.test(aired) && holds(rel, [aired.slice(0, 4), aired.slice(5, 7), aired.slice(8, 10)])) return { ok: true, why: '', fits: 'the name and air date fit' };
  const { episodes, seasons } = markers(rel);
  if (episodes.some(([s, e]) => s === season && e === episode)) return { ok: true, why: '', fits: 'the name and episode fit' };
  if (episodes.length > 0) {
    const [s, e] = [...episodes].sort((a, b) => a[0] - b[0] || a[1] - b[1])[0];
    return { ok: false, why: `it is S${two(s)}E${two(e)}, not S${two(season)}E${two(episode)}`, against: true };
  }
  if (seasons.has(season)) return { ok: true, why: '', fits: 'the name and season fit (a season pack)' };
  if (seasons.size > 0) return { ok: false, why: `it is a pack of season ${Math.min(...seasons)}, not season ${season}`, against: true };
  return { ok: false, why: `it names no season or episode (S${two(season)}E${two(episode)} wanted)` };
}

// --------------------------------------------------------------------------- the flow

/** The loose rule: the inherited text-search match, over the title's name and its other names. */
export function looseMatch(release: string, title: FlowTitle): boolean {
  return isTextSearchMatch(title.name, release, title.year, title.country, title.otherNames, title.titleYear);
}

/**
 * Search Flow's answer for one release of a title: **sure** when the strict rule passes it (kept even where the loose
 * rule would drop it: a sure Source is never dropped), **maybe** when only the loose rule keeps it, **dropped** when
 * neither fits. The why of a maybe or a drop is the strict rule's.
 */
export function searchFlow(release: string, title: FlowTitle): FlowVerdict {
  const strict = strictMatch(release, title);
  if (strict.ok) return { flow: 'sure', why: strict.fits! };
  return { flow: looseMatch(release, title) ? 'maybe' : 'dropped', why: strict.why };
}

/** A title's search as its name filters see it: the title, the indexer being asked (when one is), and with the dev
 *  switch on the releases each indexer's name filter dropped, with why (`dropped`, keyed by indexer, '' when the
 *  query went to several at once). */
interface Searching { title: FlowTitle; indexer?: string; dropped?: Map<string, Map<string, string>> }

const searching = new AsyncLocalStorage<Searching>();

/** Run a title's search (Kaiju Search, #285) with its title known to every name filter inside it (`nameKeeps`); with
 *  `record`, the releases they drop are kept for `droppedBy` (the dev switch's search lines). */
export function withFlowTitle<T>(title: FlowTitle, fn: () => T, record = false): T {
  return searching.run({ title, ...(record ? { dropped: new Map() } : {}) }, fn);
}

/** Run one indexer's queries inside a title's search, so what its name filter drops is put down to it. */
export function withSearchIndexer<T>(indexer: string, fn: () => T): T {
  const s = searching.getStore();
  return s ? searching.run({ ...s, indexer }, fn) : fn();
}

/** The releases each indexer's name filter dropped in this search, with why ('' for a query to several at once);
 *  empty unless the search records them. */
export function droppedBy(): Map<string, Map<string, string>> {
  return searching.getStore()?.dropped ?? new Map();
}

/**
 * The searchers' name filter: Search Flow's keep. The loose rule with the searcher's own name for the query (its
 * arguments are `isTextSearchMatch`'s), or the strict rule on the title being searched (`withFlowTitle`), so a
 * release the strict rule passes is kept even where the loose rule would drop it, and so is one that fits another
 * TMDB/TVDB name of the title (`knownNames`, extra proof, #286). Outside a search, the loose rule.
 */
export function nameKeeps(name: string, release: string, year?: string, country?: string, otherNames?: string[], titleYear?: string): boolean {
  if (isTextSearchMatch(name, release, year, country, otherNames, titleYear)) return true;
  const s = searching.getStore();
  if (s === undefined) return false;
  const strict = strictMatch(release, s.title);
  if (strict.ok || fitsKnownName(release, s.title)) return true;
  if (s.dropped) {
    const key = s.indexer ?? '';
    if (!s.dropped.has(key)) s.dropped.set(key, new Map());
    s.dropped.get(key)!.set(release, strict.why);
  }
  return false;
}

/** What the list path knows of a title (its SearchContext), as Search Flow judges releases against it. */
export function flowTitleOf(ctx: {
  type: string; title: string; year?: string; season?: number; episode?: number; country?: string; titleYear?: string;
  additionalTitles?: string[]; searchAliases?: string[]; episodeAired?: string; knownNames?: string[]; runtime?: number;
}): FlowTitle {
  const otherNames = [...new Set([...(ctx.additionalTitles ?? []), ...(ctx.searchAliases ?? [])].filter(n => n && n !== ctx.title))];
  return {
    type: ctx.type === 'series' ? 'series' : 'movie',
    name: ctx.title, otherNames, year: ctx.year, season: ctx.season, episode: ctx.episode, aired: ctx.episodeAired,
    country: ctx.country, titleYear: ctx.titleYear,
    ...(ctx.knownNames?.length ? { knownNames: ctx.knownNames.filter(n => n && n !== ctx.title && !otherNames.includes(n)) } : {}),
    ...(ctx.runtime ? { runtime: ctx.runtime } : {}),
  };
}

/** The kinds of extra proof that make a maybe sure (#286): the ID search returned it too, the video file inside its NZB
 *  fits, its runtime or its size fits, or it fits another TMDB/TVDB name of the title. */
export type FlowProof = 'id' | 'nzb video' | 'runtime' | 'size' | 'other name';

/** A Source of a title's list as Search Flow marks it: its release name, and what Kaiju Search knows of it: the ways
 *  that found it, its size (bytes) and its own runtime (seconds, the indexer's). */
export interface FlowSource { title: string; foundBy?: ('id' | 'name')[]; size?: number; duration?: number }

/** A runtime fits the title's within a minute or 2 %, whichever is more (a release's own runtime is the cut's). */
const runtimeFits = (own: number, title: number) => Math.abs(own - title) <= Math.max(60, title * 0.02);
/** Two sizes are one upload's within 0.1 % (indexers round a size), of a Source big enough to be a film or episode. */
const MIN_PROOF_SIZE = 100 * 1024 ** 2;
const sameSize = (a: number, b: number) => a >= MIN_PROOF_SIZE && b >= MIN_PROOF_SIZE && Math.abs(a - b) <= Math.max(a, b) * 0.001;
const minutes = (s: number) => Math.round(s / 60);

/** A marked Source: sure or maybe with why, and the extra proof that made it sure, when one did. */
export type Marked<T> = T & { flow: FlowMark['flow']; flowWhy: string; proof?: FlowProof };

/** The other TMDB/TVDB name of the title (`knownNames`) the release fits by the strict rule, if one. */
function fitsKnownName(release: string, title: FlowTitle): string | undefined {
  return (title.knownNames ?? []).find(n => strictMatch(release, { ...title, name: n, otherNames: [] }).ok);
}

/**
 * The extra proof a maybe has in its list, with why; none when it has none. The ID search and the runtime back only a
 * name the loose rule keeps (an indexer files a release under a wrong ID, many films run as long); another TMDB/TVDB
 * name and the size of a sure Source (`sure`, the list's) are proof on their own. A name that says another year, season
 * or episode (`against`) has none but another name.
 */
function listProof(source: FlowSource, title: FlowTitle, loose: boolean, against: boolean, sure: FlowSource[]): { proof: FlowProof; why: string } | undefined {
  if (!against && loose && source.foundBy?.includes('id')) return { proof: 'id', why: 'the ID search returned it too' };
  if (!against && loose && source.duration && title.runtime && runtimeFits(source.duration, title.runtime)) {
    return { proof: 'runtime', why: `its runtime fits (${minutes(source.duration)} min, the title's ${minutes(title.runtime)} min)` };
  }
  const twin = against || !source.size ? undefined : sure.find(s => s.size && sameSize(s.size, source.size!));
  if (twin) return { proof: 'size', why: `it is the size of a sure Source, ${twin.title}` };
  const other = fitsKnownName(source.title, title);
  if (other) return { proof: 'other name', why: `it fits another name of the title, "${other}"` };
  return undefined;
}

/**
 * Mark every Source of a title's list sure or maybe, with why (`flow`, `flowWhy`). Every Source in it has stayed: the
 * searchers dropped what Search Flow drops (`nameKeeps`), and a result found by ID, which no name rule drops, is marked
 * too; one neither rule fits by its name is a maybe that says so. A maybe with extra proof (#286) is sure, with the
 * proof (`proof`) and why, and its name's why after it. New objects; the list's order is kept.
 */
export function markSources<T extends FlowSource>(sources: T[], title: FlowTitle): Marked<T>[] {
  const verdicts = sources.map(source => ({ source, v: searchFlow(source.title, title), against: strictMatch(source.title, title).against === true }));
  const sure = verdicts.filter(x => x.v.flow === 'sure').map(x => x.source);
  return verdicts.map(({ source, v, against }) => {
    if (v.flow === 'sure') return { ...source, flow: v.flow, flowWhy: v.why };
    const loose = v.flow === 'maybe';
    const why = loose ? v.why : `${v.why}; the loose rule does not fit it either`;
    const proved = listProof(source, title, loose, against, sure);
    return proved
      ? { ...source, flow: 'sure' as const, flowWhy: `${proved.why}; by its name alone: ${why}`, proof: proved.proof }
      : { ...source, flow: 'maybe' as const, flowWhy: why };
  });
}

/**
 * The Play-time check's extra proof (#286): a maybe whose NZB holds a video file (`videoName`, read when the check
 * fetches it) that fits the title by the strict rule is sure, with why. Undefined when it proves nothing: a sure Source,
 * no video file named (an archive), or a file that does not fit. A new object.
 */
export function videoProof<T extends { title: string; flow?: FlowMark['flow']; flowWhy?: string }>(
  source: T, videoName: string | undefined, title: FlowTitle,
): Marked<T> | undefined {
  if (source.flow !== 'maybe' || !videoName || !strictMatch(videoName, title).ok) return undefined;
  const why = `the video file inside its NZB fits, ${videoName}`;
  return { ...source, flow: 'sure', proof: 'nzb video', flowWhy: `${why}; by its name alone: ${source.flowWhy ?? ''}` };
}

/** Best's Walk order: the sure Sources first, then the maybe ones, each in list order. A Source with no mark (a list
 *  from before Search Flow) counts as sure, so an old list keeps its order. */
export function sureFirst<T extends { flow?: FlowMark['flow'] }>(sources: T[]): T[] {
  return [...sources.filter(s => s.flow !== 'maybe'), ...sources.filter(s => s.flow === 'maybe')];
}
