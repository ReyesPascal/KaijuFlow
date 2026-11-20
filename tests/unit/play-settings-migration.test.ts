// #200: old configs keep their play settings under the new play* names, and lose streamingMode.
// The whole path (config on disk → startup migration → /api/config) is INT-BACKEND-SETTING-001.
import test from 'node:test';
import assert from 'node:assert/strict';
import { migratePlaySettings } from '../../src/config/playSettingsMigration.ts';

test('the nzbdav* play settings move to play* with their values; streamingMode is dropped', () => {
  const c: Record<string, unknown> = { cacheTTL: 9000, streamingMode: 'nzbdav', nzbdavStreamingMethod: 'pipe',
    nzbdavStreamBufferMB: 64, nzbdavPipeBufferMB: 4, nzbdavCacheTimeouts: false };
  assert.equal(migratePlaySettings(c), true);
  assert.deepEqual(c, { cacheTTL: 9000, playDeliveryMethod: 'pipe', playStreamBufferMB: 64, playPipeBufferMB: 4, playCacheTimeouts: false });
});

test('the old proxy switch becomes the delivery method it stood for', () => {
  const off: Record<string, unknown> = { nzbdavProxyEnabled: false };
  migratePlaySettings(off);
  assert.deepEqual(off, { playDeliveryMethod: 'direct' });
  const on: Record<string, unknown> = { nzbdavProxyEnabled: true };
  migratePlaySettings(on);
  assert.deepEqual(on, { playDeliveryMethod: 'proxy' });
});

test('a saved delivery method wins over the old proxy switch and over an old value', () => {
  const c: Record<string, unknown> = { nzbdavStreamingMethod: 'pipe', nzbdavProxyEnabled: false };
  migratePlaySettings(c);
  assert.deepEqual(c, { playDeliveryMethod: 'pipe' });
  const both: Record<string, unknown> = { playStreamBufferMB: 32, nzbdavStreamBufferMB: 64 };
  migratePlaySettings(both);
  assert.deepEqual(both, { playStreamBufferMB: 32 });
});

test('an empty old delivery method does not hide the old proxy switch', () => {
  const c: Record<string, unknown> = { nzbdavStreamingMethod: null, nzbdavProxyEnabled: false };
  migratePlaySettings(c);
  assert.deepEqual(c, { playDeliveryMethod: 'direct' });
  const blank: Record<string, unknown> = { nzbdavStreamingMethod: '' };
  migratePlaySettings(blank);
  assert.deepEqual(blank, {});
});

test('a config already on the new names is left alone', () => {
  const c: Record<string, unknown> = { playDeliveryMethod: 'proxy', playCacheTimeouts: true };
  assert.equal(migratePlaySettings(c), false);
  assert.deepEqual(c, { playDeliveryMethod: 'proxy', playCacheTimeouts: true });
});
