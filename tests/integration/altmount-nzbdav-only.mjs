// NzbDAV-only features with AltMount active (#24): Ultimate Fallback acts as off, library links are dead.
// Real stream route over HTTP; no Backend is contacted by these requests.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const report = { id: 'INT-ALTMOUNT-NZBDAV-ONLY-001', boundaries: ['No Backend is contacted', 'Config switched in memory'] };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };
try {
  const { config, configData } = await import(root + '/dist/config/index.js');
  const { isUltimateFallbackActive, isNzbdavLibraryConfigured } = await import(root + '/dist/nzbdav/utils.js');
  const { default: express } = await import(root + '/node_modules/express/index.js');
  const { handleStream } = await import(root + '/dist/nzbdav/streamHandler.js');
  const { createNzbdavStreamRoutes } = await import(root + '/dist/routes/nzbdav.js');
  const app = express();
  app.use('/stremio/:manifestKey/nzbdav', createNzbdavStreamRoutes({ config, handleStream, getLatestVersions: () => ({ chrome: 'synthetic' }) }));
  const kf = await listen(app);
  const base = kf + '/stremio/synthetic-manifest/nzbdav';
  const tile = o => Buffer.from(JSON.stringify(o)).toString('base64url');
  const get = p => fetch(base + p, { redirect: 'manual', signal: AbortSignal.timeout(5000) });

  Object.assign(configData, { streamingMode: 'nzbdav', nzbdavWebdavUrl: 'http://127.0.0.1:1', nzbdavWebdavUser: 'u',
    ultimateFallback: { enabled: true, whenToResolve: 'on-tile-selection' } });
  const checks = [];
  const check = async (name, fn) => { try { await fn(); checks.push({ name, status: 'pass' }); } catch (e) { checks.push({ name, status: 'fail', error: String(e?.message || e) }); } };

  configData.backend = 'nzbdav';
  await check('NzbDAV active: Ultimate Fallback and library are on', async () => {
    assert.equal(isUltimateFallbackActive(), true);
    assert.equal(isNzbdavLibraryConfigured(), true);
    const r = await get('/library-bypass');
    assert.notEqual(r.status, 404);
  });

  configData.backend = 'altmount';
  await check('AltMount active: Ultimate Fallback enabled in settings acts as off', async () => {
    assert.equal(config.ultimateFallback.enabled, true);
    assert.equal(isUltimateFallbackActive(), false);
    assert.equal(isNzbdavLibraryConfigured(), false);
  });
  await check('AltMount active: Ultimate Fallback tile request is refused like any request without a Source', async () => {
    const r = await get('/stream/ultimate-fallback?t=' + tile({ sk: 'synthetic-session' }));
    assert.equal(r.status, 400);
  });
  await check('AltMount active: library stream and library links are dead', async () => {
    assert.equal((await get('/stream/x.mkv?libraryVideoPath=' + encodeURIComponent('/content/movies/x.mkv'))).status, 404);
    for (const p of ['/library-bypass', '/library-delete', '/library-delete-all']) assert.equal((await get(p)).status, 404, p);
  });
  Object.assign(report, { status: checks.every(c => c.status === 'pass') ? 'pass' : 'fail', results: checks });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
