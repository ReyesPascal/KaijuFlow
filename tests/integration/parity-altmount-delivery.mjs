// Pipe and direct delivery against fake AltMount (#23). Application modules are real; the Backend is fake.
// Ultimate Fallback off: the list-time route, until #191 (the owner's setup, with the Play-time check, is parity-play-time-check). Checks what the player receives, and that seeking works.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { createFakeAltmount } from './parity/fake-altmount.mjs';
import { API_KEY } from './parity/fake-altmount.mjs';
import { assertBytes } from './parity/bytes.mjs';
import crypto from 'node:crypto';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const load = p => import(root + '/dist/' + p + '.js');
const report = { id: 'INT-ALTMOUNT-DELIVERY-001', backend: 'altmount', boundaries: ['Fake AltMount prepares at once and answers only the stream route and file route', 'Synthetic media bytes, not decodable video'] };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };
try {
  const backend = await createFakeAltmount(listen);
  const { config, configData } = await load('config/index');
  backend.configure(configData);
  const { default: express } = await import(root + '/node_modules/express/index.js');
  const { handleStream } = await load('play/streamHandler');
  const { createPlayStreamRoutes } = await load('routes/play');
  const app = express();
  app.use('/stremio/:manifestKey/play', createPlayStreamRoutes({ config, handleStream, getLatestVersions: () => ({ chrome: 'synthetic' }) }));
  const kaijuflow = await listen(app);
  const mediaFor = tag => Buffer.from(`KaijuFlow delivery bytes for ${tag}: 0123456789abcdefghijklmnopqrstuvwxyz`);
  const downloadKey = crypto.createHash('sha256').update(API_KEY).digest('hex');
  const tileUrl = (nzb, title) => `${kaijuflow}/stremio/synthetic-manifest/play/stream/movie.mkv?t=` + Buffer.from(JSON.stringify({ url: nzb, title, indexer: 'Delivery', ty: 'movie' })).toString('base64url');
  const leaks = text => text.includes(API_KEY) || text.includes(downloadKey) || /download_key/i.test(text);
  const headerText = h => [...h.entries()].map(([k, v]) => `${k}: ${v}`).join('\n');
  const results = [];
  const check = async (id, fn) => { const before = backend.requests.length; try { await fn(); results.push({ id, status: 'pass' }); } catch (e) { results.push({ id, status: 'fail', error: String(e), requests: backend.requests.slice(before).slice(-15) }); } };
  const get = (url, range) => fetch(url, { headers: range ? { Range: range } : {}, redirect: 'manual', signal: AbortSignal.timeout(20000) });

  for (const method of ['proxy', 'pipe']) {
    await check(`${method}-plays-seeks-hides-key`, async () => {
      configData.playDeliveryMethod = method;
      const media = mediaFor(method), title = `KaijuFlow.Delivery.${method}.2026.1080p.WEB-DL.H264`;
      const url = tileUrl(backend.addMovie(method, title, media), title);
      const full = await get(url);
      assert.equal(full.status, 200, 'should play inline, not redirect');
      assertBytes(Buffer.from(await full.arrayBuffer()), media);
      assert.ok(!leaks(headerText(full.headers)), 'key must not appear in headers the player receives');
      const seek = await get(url, 'bytes=10-29');
      assert.equal(seek.status, 206, 'seek should return 206');
      assertBytes(Buffer.from(await seek.arrayBuffer()), media.subarray(10, 30));
      assert.equal(seek.headers.get('content-range'), `bytes 10-29/${media.length}`);
      assert.ok(!leaks(headerText(seek.headers)), 'key must not appear in seek headers');
      assert.equal(backend.submitsFor(method), 1, 'seek should not resubmit');
    });
  }

  await check('direct-redirects-to-file-route-and-seeks', async () => {
    configData.playDeliveryMethod = 'direct';
    const media = mediaFor('direct'), title = 'KaijuFlow.Delivery.direct.2026.1080p.WEB-DL.H264';
    const url = tileUrl(backend.addMovie('direct', title, media), title);
    const r = await get(url);
    assert.equal(r.status, 302, 'direct should redirect');
    const loc = r.headers.get('location');
    assert.match(loc, /\/api\/files\/stream\?/, 'should point at AltMount file route');
    const full = await get(loc);
    assert.equal(full.status, 200);
    assertBytes(Buffer.from(await full.arrayBuffer()), media);
    const seek = await get(loc, 'bytes=10-29');
    assert.equal(seek.status, 206, 'seeking works on the direct link');
    assertBytes(Buffer.from(await seek.arrayBuffer()), media.subarray(10, 30));
    // A second tile request (player seek/probe) still redirects, and stays Backend-correct.
    const again = await get(url);
    assert.equal(again.status, 302);
    assert.equal(backend.submitsFor('direct'), 1);
  });

  await check('proxy-default-for-unset-method', async () => {
    configData.playDeliveryMethod = 'proxy';
    const media = mediaFor('dflt'), title = 'KaijuFlow.Delivery.dflt.2026.1080p.WEB-DL.H264';
    const r = await get(tileUrl(backend.addMovie('dflt', title, media), title));
    assert.equal(r.status, 200);
  });
  Object.assign(report, { status: results.every(r => r.status === 'pass') ? 'pass' : 'fail', results });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
