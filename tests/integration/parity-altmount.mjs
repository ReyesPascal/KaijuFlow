// Parity suite against fake AltMount. Application modules are real; the Backend is fake.
// Ultimate Fallback off (the owner's setup), proxy delivery.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { createFakeAltmount } from './parity/fake-altmount.mjs';
import { runParity } from './parity/scenarios.mjs';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const load = p => import(root + '/dist/' + p + '.js');
const report = { id: 'INT-PARITY-ALTMOUNT-001', backend: 'altmount', boundaries: ['Fake AltMount prepares at once and answers only the stream route and file route', 'Synthetic media bytes, not decodable video'] };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };
try {
  const backend = await createFakeAltmount(listen);
  const { config, configData } = await load('config/index');
  backend.configure(configData);
  const { default: express } = await import(root + '/node_modules/express/index.js');
  const { handleStream } = await load('nzbdav/streamHandler');
  const { createNzbdavStreamRoutes } = await load('routes/nzbdav');
  const app = express();
  app.use('/stremio/:manifestKey/nzbdav', createNzbdavStreamRoutes({ config, handleStream, getLatestVersions: () => ({ chrome: 'synthetic' }) }));
  const kaijuflow = await listen(app);
  const results = await runParity({ kaijuflow, backend });
  Object.assign(report, { status: results.every(r => r.status === 'pass') ? 'pass' : 'fail', results });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
