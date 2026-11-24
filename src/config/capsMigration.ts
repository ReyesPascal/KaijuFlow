/**
 * Caps marked as read (#285, review of #279): caps read since then carry `version` (CAPS_VERSION), and an empty list
 * in them is a kind the indexer said is not available (`available="no"`): it is asked by no ID for that kind. Caps saved
 * before hold no version, and the old parser stored caps it could not read (a Newznab <error> sent with HTTP 200, no
 * <searching> block, no supportedParams) as empty lists, so an empty list there means unknown: the indexer is asked by
 * IMDb, as it was. `asRead` reads either; `migrateLegacyCaps` rewrites a config's legacy caps once, at startup.
 */
import type { IndexerCaps } from '../types.js';

export const CAPS_VERSION = 2;

/** The caps as this version reads them: legacy caps (no version) lose their empty lists, which meant unknown. */
export function asRead(caps: IndexerCaps | undefined): IndexerCaps | undefined {
  if (!caps || caps.version !== undefined) return caps;
  const out: IndexerCaps = { version: CAPS_VERSION };
  if (caps.movieSearchParams?.length) out.movieSearchParams = caps.movieSearchParams;
  if (caps.tvSearchParams?.length) out.tvSearchParams = caps.tvSearchParams;
  return out;
}

/** Every Newznab indexer's `caps` and synced indexer's `capabilities` in a config read as this version reads them
 *  (asRead). Whether anything changed. */
export function migrateLegacyCaps(c: Record<string, unknown>): boolean {
  let changed = false;
  const fix = (rows: unknown, field: 'caps' | 'capabilities') => {
    if (!Array.isArray(rows)) return;
    for (const row of rows as Record<string, unknown>[]) {
      const caps = row?.[field] as IndexerCaps | undefined;
      if (caps && typeof caps === 'object' && caps.version === undefined) {
        row[field] = asRead(caps);
        changed = true;
      }
    }
  };
  fix(c.indexers, 'caps');
  fix(c.syncedIndexers, 'capabilities');
  return changed;
}
