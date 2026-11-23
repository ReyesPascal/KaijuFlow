// Fake AltMount Backend for the Parity suite (contract: docs/kaijuflow/research/ALTMOUNT_INTEGRATION.md, v0.4.0).
// POST /api/nzb/streams (multipart, nzb_url) + GET/HEAD /api/files/stream. Synthetic NZBs and media only.
// Contract: { name, requests[], addMovie(tag,title,media)->nzbUrl, submitsFor(tag), configure(configData) }.
import crypto from 'node:crypto';
import { serveBytes } from './serve-bytes.mjs';
import { fault } from './first-byte-fault.mjs';
import { nzbTag, rarVolumeCheck } from './fake-rar-rules.mjs';
import { scrambledRarSet } from './fake-nntp.mjs';

// A release name ending in one of these is filed by real AltMount v0.4.0 as a folder holding the file.
/**
 * What real AltMount v0.4.0 logged when it refused a Source (Test 2's cancelled
 * record, quoted in ADR 0008; the logs are gone). No text was kept for a bare
 * disc image, only that it failed.
 */
const ALTMOUNT_REFUSALS = {
  'compressed-7z': 'no valid files found in 7zip archive after filtering. Only uncompressed files are supported',
  'scrambled-rar4': 'all files failed validation',
  'disc-image': 'failed (no log text kept)',
};

const VIDEO_EXTS = ['.mkv', '.mp4', '.avi', '.m4v', '.ts', '.m2ts', '.wmv', '.webm', '.mov', '.mpg', '.mpeg'];

export const API_KEY = 'synthetic-altmount-key';
const DOWNLOAD_KEY = crypto.createHash('sha256').update(API_KEY).digest('hex');

