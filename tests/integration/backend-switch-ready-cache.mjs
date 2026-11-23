// AltMount is the only Backend (#188): ready entries NzbDAV left in the saved ready cache
// (untagged ones from before Backends, and ones tagged nzbdav) are never served; AltMount
// prepares the Source and its own entry is reused.
// Real config, real stream route and prepare pipeline; the Backend is a fake AltMount.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { createFakeAltmount } from './parity/fake-altmount.mjs';
import { assertBytes } from './parity/bytes.mjs';
import { useFakeNews } from './parity/fake-nntp.mjs';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const load = p => import(root + '/dist/' + p + '.js');
const report = { id: 'INT-BACKEND-SWITCH-READY-001', boundaries: ['Fake AltMount, synthetic media bytes', 'Saved NzbDAV ready entries written as fixtures'] };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };
const media = Buffer.from('KaijuFlow backend switch bytes 0123456789abcdefghijklmnopqrstuvwxyz');
try {
  const alt = await createFakeAltmount(listen);
  // The config loads before the play modules (which read the ready cache written below).
  const { config, configData } = await load('config/index');
  alt.configure(configData);
  // Every Source is checked when it is played (#191): the fake news server holds their articles.
  alt.useNews(await useFakeNews(configData, config));
  const old = { title: 'KaijuFlow.Old.Movie.2026.1080p.WEB-DL.H264', tag: 'old' };
  const tagged = { title: 'KaijuFlow.Tagged.Movie.2026.1080p.WEB-DL.H264', tag: 'tagged' };
  for (const s of [old, tagged]) s.nzb = alt.addMovie(s.tag, s.title, media);
  // What NzbDAV left on disk: WebDAV paths AltMount never had.
  const entry = (s, backend) => ({ data: { nzoId: 'nzbdav-job', videoPath: `/content/Movies/${s.title}/${s.tag}.mkv`, videoSize: media.length },
    indexerName: 'Switch', createdAt: Date.now(), expiresAt: Date.now() + 3_600_000, ...(backend ? { backend } : {}) });
  fs.mkdirSync(root + '/config', { recursive: true });
  fs.writeFileSync(root + '/config/healthy-nzbs.json', JSON.stringify({
    [`${old.nzb}::${old.title}`]: entry(old),
    [`${tagged.nzb}::${tagged.title}`]: entry(tagged, 'nzbdav'),
  }));

  const { default: express } = await import(root + '/node_modules/express/index.js');
  const { handleStream, prepareStream } = await load('play/streamHandler');
  const { findReadyStream, getCacheEntries } = await load('play/streamCache');
  const { createPlayStreamRoutes } = await load('routes/play');
  const app = express();
  app.use('/stremio/:manifestKey/play', createPlayStreamRoutes({ config, handleStream, getLatestVersions: () => ({ chrome: 'synthetic' }) }));
  const kaijuflow = await listen(app);
  const play = async s => {
    const t = Buffer.from(JSON.stringify({ url: s.nzb, title: s.title, indexer: 'Switch', ty: 'movie' })).toString('base64url');
    const res = await fetch(`${kaijuflow}/stremio/synthetic-manifest/play/stream/movie.mkv?t=${t}`, { signal: AbortSignal.timeout(20000) });
    return { status: res.status, body: Buffer.from(await res.arrayBuffer()) };
  };

  // 1. NzbDAV's entries are not offered as ready.
  assert.equal(getCacheEntries().ready.length, 0, 'NzbDAV ready entries are hidden');
  for (const s of [old, tagged]) assert.equal(findReadyStream(s.nzb, s.title, undefined), null, s.tag);

  // 2. Each Source plays through AltMount, uploaded once.
  for (const s of [old, tagged]) {
    const r = await play(s);
    assert.equal(r.status, 200, s.tag); assertBytes(r.body, media);
    assert.equal(alt.submitsFor(s.tag), 1, s.tag);
    assert.ok(!findReadyStream(s.nzb, s.title, undefined).videoPath.startsWith('/content/'), 'the ready entry is AltMount\'s now');
  }
  assert.equal(getCacheEntries().ready.length, 2);

  // 3. Re-preparing reuses AltMount's entry: no second upload.
  const again = await prepareStream(old.nzb, old.title);
  assert.equal(again.videoPath, findReadyStream(old.nzb, old.title, undefined).videoPath);
  assert.equal(alt.submitsFor(old.tag), 1, 'reuse must not upload again');
  Object.assign(report, { status: 'pass' });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
