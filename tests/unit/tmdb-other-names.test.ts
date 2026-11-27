// Search Flow's extra proof (#286): a film's other names come from TMDB's alternative titles, read from the reply to
// the request KaijuFlow makes (`/movie/{id}?append_to_response=release_dates,alternative_titles`), and reach the
// search as `knownNames` through resolveTitle. The replies are real ones, captured on 2026-11-24
// (tests/fixtures/tmdb/README.md, tests/fixtures/cinemeta/README.md); any other request is refused.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { configData } from '../../src/config/index.ts';
import { resolveTitle } from '../../src/addon/titleResolver.ts';
import { captureLogs } from './capture-logs.ts';

const fixture = (path: string) => JSON.parse(fs.readFileSync(new URL(`../fixtures/${path}`, import.meta.url), 'utf8'));
const tmdb: Record<string, [number, unknown]> = fixture('tmdb/movie-amelie.json');
const cinemeta = fixture('cinemeta/movie-tt0211915.json');

const asked: string[] = [];
const interceptor = axios.interceptors.request.use((cfg: InternalAxiosRequestConfig) => {
  const url = new URL(cfg.url ?? '');
  const params = new URLSearchParams(Object.entries(cfg.params ?? {})
    .filter(([k]) => k !== 'api_key').map(([k, v]): [string, string] => [k, String(v)]));
  const key = `${url.pathname.replace(/^\/3/, '')}${params.size ? `?${params}` : ''}`;
  asked.push(`${url.host}${key}`);
  const reply = url.host === 'v3-cinemeta.strem.io' && url.pathname === '/meta/movie/tt0211915.json' ? [200, cinemeta]
    : url.host === 'api.themoviedb.org' ? tmdb[key] : undefined;
  cfg.adapter = async () => {
    if (!reply) throw new AxiosError(`refused: no captured reply for ${url.host}${key}`, 'ECONNREFUSED', cfg);
    return { data: reply[1], status: reply[0] as number, statusText: 'OK', headers: {}, config: cfg };
  };
  return cfg;
});

const saved = configData.searchConfig;
configData.searchConfig = { ...saved, tmdbApiKey: 'test-key' };
after(() => {
  axios.interceptors.request.eject(interceptor);
  configData.searchConfig = saved;
});

test("a film's TMDB alternative titles reach the search as its known names", async () => {
  let info: Awaited<ReturnType<typeof resolveTitle>> | undefined;
  await captureLogs(async () => { info = await resolveTitle('movie', 'tt0211915'); });

  assert.ok(asked.includes('api.themoviedb.org/movie/194?append_to_response=release_dates%2Calternative_titles'), asked.join('\n'));
  assert.equal(info!.title, 'Amélie');
  assert.equal(info!.runtime, 122 * 60);
  const names = info!.knownNames ?? [];
  for (const n of ['The Fabulous Destiny of Amelie Poulain', 'El fabuloso destino de Amelie Poulain', 'Ameri']) {
    assert.ok(names.includes(n), `${n} is among the known names: ${names.join(', ')}`);
  }
  assert.ok(!names.includes('Amélie'), 'the name searched by is not an other name');
  assert.equal(new Set(names).size, names.length, 'each name once');
});