export async function createFakeAltmount(listen) {
  const sources = new Map(); // tag -> { tag, title, files[{season,episode,media,path}], queueId, submits, completed }
  const requests = [];
  const submitKinds = []; // 'file' | 'nzb_url' per submit
  const submitFields = []; // { season, episode } per submit (strings as received, or undefined)
  const submitted = []; // tag per accepted submit, in order
  let base = '';
  let down = false;
  let indexerDown = 0; // HTTP status the NZB link answers while the indexer is "down" (0 = serves the NZB)
  const grabs = []; // { tag, asked, answered, closed } per NZB link fetched: the indexer's side of a grab
  const slowGrabs = new Map(); // tag prefix -> ms every NZB link of it waits before answering
  let nextQueueId = 1; // real AltMount queue ids are integers
  const uploads = new Map(); // tag -> uploaded NZB texts
  const volumeOf = new Map(); // first-article id -> real RAR5 volume, for Scrambled RAR sets
  let news = null; // fake news server (useNews): Sources then get NZBs KaijuFlow's health check can read
  let fixture = () => { throw new Error('useNews was given no archive fixtures'); };

  /**
   * With a fake news server: an NZB naming one file, 3 segments, its articles on
   * the news server unless `dead` (articles missing, as on Newshosting in #189).
   */
  const checkableNzb = (tag, fileName, { dead = false } = {}) => {
    const ids = [1, 2, 3].map(n => `${tag}-s${n}@fake`);
    if (!dead) for (const id of ids) news.articles.set(id, Buffer.alloc(200, 0x41));
    const subject = `[1/1] - &quot;${fileName.replace(/&/g, '&amp;')}&quot; yEnc (1/3)`;
    return `<?xml version="1.0" encoding="UTF-8"?>\n<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><head><meta type="kf-tag">${tag}</meta></head>\n` +
      `<file poster="kf@fake" date="1700000000" subject="${subject}"><groups><group>alt.binaries.synthetic</group></groups><segments>` +
      ids.map((id, i) => `<segment bytes="750000" number="${i + 1}">${id}</segment>`).join('') + `</segments></file>\n</nzb>\n`;
  };

  /**
   * With a fake news server: a season pack of loose videos laid out like the
   * edge2020 pack captured in #189 (tests/fixtures/nzbs/season-pack-loose-edge2020.nzb):
   * an obfuscated par2 first, then one file per episode in episode order, 3
   * segments each. The articles of the episodes in `deadEpisodes` are missing.
   */
  const checkablePackNzb = (tag, files, { deadEpisodes = [] } = {}) => {
    const fileXml = (name, idBase, dead, i, total) => {
      const ids = [1, 2, 3].map(n => `${tag}-${idBase}-s${n}@fake`);
      if (!dead) for (const id of ids) news.articles.set(id, Buffer.alloc(200, 0x41));
      const subject = `[${i}/${total}] - &quot;${name.replace(/&/g, '&amp;')}&quot; yEnc (1/3)`;
      return `<file poster="kf@fake" date="1700000000" subject="${subject}"><groups><group>alt.binaries.synthetic</group></groups><segments>` +
        ids.map((id, n) => `<segment bytes="750000" number="${n + 1}">${id}</segment>`).join('') + `</segments></file>\n`;
    };
    const total = files.length + 1;
    return `<?xml version="1.0" encoding="UTF-8"?>\n<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><head><meta type="kf-tag">${tag}</meta></head>\n` +
      fileXml(`${crypto.createHash('md5').update(tag).digest('hex')}.par2`, 'par2', false, 1, total) +
      files.map((f, i) => fileXml(f.path.split('/').pop(), `e${f.episode}`, deadEpisodes.includes(f.episode), i + 2, total)).join('') + `</nzb>\n`;
  };

  base = await listen(async (req, res) => {
    const u = new URL(req.url, 'http://127.0.0.1');
    const path = u.pathname;
    requests.push({ method: req.method, path, range: req.headers.range || null });
    const json = (status, x) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(x)); };

    if (path.endsWith('.nzb')) {
      const tag = path.slice(1, -4);
      const grab = { tag, asked: Date.now(), answered: null };
      grabs.push(grab);
      res.on('finish', () => { grab.answered = Date.now(); });
      res.on('close', () => { if (grab.answered === null) grab.closed = Date.now(); });
      const wait = [...slowGrabs].find(([prefix]) => tag.startsWith(prefix))?.[1];
      if (wait) await new Promise(r => setTimeout(r, wait));
      // A link the indexer does not know (addGone) answers 404, as an indexer does for a removed NZB.
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
      const uploadName = /name="file"; filename="([^"]*)"/.exec(body)?.[1]?.replace(/\.nzb$/i, '');
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
      submitted.push(tag);
      // Real AltMount v0.4.0 (captured in #84): an upload named like a video file is filed as a FOLDER with that name
      // holding the file of the same name. The reply offers the folder, which answers 400 "Cannot stream directory".
      let offered = file.path;
      if (src.files.length === 1 && uploadName && VIDEO_EXTS.some(e => uploadName.toLowerCase().endsWith(e))) {
        offered = `/complete/kaijuflow/${uploadName}`;
        file.folder = offered;
        file.path = `${offered}/${uploadName}`;
      }
      // AltMount v0.4.0 RAR volume rules: a failed queue item, answered like any other.
      if (fileMatch && rarVolumeCheck(fileMatch[1], volumeOf)) return json(500, { error: 'NZB processing failed' });
      // Articles gone from the news server: real AltMount's import probe fails the queue item
      // ("fast-fail segment check failed", #189), answered like any failed item.
      if (news && fileMatch && [...fileMatch[1].matchAll(/<segment\b[^>]*>([^<]+)<\/segment>/g)].some(m => !news.articles.has(m[1]))) {
        return json(500, { error: 'NZB processing failed' });
      }
      // Scripted answer (status + body) for a Source, to exercise AltMount's other error answers.
      if (src.scripted) return json(src.scripted.status, src.scripted.body);
      // Failed queue item: pinned handler answers 500 "NZB processing failed" (not 400/422).
      // A refused Source (addRefused) fails the same way; the reason is only in AltMount's log.
      if (src.rejected || src.refused) return json(500, { error: 'NZB processing failed' });
      // Not ready in time: AltMount answers 408 with the queue ID; the queued work is NOT cancelled.
      if (src.neverReady) { await new Promise(r => setTimeout(r, 300)); return json(408, { error: 'Timeout waiting for stream', details: src.queueId }); }
      const cached = src.completed;
      src.completed = true;
      // Pinned v0.4.0 StremioStreamsResponse: the queue fields sit next to `streams`.
      return json(200, {
        streams: [{
          url: `${base}/api/files/stream?path=${encodeURIComponent(offered)}&download_key=${DOWNLOAD_KEY}`,
          title: src.title, name: 'AltMount',
        }],
        _queue_item_id: src.queueId, _queue_status: src.queueStatus ?? (cached ? 'completed' : 'streamable'), _cached: cached,
      });
    }

    if ((req.method === 'GET' || req.method === 'HEAD') && path === '/api/files/stream') {
      if (u.searchParams.get('download_key') !== DOWNLOAD_KEY) { res.writeHead(401); res.end(); return; }
      const asked = u.searchParams.get('path');
      const done = [...sources.values()].filter(s => s.completed);
      if (done.some(s => s.files.some(f => f.folder && f.folder === asked))) { res.writeHead(400, { 'Content-Type': 'text/plain' }); res.end('Cannot stream directory.'); return; }
      const owner = done.find(s => s.files.some(f => f.path === asked));
      const file = owner?.files.find(f => f.path === asked);
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
    addMovie(tag, title, media, opts = {}) {
      sources.set(tag, { tag, title, files: [{ media, path: `/movies/${title}/${tag}.mkv` }], queueId: nextQueueId++, submits: 0, completed: false });
      if (news) sources.get(tag).nzb = checkableNzb(tag, `${title}.mkv`, opts);
      return `${base}/${tag}.nzb`;
    },
    /**
     * Register a TV Source: one episode, or a season pack when several. episodes: [{season, episode, media, name?}]
     * (name: the file's name without .mkv, as a daily show's pack names its files by aired date; default <title>.SxxEyy).
     * With a news server, opts { dead: true } leaves an episode's articles missing, and a pack's NZB names each
     * episode file, opts { deadEpisodes: [episode numbers] } leaving those episodes' articles missing.
     */
    addSeries(tag, title, episodes, opts = {}) {
      const files = episodes.map(e => ({ ...e, path: `/tv/${title}/${e.name ?? `${title}.S${String(e.season).padStart(2, '0')}E${String(e.episode).padStart(2, '0')}`}.mkv` }));
      sources.set(tag, { tag, title, files, queueId: nextQueueId++, submits: 0, completed: false });
      if (news) sources.get(tag).nzb = files.length > 1 ? checkablePackNzb(tag, files, opts) : checkableNzb(tag, `${title}.mkv`, opts);
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
      // With a news server the parts' later articles and the .nfo and .par2 are there too (the scenario
      // posts the first ones), so the play-time check can sample them and AltMount's probe finds them.
      if (news) {
        for (const p of set.parts) for (const n of [2, 3]) news.articles.set(`${tag}-v${p.volume}-s${n}@fake`, Buffer.alloc(200, 0x41));
        for (const id of [`${tag}-nfo@fake`, `${tag}-par2@fake`]) news.articles.set(id, Buffer.alloc(200, 0x41));
      }
      return nzb;
    },
    /**
     * Register a stored 7z set Source (#193): a real stored 7z split in volumes (tests/fixtures/archives,
     * stored-split.7z.001 to .004, from make.sh), posted as `<title>.7z.001` ... in volume order, each
     * part's real bytes cut into three articles (a 7z keeps its header at the end), every article on
     * the news server. Real AltMount v0.4.0 streams a stored 7z (spec #183, Test 1), so it plays; a
     * compressed one is refused (addRefused).
     */
    addSevenZip(tag, title, media) {
      if (!news) throw new Error('a 7z set Source needs the news server (useNews)');
      const nzb = this.addMovie(tag, title, media);
      const files = [1, 2, 3, 4].map(n => {
        const data = fixture(`stored-split.7z.00${n}`);
        const size = Math.ceil(data.length / 3);
        const segs = [0, 1, 2].map(i => ({ id: `${tag}-p${n}-s${i + 1}@fake`, bytes: data.subarray(i * size, (i + 1) * size) }));
        for (const s of segs) news.articles.set(s.id, s.bytes);
        const subject = `[${n}/4] - &quot;${title}.7z.00${n}&quot; yEnc (1/3)`;
        return `<file poster="kf@fake" date="1700000000" subject="${subject}"><groups><group>alt.binaries.synthetic</group></groups><segments>` +
          segs.map((s, i) => `<segment bytes="${s.bytes.length}" number="${i + 1}">${s.id}</segment>`).join('') + `</segments></file>\n`;
      });
      sources.get(tag).nzb = `<?xml version="1.0" encoding="UTF-8"?>\n<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><head><meta type="kf-tag">${tag}</meta></head>\n` +
        files.join('') + `</nzb>\n`;
      return nzb;
    },
    /** Why real AltMount v0.4.0 would fail this NZB's RAR set, or null if it would accept it. */
    rarVolumeCheck(nzbText) { return rarVolumeCheck(nzbText, volumeOf); },
    /** The NZB texts KaijuFlow uploaded for a Source, in order. */
    uploadedNzbs(tag) { return uploads.get(tag) ?? []; },
    /** Register a Source whose queue item fails. */
    addRejected(tag, title) {
      // With a news server its articles are all there: it passes KaijuFlow's health check and AltMount still fails it.
      const nzb = this.addMovie(tag, title, Buffer.from('unused'));
      sources.get(tag).rejected = true;
      return nzb;
    },
    /**
     * Register a Source real AltMount v0.4.0 refuses (#184, ADR 0009): its queue
     * item fails. `kind`: 'compressed-7z', 'scrambled-rar4' or 'disc-image'.
     * `refusal(tag)` gives the reason AltMount logs.
     */
    addRefused(tag, title, kind) {
      if (!(kind in ALTMOUNT_REFUSALS)) throw new Error(`unknown refusal ${kind}`);
      const nzb = this.addMovie(tag, title, Buffer.from('unused'));
      sources.get(tag).refused = kind;
      if (news && kind === 'scrambled-rar4') {
        // Its RAR parts as posted: a real stored RAR4 set (tests/fixtures/archives) number-named out of
        // volume order, every article on the news server.
        const rar4 = ['rar4-stored.rar', 'rar4-stored.r00', 'rar4-stored.r01', 'rar4-stored.r02'];
        const set = scrambledRarSet({ base: `${tag}-rar4`, parts: 4, startAt: 10, tag, firstArticle: v => fixture(rar4[v]) });
        for (const [id, bytes] of set.articles) news.articles.set(id, bytes);
        for (const p of set.parts) for (const n of [2, 3]) news.articles.set(`${tag}-v${p.volume}-s${n}@fake`, Buffer.alloc(200, 0x41));
        sources.get(tag).nzb = set.nzb;
      } else if (news && kind === 'disc-image') {
        sources.get(tag).nzb = checkableNzb(tag, `${title}.iso`);
      } else if (news) {
        throw new Error(`no NZB for a ${kind} Source with a news server yet`);
      }
      return nzb;
    },
    refusal(tag) { return ALTMOUNT_REFUSALS[sources.get(tag)?.refused] ?? null; },
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
    /** The NZB link of a Source the indexer says is gone: every grab of it answers 404. */
    addGone(tag) { return `${base}/${tag}.nzb`; },
    /** Every NZB link fetched, in order: { tag, asked, answered, closed } (ms; answered null while it waits; closed
     *  when the grab hung up before its answer). */
    grabs,
    /** Make every NZB link whose tag starts with prefix wait ms before answering (0 = answer at once). */
    slowGrabs(prefix, ms) { if (ms > 0) slowGrabs.set(prefix, ms); else slowGrabs.delete(prefix); },
    /**
     * Give every Source registered from now on an NZB KaijuFlow's health check can
     * read, its articles on this fake news server (startFakeNntp). addMovie and
     * addSeries take { dead: true } for a Source whose articles are missing.
     * archiveFixture(name): the bytes of a real archive from tests/fixtures/archives.
     */
    useNews(server, { archiveFixture } = {}) { news = server; if (archiveFixture) fixture = archiveFixture; },
    /** Tags of the Sources KaijuFlow submitted, in submit order. */
    submitted,
    /** Make the Backend unreachable (true) or reachable again (false). */
    setDown(v) { down = v; },
    /** Make the indexer answer this HTTP status for every NZB link (0 = serve the NZB again). */
    setIndexerDown(status) { indexerDown = status; },
    submitsFor(tag) { return sources.get(tag)?.submits ?? 0; },
    /** KaijuFlow settings that point the AltMount Backend at this fake. */
    configure(configData) {
      Object.assign(configData, {
        indexManager: 'manual',
        altmountUrl: base, altmountApiKey: API_KEY, altmountCategory: 'kaijuflow', altmountPrepareTimeout: 20,
        playDeliveryMethod: 'proxy',
        ultimateFallback: { ...configData.ultimateFallback, enabled: false },
      });
    },
  };
}
