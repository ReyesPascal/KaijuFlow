// The config save keeps the owner of the file it replaces (#261). The test container runs as root, so a save there
// (a settings change, a startup migration) used to leave the test copy's config.json root-owned, and testbed.py apply
// (user brain) then failed with PermissionError. Tests don't run as root, so fs is spied: the old file's owner is
// faked through statSync and chownSync is recorded instead of run.
import { test, mock, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'fs';
import { configData, saveConfigFile, CONFIG_FILE } from '../../src/config/index.ts';

const realStatSync = fs.statSync;

/** Fakes the owner of the file at CONFIG_FILE (or its absence); every other path is stat'ed for real. */
function fakeConfigFileOwner(owner: { uid: number; gid: number } | 'missing'): void {
  mock.method(fs, 'statSync', (p: fs.PathLike, ...rest: unknown[]) => {
    if (String(p) === CONFIG_FILE) {
      if (owner === 'missing') {
        throw Object.assign(new Error(`ENOENT: no such file or directory, stat '${CONFIG_FILE}'`), { code: 'ENOENT' });
      }
      return { ...realStatSync(p), uid: owner.uid, gid: owner.gid };
    }
    return (realStatSync as (...a: unknown[]) => unknown)(p, ...rest);
  });
}

/** Records chownSync and renameSync calls in order; rename still runs, chown runs `chown` (default: nothing). */
function recordChownAndRename(chown: () => void = () => {}): string[][] {
  const calls: string[][] = [];
  const realRename = fs.renameSync;
  mock.method(fs, 'chownSync', (p: fs.PathLike, uid: number, gid: number) => {
    calls.push(['chown', String(p), String(uid), String(gid)]);
    chown();
  });
  mock.method(fs, 'renameSync', (from: fs.PathLike, to: fs.PathLike) => {
    calls.push(['rename', String(from), String(to)]);
    realRename(from, to);
  });
  return calls;
}

afterEach(() => mock.restoreAll());

// A uid/gid this process never runs as, so the old file's owner differs from the temp file's.
const ROOT_OWNER = { uid: 0, gid: 0 };
const OTHER_OWNER = { uid: 4242, gid: 4343 };
const otherThanMe = process.getuid?.() === 0 ? OTHER_OWNER : ROOT_OWNER;

test('saving over a config file gives the temp file that file\'s uid and gid before the rename', () => {
  fakeConfigFileOwner(otherThanMe);
  const calls = recordChownAndRename();

  saveConfigFile(configData);

  assert.equal(calls.length, 2, JSON.stringify(calls));
  const [chown, rename] = calls;
  assert.deepEqual(chown.slice(2), [String(otherThanMe.uid), String(otherThanMe.gid)]);
  assert.deepEqual(rename, ['rename', chown[1], CONFIG_FILE], 'chown hits the temp file, which is then renamed over');
});
