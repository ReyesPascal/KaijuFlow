// Fake AltMount Backend for the Parity suite (contract: docs/kaijuflow/research/ALTMOUNT_INTEGRATION.md, v0.4.0).
// POST /api/nzb/streams (multipart, nzb_url) + GET/HEAD /api/files/stream. Synthetic NZBs and media only.
// Same contract as fake NzbDAV: { name, requests[], addMovie(tag,title,media)->nzbUrl, submitsFor(tag), configure(configData) }.
import crypto from 'node:crypto';
import { serveBytes } from './serve-bytes.mjs';

export const API_KEY = 'synthetic-altmount-key';
const DOWNLOAD_KEY = crypto.createHash('sha256').update(API_KEY).digest('hex');

export async function createFakeAltmount(listen) {
  const sources = new Map(); // tag -> { tag, title, media, path, queueId, submits, completed }
  const requests = [];
  let base = '';

  base = await listen(async (req, res) => {
    const u = new URL(req.url, 'http://127.0.0.1');
    const path = u.pathname;
    requests.push({ method: req.method, path, range: req.headers.range || null });
    const json = (status, x) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(x)); };

    if (path.endsWith('.nzb')) {
      const tag = path.slice(1, -4);
      if (!sources.has(tag)) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': 'application/x-nzb' });
      res.end(`<nzb><file subject="${tag}"/></nzb>`);
      return;
    }

    if (req.method === 'POST' && path === '/api/nzb/streams') {
      const chunks = []; for await (const c of req) chunks.push(c);
      const body = Buffer.concat(chunks).toString('latin1');
      const field = name => new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]*)\\r\\n`).exec(body)?.[1];
      if (req.headers['x-api-key'] !== API_KEY) return json(401, { error: 'unauthorized' });
      const nzbUrl = field('nzb_url');
      if (!nzbUrl) return json(400, { error: 'No file provided' });
      const fetched = await fetch(nzbUrl).catch(() => null);
      const tag = new URL(nzbUrl).pathname.slice(1, -4);
      const src = sources.get(tag);
      if (!fetched?.ok || !src) return json(400, { error: 'could not fetch NZB' });
      src.submits++;
      const cached = src.completed;
      src.completed = true;
      return json(200, { streams: [{
        url: `${base}/api/files/stream?path=${encodeURIComponent(src.path)}&download_key=${DOWNLOAD_KEY}`,
        title: src.title, name: 'AltMount', _queue_item_id: src.queueId, _queue_status: cached ? 'completed' : 'streamable', _cached: cached,
      }] });
    }

    if ((req.method === 'GET' || req.method === 'HEAD') && path === '/api/files/stream') {
      if (u.searchParams.get('download_key') !== DOWNLOAD_KEY) { res.writeHead(401); res.end(); return; }
      const src = [...sources.values()].find(s => s.completed && s.path === u.searchParams.get('path'));
      if (src) { serveBytes(req, res, src.media); return; }
    }
    res.writeHead(404); res.end();
  });

  return {
    name: 'altmount',
    requests,
    /** Register a movie Source the fake will accept. Returns its NZB link. */
    addMovie(tag, title, media) {
      sources.set(tag, { tag, title, media, path: `/movies/${title}/${tag}.mkv`, queueId: `q-${tag}`, submits: 0, completed: false });
      return `${base}/${tag}.nzb`;
    },
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
