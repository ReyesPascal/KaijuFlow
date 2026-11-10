// KaijuFlow finding 7: TLS certificate checks are on by default. A provider
// with an invalid (here self-signed) certificate is rejected with a clear
// error unless "Verify TLS Certificates" is turned off.
// Run: npm run test:unit
import { test, after, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import tls from 'node:tls';
import fs from 'node:fs';
import type { AddressInfo } from 'node:net';
import express from 'express';
import { connectToUsenet, bindVerifyTlsCertificates } from '../../src/health/index.ts';
import { createHealthCheckRoutes } from '../../src/routes/healthCheck.ts';

const fixture = (name: string) => fs.readFileSync(new URL(`./fixtures/${name}`, import.meta.url));

// --- Fake NNTP server over TLS with a self-signed certificate ---
const nntp = tls.createServer(
  { key: fixture('self-signed-key.pem'), cert: fixture('self-signed-cert.pem') },
  sock => {
    sock.on('error', () => {});
    sock.write('200 fake news ready\r\n');
    let buf = '';
    sock.on('data', d => {
      buf += d.toString();
      const lines = buf.split('\r\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('AUTHINFO USER')) sock.write('381 more\r\n');
        else if (line.startsWith('AUTHINFO PASS')) sock.write('281 ok\r\n');
        else if (line.startsWith('QUIT')) sock.end('205 bye\r\n');
      }
    });
  },
);
nntp.on('tlsClientError', () => {}); // the client hangs up on our bad certificate
await new Promise<void>(resolve => nntp.listen(0, '127.0.0.1', resolve));
const port = (nntp.address() as AddressInfo).port;
const provider = { host: '127.0.0.1', port, useTLS: true, username: 'u', password: 'p' };

// The setting as the server binds it; each test sets the value it needs.
let verify = true;
bindVerifyTlsCertificates(() => verify);

// --- The provider "Test Connection" route, mounted on a throwaway app ---
const app = express();
app.use(express.json());
app.use('/api/health-check', createHealthCheckRoutes({
  getProviders: () => [],
  addProvider: () => { throw new Error('unused'); },
  updateProvider: () => { throw new Error('unused'); },
  deleteProvider: () => {},
  reorderProviders: () => {},
}));
const web = app.listen(0, '127.0.0.1');
await new Promise(resolve => web.once('listening', resolve));
const webPort = (web.address() as AddressInfo).port;

async function testConnection(): Promise<{ status: number; body: { success: boolean; message: string } }> {
  const res = await fetch(`http://127.0.0.1:${webPort}/api/health-check/test`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(provider),
  });
  return { status: res.status, body: (await res.json()) as { success: boolean; message: string } };
}

afterEach(() => { verify = true; });
after(() => { nntp.close(); web.close(); });

test('health checks reject a self-signed certificate by default, with a clear error', async () => {
  await assert.rejects(connectToUsenet(provider), (err: Error) => {
    assert.match(err.message, /TLS certificate check failed/);
    assert.match(err.message, /self-signed/);
    assert.match(err.message, /Verify TLS Certificates/);
    return true;
  });
});

test('health checks connect to a self-signed server when checking is turned off', async () => {
  verify = false;
  const socket = await connectToUsenet(provider);
  assert.equal(socket.destroyed, false);
  socket.destroy();
});

test('Test Connection reports the certificate failure when checking is on', async () => {
  const { status, body } = await testConnection();
  assert.equal(status, 500);
  assert.equal(body.success, false);
  assert.match(body.message, /TLS certificate check failed/);
  assert.match(body.message, /Verify TLS Certificates/);
});

test('Test Connection succeeds against a self-signed server when checking is off', async () => {
  verify = false;
  const { status, body } = await testConnection();
  assert.equal(status, 200);
  assert.equal(body.success, true);
});
