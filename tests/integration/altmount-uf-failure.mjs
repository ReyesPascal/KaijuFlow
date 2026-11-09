// Gap left by #24: Ultimate Fallback enabled in settings + AltMount active.
// A failed Source plays the failure video and no fallback-group candidate is tried.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { createFakeAltmount } from './parity/fake-altmount.mjs';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const load = p => import(root + '/dist/' + p + '.js');
const report = { id: 'INT-ALTMOUNT-UF-FAILURE-001', boundaries: ['Fake AltMount rejects one Source and would accept another', 'Synthetic media bytes'] };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };
try {
  const backend = await createFakeAltmount(listen);
  const { config, configData } = await load('config/index');
  backend.configure(configData);
  configData.ultimateFallback = { ...configData.ultimateFallback, enabled: true, userPickFallback: 'fallback-chain', whenToResolve: 'on-tile-selection' };
  const { isUltimateFallbackActive } = await load('nzbdav/utils');
  const { createFallbackGroup } = await load('nzbdav/fallbackManager');
  const { default: express } = await import(root + '/node_modules/express/index.js');
  const { handleStream } = await load('nzbdav/streamHandler');
  const { createNzbdavStreamRoutes } = await load('routes/nzbdav');
  const app = express();
  app.use('/stremio/:manifestKey/nzbdav', createNzbdavStreamRoutes({ config, handleStream, getLatestVersions: () => ({ chrome: 'synthetic' }) }));
  const kf = await listen(app);

  const badTitle = 'KaijuFlow.UF.Bad.2026.1080p.WEB-DL.H264', goodTitle = 'KaijuFlow.UF.Good.2026.1080p.WEB-DL.H264';
  const media = Buffer.from('KaijuFlow UF good bytes 0123456789');
  const badNzb = backend.addRejected('bad', badTitle);
  const goodNzb = backend.addMovie('good', goodTitle, media);
  createFallbackGroup('synthetic-group', [
    { nzbUrl: badNzb, title: badTitle, indexerName: 'Parity' },
    { nzbUrl: goodNzb, title: goodTitle, indexerName: 'Parity' },
  ], 'movie');
  const t = Buffer.from(JSON.stringify({ url: badNzb, title: badTitle, indexer: 'Parity', ty: 'movie', fbg: 'synthetic-group', idx: 0 })).toString('base64url');
  const checks = [];
  const check = async (name, fn) => { try { await fn(); checks.push({ name, status: 'pass' }); } catch (e) { checks.push({ name, status: 'fail', error: String(e?.message || e) }); } };
  await check('UF enabled in settings but off under AltMount', async () => {
    assert.equal(configData.ultimateFallback.enabled, true);
    assert.equal(isUltimateFallbackActive(), false);
  });
  await check('failed Source plays the failure video; no fallback-group candidate is tried', async () => {
    const res = await fetch(`${kf}/stremio/synthetic-manifest/nzbdav/stream/movie.mkv?t=${t}`, { signal: AbortSignal.timeout(20000) });
    const body = Buffer.from(await res.arrayBuffer());
    assert.equal(res.status, 200);
    assert.equal(res.headers.get('content-type'), 'video/mp4');
    assert.ok(body.length > media.length);
    assert.equal(backend.submitsFor('bad'), 1);
    assert.equal(backend.submitsFor('good'), 0, 'fallback candidate must not be tried');
  });
  Object.assign(report, { status: checks.every(c => c.status === 'pass') ? 'pass' : 'fail', results: checks });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
