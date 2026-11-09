// Fake NzbDAV Backend for the Parity suite: SAB-style API + WebDAV over loopback HTTP.
// Synthetic NZBs and synthetic media bytes only. Records every request it gets.
import { serveBytes } from './serve-bytes.mjs';

const ADVERTISED_SIZE = 128 * 1024 * 1024; // meets KaijuFlow's 100 MiB video threshold

export async function createFakeNzbdav(listen) {
  const sources = new Map(); // nzb tag -> { title, files[{name,media,path}], dir, job, submits }
  const requests = [];
  let base = '';
  let down = false;

  const propfindEntry = (href, dir) => `<d:response><d:href>${href}</d:href><d:propstat><d:prop><d:resourcetype>${dir ? '<d:collection/>' : ''}</d:resourcetype><d:getcontentlength>${dir ? 0 : ADVERTISED_SIZE}</d:getcontentlength><d:getcontenttype>${dir ? 'httpd/unix-directory' : 'video/x-matroska'}</d:getcontenttype></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>`;

  base = await listen(async (req, res) => {
    const u = new URL(req.url, 'http://127.0.0.1');
    const path = decodeURIComponent(u.pathname);
    requests.push({ method: req.method, path, mode: u.searchParams.get('mode'), range: req.headers.range || null });
    const json = x => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(x)); };

    if (path.endsWith('.nzb')) {
      const tag = path.slice(1, -4);
      if (!sources.has(tag)) { res.writeHead(404); res.end(); return; }
      res.setHeader('Content-Type', 'application/x-nzb');
      res.end(`<nzb><file subject="${tag}"><groups><group>alt.synthetic</group></groups><segments><segment bytes="64" number="1">${tag}@invalid</segment></segments></file></nzb>`);
      return;
    }
    // Unreachable Backend: drop every Backend connection (the NZB link stays served, it is the indexer's).
    if (down) { req.destroy(); return; }
    if (path === '/api') {
      const mode = u.searchParams.get('mode');
      if (mode === 'addfile') {
        let body = ''; for await (const c of req) body += c;
        const src = [...sources.values()].find(s => body.includes(`subject="${s.tag}"`));
        if (!src) { json({ status: false, error: 'unknown nzb' }); return; }
        src.submits++;
        json({ status: true, nzo_ids: [src.job] });
        return;
      }
      if (mode === 'queue') { json({ queue: { slots: [] } }); return; }
      if (mode === 'history') {
        json({ history: { slots: [...sources.values()].filter(s => s.submits > 0).map(s => ({ nzo_id: s.job, status: s.rejected ? 'Failed' : 'Completed', name: s.title, fail_message: s.rejected ? 'Synthetic rejection: missing articles' : undefined })) } });
        return;
      }
      json({ status: true }); return;
    }
    if (req.method === 'PROPFIND') {
      const src = [...sources.values()].find(s => s.submits > 0 && (path.replace(/\/+$/, '') === s.dir || s.files.some(f => f.path === path)));
      if (!src) { res.writeHead(404); res.end(); return; }
      res.writeHead(207, { 'Content-Type': 'application/xml' });
      res.end('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + propfindEntry(src.dir + '/', true) + src.files.map(f => propfindEntry(f.path, false)).join('') + '</d:multistatus>');
      return;
    }
    if (req.method === 'GET' || req.method === 'HEAD') {
      const file = [...sources.values()].filter(s => s.submits > 0).flatMap(s => s.files).find(f => f.path === path);
      if (file) { serveBytes(req, res, file.media); return; }
    }
    res.writeHead(404); res.end();
  });

  return {
    name: 'nzbdav',
    requests,
    /** Register a movie Source the fake will accept. Returns its NZB link. */
    addMovie(tag, title, media) {
      const dir = `/content/Movies/${title}`;
      sources.set(tag, { tag, title, dir, files: [{ media, path: `${dir}/${tag}.mkv` }], job: `job-${tag}`, submits: 0 });
      return `${base}/${tag}.nzb`;
    },
    /** Register a TV Source: one episode, or a season pack when several. episodes: [{season, episode, media}]. */
    addSeries(tag, title, episodes) {
      const dir = `/content/TV/${title}`;
      const files = episodes.map(e => ({ ...e, path: `${dir}/${title}.S${String(e.season).padStart(2, '0')}E${String(e.episode).padStart(2, '0')}.mkv` }));
      sources.set(tag, { tag, title, dir, files, job: `job-${tag}`, submits: 0 });
      return `${base}/${tag}.nzb`;
    },
    /** Register a Source the Backend accepts then fails (job ends Failed). */
    addRejected(tag, title) {
      const nzb = this.addMovie(tag, title, Buffer.from('unused'));
      sources.get(tag).rejected = true;
      return nzb;
    },
    /** Make the Backend unreachable (true) or reachable again (false). */
    setDown(v) { down = v; },
    // No addNeverReady: KaijuFlow gives NzbDAV no preparation time limit.
    submitsFor(tag) { return sources.get(tag)?.submits ?? 0; },
    /** KaijuFlow settings that point the NzbDAV Backend at this fake. */
    configure(configData) {
      Object.assign(configData, {
        streamingMode: 'nzbdav', indexManager: 'manual',
        nzbdavUrl: base, nzbdavWebdavUrl: base, nzbdavApiKey: 'synthetic-key',
        nzbdavWebdavUser: '', nzbdavWebdavPassword: '', nzbdavMoviesCategory: 'Movies', nzbdavTvCategory: 'TV',
        nzbdavStreamingMethod: 'proxy',
        ultimateFallback: { ...configData.ultimateFallback, enabled: false },
      });
    },
  };
}
