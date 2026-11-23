// Parity suite for the Play-time check (#190, spec #183): KaijuFlow with its fallback on, the owner's setup,
// in the play-time world (parity/play-time-world.mjs). Application modules are real; indexer, news server and
// Backend are fake.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { createPlayTimeWorld, PLAY_TIME_BOUNDARIES } from './parity/play-time-world.mjs';
import { runPlayTimeParity, playTimeScenarios } from './parity/play-time-scenarios.mjs';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const report = { id: 'INT-PARITY-PLAY-TIME-CHECK-001', backend: 'altmount', boundaries: PLAY_TIME_BOUNDARIES };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };

try {
  const w = await createPlayTimeWorld({ root, listen });
  const results = await runPlayTimeParity(w, playTimeScenarios);
  Object.assign(report, { status: results.every(r => r.status === 'pass') ? 'pass' : 'fail', results });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
