// KaijuFlow finding 1: self-requests must use 127.0.0.1, not localhost.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { getSelfUrl } from '../../src/utils/selfUrl.ts';

test('getSelfUrl uses IPv4 loopback and the given port', () => {
  assert.equal(getSelfUrl(1337), 'http://127.0.0.1:1337');
  assert.equal(getSelfUrl('8080'), 'http://127.0.0.1:8080');
});

test('getSelfUrl defaults to PORT env, then 1337', () => {
  const saved = process.env.PORT;
  try {
    delete process.env.PORT;
    assert.equal(getSelfUrl(), 'http://127.0.0.1:1337');
    process.env.PORT = '4242';
    assert.equal(getSelfUrl(), 'http://127.0.0.1:4242');
  } finally {
    if (saved === undefined) delete process.env.PORT; else process.env.PORT = saved;
  }
});

test('a server listening on IPv4 only is reachable at getSelfUrl', async () => {
  // Same shape as the failing container: nothing listens on ::1.
  const server = http.createServer((_req, res) => res.end('ok'));
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as { port: number }).port;
  try {
    const res = await fetch(`${getSelfUrl(port)}/ping`);
    assert.equal(res.status, 200);
    assert.equal(await res.text(), 'ok');
  } finally {
    server.close();
  }
});

test('self-request call sites use getSelfUrl, not localhost', () => {
  const files = [
    'src/addon/healthCheckCoordinator.ts',
    'src/addon/index.ts',
    'src/addon/streamBuilder.ts',
  ];
  for (const f of files) {
    const src = readFileSync(f, 'utf8');
    assert.ok(src.includes('getSelfUrl('), `${f} should call getSelfUrl()`);
    assert.ok(!/http:\/\/localhost:\$\{process\.env\.PORT/.test(src), `${f} still builds a localhost self-URL`);
    assert.ok(!src.includes("'http://localhost:1337'"), `${f} still has a localhost:1337 fallback`);
  }
});
