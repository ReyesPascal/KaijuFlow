// The list deadline (#301, spec #298 stories 34, 35, 37): Kaiju Search answers as soon as an indexer's answer holds a
// sure Source (Search Flow's sure), without waiting for a slower indexer; the slower one's Sources come later
// (`late`), merged into their Releases. When no answer so far holds a sure Source it waits for every indexer, each
// bounded by its own timeout. Owner: NinjaCentral is the fast go-to, DrunkenSlug slower with rarer and older releases.
// The fakes answer with real answers of both (tests/fixtures/indexer-answers/, review rule 2).
// Run: npm run test:unit
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { kaijuSearch, type SearchContext } from '../../src/addon/searchOrchestrator.ts';
import { ANSWERS, item, rss, quiet, plainSettings, twoIndexers } from './fake-indexers.ts';

beforeEach(plainSettings);

const girlfriends: SearchContext = { type: 'series', imdbId: 'tt0247102', title: 'Girlfriends', year: '2000', season: 4, episode: 4, isAnime: false, additionalTitles: [] };
const SQUALOR = 'Girlfriends.S04E04.You.Aint.Gotta.Go.Home.But.You.Know.the.Rest.WEB-DL.DDP2.0.H.264-squalor';
const REGRET = 'Girlfriends.S04E04.720p.HDTV.x264-REGRET';
const SLOW_MS = 1500;
const ninja = () => fs.readFileSync(`${ANSWERS}/ninjacentral-search-girlfriends-s04e04.xml`, 'utf8');
const slug = () => fs.readFileSync(`${ANSWERS}/drunkenslug-search-girlfriends-s04e04.xml`, 'utf8');

/** A Release as the test reads it: its name, and each Source's indexer and size. */
const shown = (r: { title: string; sources: { indexerName: string; size: number }[] }) =>
  `${r.title} ${r.sources.map(s => `${s.indexerName}:${s.size}`).join(' ')}`;

test('NinjaCentral answers fast with a sure Source: the search answers at its time, and DrunkenSlug\'s Sources come later, merged into their Releases', async () => {
  await twoIndexers(ninja(), slug(), SLOW_MS);
  const t0 = Date.now();
  const answer = await quiet(() => kaijuSearch(girlfriends));
  const ms = Date.now() - t0;

  assert.ok(ms < SLOW_MS - 500, `answered at NinjaCentral's time, not DrunkenSlug's (${ms} ms)`);
  assert.ok(answer.indexer.length > 0);
  assert.deepEqual([...new Set(answer.indexer.flatMap(r => r.sources.map((s: { indexerName: string }) => s.indexerName)))], ['NinjaCentral']);
  assert.ok(answer.late, 'the slower indexer\'s answer is still to come');
  assert.deepEqual(answer.notWaitedFor, ['DrunkenSlug'], 'the list went out without DrunkenSlug');

  const late = await quiet(() => answer.late!);
  assert.ok(Date.now() - t0 >= SLOW_MS, 'the late answer holds DrunkenSlug\'s');
  const mine = late.indexer.filter(r => r.title === SQUALOR || r.title === REGRET).map(shown);
  assert.deepEqual(mine.sort(), [
    `${SQUALOR} NinjaCentral:193428257 DrunkenSlug:193428257`,
    `${REGRET} DrunkenSlug:600661974`,
    `${REGRET} NinjaCentral:609810415 DrunkenSlug:610490962`,
  ].sort(), 'a late Source joins its Release; an upload only DrunkenSlug has is a Release of its own');
  // The Releases already listed keep their place: the late list starts with them, in their order.
  assert.deepEqual(late.indexer.slice(0, answer.indexer.length).map(r => r.title), answer.indexer.map(r => r.title));
});

test('NinjaCentral answers fast with only a maybe: the search waits for DrunkenSlug and answers with both', async () => {
  const GB = 1_000_000_000;
  const MAYBE = 'Girlfriends.Uncut.S04E04.720p.HDTV.x264-AAA'; // the loose rule keeps it, the strict one does not
  await twoIndexers(rss([item(MAYBE, 'nc-1', 2 * GB)]), slug(), SLOW_MS);
  const t0 = Date.now();
  const answer = await quiet(() => kaijuSearch(girlfriends));
  const ms = Date.now() - t0;

  assert.ok(ms >= SLOW_MS, `waited for DrunkenSlug (${ms} ms)`);
  assert.equal(answer.late, undefined, 'nothing is left to come');
  assert.equal(answer.notWaitedFor, undefined);
  assert.ok(answer.indexer.some(r => r.title === MAYBE), 'NinjaCentral\'s maybe is listed');
  assert.ok(answer.indexer.some(r => r.title === SQUALOR), 'and DrunkenSlug\'s Sources');
});
