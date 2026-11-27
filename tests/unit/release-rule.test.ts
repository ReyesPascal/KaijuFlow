// The Release rule's shared table (tests/fixtures/release-rule/table.tsv): the same table tools/brain/quickcheck.py's
// copy is tested against, so the two cannot drift apart.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { mergeReleases, releaseNameKey } from '../../src/addon/kaijuSearch.js';

const [head, ...lines] = fs.readFileSync(new URL('../fixtures/release-rule/table.tsv', import.meta.url), 'utf8').trimEnd().split('\n');
const cols = head.split('\t');
const rows = lines.map(l => Object.fromEntries(l.split('\t').map((v, i) => [cols[i], v])) as Record<string, string>);
const size = (v: string) => (v ? Number(v) : undefined);

for (const r of rows) {
  test(`the Release rule: ${r.a} (${r.size_a || 'no size'}) and ${r.b} (${r.size_b || 'no size'}) are ${r.same === 'yes' ? 'one Release' : 'two'}`, () => {
    assert.equal(releaseNameKey(r.a), r.key_a);
    const merged = mergeReleases([
      { title: r.a, size: size(r.size_a), indexerName: 'NinjaCentral' },
      { title: r.b, size: size(r.size_b), indexerName: 'DrunkenSlug' },
    ]);
    assert.equal(merged.length, r.same === 'yes' ? 1 : 2);
  });
}
