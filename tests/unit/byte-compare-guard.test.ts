// Retro of #16: assert.deepEqual / deepStrictEqual on byte Buffers builds a
// text diff of both buffers when they differ. For the 1.2 MB failure video
// that diff took ~28 GB and the kernel OOM-killed the test runner and the
// terminal around it (3 crashes on 2026-11-09). Byte checks in tests use
// assertBytes (tests/integration/parity/bytes.mjs), which compares with
// Buffer.equals and reports lengths + hashes.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const TESTS = path.resolve('tests');
// tests/a4 is frozen audit evidence (docs/kaijuflow/audit/A4-*.md) and only
// compares a few bytes; it is not rewritten.
const FROZEN = [path.resolve('tests/a4')];
const BYTES_HINT = /\b(body|bytes|media|buf|buffer)\b|Buffer\.|arrayBuffer\(|subarray\(/i;
const DEEP_EQUAL = /\bdeep(?:Strict)?Equal\s*\(([^\n]*)/g;

/** Lines in `text` that deep-compare something that looks like bytes. */
export function byteDeepEquals(text: string): number[] {
  const hits: number[] = [];
  text.split('\n').forEach((line, i) => {
    // Only the first argument (the delivered value) decides; expected values such
    // as range strings ('bytes=2-5') are not bytes.
    for (const m of line.matchAll(DEEP_EQUAL)) if (BYTES_HINT.test(m[1].split(',')[0])) hits.push(i + 1);
  });
  return hits;
}

function testFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return e.name === 'node_modules' || e.name === 'fixtures' ? [] : testFiles(p);
    return /\.(mjs|js|ts)$/.test(p) ? [p] : [];
  });
}

test('detector flags byte deep-equals and leaves other deep-equals alone', () => {
  assert.deepEqual(byteDeepEquals('assert.deepEqual(r.body, media);'), [1]);
  assert.deepEqual(byteDeepEquals('x\nassert.deepStrictEqual(Buffer.from(await res.arrayBuffer()), want)'), [2]);
  assert.deepEqual(byteDeepEquals("assert.deepEqual(violations, [], 'msg')"), []);
  assert.deepEqual(byteDeepEquals('assert.deepEqual(backend.submitFields.at(-1), { season: "1" })'), []);
  assert.deepEqual(byteDeepEquals("assert.deepEqual(upstreamRanges.slice(0,4),['bytes=2-5'])"), []);
});

test('tests compare bytes with assertBytes, never deepEqual', () => {
  const self = path.resolve('tests/unit/byte-compare-guard.test.ts');
  const violations = testFiles(TESTS)
    .filter(f => f !== self && !FROZEN.some(d => f.startsWith(d + path.sep)))
    .flatMap(f => byteDeepEquals(fs.readFileSync(f, 'utf8')).map(l => `${path.relative('.', f)}:${l}`));
  assert.deepEqual(violations, [], 'use assertBytes from tests/integration/parity/bytes.mjs');
});
