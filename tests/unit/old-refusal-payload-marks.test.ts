// Round 2 review of #239, finding memory-2.
// ADR 0004, "The walk's grabs": an error payload with any code but 300 is the indexer refusing us, the Source kept.
// Earlier builds wrote a dead mark for every error payload, as "Indexer returned error: <description>", whatever its
// code. Those marks say nothing about the Source, so the Source memory drops them when it loads, as it drops the
// marks an unavailable indexer caused (ADR 0004, Consequences).
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isIndexerUnavailableMessage, pruneIndexerUnavailableMarks } from '../../src/play/utils.ts';

// The descriptions of Newznab's refusal codes (100, 101, 102, 500, 501, 900, 910), as earlier builds stored them.
const REFUSALS = [
  'Indexer returned error: Request limit reached',
  'Indexer returned error: Download limit reached',
  'Indexer returned error: Incorrect user credentials',
  'Indexer returned error: Account suspended',
  'Indexer returned error: Insufficient privileges/not authorized',
  'Indexer returned error: Unknown error',
  'Indexer returned error: API Disabled',
];

test('a stored mark for a refusal payload is one an unavailable indexer caused', () => {
  for (const m of REFUSALS) assert.equal(isIndexerUnavailableMessage(m), true, m);
});

test('loading the dead marks drops the ones an earlier build wrote for a refusal payload', () => {
  const mark = (message: string) => ({ title: 't', indexerName: 'x', error: { message, isBadSource: true }, createdAt: 1, expiresAt: 0 });
  const stored = {
    'https://indexer.example/getnzb/limit.nzb': mark('Indexer returned error: Request limit reached'),
    'https://indexer.example/getnzb/pack.nzb::S01[. _-]?E01(?!\\d)': mark('Indexer returned error: Download limit reached'),
    'https://indexer.example/getnzb/blocked.nzb': mark('Health check: blocked'),
  };
  const { kept, dropped } = pruneIndexerUnavailableMarks(stored);
  assert.deepEqual(dropped.sort(), ['https://indexer.example/getnzb/limit.nzb', 'https://indexer.example/getnzb/pack.nzb::S01[. _-]?E01(?!\\d)']);
  assert.deepEqual(Object.keys(kept), ['https://indexer.example/getnzb/blocked.nzb']);
});
