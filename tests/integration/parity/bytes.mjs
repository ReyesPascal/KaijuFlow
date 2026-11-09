import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const digest = (b) => createHash('sha256').update(b).digest('hex').slice(0, 16);

/**
 * Compare delivered bytes with the expected media. Never use assert.deepEqual on
 * Buffers: on a mismatch Node builds a text diff of both, and for a 1.2 MB
 * failure video that diff needs tens of GB of RAM (it OOM-killed the machine).
 */
export function assertBytes(actual, expected, message = 'delivered bytes should match') {
  const a = Buffer.from(actual);
  const e = Buffer.from(expected);
  if (a.equals(e)) return;
  assert.fail(`${message}: got ${a.length} bytes (sha256 ${digest(a)}), expected ${e.length} bytes (sha256 ${digest(e)})`);
}
