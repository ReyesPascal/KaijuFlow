// The fake TVDB must answer in real TVDB v4's reply layout (review rule 2). Fixtures in tests/fixtures/tvdb/ are
// replies captured from api4.thetvdb.com on 2026-11-23; only the status and the layout (fields, nesting, types)
// are compared, never values.
// Run: npm run test:unit
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { createFakeTvdb } from '../integration/parity/fake-tvdb.mjs';

interface Capture { status: number; body: unknown }
const capture = (name: string): Capture => JSON.parse(readFileSync(new URL(`../fixtures/tvdb/${name}`, import.meta.url), 'utf8'));

const isObject = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);

/**
 * What every element of a captured array holds: the keys all of them have, each with its first non-null value (the
 * captured episodes are specials, some with airsBeforeSeason, some without).
 */
function commonElement(items: unknown[]): unknown {
  if (!items.every(isObject)) return items.find(v => v !== null) ?? null;
  const keys = Object.keys(items[0]).filter(k => items.every(i => k in (i as Record<string, unknown>)));
  return Object.fromEntries(keys.map(k => {
    const values = items.map(i => (i as Record<string, unknown>)[k]);
    return [k, values.every(Array.isArray) ? values.flat() : values.find(v => v !== null) ?? null];
  }));
}

/**
 * The fake's reply has the captured reply's layout: the same keys at every level, and the same type for each value,
 * null matching any type (a field the capture or the fake has empty); every element of a fake array has the layout
 * of the captured array's elements.
 */
function assertLayout(fake: unknown, real: unknown, at = 'body'): void {
  if (fake === null || real === null) return;
  if (Array.isArray(real)) {
    assert.ok(Array.isArray(fake), `${at}: an array in TVDB's reply`);
    if (real.length === 0) return;
    const element = commonElement(real);
    fake.forEach((v, i) => assertLayout(v, element, `${at}[${i}]`));
    return;
  }
  if (isObject(real)) {
    assert.ok(isObject(fake), `${at}: an object in TVDB's reply`);
    assert.deepEqual(Object.keys(fake).sort(), Object.keys(real).sort(), `${at}: the fields of TVDB's reply`);
    for (const k of Object.keys(real)) assertLayout(fake[k], real[k], `${at}.${k}`);
    return;
  }
  assert.equal(typeof fake, typeof real, `${at}: a ${typeof real} in TVDB's reply`);
}

const servers: http.Server[] = [];
const listen = async (handler: http.RequestListener) => {
  const s = http.createServer(handler);
  await new Promise<void>(r => s.listen(0, '127.0.0.1', () => r()));
  servers.push(s);
  return `http://127.0.0.1:${(s.address() as { port: number }).port}`;
};
test.after(() => { for (const s of servers) s.close(); });

const fake = await createFakeTvdb(listen);
fake.addShow('tt0115147', 'KaijuFlow Daily Shape', [{ season: 1, episode: 1, aired: '2026-11-02' }, { season: 1, episode: 2, aired: '2026-11-03' }]);

async function ask(path: string, { token, body }: { token?: string; body?: unknown } = {}): Promise<Capture> {
  const res = await fetch(`${fake.url}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: res.status, body: await res.json() };
}

function assertAnswersAs(reply: Capture, name: string): void {
  const real = capture(name);
  assert.equal(reply.status, real.status, `${name}: TVDB's status`);
  assertLayout(reply.body, real.body);
}

const login = await ask('/v4/login', { body: { apikey: fake.key } });
const token = (login.body as { data: { token: string } }).data.token;

test('login with the key: the real layout', () => assertAnswersAs(login, 'tvdb-v4-login.json'));

test('login with a wrong key: refused as TVDB refuses it', async () => {
  assertAnswersAs(await ask('/v4/login', { body: { apikey: 'not-the-key' } }), 'tvdb-v4-login-wrong-key.json');
});

test('a call without the token: refused as TVDB refuses it', async () => {
  assertAnswersAs(await ask('/v4/search/remoteid/tt0115147'), 'tvdb-v4-no-token.json');
});

test('search by IMDB id: the real layout', async () => {
  assertAnswersAs(await ask('/v4/search/remoteid/tt0115147', { token }), 'tvdb-v4-search-remoteid.json');
});

test('a show\'s episodes: the real layout, links with total_items and page_size', async () => {
  const found = await ask('/v4/search/remoteid/tt0115147', { token });
  const id = (found.body as { data: { series: { id: number } }[] }).data[0].series.id;
  assertAnswersAs(await ask(`/v4/series/${id}/episodes/default?page=0`, { token }), 'tvdb-v4-series-episodes-default.json');
});

test('the episodes of a series TVDB does not know: refused as TVDB refuses it', async () => {
  assertAnswersAs(await ask('/v4/series/1/episodes/default?page=0', { token }), 'tvdb-v4-series-unknown.json');
});
