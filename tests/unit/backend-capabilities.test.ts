// Pins what the Backend declares it can do (R1, #16). AltMount is the only
// Backend (#188); Ultimate Fallback, the Play-time check's engine, is on for it since #190.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createAltmountBackend, buildAltmountSettings } from '../../src/backends/altmount.js';
import { getActiveBackend } from '../../src/backends/index.js';
import { backendCapabilities } from '../../src/backends/capabilities.js';

test('the Backend is AltMount', () => {
  assert.equal(getActiveBackend().id, 'altmount');
  assert.equal(getActiveBackend().label, 'AltMount');
});

test('AltMount runs Ultimate Fallback (the Play-time check)', () => {
  const b = createAltmountBackend(buildAltmountSettings());
  assert.deepEqual({ ...b.capabilities }, { ultimateFallback: true });
  assert.deepEqual({ ...backendCapabilities() }, { ...b.capabilities });
});
