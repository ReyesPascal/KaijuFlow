// Pins what the Backend declares it can do (R1, #16). AltMount is the only
// Backend (#188); Ultimate Fallback stays off for it until #190 turns it on.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createAltmountBackend, buildAltmountSettings } from '../../src/backends/altmount.js';
import { getActiveBackend } from '../../src/backends/index.js';
import { backendCapabilities } from '../../src/backends/capabilities.js';

test('the Backend is AltMount', () => {
  assert.equal(getActiveBackend().id, 'altmount');
  assert.equal(getActiveBackend().label, 'AltMount');
});

test('AltMount has no Ultimate Fallback yet', () => {
  const b = createAltmountBackend(buildAltmountSettings());
  assert.deepEqual({ ...b.capabilities }, { ultimateFallback: false });
  assert.deepEqual({ ...backendCapabilities() }, { ...b.capabilities });
});
