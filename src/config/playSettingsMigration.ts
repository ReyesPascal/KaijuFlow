// One-time rename of the play settings (#200), kept apart from migrations.ts so it
// can be tested without loading a config from disk.

/**
 * Move the old nzbdav* play settings to their play* names and drop streamingMode
 * (#200). A value already under the new name wins. The old nzbdavProxyEnabled switch
 * becomes the delivery method it stood for when no method was saved. True when
 * anything changed.
 */
export function migratePlaySettings(c: Record<string, unknown>): boolean {
  let changed = false;
  const RENAMES: [string, string][] = [
    ['nzbdavStreamingMethod', 'playDeliveryMethod'],
    ['nzbdavStreamBufferMB', 'playStreamBufferMB'],
    ['nzbdavPipeBufferMB', 'playPipeBufferMB'],
    ['nzbdavCacheTimeouts', 'playCacheTimeouts'],
  ];
  for (const [from, to] of RENAMES) {
    if (!(from in c)) continue;
    // An empty old value (null, '') counted as unset before: it does not move.
    if (c[to] == null && c[from] != null && c[from] !== '') c[to] = c[from];
    delete c[from];
    changed = true;
  }
  if ('nzbdavProxyEnabled' in c) {
    if (c.playDeliveryMethod == null && typeof c.nzbdavProxyEnabled === 'boolean') {
      c.playDeliveryMethod = c.nzbdavProxyEnabled ? 'proxy' : 'direct';
    }
    delete c.nzbdavProxyEnabled;
    changed = true;
  }
  if ('streamingMode' in c) {
    delete c.streamingMode;
    changed = true;
  }
  return changed;
}
