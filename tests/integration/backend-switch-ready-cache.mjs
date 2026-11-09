// Ready entries record the Backend that made them and are ignored when another Backend is active.
// Real config, real stream route and prepare pipeline; both Backends are fakes.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { createFakeAltmount } from './parity/fake-altmount.mjs';
import { createFakeNzbdav } from './parity/fake-nzbdav.mjs';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const load = p => import(root + '/dist/' + p + '.js');
const report = { id: 'INT-BACKEND-SWITCH-READY-001', boundaries: ['Fake AltMount and fake NzbDAV, synthetic media bytes'] };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };
const media = Buffer.from('KaijuFlow backend switch bytes 0123456789abcdefghijklmnopqrstuvwxyz');
const title = 'KaijuFlow.Switch.Movie.2026.1080p.WEB-DL.H264';
try {
  const alt = await createFakeAltmount(listen);
  const dav = await createFakeNzbdav(listen);
  const { config, configData } = await load('config/index');
  dav.configure(configData);
  alt.configure(configData); // sets backend=altmount and AltMount settings; NzbDAV settings stay
  const altNzb = alt.addMovie('sw', title, media);
  const davNzb = dav.addMovie('sw', title, media);
  const { default: express } = await import(root + '/node_modules/express/index.js');
  const { handleStream, prepareStream } = await load('nzbdav/streamHandler');
  const { findReadyStream, getCacheEntries } = await load('nzbdav/streamCache');
  const { buildNzbdavConfig } = await load('nzbdav/utils');
  const { createNzbdavStreamRoutes } = await load('routes/nzbdav');
  const app = express();
  app.use('/stremio/:manifestKey/nzbdav', createNzbdavStreamRoutes({ config, handleStream, getLatestVersions: () => ({ chrome: 'synthetic' }) }));
  const kaijuflow = await listen(app);
  const play = async nzb => {
    const t = Buffer.from(JSON.stringify({ url: nzb, title, indexer: 'Switch', ty: 'movie' })).toString('base64url');
    const res = await fetch(`${kaijuflow}/stremio/synthetic-manifest/nzbdav/stream/movie.mkv?t=${t}`, { signal: AbortSignal.timeout(20000) });
    return { status: res.status, body: Buffer.from(await res.arrayBuffer()) };
  };

  // 1. AltMount plays and the ready entry is tagged AltMount.
  let r = await play(altNzb);
  assert.equal(r.status, 200); assert.deepEqual(r.body, media);
  assert.equal(alt.submitsFor('sw'), 1);
  assert.ok(findReadyStream(altNzb, title, undefined, 'altmount'), 'ready entry should be found for AltMount');
  assert.equal(findReadyStream(altNzb, title, undefined, 'nzbdav'), null, 'ready entry must not count for NzbDAV');
  assert.equal(getCacheEntries().ready.length, 1);

  // 2. Re-preparing the same Source on AltMount reuses the entry: no second upload.
  const again = await prepareStream(altNzb, title, buildNzbdavConfig());
  assert.equal(again.videoPath, findReadyStream(altNzb, title, undefined, 'altmount').videoPath);
  assert.equal(alt.submitsFor('sw'), 1, 'reuse must not upload again');

  // 3. Switch to NzbDAV: the AltMount entry is ignored, and NzbDAV plays through its own Backend.
  configData.backend = 'nzbdav';
  assert.equal(getCacheEntries().ready.length, 0, 'AltMount entries are hidden while NzbDAV is active');
  r = await play(altNzb); // same Source link; the fake NzbDAV does not know it
  assert.notEqual(r.status === 200 && r.body.equals(media), true, 'must not serve the AltMount link under NzbDAV');
  r = await play(davNzb);
  assert.equal(r.status, 200); assert.deepEqual(r.body, media);
  assert.equal(dav.submitsFor('sw'), 1);
  assert.equal(alt.submitsFor('sw'), 1, 'AltMount untouched while NzbDAV is active');

  // 4. Switch back: the AltMount entry is valid again and still no second upload.
  configData.backend = 'altmount';
  assert.equal(getCacheEntries().ready.length, 1);
  await prepareStream(altNzb, title, buildNzbdavConfig());
  assert.equal(alt.submitsFor('sw'), 1);
  Object.assign(report, { status: 'pass' });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
