// Each fake Backend must answer in the real Backend's reply layout. Fixtures in
// tests/fixtures/backends/ are replies captured from the real Backends on Brain;
// only the layout (fields, nesting, types) is compared, never values.
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { createFakeAltmount, API_KEY } from '../integration/parity/fake-altmount.mjs';
import { createFakeNzbdav } from '../integration/parity/fake-nzbdav.mjs';

type Shape = string | Shape[] | { [k: string]: Shape };

/** Layout of a JSON value: object keys (sorted), first array element, primitive type. */
function shapeOf(v: unknown): Shape {
  if (Array.isArray(v)) return v.length ? [shapeOf(v[0])] : [];
  if (v && typeof v === 'object') {
    return Object.fromEntries(Object.keys(v).sort().map(k => [k, shapeOf((v as Record<string, unknown>)[k])]));
  }
  return v === null ? 'null' : typeof v;
}

/**
 * Paths where the fake sends something the real Backend does not: a field it
 * lacks or a different type. The fake may leave real fields out.
 */
function extraInFake(fake: Shape, real: Shape, path = '$'): string[] {
  if (typeof fake === 'string' || typeof real === 'string') return fake === real ? [] : [`${path}: fake ${JSON.stringify(fake)}, real ${JSON.stringify(real)}`];
  if (Array.isArray(fake) || Array.isArray(real)) {
    if (!Array.isArray(fake) || !Array.isArray(real)) return [`${path}: array in only one`];
    return fake.length && real.length ? extraInFake(fake[0], real[0], `${path}[0]`) : [];
  }
  return Object.keys(fake).flatMap(k => k in real ? extraInFake(fake[k], real[k], `${path}.${k}`) : [`${path}.${k}: not in the real reply`]);
}

const fixture = (name: string) => JSON.parse(readFileSync(new URL(`../fixtures/backends/${name}`, import.meta.url), 'utf8')).reply;

const servers: http.Server[] = [];
const listen = async (handler: http.RequestListener) => {
  const s = http.createServer(handler);
  await new Promise<void>(r => s.listen(0, '127.0.0.1', () => r()));
  servers.push(s);
  return `http://127.0.0.1:${(s.address() as { port: number }).port}`;
};
test.after(() => { for (const s of servers) s.close(); });

// Exact layout: a field the fake leaves out (like the queue fields before #35) fails too.
test('fake AltMount streams reply has the real v0.4.0 layout', async () => {
  const fake = await createFakeAltmount(listen);
  const nzbUrl: string = fake.addMovie('shape', 'Shape.Test.2026.1080p', Buffer.from('synthetic'));
  const base = new URL(nzbUrl).origin;
  const nzb = await (await fetch(nzbUrl)).text();
  const form = new FormData();
  form.append('file', new Blob([nzb], { type: 'application/x-nzb' }), 'Shape.Test.2026.1080p.nzb');
  form.append('category', 'kaijuflow');
  const res = await fetch(`${base}/api/nzb/streams`, { method: 'POST', headers: { 'X-Api-Key': API_KEY }, body: form });
  assert.equal(res.status, 200);
  assert.deepEqual(shapeOf(await res.json()), shapeOf(fixture('altmount-v0.4.0-streams.json')));
});

test('fake NzbDAV queue and history replies use only real NzbDAV fields', async () => {
  const fake = await createFakeNzbdav(listen);
  // One Completed and one Failed job, so both history slot kinds are compared.
  const links: string[] = [fake.addMovie('done', 'Shape.Done.2026.1080p', Buffer.from('synthetic')), fake.addRejected('failed', 'Shape.Failed.2026.1080p')];
  const base = new URL(links[0]).origin;
  for (const link of links) {
    const form = new FormData();
    form.append('name', new Blob([await (await fetch(link)).text()], { type: 'application/x-nzb' }), 'shape.nzb');
    await fetch(`${base}/api?mode=addfile&cat=Movies&output=json`, { method: 'POST', body: form });
  }
  for (const mode of ['queue', 'history']) {
    const reply = (await (await fetch(`${base}/api?mode=${mode}&output=json`)).json()) as Record<string, any>;
    const real = shapeOf(fixture(`nzbdav-${mode}.json`));
    const slots = (reply[mode]?.slots ?? []) as unknown[];
    for (const slot of slots.length ? slots : [undefined]) {
      // Compare every slot, not only the first one shapeOf keeps.
      assert.deepEqual(extraInFake(shapeOf({ ...reply, [mode]: { ...reply[mode], slots: slot ? [slot] : [] } }), real), [], mode);
    }
  }
});
