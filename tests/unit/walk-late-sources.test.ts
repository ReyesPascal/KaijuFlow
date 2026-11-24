// Best's Walk on a list still growing (#301, spec #298 stories 36, 38; GLOSSARY: Walk): the list went out before a
// slower indexer answered, so its Sources join the Walk as they arrive. While more may come, a Walk whose Sources all
// failed waits for them instead of ending, and a healthy maybe is not handed to the Backend (a sure Source still to
// come goes first). Once the list is whole the Walk ends, or plays the maybe, as before.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Walk, type WalkDecision } from '../../src/play/walk.ts';

/** A Walk over `flows` (each Source's Search Flow mark, in Walk order), from one indexer, none dead, no library hit. */
function walkOver(flows: ('sure' | 'maybe')[], inFlight: number) {
  const marks = [...flows];
  const walk = new Walk({
    size: marks.length, inFlight, open: true,
    isDead: () => false, indexerOf: () => 'NinjaCentral', hits: new Map(),
    isMaybe: index => marks[index] === 'maybe',
  });
  /** Late Sources put in the list at `at`, as the adapter does. */
  const insert = (at: number, late: ('sure' | 'maybe')[]) => { marks.splice(at, 0, ...late); return walk.on({ type: 'more', at, count: late.length }); };
  return { walk, insert };
}
const kinds = (ds: WalkDecision[]) => ds.map(d => ('index' in d ? `${d.type} ${d.index}` : 'end' in d ? `${d.type} ${d.end}` : d.type));

test('a Walk whose Sources all failed waits for the late ones, walks them, and plays one', () => {
  const { walk, insert } = walkOver(['sure', 'sure'], 2);
  assert.deepEqual(kinds(walk.start()), ['grab 0', 'grab 1']);
  walk.on({ type: 'grabFailed', index: 0, badSource: true });
  assert.deepEqual(kinds(walk.on({ type: 'grabFailed', index: 1, badSource: true })), ['markDead 1'], 'no end: more may come');
  assert.equal(walk.done, false);

  assert.deepEqual(kinds(insert(2, ['sure'])), ['grab 2'], 'the late Source is walked');
  walk.on({ type: 'grabbed', index: 2 });
  assert.deepEqual(kinds(walk.on({ type: 'checked', index: 2, verdict: 'healthy' })), ['prepare 2']);
  assert.deepEqual(kinds(walk.on({ type: 'prepared', index: 2, videoPath: '/v/a.mkv' })), ['settle 2']);
  assert.equal(walk.done, true);
});

test('a Walk whose Sources all failed ends when the list is whole and nothing more came', () => {
  const { walk } = walkOver(['sure'], 1);
  walk.start();
  assert.deepEqual(kinds(walk.on({ type: 'grabFailed', index: 0, badSource: true })), ['markDead 0']);
  assert.deepEqual(kinds(walk.on({ type: 'closed' })), ['settleNone ran-out']);
  assert.equal(walk.done, true);
});

test('while more may come a healthy maybe waits, and a late sure Source put before it plays first', () => {
  const { walk, insert } = walkOver(['maybe'], 2);
  walk.start();
  walk.on({ type: 'grabbed', index: 0 });
  assert.deepEqual(kinds(walk.on({ type: 'checked', index: 0, verdict: 'healthy' })), [], 'the healthy maybe is not prepared yet');

  // The adapter puts a late sure Source after what the Walk reached and before the maybes it has not: here index 1.
  assert.deepEqual(kinds(insert(1, ['sure'])), ['grab 1']);
  walk.on({ type: 'grabbed', index: 1 });
  assert.deepEqual(kinds(walk.on({ type: 'checked', index: 1, verdict: 'healthy' })), ['prepare 1'], 'the sure Source goes first');
  assert.deepEqual(kinds(walk.on({ type: 'prepared', index: 1, videoPath: '/v/b.mkv' })), ['settle 1']);
});

test('once the list is whole a healthy maybe is played, as before', () => {
  const { walk } = walkOver(['maybe'], 1);
  walk.start();
  walk.on({ type: 'grabbed', index: 0 });
  walk.on({ type: 'checked', index: 0, verdict: 'healthy' });
  assert.deepEqual(kinds(walk.on({ type: 'closed' })), ['prepare 0']);
});

test('a held maybe leaves its place in the Walk to a late sure Source, not to another maybe', () => {
  const { walk, insert } = walkOver(['maybe', 'maybe'], 1);
  walk.start();
  walk.on({ type: 'grabbed', index: 0 });
  assert.deepEqual(kinds(walk.on({ type: 'checked', index: 0, verdict: 'healthy' })), [], 'the next maybe waits too: no grab spent on it');
  assert.deepEqual(kinds(insert(1, ['sure'])), ['grab 1'], 'one at a time, yet the late sure Source is walked');
  walk.on({ type: 'grabFailed', index: 1, badSource: true });
  assert.deepEqual(kinds(walk.on({ type: 'closed' })), ['prepare 0'], 'the list whole: the held maybe plays');
});
