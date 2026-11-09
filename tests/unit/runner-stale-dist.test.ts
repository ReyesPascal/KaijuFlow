// The integration and A4 runners copy dist/, so they must refuse a dist/ that is
// older than src/. Each case runs the runner in a throwaway git repo, with a
// sudo stub first on PATH so a runner that gets past the check stops there.
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync, execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, copyFileSync, writeFileSync, utimesSync, chmodSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = fileURLToPath(new URL('../..', import.meta.url));

const RUNNERS = ['tests/integration/run-ci.sh', 'tests/a4/run-ci.sh'];
const OLD = new Date('2020-01-01T00:00:00Z');
const NEW = new Date('2026-01-01T00:00:00Z');

function runIn(runner: string, distTime: Date, srcTime: Date) {
  const dir = mkdtempSync(join(tmpdir(), 'kf-stale-dist-'));
  try {
    mkdirSync(join(dir, 'tests/integration'), { recursive: true });
    mkdirSync(join(dir, 'tests/a4'), { recursive: true });
    for (const r of RUNNERS) copyFileSync(join(REPO, r), join(dir, r));
    mkdirSync(join(dir, 'src')); mkdirSync(join(dir, 'dist')); mkdirSync(join(dir, 'bin'));
    writeFileSync(join(dir, 'src/server.ts'), 'export {};\n');
    writeFileSync(join(dir, 'dist/server.js'), 'export {};\n');
    writeFileSync(join(dir, 'bin/sudo'), '#!/bin/sh\necho SUDO-REACHED\nexit 99\n');
    chmodSync(join(dir, 'bin/sudo'), 0o755);
    const git = (...a: string[]) => execFileSync('git', ['-c', 'user.email=t@t', '-c', 'user.name=t', ...a], { cwd: dir, stdio: 'ignore' });
    git('init', '-q'); git('add', '-A'); git('commit', '-qm', 'fixture');
    utimesSync(join(dir, 'dist/server.js'), distTime, distTime);
    utimesSync(join(dir, 'src/server.ts'), srcTime, srcTime);
    const r = spawnSync('bash', [runner], { cwd: dir, encoding: 'utf8', env: { ...process.env, PATH: `${join(dir, 'bin')}:${process.env.PATH}` }, timeout: 20000 });
    return { status: r.status, out: (r.stdout ?? '') + (r.stderr ?? '') };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

for (const runner of RUNNERS) {
  test(`${runner} refuses a dist/ older than src/`, () => {
    const r = runIn(runner, OLD, NEW);
    assert.equal(r.status, 16, r.out);
    assert.match(r.out, /STALE-DIST/);
    assert.doesNotMatch(r.out, /SUDO-REACHED/);
  });

  test(`${runner} accepts a dist/ built after src/`, () => {
    const r = runIn(runner, NEW, OLD);
    assert.doesNotMatch(r.out, /STALE-DIST/);
    assert.match(r.out, /SUDO-REACHED/, r.out); // got past the check to the next step
  });
}
