// Pins what each Backend declares it can do (R1, #16). A new Backend (e.g.
// InfiniDysk) adds its own row here instead of touching callers.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createNzbdavBackend } from '../../src/backends/nzbdav.js';
import { createAltmountBackend, buildAltmountSettings } from '../../src/backends/altmount.js';
import { buildNzbdavConfig } from '../../src/nzbdav/utils.js';
import { backendCapabilities } from '../../src/backends/capabilities.js';

test('NzbDAV has a library and Ultimate Fallback', () => {
  const b = createNzbdavBackend(buildNzbdavConfig());
  assert.deepEqual({ ...b.capabilities }, { library: true, ultimateFallback: true });
  assert.deepEqual({ ...backendCapabilities('nzbdav') }, { ...b.capabilities });
});

test('AltMount has neither a library nor Ultimate Fallback', () => {
  const b = createAltmountBackend(buildAltmountSettings());
  assert.deepEqual({ ...b.capabilities }, { library: false, ultimateFallback: false });
  assert.deepEqual({ ...backendCapabilities('altmount') }, { ...b.capabilities });
});
