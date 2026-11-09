import test from 'node:test';
import assert from 'node:assert/strict';
import { readyMediaOf } from '../../src/backends/altmount.js';

const BASE = 'http://altmount:8080';
const url = (path: string) => `${BASE}/api/files/stream?path=${encodeURIComponent(path)}&download_key=abc`;
// Real v0.4.0 reply (StremioStreamsResponse): queue fields next to `streams`, entries are url/title/name only.
const reply = (extra: Record<string, unknown>, path = '/complete/kaijuflow/Movie/Movie.mkv') =>
  JSON.stringify({ streams: [{ url: url(path), title: 'Movie.mkv', name: 'AltMount' }], ...extra });

test('a reused completed item is ready (queue fields at the top of the reply)', () => {
  assert.deepEqual(readyMediaOf(reply({ _queue_item_id: 4, _queue_status: 'completed', _cached: true }), BASE),
    { queueId: '4', videoPath: '/complete/kaijuflow/Movie/Movie.mkv', cached: true, status: 'completed' });
});

test('a streamable item is ready', () => {
  assert.equal(readyMediaOf(reply({ _queue_item_id: 6, _queue_status: 'streamable', _cached: false }), BASE)?.videoPath,
    '/complete/kaijuflow/Movie/Movie.mkv');
});

test('not ready, no streams, or not JSON means no media', () => {
  assert.equal(readyMediaOf(reply({ _queue_item_id: 6, _queue_status: 'processing', _cached: false }), BASE), null);
  assert.equal(readyMediaOf(JSON.stringify({ streams: [], _queue_item_id: 6, _queue_status: 'completed', _cached: true }), BASE), null);
  assert.equal(readyMediaOf('oops', BASE), null);
});

test('queue fields inside a stream entry are not the contract', () => {
  const old = JSON.stringify({ streams: [{ url: url('/m.mkv'), _queue_status: 'completed', _cached: true }] });
  assert.equal(readyMediaOf(old, BASE), null);
});
