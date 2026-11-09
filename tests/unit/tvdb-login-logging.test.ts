// KaijuFlow finding 8: a failed TVDB login logs that it failed and the status
// code, never any of the response body. A successful login logs what it
// always did.
// Run: npm run test:unit
import { test, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import axios from 'axios';
import { configData } from '../../src/config/index.ts';
import { captureLogs } from './capture-logs.ts';
import { detectRemake, clearTvdbToken } from '../../src/idResolver.ts';

// Text that must never reach the logs.
const SECRET = 'LEAKED-RESPONSE-CONTENT';

// --- Fake TVDB server; each test sets the login reply it needs ---
let loginReply: { status: number; body: unknown } = { status: 200, body: {} };
const tvdb = http.createServer((req, res) => {
  req.resume();
  req.on('end', () => {
    const reply = req.url === '/v4/login'
      ? loginReply
      : { status: 200, body: { data: [] } }; // search after a good login: no results
    res.writeHead(reply.status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(reply.body));
  });
});
await new Promise<void>(resolve => tvdb.listen(0, '127.0.0.1', resolve));
const tvdbBase = `http://127.0.0.1:${(tvdb.address() as AddressInfo).port}`;

// Send the resolver's TVDB calls to the fake server instead of the real one,
// or to a port nothing listens on when a test wants a network error.
let unreachable = false;
const interceptor = axios.interceptors.request.use(cfg => {
  cfg.url = cfg.url?.replace('https://api4.thetvdb.com', unreachable ? 'http://127.0.0.1:1' : tvdbBase);
  return cfg;
});

const savedSearchConfig = configData.searchConfig;
configData.searchConfig = { ...savedSearchConfig, includeSeasonPacks: true, tvdbApiKey: 'test-key' };

let n = 0;
beforeEach(() => clearTvdbToken());
// A fresh title each time so detectRemake's cache never skips the login.
const lookUp = () => detectRemake(`Some Show ${++n}`);

after(() => {
  axios.interceptors.request.eject(interceptor);
  configData.searchConfig = savedSearchConfig;
  tvdb.close();
});

test('a 200 login reply without a token logs the failure and status, no body', async () => {
  loginReply = { status: 200, body: { status: 'failure', message: SECRET, data: { note: SECRET } } };
  const logs = await captureLogs(lookUp);
  assert.match(logs, /TVDB login failed/);
  assert.match(logs, /200/);
  assert.doesNotMatch(logs, new RegExp(SECRET));
  assert.doesNotMatch(logs, /failure/);
});

test('a rejected login (401) logs the failure and status, no body', async () => {
  loginReply = { status: 401, body: { status: 'failure', message: SECRET } };
  const logs = await captureLogs(lookUp);
  assert.match(logs, /TVDB login failed/);
  assert.match(logs, /401/);
  assert.doesNotMatch(logs, new RegExp(SECRET));
});

test('a login that never reaches TVDB logs the failure as a network error', async () => {
  unreachable = true;
  try {
    const logs = await captureLogs(lookUp);
    assert.match(logs, /TVDB login failed \(network error: /);
  } finally {
    unreachable = false;
  }
});

test('a successful login logs only what it did before', async () => {
  loginReply = { status: 200, body: { status: 'success', data: { token: SECRET } } };
  const logs = await captureLogs(lookUp);
  const loginLines = logs.split('\n').filter(l => /TVDB token|TVDB login/.test(l));
  assert.deepEqual(loginLines, [
    '🔗 Requesting new TVDB token...',
    '🔗 TVDB token obtained successfully',
  ]);
  assert.doesNotMatch(logs, new RegExp(SECRET));
});
