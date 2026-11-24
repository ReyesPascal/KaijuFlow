/**
 * Which indexer a Release's NZB is fetched from first (#300): the one whose recent NZB downloads were fastest, a tie
 * going to the indexer listed first. The Walk tests (tests/integration/parity/play-time-scenarios.mjs) play it through
 * the routes; these pin the order's edges.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { nzbOrder } from '../../src/play/releaseGrab.js';

const source = (indexerName: string) => ({ nzbUrl: `https://${indexerName}.example/1.nzb`, title: 'Some.Show.S01E01.1080p.WEB-DL-GRP', indexerName });
const order = (indexers: string[], ms: Record<string, number>, listed: string[]) =>
  nzbOrder(indexers.map(source), { downloadMs: i => ms[i], listed }).map(s => s.indexerName);

test('the indexer whose recent NZB downloads were fastest comes first', () => {
  assert.deepEqual(order(['NinjaCentral', 'DrunkenSlug'], { NinjaCentral: 900, DrunkenSlug: 300 }, ['NinjaCentral', 'DrunkenSlug']), ['DrunkenSlug', 'NinjaCentral']);
});

test('a tie goes to the indexer listed first, whatever order the Sources came in', () => {
  assert.deepEqual(order(['DrunkenSlug', 'NinjaCentral'], { NinjaCentral: 300, DrunkenSlug: 300 }, ['NinjaCentral', 'DrunkenSlug']), ['NinjaCentral', 'DrunkenSlug']);
  assert.deepEqual(order(['DrunkenSlug', 'NinjaCentral'], {}, ['NinjaCentral', 'DrunkenSlug']), ['NinjaCentral', 'DrunkenSlug']);
});

test('an indexer with no recent NZB download comes after the measured ones', () => {
  assert.deepEqual(order(['NinjaCentral', 'DrunkenSlug'], { DrunkenSlug: 2000 }, ['NinjaCentral', 'DrunkenSlug']), ['DrunkenSlug', 'NinjaCentral']);
});

test('an indexer missing from the list (named by Prowlarr) keeps the Release\'s order after the listed ones', () => {
  assert.deepEqual(order(['B', 'A', 'NinjaCentral'], {}, ['NinjaCentral']), ['NinjaCentral', 'B', 'A']);
});
