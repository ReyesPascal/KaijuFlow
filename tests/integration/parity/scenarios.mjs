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
];

/** The failure video is a long video/mp4, much bigger than the synthetic media. */
function assertFailureVideo(r, media) {
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('content-type'), 'video/mp4', 'player should get the failure video');
  assert.ok(r.body.length > media.length, 'failure video is not the Backend media');
}

const failureScenarios = [
  {
    // A Source the Backend rejects: failure video, then marked dead (the repeat is
    // answered without asking the Backend again).
    id: 'rejected-source-failure-video-and-dead',
    async run({ kaijuflow, backend }) {
      const title = 'KaijuFlow.Parity.Rejected.2026.1080p.WEB-DL.H264';
      const nzb = backend.addRejected('rejected', title);
      assertFailureVideo(await play(streamUrl(kaijuflow, nzb, title)), mediaFor('rejected'));
      assert.equal(backend.submitsFor('rejected'), 1);
      assertFailureVideo(await play(streamUrl(kaijuflow, nzb, title)), mediaFor('rejected'));
      assert.equal(backend.submitsFor('rejected'), 1, 'dead Source should not be submitted again');
    },
  },
  {
    // Only for Backends with a preparation time limit (AltMount). NzbDAV has none.
    id: 'never-ready-failure-video-and-dead',
    needs: 'addNeverReady',
    async run({ kaijuflow, backend }) {
      const title = 'KaijuFlow.Parity.NeverReady.2026.1080p.WEB-DL.H264';
      const nzb = backend.addNeverReady('neverready', title);
      assertFailureVideo(await play(streamUrl(kaijuflow, nzb, title)), mediaFor('neverready'));
      assert.equal(backend.submitsFor('neverready'), 1);
      assert.ok(!backend.requests.some(q => /cancel/.test(q.path)), 'a timeout is not a cancel');
      assertFailureVideo(await play(streamUrl(kaijuflow, nzb, title)), mediaFor('neverready'));
      assert.equal(backend.submitsFor('neverready'), 1, 'timed-out Source should be marked dead');
    },
  },
  {
    // Backend down: the player gets the failure video but the Source is NOT dead,
    // so it plays once the Backend is back.
    id: 'unreachable-backend-not-dead',
    async run({ kaijuflow, backend }) {
      const media = mediaFor('unreachable');
      const title = 'KaijuFlow.Parity.Unreachable.2026.1080p.WEB-DL.H264';
      const nzb = backend.addMovie('unreachable', title, media);
      backend.setDown(true);
      try {
        assertFailureVideo(await play(streamUrl(kaijuflow, nzb, title)), media);
      } finally {
        backend.setDown(false);
      }
      const r = await play(streamUrl(kaijuflow, nzb, title));
      assert.equal(r.status, 200);
      assert.deepEqual(r.body, media, 'Source should play once the Backend is reachable');
    },
  },
];
scenarios.push(...failureScenarios);

/** Run every scenario against one fake Backend. Returns per-scenario results. */
export async function runParity({ kaijuflow, backend }) {
  const results = [];
  for (const s of scenarios) {
    if (s.needs && typeof backend[s.needs] !== 'function') { results.push({ id: s.id, status: 'pass', skipped: `Backend has no ${s.needs}` }); continue; }
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
