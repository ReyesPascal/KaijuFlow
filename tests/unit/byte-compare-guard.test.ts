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
const BYTES_HINT = /\b(body|bytes|media|delivered|buf|buffer)\b|Buffer\.|arrayBuffer\(|subarray\(/i;
const DEEP_EQUAL = /\bdeep(?:Strict)?Equal\s*\(/g;
const STRING_LITERAL = /'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`/g;

/** The argument text of the call whose `(` is at `open`, up to its matching `)`. */
function callArgs(text: string, open: number): string {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    if (text[i] === '(') depth++;
    else if (text[i] === ')' && --depth === 0) return text.slice(open + 1, i);
  }
  return text.slice(open + 1);
}

/**
 * Lines in `text` where a deepEqual call looks like it compares bytes. Any
 * argument counts, across line breaks; string literals are ignored, so an
 * expected value such as 'bytes=2-5' is not mistaken for bytes.
 */
function byteDeepEquals(text: string): number[] {
  const hits: number[] = [];
  for (const m of text.matchAll(DEEP_EQUAL)) {
    const open = m.index! + m[0].length - 1;
    if (BYTES_HINT.test(callArgs(text, open).replace(STRING_LITERAL, "''"))) {
      hits.push(text.slice(0, m.index).split('\n').length);
    }
  }
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
  // the two sites this guard was written for: bytes named `delivered`, compared with `media`
  assert.deepEqual(byteDeepEquals('assert.deepEqual(delivered,media);'), [1]);
  assert.deepEqual(byteDeepEquals("x\nassert.deepEqual(\n  delivered,\n  media,\n  'msg')"), [2]);
});

test('tests compare bytes with assertBytes, never deepEqual', () => {
  const self = path.resolve('tests/unit/byte-compare-guard.test.ts');
  const violations = testFiles(TESTS)
    .filter(f => f !== self && !FROZEN.some(d => f.startsWith(d + path.sep)))
    .flatMap(f => byteDeepEquals(fs.readFileSync(f, 'utf8')).map(l => `${path.relative('.', f)}:${l}`));
  assert.deepEqual(violations, [], 'use assertBytes from tests/integration/parity/bytes.mjs');
});
