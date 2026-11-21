// One-time move of an old config onto the Head start (#206), kept apart from migrations.ts
// so it can be tested without loading a config from disk.

/**
 * Before #206 the default `whenToResolve` was 'on-tile-selection' (Best begins on a press), and a
 * config that saved it would get no Head start. Once, it moves to 'on-results', the default; the
 * marker `headStartMigrated` keeps a later choice of 'on-tile-selection'. True when anything changed.
 */
export function migrateToHeadStart(c: Record<string, unknown>): boolean {
  if (c.headStartMigrated === true) return false;
  const ur = c.ultimateFallback as Record<string, unknown> | undefined;
  if (ur && typeof ur === 'object' && ur.whenToResolve === 'on-tile-selection') ur.whenToResolve = 'on-results';
  c.headStartMigrated = true;
  return true;
}
