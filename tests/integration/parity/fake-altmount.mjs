// Fake AltMount Backend for the Parity suite (contract: docs/kaijuflow/research/ALTMOUNT_INTEGRATION.md, v0.4.0).
// POST /api/nzb/streams (multipart, nzb_url) + GET/HEAD /api/files/stream. Synthetic NZBs and media only.
// Same contract as fake NzbDAV: { name, requests[], addMovie(tag,title,media)->nzbUrl, submitsFor(tag), configure(configData) }.
import crypto from 'node:crypto';
import { serveBytes } from './serve-bytes.mjs';
import { fault } from './first-byte-fault.mjs';
import { nzbTag, rarVolumeCheck } from './fake-rar-rules.mjs';

export const API_KEY = 'synthetic-altmount-key';
const DOWNLOAD_KEY = crypto.createHash('sha256').update(API_KEY).digest('hex');

export async function createFakeAltmount(listen) {
  const sources = new Map(); // tag -> { tag, title, files[{season,episode,media,path}], queueId, submits, completed }
  const requests = [];
  const submitKinds = []; // 'file' | 'nzb_url' per submit
  const submitFields = []; // { season, episode } per submit (strings as received, or undefined)
  let base = '';
  let down = false;
  let indexerDown = 0; // HTTP status the NZB link answers while the indexer is "down" (0 = serves the NZB)
  let nextQueueId = 1; // real AltMount queue ids are integers
  const uploads = new Map(); // tag -> uploaded NZB texts
  const volumeOf = new Map(); // first-article id -> real RAR5 volume, for Scrambled RAR sets

  base = await listen(async (req, res) => {
    const u = new URL(req.url, 'http://127.0.0.1');
    const path = u.pathname;
    requests.push({ method: req.method, path, range: req.headers.range || null });
    const json = (status, x) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(x)); };

    if (path.endsWith('.nzb')) {
      const tag = path.slice(1, -4);
      if (!sources.has(tag)) { res.writeHead(404); res.end(); return; }
      if (indexerDown) { res.writeHead(indexerDown, { 'Retry-After': '60' }); res.end('indexer unavailable'); return; }
      res.writeHead(200, { 'Content-Type': 'application/x-nzb' });
      res.end(sources.get(tag).nzb ?? `<nzb><file subject="${tag}"/></nzb>`);
      return;
    }

    // Unreachable Backend: drop every Backend connection (the NZB link stays served, it is the indexer's).
    if (down) { req.destroy(); return; }

    if (req.method === 'POST' && path === '/api/nzb/streams') {
      const chunks = []; for await (const c of req) chunks.push(c);
      const body = Buffer.concat(chunks).toString('latin1');
      const field = name => new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]*)\\r\\n`).exec(body)?.[1];
      if (req.headers['x-api-key'] !== API_KEY) return json(401, { error: 'unauthorized' });
      // Accept a `file` upload or an `nzb_url`; record which one KaijuFlow used.
      const fileMatch = /name="file"; filename="[^"]*"\r\nContent-Type: [^\r]*\r\n\r\n([\s\S]*?)\r\n--/.exec(body);
      const nzbUrl = field('nzb_url');
      if (!fileMatch && !nzbUrl) return json(400, { error: 'No file provided' });
      let tag;
      if (fileMatch) { tag = nzbTag(fileMatch[1]); submitKinds.push('file'); uploads.set(tag, [...(uploads.get(tag) ?? []), fileMatch[1]]); }
      else {
        const fetched = await fetch(nzbUrl).catch(() => null);
        if (!fetched?.ok) return json(400, { error: 'could not fetch NZB' });
        tag = new URL(nzbUrl).pathname.slice(1, -4); submitKinds.push('nzb_url');
      }
      const src = sources.get(tag);
      if (!src) return json(400, { error: 'unknown NZB' });
      // Episode selection, as AltMount does it: a pack needs season+episode, and the answer is that episode's file.
      const season = field('season'), episode = field('episode');
      submitFields.push({ season, episode, timeout: field('timeout') });
      let file = src.files[0];
      if (src.files.length > 1) {
        if (!season || !episode) return json(400, { error: 'Episode not specified' });
        file = src.files.find(f => String(f.season) === season && String(f.episode) === episode);
        if (!file) return json(400, { error: 'Episode not found in NZB' });
      } else if (season && episode && src.files[0].season != null && (String(file.season) !== season || String(file.episode) !== episode)) {
        return json(400, { error: 'Episode not found in NZB' });
      }
      src.submits++;
      // AltMount v0.4.0 RAR volume rules: a failed queue item, answered like any other.
      if (fileMatch && rarVolumeCheck(fileMatch[1], volumeOf)) return json(500, { error: 'NZB processing failed' });
      // Scripted answer (status + body) for a Source, to exercise AltMount's other error answers.
      if (src.scripted) return json(src.scripted.status, src.scripted.body);
      // Failed queue item: pinned handler answers 500 "NZB processing failed" (not 400/422).
      if (src.rejected) return json(500, { error: 'NZB processing failed' });
      // Not ready in time: AltMount answers 408 with the queue ID; the queued work is NOT cancelled.
      if (src.neverReady) { await new Promise(r => setTimeout(r, 300)); return json(408, { error: 'Timeout waiting for stream', details: src.queueId }); }
      const cached = src.completed;
      src.completed = true;
      // Pinned v0.4.0 StremioStreamsResponse: the queue fields sit next to `streams`.
      return json(200, {
        streams: [{
          url: `${base}/api/files/stream?path=${encodeURIComponent(file.path)}&download_key=${DOWNLOAD_KEY}`,
          title: src.title, name: 'AltMount',
        }],
        _queue_item_id: src.queueId, _queue_status: src.queueStatus ?? (cached ? 'completed' : 'streamable'), _cached: cached,
      });
    }

    if ((req.method === 'GET' || req.method === 'HEAD') && path === '/api/files/stream') {
      if (u.searchParams.get('download_key') !== DOWNLOAD_KEY) { res.writeHead(401); res.end(); return; }
      const owner = [...sources.values()].filter(s => s.completed).find(s => s.files.some(f => f.path === u.searchParams.get('path')));
      const file = owner?.files.find(f => f.path === u.searchParams.get('path'));
      if (file && owner.fault) { fault(owner.fault, res, req); return; }
      if (file) { serveBytes(req, res, file.media); return; }
    }
    res.writeHead(404); res.end();
  });

  return {
    name: 'altmount',
    requests,
    submitKinds,
    submitFields,
    /** Register a movie Source the fake will accept. Returns its NZB link. */
    addMovie(tag, title, media) {
      sources.set(tag, { tag, title, files: [{ media, path: `/movies/${title}/${tag}.mkv` }], queueId: nextQueueId++, submits: 0, completed: false });
      return `${base}/${tag}.nzb`;
    },
    /** Register a TV Source: one episode, or a season pack when several. episodes: [{season, episode, media}]. */
    addSeries(tag, title, episodes) {
      const files = episodes.map(e => ({ ...e, path: `/tv/${title}/${title}.S${String(e.season).padStart(2, '0')}E${String(e.episode).padStart(2, '0')}.mkv` }));
      sources.set(tag, { tag, title, files, queueId: nextQueueId++, submits: 0, completed: false });
      return `${base}/${tag}.nzb`;
    },
    /**
     * Register a Scrambled RAR set Source (set from scrambledRarSet, built with
     * tag = this tag). The fake applies AltMount v0.4.0's RAR volume rules to
     * the uploaded NZB, so it plays only when the parts are named in real order.
     */
    addScrambled(tag, title, media, set) {
      const nzb = this.addMovie(tag, title, media);
      sources.get(tag).nzb = set.nzb;
      for (const p of set.parts) volumeOf.set(p.firstId, p.volume);
      return nzb;
    },
    /** Why real AltMount v0.4.0 would fail this NZB's RAR set, or null if it would accept it. */
    rarVolumeCheck(nzbText) { return rarVolumeCheck(nzbText, volumeOf); },
    /** The NZB texts KaijuFlow uploaded for a Source, in order. */
    uploadedNzbs(tag) { return uploads.get(tag) ?? []; },
    /** Register a Source whose queue item fails. */
    addRejected(tag, title) {
      const nzb = this.addMovie(tag, title, Buffer.from('unused'));
      sources.get(tag).rejected = true;
      return nzb;
    },
    /** Register a Source that never becomes ready (408 after a short wait). */
    addNeverReady(tag, title) {
      const nzb = this.addMovie(tag, title, Buffer.from('unused'));
      sources.get(tag).neverReady = true;
      return nzb;
    },
    /** Register a Source AltMount answers with a fixed status and JSON body. */
    addScripted(tag, title, status, body) {
      const nzb = this.addMovie(tag, title, Buffer.from('unused'));
      sources.get(tag).scripted = { status, body };
      return nzb;
    },
    /** Register a Source whose 200 answer reports a queue status that is not ready (e.g. 'queued'). */
    addNotReady(tag, title, queueStatus) {
      const nzb = this.addMovie(tag, title, Buffer.from('unused'));
      sources.get(tag).queueStatus = queueStatus;
      return nzb;
    },
    /**
     * Register a movie Source whose file the Backend cannot serve at the first byte:
     * mode 'bad-request' (400), 'drop' (connection dropped) or 'not-found' (404).
     * setFirstByteFault(tag, null) makes the file readable again.
     */
    addFirstByteFault(tag, title, media, mode) {
      const nzb = this.addMovie(tag, title, media);
      sources.get(tag).fault = mode;
      return nzb;
    },
    setFirstByteFault(tag, mode) { sources.get(tag).fault = mode; },
    /** Make the Backend unreachable (true) or reachable again (false). */
    setDown(v) { down = v; },
    /** Make the indexer answer this HTTP status for every NZB link (0 = serve the NZB again). */
    setIndexerDown(status) { indexerDown = status; },
    submitsFor(tag) { return sources.get(tag)?.submits ?? 0; },
    /** KaijuFlow settings that point the AltMount Backend at this fake. */
    configure(configData) {
      Object.assign(configData, {
        streamingMode: 'nzbdav', indexManager: 'manual', backend: 'altmount',
        altmountUrl: base, altmountApiKey: API_KEY, altmountCategory: 'kaijuflow', altmountPrepareTimeout: 20,
        nzbdavStreamingMethod: 'proxy',
        ultimateFallback: { ...configData.ultimateFallback, enabled: false },
      });
    },
  };
}
