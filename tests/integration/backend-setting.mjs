// AltMount is KaijuFlow's only Backend (#188): an old config naming NzbDAV is read as AltMount,
// its nzbdav* play settings load under the play* names with no streaming-mode key (#200),
// AltMount settings save and reload, AltMount "test connection".
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
  const GOOD = 'good-key';
  let mode = 'ok';
  const fake = await listen((req, res) => {
    if (req.method !== 'POST' || req.url !== '/api/nzb/streams') { res.statusCode = 404; return res.end('not found'); }
    req.resume();
    if (req.headers['x-api-key'] !== GOOD) { res.statusCode = 401; return res.end('{"error":"unauthorized"}'); }
    if (mode === 'integration-off') { res.statusCode = 404; return res.end('{"error":"Stremio integration is disabled"}'); }
    res.statusCode = 400; res.setHeader('Content-Type', 'application/json'); res.end('{"error":"file or nzb_url is required"}');
  });
  const dead = 'http://127.0.0.1:1';

  // An install that chose NzbDAV as its Backend, with AltMount set up beside it.
  const NZBDAV_KEYS = { backend: 'nzbdav', nzbdavUrl: 'http://nzbdav.example:3000', nzbdavApiKey: 'old-nzbdav-key',
    nzbdavWebdavUrl: 'http://nzbdav.example:8080', nzbdavWebdavUser: 'wu', nzbdavWebdavPassword: 'wp',
    nzbdavMoviesCategory: 'M', nzbdavTvCategory: 'T' };
  // Its play settings under their old names (#200), each off its default.
  const OLD_PLAY = { streamingMode: 'nzbdav', nzbdavStreamingMethod: 'direct', nzbdavStreamBufferMB: 64, nzbdavPipeBufferMB: 4, nzbdavCacheTimeouts: false };
  const old = { indexers: [], cacheEnabled: true, cacheTTL: 9000, indexManager: 'newznab',
    altmountUrl: fake, altmountApiKey: GOOD, ...NZBDAV_KEYS, ...OLD_PLAY };
  fs.mkdirSync(root + '/config', { recursive: true });
  fs.writeFileSync(configFile, JSON.stringify(old));

  const { config } = await import(root + '/dist/config/index.js');
  const { updateSettings } = await import(root + '/dist/config/index.js');
  const { createSettingsRoutes } = await import(root + '/dist/routes/settings.js');
  const { createPlayApiRoutes } = await import(root + '/dist/routes/play.js');
  const { default: express } = await import(root + '/node_modules/express/index.js');
  const app = express();
  app.use(express.json());
  const noop = () => {};
  app.use('/api', createSettingsRoutes({ config, updateSettings, fetchLatestVersions: async () => {}, getLatestVersions: () => ({ chrome: 'synthetic', prowlarr: 's', sabnzbd: 's' }), testProxyConnection: async () => ({}), clearSearchCache: noop }));
  app.use('/api/play', createPlayApiRoutes({ config, getLatestVersions: () => ({ chrome: 'synthetic' }) }));
  const kf = await listen(app);
  const call = async (method, path, body) => {
    const r = await fetch(kf + path, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    return { status: r.status, json: await r.json() };
  };

  const checks = [];
  const check = async (name, fn) => { try { await fn(); checks.push({ name, status: 'pass' }); } catch (e) { checks.push({ name, status: 'fail', error: String(e?.message || e) }); } };

  await check('an old config naming NzbDAV is read as AltMount: test connection reaches AltMount', async () => {
    const r = await call('POST', '/api/play/test', {});
    assert.equal(r.status, 200); assert.match(r.json.message, /successful/i);
  });

  await check('the NzbDAV settings are gone from disk and from the config the UI reads; the rest is kept', async () => {
    const d = diskConfig();
    for (const k of Object.keys(NZBDAV_KEYS)) assert.equal(d[k], undefined, k);
    assert.equal(d.cacheTTL, 9000);
    assert.equal(d.altmountUrl, fake); assert.equal(d.altmountApiKey, GOOD);
    const { json } = await call('GET', '/api/config');
    for (const k of Object.keys(NZBDAV_KEYS)) assert.equal(json[k], undefined, k);
    assert.equal(json.altmountCategory, 'kaijuflow');
  });

  await check('old play settings load under the play* names, with no streaming-mode key (#200)', async () => {
    const d = diskConfig();
    for (const k of Object.keys(OLD_PLAY)) assert.equal(d[k], undefined, k);
    assert.equal(d.playDeliveryMethod, 'direct'); assert.equal(d.playStreamBufferMB, 64);
    assert.equal(d.playPipeBufferMB, 4); assert.equal(d.playCacheTimeouts, false);
    const { json } = await call('GET', '/api/config');
    for (const k of Object.keys(OLD_PLAY)) assert.equal(json[k], undefined, k);
    assert.equal(json.playDeliveryMethod, 'direct'); assert.equal(json.playStreamBufferMB, 64);
    assert.equal(json.playPipeBufferMB, 4); assert.equal(json.playCacheTimeouts, false);
  });

  await check('AltMount settings save to disk and reload', async () => {
    const put = await call('PUT', '/api/settings', { altmountUrl: fake, altmountApiKey: GOOD, altmountCategory: 'kf', altmountPrepareTimeout: 120 });
    assert.equal(put.status, 200);
    const d = diskConfig();
    assert.equal(d.altmountUrl, fake); assert.equal(d.altmountCategory, 'kf'); assert.equal(d.altmountPrepareTimeout, 120);
    const { json } = await call('GET', '/api/config');
    assert.equal(json.altmountApiKey, GOOD);
    assert.equal(json.altmountPrepareTimeout, 120);
  });

  await check('asking for NzbDAV changes nothing: AltMount stays the Backend', async () => {
    await call('PUT', '/api/settings', { backend: 'nzbdav', nzbdavUrl: dead });
    const d = diskConfig();
    assert.equal(d.backend, undefined); assert.equal(d.nzbdavUrl, undefined);
    const r = await call('POST', '/api/play/test', {});
    assert.equal(r.status, 200); assert.match(r.json.message, /successful/i);
  });

  await check('test connection: wrong key is a clear error', async () => {
    const r = await call('POST', '/api/play/test', { altmountUrl: fake, altmountApiKey: 'bad' });
    assert.equal(r.status, 502); assert.match(r.json.message, /API key/);
    assert.ok(!r.json.message.includes('bad-secret'));
  });
  await check('test connection: AltMount down is a clear error', async () => {
    const r = await call('POST', '/api/play/test', { altmountUrl: dead, altmountApiKey: GOOD });
    assert.equal(r.status, 500); assert.match(r.json.message, /not reachable/);
  });
  await check('test connection: Stremio integration off is a clear error', async () => {
    mode = 'integration-off';
    const r = await call('POST', '/api/play/test', { altmountUrl: fake, altmountApiKey: GOOD });
    mode = 'ok';
    assert.equal(r.status, 502); assert.match(r.json.message, /Stremio integration is turned off/);
  });
  await check('test connection: missing URL or key is a clear error', async () => {
    const a = await call('POST', '/api/play/test', { altmountUrl: '', altmountApiKey: GOOD });
    assert.equal(a.status, 400); assert.match(a.json.message, /URL is required/);
    const b = await call('POST', '/api/play/test', { altmountUrl: fake, altmountApiKey: '' });
    assert.equal(b.status, 400); assert.match(b.json.message, /API key is required/);
  });
  await check('the NZB database card is gone, and so are its cache routes (#188)', async () => {
    for (const [method, path] of [['GET', '/api/play/cache'], ['DELETE', '/api/play/cache'], ['GET', '/api/play/cache/entries'],
      ['DELETE', '/api/play/cache/ready'], ['DELETE', '/api/play/cache/failed'], ['DELETE', '/api/play/cache/entry?key=x']]) {
      const r = await fetch(kf + path, { method });
      await r.arrayBuffer();
      assert.equal(r.status, 404, `${method} ${path}`);
    }
  });
  await check('the streaming-mode choice is gone: asking for it saves nothing (#200)', async () => {
    const r = await call('PUT', '/api/settings', { streamingMode: 'stremio' });
    assert.equal(r.status, 200);
    assert.equal(r.json.streamingMode, undefined);
    assert.equal(diskConfig().streamingMode, undefined);
  });
  Object.assign(report, { status: checks.every(c => c.status === 'pass') ? 'pass' : 'fail', results: checks });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
