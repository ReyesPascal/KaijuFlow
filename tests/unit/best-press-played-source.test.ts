// Every press of the Best entry can be told apart in KaijuFlow's log (#190): the brain tools name the played
// Source of a visit from the first prepare line after the visit's '/stream hit' line (brainreport.played_source),
// and every Best press goes to the same address (/stream/ultimate-fallback). The real play route writes the
// lines and the real reader (tools/brain/brainreport.py) reads them, as a timed run does with `docker logs -t`.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import express from 'express';
import type { AddressInfo } from 'node:net';
import { createPlayStreamRoutes } from '../../src/routes/play.ts';
import { logBestPlays, logPrepareStart } from '../../src/play/streamCache.ts';
import { encodeTileEnvelope } from '../../src/play/redirectHelpers.ts';
import type { Config } from '../../src/types.ts';

/** brainreport.played_source on a log, as the brain tools read one visit's lines. */
function playedSource(log: string): string | null {
  const code = 'import sys; sys.path.insert(0, "tools/brain"); import brainreport; print(brainreport.played_source(sys.stdin.read()) or "")';
  const r = spawnSync('python3', ['-I', '-c', code], { input: log, encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  return r.stdout.trim() || null;
}

test('two Best presses a few seconds apart each name their own played Source', async () => {
  const lines: string[] = [];
  const saved = console.log;
  console.log = (...a: unknown[]) => { lines.push(`${new Date().toISOString()} ${a.map(String).join(' ')}`); };
  const playing: string[] = [];
  const app = express();
  app.use('/stremio/:manifestKey/play', createPlayStreamRoutes({
    config: {} as Config,
    isStreamCached: () => false,
    getLatestVersions: () => ({ chrome: 'synthetic' }),
    // What Best does on a press: one Source goes to the Backend (the line the reader takes), then the video.
    handleStream: async (req, res) => {
      if (!req.headers.range) logPrepareStart(`👑 Ultimate-Fallback [k] [prepare #2] `, playing.at(-1)!);
      res.end('video');
    },
  }));
  const server = app.listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}/stremio/key/play/stream/ultimate-fallback`;
  /** One visit: its list's Best entry (a new fallback group per list) pressed, then a range probe of it. */
  const visit = async (sk: string, title: string) => {
    const from = lines.length;
    playing.push(title);
    const url = `${base}?t=${encodeTileEnvelope({ sk, fbg: Math.random().toString(16).slice(2, 14) })}`;
    await (await fetch(url)).text();
    await (await fetch(url, { headers: { Range: 'bytes=1000-' } })).text();
    return () => lines.slice(from).join('\n');
  };
  let first = () => '', second = () => '';
  try {
    first = await visit('key:movie:tt0000001::', 'Film.One.2026.2160p.WEB-DL-GRP');
    second = await visit('key:movie:tt0000002::', 'Film.Two.2026.2160p.WEB-DL-GRP');
  } finally {
    console.log = saved;
    server.close();
  }
  assert.equal(playedSource(first()), 'Film.One.2026.2160p.WEB-DL-GRP');
  assert.equal(playedSource(second()), 'Film.Two.2026.2160p.WEB-DL-GRP', 'the second press, inside the 15 s window, is found too');
  assert.equal(lines.filter(l => l.includes('/stream hit')).length, 2, 'a range probe of the same entry writes no second line');
});

test('a press of Best that plays what its Head start prepared names the played Source', async () => {
  const lines: string[] = [];
  const saved = console.log;
  console.log = (...a: unknown[]) => { lines.push(`${new Date().toISOString()} ${a.map(String).join(' ')}`); };
  const app = express();
  app.use('/stremio/:manifestKey/play', createPlayStreamRoutes({
    config: {} as Config,
    isStreamCached: () => false,
    getLatestVersions: () => ({ chrome: 'synthetic' }),
    // The Head start prepared the Source before the press (#206): the press writes no prepare line, only what it plays.
    handleStream: async (_req, res) => { logBestPlays('Film.Three.2026.2160p.WEB-DL-GRP'); res.end('video'); },
  }));
  const server = app.listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const url = `http://127.0.0.1:${(server.address() as AddressInfo).port}/stremio/key/play/stream/ultimate-fallback?t=${encodeTileEnvelope({ sk: 'key:movie:tt0000003::', fbg: 'abc123' })}`;
  let visit = '';
  try {
    // The Head start's own prepare line, written while the list was read, comes before the press.
    logPrepareStart('👑 Ultimate-Fallback [key:movie:tt0000003::] [prepare #1] ', 'Film.Three.2026.2160p.WEB-DL-GRP');
    const from = lines.length;
    await (await fetch(url)).text();
    visit = lines.slice(from).join('\n');
  } finally {
    console.log = saved;
    server.close();
  }
  assert.equal(playedSource(visit), 'Film.Three.2026.2160p.WEB-DL-GRP');
});
