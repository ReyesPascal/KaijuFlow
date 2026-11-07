import assert from 'node:assert/strict';
import net from 'node:net';
import dgram from 'node:dgram';
import dns from 'node:dns/promises';
import http from 'node:http';
import os from 'node:os';

assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
async function deniedTCP(host, family) {
  await new Promise((resolve, reject) => {
    const s = net.createConnection({ host, port: 443, family, timeout: 1500 });
    s.once('connect', () => { s.destroy(); reject(new Error('EGRESS ALLOWED: '+host)); });
    s.once('error', e => ['ENETUNREACH','EHOSTUNREACH','EADDRNOTAVAIL','ENETDOWN'].includes(e.code) ? resolve() : reject(e));
    s.once('timeout', () => { s.destroy(); reject(new Error('TCP probe timed out without routing-denial proof')); });
  });
}
await deniedTCP('192.0.2.1', 4);
await deniedTCP('2001:db8::1', 6);
await new Promise((resolve, reject) => {
  const s = dgram.createSocket('udp4');
  s.connect(53, '1.1.1.1', e => {
    s.close();
    e && ['ENETUNREACH','EHOSTUNREACH','ENETDOWN'].includes(e.code) ? resolve() : reject(new Error('UDP DNS egress was not denied: '+String(e)));
  });
});
await assert.rejects(
  Promise.race([dns.lookup('a4-kaijuflow-no-record.invalid'),
    new Promise((_, reject) => setTimeout(() => reject(new Error('DNS did not fail promptly')), 4000))])
);
const server = http.createServer((_req,res) => res.end('synthetic-loopback'));
await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
try {
  const r = await fetch('http://127.0.0.1:'+server.address().port);
  assert.equal(await r.text(),'synthetic-loopback');
} finally { await new Promise(resolve => server.close(resolve)); }
if (process.env.A4_FORCE_FAIL === '1') { console.error('INJECTED GATE DENIAL after successful network probes'); process.exit(77); }
console.log('A4_ISOLATION_GATE_PASS');
