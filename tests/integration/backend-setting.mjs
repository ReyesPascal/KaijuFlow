// Backend setting (#18): migration of an old config, save + reload, AltMount "test connection".
// Real config/settings/test routes over HTTP; the Backend is a fake AltMount on loopback.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const report = { id: 'INT-BACKEND-SETTING-001', boundaries: ['Fake AltMount answers only POST /api/nzb/streams', 'Fabricated keys'] };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };
const configFile = root + '/config/config.json';
const diskConfig = () => JSON.parse(fs.readFileSync(configFile, 'utf8'));
try {
  // An install from before the Backend setting.
  const old = { indexers: [], cacheEnabled: true, cacheTTL: 9000, streamingMode: 'nzbdav', indexManager: 'newznab',
    nzbdavUrl: 'http://nzbdav.example:3000', nzbdavApiKey: 'old-nzbdav-key', nzbdavWebdavUrl: 'http://nzbdav.example:8080',
    nzbdavWebdavUser: 'wu', nzbdavWebdavPassword: 'wp', nzbdavMoviesCategory: 'M', nzbdavTvCategory: 'T', nzbdavStreamingMethod: 'direct' };
  fs.mkdirSync(root + '/config', { recursive: true });
  fs.writeFileSync(configFile, JSON.stringify(old));

  const GOOD = 'good-key';
  let mode = 'ok';
  const fake = await listen((req, res) => {
    if (req.method !== 'POST' || req.url !== '/api/nzb/streams') { res.statusCode = 404; return res.end('not found'); }
    req.resume();
    if (req.headers['x-api-key'] !== GOOD) { res.statusCode = 401; return res.end('{"error":"unauthorized"}'); }
    if (mode === 'integration-off') { res.statusCode = 503; return res.end('{"error":"Stremio integration is disabled"}'); }
    res.statusCode = 400; res.setHeader('Content-Type', 'application/json'); res.end('{"error":"file or nzb_url is required"}');
  });
  const dead = 'http://127.0.0.1:1';

  const { config, configData } = await import(root + '/dist/config/index.js');
  const { updateSettings } = await import(root + '/dist/config/index.js');
  const { createSettingsRoutes } = await import(root + '/dist/routes/settings.js');
  const { createNzbdavRoutes } = await import(root + '/dist/routes/nzbdav.js');
  const { default: express } = await import(root + '/node_modules/express/index.js');
  const app = express();
  app.use(express.json());
  const noop = () => {};
  app.use('/api', createSettingsRoutes({ config, updateSettings, fetchLatestVersions: async () => {}, getLatestVersions: () => ({ chrome: 'synthetic', prowlarr: 's', sabnzbd: 's' }), testProxyConnection: async () => ({}), clearSearchCache: noop }));
  app.use('/api/nzbdav', createNzbdavRoutes({ config, getCacheStats: () => ({}), clearStreamCache: noop, clearReadyCache: noop, clearFailedCache: noop, deleteCacheEntry: noop, getCacheEntries: () => [], getLatestVersions: () => ({ chrome: 'synthetic' }) }));
  const kf = await listen(app);
  const call = async (method, path, body) => {
    const r = await fetch(kf + path, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    return { status: r.status, json: await r.json() };
  };

  const checks = [];
  const check = async (name, fn) => { try { await fn(); checks.push({ name, status: 'pass' }); } catch (e) { checks.push({ name, status: 'fail', error: String(e?.message || e) }); } };

  await check('old config migrates to Backend nzbdav and keeps every NzbDAV setting', async () => {
    const d = diskConfig();
    assert.equal(d.backend, 'nzbdav');
    for (const [k, v] of Object.entries(old)) assert.deepEqual(d[k], v, k);
    const { json } = await call('GET', '/api/config');
    assert.equal(json.backend, 'nzbdav');
    assert.equal(json.altmountCategory, 'kaijuflow');
    assert.equal(json.nzbdavUrl, old.nzbdavUrl);
  });

  await check('Backend and AltMount settings save to disk; NzbDAV settings untouched', async () => {
    const put = await call('PUT', '/api/settings', { backend: 'altmount', altmountUrl: fake, altmountApiKey: GOOD, altmountCategory: 'kf', altmountPrepareTimeout: 120 });
    assert.equal(put.status, 200);
    assert.equal(put.json.backend, 'altmount');
    const d = diskConfig();
    assert.equal(d.backend, 'altmount');
    assert.equal(d.altmountUrl, fake); assert.equal(d.altmountCategory, 'kf'); assert.equal(d.altmountPrepareTimeout, 120);
    for (const [k, v] of Object.entries(old)) assert.deepEqual(d[k], v, k);
    const { json } = await call('GET', '/api/config');
    assert.equal(json.altmountApiKey, GOOD);
    assert.equal(json.altmountPrepareTimeout, 120);
  });

  await check('an invalid Backend is rejected', async () => {
    const r = await call('PUT', '/api/settings', { backend: 'bogus' });
    assert.equal(r.status, 400);
    assert.equal(diskConfig().backend, 'altmount');
  });

  await check('test connection: saved AltMount settings succeed', async () => {
    const r = await call('POST', '/api/nzbdav/test', {});
    assert.equal(r.status, 200); assert.match(r.json.message, /successful/i);
  });
  await check('test connection: wrong key is a clear error', async () => {
    const r = await call('POST', '/api/nzbdav/test', { backend: 'altmount', altmountUrl: fake, altmountApiKey: 'bad' });
    assert.equal(r.status, 502); assert.match(r.json.message, /API key/);
    assert.ok(!r.json.message.includes('bad-secret'));
  });
  await check('test connection: AltMount down is a clear error', async () => {
    const r = await call('POST', '/api/nzbdav/test', { backend: 'altmount', altmountUrl: dead, altmountApiKey: GOOD });
    assert.equal(r.status, 500); assert.match(r.json.message, /not reachable/);
  });
  await check('test connection: Stremio integration off is a clear error', async () => {
    mode = 'integration-off';
    const r = await call('POST', '/api/nzbdav/test', { backend: 'altmount', altmountUrl: fake, altmountApiKey: GOOD });
    mode = 'ok';
    assert.equal(r.status, 502); assert.match(r.json.message, /Stremio integration is turned off/);
  });
  await check('test connection: missing URL or key is a clear error', async () => {
    const a = await call('POST', '/api/nzbdav/test', { backend: 'altmount', altmountUrl: '', altmountApiKey: GOOD });
    assert.equal(a.status, 400); assert.match(a.json.message, /URL is required/);
    const b = await call('POST', '/api/nzbdav/test', { backend: 'altmount', altmountUrl: fake, altmountApiKey: '' });
    assert.equal(b.status, 400); assert.match(b.json.message, /API key is required/);
  });
  await check('switching back to NzbDAV restores NzbDAV checks', async () => {
    await call('PUT', '/api/settings', { backend: 'nzbdav' });
    assert.equal(diskConfig().backend, 'nzbdav');
    const r = await call('POST', '/api/nzbdav/test', { url: dead });
    assert.match(r.json.message, /NZBDav|Connection failed/);
  });
  await check('streamingMode stremio is unchanged by Backend settings', async () => {
    const r = await call('PUT', '/api/settings', { streamingMode: 'stremio', backend: 'altmount' });
    assert.equal(r.json.streamingMode, 'stremio');
    assert.equal(diskConfig().streamingMode, 'stremio');
  });
  Object.assign(report, { status: checks.every(c => c.status === 'pass') ? 'pass' : 'fail', results: checks });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
