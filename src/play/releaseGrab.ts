/**
 * A Release's NZB (#300; GLOSSARY: Release): which indexer it is fetched from, and the Walk's grab of it. One path for
 * Best's Walk (ultimateFallback.ts) and a clicked list entry's walk-on (streamHandler.ts), so both grab a Release alike.
 *
 * - The NZB is fetched from the indexer whose recent NZB downloads were fastest (KaijuFlow's stats), a tie going to
 *   the indexer listed first (`nzbOrder`).
 * - When that fetch fails, the Release's Source on the next indexer is fetched. An indexer that refuses (ADR 0004: a
 *   limit, an outage, refused credentials) is named in the answer, so the Walk skips it for the rest of the walk; a link
 *   the indexer says is gone, or its bad NZB, is that Source's alone (a `linkOnly` dead mark, sourceMemory.ts).
 * - The grab counts once against the Walk's 30, however many indexers it asks: the caller counts it.
 */

import { config as globalConfig } from '../config/index.js';
import { walkGrab } from '../backends/nzbGrab.js';
import { isSourceFailure } from '../backends/types.js';
import { recentNzbDownloadMs } from '../statsTracker.js';
import { ProxyCircuitAbortError } from '../proxy.js';
import { recall, remember, sourcesOf, type RememberedSource } from './sourceMemory.js';
import type { PlayContext } from './playContext.js';
import type { ReleaseSource } from './types.js';

/** What the order goes by: an indexer's recent NZB download time (undefined: none), and the indexers as listed. */
export interface NzbOrderBy {
  downloadMs: (indexer: string) => number | undefined;
  listed: readonly string[];
}

/**
 * A Release's Sources in the order their NZB is fetched: fastest recent NZB downloads first; an indexer with none comes
 * after the measured ones; a tie goes to the indexer listed first, then the Release's own order.
 */
export function nzbOrder<T extends { indexerName?: string }>(sources: readonly T[], by: NzbOrderBy): T[] {
  const place = (s: T) => {
    const i = by.listed.indexOf(s.indexerName ?? '');
    return i < 0 ? by.listed.length : i;
  };
  return sources
    .map((s, i) => ({ s, i, ms: by.downloadMs(s.indexerName ?? ''), place: place(s) }))
    .sort((a, b) => Number(a.ms === undefined) - Number(b.ms === undefined)
      || (a.ms ?? 0) - (b.ms ?? 0) || a.place - b.place || a.i - b.i)
    .map(x => x.s);
}

/** KaijuFlow's own order: its stats and its indexer list. */
const kaijuflowOrder = (): NzbOrderBy => ({
  downloadMs: recentNzbDownloadMs,
  listed: (globalConfig.indexers ?? []).map(i => i.name),
});

/** The Source whose NZB a grab fetched, and the indexers that refused it on the way. */
export interface ReleaseGrabbed {
  source: ReleaseSource;
  refused: string[];
}

/** The Release a grab takes: a Walk's candidate, or the Source a clicked list entry plays. */
export type GrabbedRelease = RememberedSource & { indexerName?: string; searchExitIp?: string };

/**
 * The Walk's grab of a Release: its Sources' NZBs in `nzbOrder`, until one is fetched (kept for the check and the
 * prepare, walkGrab). Passes by a Source remembered dead and one whose indexer the Walk `skips`. Throws when none was
 * fetched: a Source failure (isSourceFailure, a bad Release) only when every Source tried was gone or bad and none was
 * passed by; otherwise a plain error. Either way the error's `refused` names the indexers that refused.
 */
export async function grabRelease(
  release: GrabbedRelease,
  opts: { play?: PlayContext; skips?: (indexer: string) => boolean; logPrefix?: string; stop?: AbortSignal } = {},
): Promise<ReleaseGrabbed> {
  const { play, skips, logPrefix = '', stop } = opts;
  const all = sourcesOf(release).map(s => ({ ...s, indexerName: s.indexerName ?? '', searchExitIp: s.searchExitIp ?? release.searchExitIp }));
  const order = nzbOrder(all, kaijuflowOrder());
  const refused: string[] = [];
  let passedBy = false;
  let last: unknown;
  for (const [n, s] of order.entries()) {
    if (all.length > 1 && recall(s, play).dead) { passedBy = true; continue; }
    if (skips?.(s.indexerName)) { passedBy = true; continue; }
    try {
      await walkGrab(s.nzbUrl, s.title, logPrefix, s.indexerName, s.searchExitIp, stop);
      return { source: s, refused };
    } catch (err) {
      // A stop, or the proxy's exit IP changed (every other Source would fail alike): no other Source is tried.
      if (stop?.aborted || err instanceof ProxyCircuitAbortError) throw Object.assign(err as Error, { refused });
      last = err;
      if (!isSourceFailure(err)) refused.push(s.indexerName);
      // Gone on this indexer, or its NZB bad: that Source's own mark, so the next play starts at another indexer.
      else if (all.length > 1) remember({ source: s, play, dead: err as Error, everyEpisode: true, linkOnly: true });
      if (n < order.length - 1) console.log(`${logPrefix}↪️ ${s.indexerName}'s NZB not fetched (${(err as Error).message}): trying the Release's other Sources`);
    }
  }
  const bad = last !== undefined && refused.length === 0 && !passedBy;
  // A gone Source beside a refusal is no bad Release: a plain error. A refusal is thrown as it came.
  const error = bad || (last !== undefined && !isSourceFailure(last)) ? last as Error
    : last ? new Error((last as Error).message)
    : new Error('every Source of the Release was passed by: its indexers refused earlier in this Walk');
  throw Object.assign(error, { refused });
}

/** The indexers a grab's error says refused (grabRelease). */
export function refusedBy(err: unknown): string[] {
  return (err as { refused?: string[] } | null)?.refused ?? [];
}
