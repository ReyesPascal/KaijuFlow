// Parity scenarios: one shared set, run against every fake Backend.
// Each scenario drives KaijuFlow's real stream route over HTTP and asserts only
// on what the player receives and on the fake Backend's recorded requests.
import assert from 'node:assert/strict';

const mediaFor = tag => Buffer.from(`KaijuFlow parity bytes for ${tag}: 0123456789abcdefghijklmnopqrstuvwxyz`);

function streamUrl(kaijuflow, nzbUrl, title) {
  const t = Buffer.from(JSON.stringify({ url: nzbUrl, title, indexer: 'Parity', ty: 'movie' })).toString('base64url');
  return `${kaijuflow}/stremio/synthetic-manifest/nzbdav/stream/movie.mkv?t=${t}`;
}

async function play(url, range) {
  const res = await fetch(url, { headers: range ? { Range: range } : {}, signal: AbortSignal.timeout(20000) });
  return { status: res.status, headers: res.headers, body: Buffer.from(await res.arrayBuffer()) };
}

function seriesUrl(kaijuflow, nzbUrl, title, season, episode, pack) {
  const t = Buffer.from(JSON.stringify({ url: nzbUrl, title, indexer: 'Parity', ty: 'series', season, episode, ...(pack ? { seasonpack: 1, epcount: 3 } : {}) })).toString('base64url');
  return `${kaijuflow}/stremio/synthetic-manifest/nzbdav/stream/series.mkv?t=${t}`;
}

export const scenarios = [
  {
    id: 'movie-plays',
    async run({ kaijuflow, backend }) {
      const media = mediaFor('movie');
      const title = 'KaijuFlow.Parity.Movie.2026.2160p.WEB-DL.H265';
      const nzb = backend.addMovie('movie', title, media);
      const r = await play(streamUrl(kaijuflow, nzb, title));
      assert.equal(r.status, 200, 'movie should play');
      assert.deepEqual(r.body, media, 'delivered bytes should match the Backend media');
      assert.equal(backend.submitsFor('movie'), 1, 'NZB should be submitted once');
      // AltMount: KaijuFlow grabs the NZB itself and uploads it; it never hands over the link.
      if (backend.submitKinds) assert.deepEqual(backend.submitKinds, ['file'], 'KaijuFlow should send a file, never nzb_url');
    },
  },
  {
    id: 'byte-range-206',
    async run({ kaijuflow, backend }) {
      const media = mediaFor('range');
      const title = 'KaijuFlow.Parity.Range.2026.1080p.WEB-DL.H264';
      const nzb = backend.addMovie('range', title, media);
      const r = await play(streamUrl(kaijuflow, nzb, title), 'bytes=10-29');
      assert.equal(r.status, 206, 'range request should return 206');
      assert.deepEqual(r.body, media.subarray(10, 30), 'range body should be the requested slice');
      assert.equal(r.headers.get('content-range'), `bytes 10-29/${media.length}`);
    },
  },
  {
    // Owner decision 2026-11-09 (#17): a range past the end is NOT answered
    // with 416. KaijuFlow retries without Range and serves the whole file
    // from byte 0, so a player carrying a stale seek position across a Source
    // switch still recovers. Every Backend must match this.
    id: 'bad-range-full-file',
    async run({ kaijuflow, backend }) {
      const media = mediaFor('badrange');
      const title = 'KaijuFlow.Parity.BadRange.2026.1080p.WEB-DL.H264';
      const nzb = backend.addMovie('badrange', title, media);
      const r = await play(streamUrl(kaijuflow, nzb, title), `bytes=${media.length + 100}-`);
      assert.equal(r.status, 200, 'range past the end should fall back to the whole file');
      assert.deepEqual(r.body, media, 'fallback body should be the whole file from byte 0');
    },
  },
  {
    // A Source the Backend already prepared is not submitted a second time.
    id: 'already-prepared',
    async run({ kaijuflow, backend }) {
      const media = mediaFor('again');
      const title = 'KaijuFlow.Parity.Again.2026.1080p.WEB-DL.H264';
      const nzb = backend.addMovie('again', title, media);
      const url = streamUrl(kaijuflow, nzb, title);
      const first = await play(url);
      assert.equal(first.status, 200, 'first play should work');
      const second = await play(url);
      assert.equal(second.status, 200, 'second play should work');
      assert.deepEqual(second.body, media, 'second play should deliver the same bytes');
      assert.equal(backend.submitsFor('again'), 1, 'an already-prepared Source must not be submitted again');
    },
  },
  {
    id: 'episode-plays',
    async run({ kaijuflow, backend }) {
      const media = mediaFor('episode');
      const title = 'KaijuFlow.Parity.Show.S02E05.1080p.WEB-DL.H264';
      const nzb = backend.addSeries('episode', title, [{ season: 2, episode: 5, media }]);
      const r = await play(seriesUrl(kaijuflow, nzb, title, 2, 5, false));
      assert.equal(r.status, 200, 'single-episode Source should play');
      assert.deepEqual(r.body, media);
      assert.equal(backend.submitsFor('episode'), 1);
    },
  },
  {
    // The pack holds three episodes; the player asked for E03 and must get E03's bytes.
    id: 'season-pack',
    async run({ kaijuflow, backend }) {
      const eps = [1, 2, 3].map(e => ({ season: 1, episode: e, media: mediaFor(`pack-e${e}`) }));
      const title = 'KaijuFlow.Parity.Pack.S01.1080p.WEB-DL.H264';
      const nzb = backend.addSeries('pack', title, eps);
      const r = await play(seriesUrl(kaijuflow, nzb, title, 1, 3, true));
      assert.equal(r.status, 200, 'season pack should play');
      assert.deepEqual(r.body, eps[2].media, 'the requested episode, not another one');
      assert.equal(backend.submitsFor('pack'), 1);
      // AltMount is told which episode to pick.
      if (backend.submitFields) assert.deepEqual(backend.submitFields.at(-1), { season: '1', episode: '3' });
    },
  },
];

/** Run every scenario against one fake Backend. Returns per-scenario results. */
export async function runParity({ kaijuflow, backend }) {
  const results = [];
  for (const s of scenarios) {
    const before = backend.requests.length;
    try {
      await s.run({ kaijuflow, backend });
      results.push({ id: s.id, status: 'pass' });
    } catch (e) {
      results.push({ id: s.id, status: 'fail', error: String(e), requests: backend.requests.slice(before).slice(-15) });
    }
  }
  return results;
}
