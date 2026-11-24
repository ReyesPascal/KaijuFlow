/**
 * Result Deduplication
 *
 * Content-only passes that run before any user-preference filtering:
 *  - stripBareArchiveParts: drops non-release entries (par2/rar/nzb/etc.)
 *  - deduplicateByUrl: removes entries that share a download URL
 *
 * The same upload on several indexers is one Release, merged by Kaiju Search (`mergeReleases`, #299), which replaced
 * the priority dedup.
 */

import { config } from '../config/index.js';
import { isBareArchivePart, matchedJunkKind, safeLogTitle, JUNK_EMOJI } from './junkFilter.js';

/**
 * Baseline junk filter — strips bare archive parts and NZB containers that
 * leak in from older indexer databases. These are never valid releases.
 * Runs before anything else so they don't reach parsing, dedup, or rules.
 */
export function stripBareArchiveParts(allResults: any[]): any[] {
  if (config.searchConfig?.junkFilter === false || allResults.length === 0) return allResults;
  const dropped: { title: string; kind: string }[] = [];
  const kept = allResults.filter(r => {
    if (isBareArchivePart(r.title)) {
      dropped.push({ title: r.title, kind: matchedJunkKind(r.title) || 'junk' });
      return false;
    }
    return true;
  });
  if (dropped.length > 0) {
    console.log(`${JUNK_EMOJI} Junk filter: removed ${dropped.length} non-release(s) (${kept.length} remaining)`);
    for (const d of dropped) console.log(`   ✂️  "${safeLogTitle(d.title)}" (${d.kind})`);
  }
  return kept;
}

/**
 * Within-indexer content dedup — drops repeats of the same release returned
 * by the same indexer. Catches multi-method indexers (e.g. Prowlarr with
 * imdb+tvdb+tvmaze enabled) whose proxy generates a unique URL per call,
 * defeating URL-dedup even when the underlying release is identical.
 *
 * Key: indexerName|title|size|pubDate-as-epoch. pubDate distinguishes
 * re-uploads of the same release name + size from the same physical post
 * returned across different ID-method calls. pubDate is parsed to epoch
 * because Prowlarr's aggregate endpoint emits ISO-8601 while its newznab
 * proxy emits RFC-822 for the same field.
 */
export function deduplicateByIndexerContent(allResults: any[]): any[] {
  if (allResults.length === 0) return allResults;
  const seen = new Map<string, string>();
  const duplicates: { title: string; indexer: string }[] = [];
  const deduped = allResults.filter(r => {
    const key = indexerContentKey(r);
    if (seen.has(key)) {
      duplicates.push({ title: r.title, indexer: r.indexerName || 'Unknown' });
      return false;
    }
    seen.set(key, r.indexerName || 'Unknown');
    return true;
  });
  if (duplicates.length > 0) {
    const byIndexer = new Map<string, number>();
    for (const d of duplicates) byIndexer.set(d.indexer, (byIndexer.get(d.indexer) || 0) + 1);
    const breakdown = [...byIndexer.entries()].map(([name, n]) => `${name}: ${n}`).join(', ');
    console.log(`🔁 Indexer-content dedup: removed ${duplicates.length} duplicate(s) [${breakdown}] (${deduped.length} remaining)`);
    for (const d of duplicates) console.log(`   ✂️  "${d.title}" [${d.indexer}]`);
  }
  return deduped;
}

/** One release of one indexer, whatever link or date format it came with (deduplicateByIndexerContent's key; Kaiju
 *  Search's merge uses it too, #285). */
export function indexerContentKey(r: { indexerName?: string; title?: string; size?: number; pubDate?: string }): string {
  const pubMs = r.pubDate ? Date.parse(r.pubDate) : 0;
  const pubKey = isNaN(pubMs) ? (r.pubDate || '') : pubMs;
  return `${r.indexerName || ''}|${(r.title || '').trim()}|${r.size || 0}|${pubKey}`;
}

/**
 * URL deduplication — removes results with identical download URLs.
 * First occurrence wins; subsequent duplicates are dropped.
 */
export function deduplicateByUrl(allResults: any[]): any[] {
  if (config.searchConfig?.urlDedup === false || allResults.length === 0) return allResults;

  const seen = new Map<string, string>(); // link → indexerName of first occurrence
  const duplicates: { title: string; indexer: string }[] = [];
  const deduped = allResults.filter(r => {
    if (!r.link) return true;
    const existing = seen.get(r.link);
    if (existing) {
      duplicates.push({ title: r.title, indexer: existing });
      return false;
    }
    seen.set(r.link, r.indexerName || 'Unknown');
    return true;
  });

  if (duplicates.length > 0) {
    console.log(`🔗 URL dedup: removed ${duplicates.length} duplicate(s) (${deduped.length} remaining)`);
    for (const d of duplicates) console.log(`   ✂️  "${d.title}" (duplicate of ${d.indexer} result)`);
  }

  return deduped;
}
