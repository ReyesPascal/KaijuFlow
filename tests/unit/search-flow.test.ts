// Search Flow (#282, spec #279; GLOSSARY: Search Flow): the loose rule (the inherited isTextSearchMatch) decides what
// stays in a title's list, the strict rule (the quick check's right-title rule, ported) only sorts: a Source that
// passes strict is sure, one the loose rule keeps alone is maybe. Both copies of the strict rule (this one and
// tools/brain/quickcheck.py's) are tested on one shared table of real release names, tests/fixtures/release-names/.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { strictMatch, looseMatch, searchFlow, type FlowTitle } from '../../src/parsers/searchFlow.ts';

interface Row { release: string; type: string; label: string; date: string; other: string; right: string; strict: string; loose: string }

/** The shared release-name table, one row per real release name and the title it was matched against. */
function table(): Row[] {
  const [head, ...lines] = fs.readFileSync(new URL('../fixtures/release-names/table.tsv', import.meta.url), 'utf8').trimEnd().split('\n');
  const cols = head.split('\t');
  return lines.map(line => Object.fromEntries(line.split('\t').map((v, i) => [cols[i], v])) as unknown as Row);
}

/** A row's title as KaijuFlow knows it: a film's name and year, an episode's show, season, episode and air date. */
function titleOf(row: Row): FlowTitle {
  const otherNames = row.other ? row.other.split('|') : [];
  if (row.type === 'movie') return { type: 'movie', name: row.label, otherNames, year: row.date.slice(0, 4) };
  const m = /^(.*) S(\d+)E(\d+)$/.exec(row.label);
  return m
    ? { type: 'series', name: m[1], otherNames, season: Number(m[2]), episode: Number(m[3]), aired: row.date }
    : { type: 'series', name: row.label, otherNames, aired: row.date };
}

test('the strict rule gives every row of the shared table the answer the quick check gives it', () => {
  const rows = table();
  assert.ok(rows.length >= 60, 'the table holds the real release names');
  for (const row of rows) {
    const { ok, why } = strictMatch(row.release, titleOf(row));
    assert.equal(ok ? 'pass' : why, row.strict, `${row.release} as ${row.label}`);
  }
});

test('the loose rule gives every row of the shared table its answer', () => {
  for (const row of table()) assert.equal(looseMatch(row.release, titleOf(row)) ? 'keep' : 'drop', row.loose, `${row.release} as ${row.label}`);
});

/** The first row of the table for this release and label. */
function row(release: string, label: string): Row {
  const found = table().find(r => r.release === release && r.label === label);
  assert.ok(found, `${release} as ${label} is in the table`);
  return found;
}

test('an obscure real release the strict rule fails stays as a maybe, with the strict rule\'s why', () => {
  const joker = row('Joker 1080p WEB-DL DD5.1 H264 (2019) NL Subs', 'Joker');
  assert.deepEqual(searchFlow(joker.release, titleOf(joker)), { flow: 'maybe', why: 'the name "Joker" is not followed by a year (2019 wanted)' });
  const matrix = row('The Matrix 1 (1999).English.1080p-NoGroup', 'The Matrix');
  assert.equal(searchFlow(matrix.release, titleOf(matrix)).flow, 'maybe');
});

test('a release the strict rule passes is sure, even one the loose rule would drop', () => {
  const reacher = row('REACHER.TV.S01E01.Welcome.to.Margrave.1080p.AMZN.WEB-DL.DDP5.1.H.265-NINJACENTRAL', 'Reacher S01E01');
  assert.equal(reacher.loose, 'drop');
  assert.deepEqual(searchFlow(reacher.release, titleOf(reacher)), { flow: 'sure', why: 'the name and episode fit' });
  const avatar = row('Avatar.2009.{edition-Extended}.1080p.BluRay.DDP.5.1.10bit.H.265-iVy.part01.rar', 'Avatar');
  assert.deepEqual(searchFlow(avatar.release, titleOf(avatar)), { flow: 'sure', why: 'the name and year fit' });
  const pack = row('a.b.mm efnet - req 96401 - Pushing.Daisies.S01.DVDRip - 037 315 - pd.103.dvdrip-rwd.r00', 'Pushing Daisies S01E03');
  assert.deepEqual(searchFlow(pack.release, titleOf(pack)), { flow: 'sure', why: 'the name and season fit (a season pack)' });
});

test('a release neither rule fits is dropped, with why', () => {
  const wick = row('John Wick Chapter 4 2023 1080p AMZN WEB-DL DDP5 1 H 265-ViSTA', 'John Wick');
  assert.deepEqual(searchFlow(wick.release, titleOf(wick)), { flow: 'dropped', why: 'the name "John Wick" is not followed by a year (2014 wanted)' });
});

test('over the whole table no release the strict rule passes is dropped, and every right release the loose rule keeps stays', () => {
  for (const r of table()) {
    const { flow } = searchFlow(r.release, titleOf(r));
    if (r.strict === 'pass') assert.equal(flow, 'sure', r.release);
    if (r.right === 'yes' && r.loose === 'keep') assert.notEqual(flow, 'dropped', r.release);
  }
});
