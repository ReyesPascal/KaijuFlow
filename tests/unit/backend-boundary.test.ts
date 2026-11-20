// Backend slot boundary. AltMount is KaijuFlow's only Backend (#188): every
// caller goes through getActiveBackend() (src/backends/), and the NzbDAV
// client code (job API, WebDAV client, library search, history and delete)
// is gone and must not come back. Its name is gone too (#200): the play code
// lives in src/play/ and the routes under /play and /api/play.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve('src');

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? sourceFiles(p) : p.endsWith('.ts') ? [p] : [];
  });
}

const rel = (file: string) => path.relative(SRC, file).split(path.sep).join('/');

test('the Backend slot holds one Backend, AltMount', () => {
  const backends = fs.readdirSync(path.join(SRC, 'backends')).filter(f => f.endsWith('.ts')).sort();
  assert.deepEqual(backends, ['altmount.ts', 'capabilities.ts', 'firstByte.ts', 'index.ts', 'nzbGrab.ts', 'sourceNzb.ts', 'types.ts']);
  const index = fs.readFileSync(path.join(SRC, 'backends/index.ts'), 'utf8');
  assert.match(index, /return createAltmountBackend\(buildAltmountSettings\(\)\);/);
  assert.doesNotMatch(index, /nzbdav/i, 'getActiveBackend has no NzbDAV branch');
});

test('no NzbDAV client code is left', () => {
  const gone = ['nzbdavApi', 'videoDiscovery', 'librarySearch', 'webdavClient', 'historyApi', 'staleFolderCleanup', 'deleteAllTargetsStore', 'bdmvResolver'];
  assert.ok(!fs.existsSync(path.join(SRC, 'nzbdav')), 'src/nzbdav/ is back');
  for (const mod of gone) assert.ok(!fs.existsSync(path.join(SRC, 'play', `${mod}.ts`)), `src/play/${mod}.ts is back`);
  assert.ok(!fs.existsSync(path.join(SRC, 'backends/nzbdav.ts')), 'src/backends/nzbdav.ts is back');
  const importRe = /(?:from\s+|import\()\s*['"]([^'"]+)['"]/g;
  const violations: string[] = [];
  for (const file of sourceFiles(SRC)) {
    for (const m of fs.readFileSync(file, 'utf8').matchAll(importRe)) {
      if (m[1] === 'webdav' || gone.includes(path.basename(m[1]).replace(/\.(js|ts)$/, ''))) violations.push(`${rel(file)} imports ${m[1]}`);
    }
  }
  assert.deepEqual(violations, []);
});

// Retro of #16: callers ask what the Backend can do (its capabilities,
// src/backends/capabilities.ts) rather than checking which Backend id is
// selected, so turning a capability on (Ultimate Fallback for AltMount, #190)
// touches only src/backends/.
const ID_COMPARE_OWNERS = ['backends/', 'config/'];

test('only the Backend slot and config compare Backend ids', () => {
  const idCompareRe = /(?:[\w.]*backend[\w.]*|\.id)\s*[!=]==?\s*['"](?:nzbdav|altmount)['"]|['"](?:nzbdav|altmount)['"]\s*[!=]==?\s*[\w.]*backend/gi;
  const violations: string[] = [];
  for (const file of sourceFiles(SRC)) {
    if (ID_COMPARE_OWNERS.some(o => rel(file).startsWith(o))) continue;
    const lines = fs.readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, i) => {
      for (const m of line.matchAll(idCompareRe)) violations.push(`${rel(file)}:${i + 1} ${m[0]}`);
    });
  }
  assert.deepEqual(violations, [], 'ask backendCapabilities() / backend.capabilities instead of comparing Backend ids');
});

// #43 (spec #42): the Backend's prepare gets its NZB through the one shared
// grab-then-hand-to-Backend step (src/backends/sourceNzb.ts), the single place
// Unscramble plugs in. The Backend never calls grabNzb itself.
const GRAB_OWNERS = ['backends/sourceNzb.ts', 'backends/nzbGrab.ts'];

test('only the shared step calls grabNzb', () => {
  const violations: string[] = [];
  for (const file of sourceFiles(SRC)) {
    if (GRAB_OWNERS.includes(rel(file))) continue;
    const lines = fs.readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, i) => {
      if (/\bgrabNzb\b/.test(line) && !/^\s*(\/\/|\*)/.test(line)) violations.push(`${rel(file)}:${i + 1}`);
    });
  }
  assert.deepEqual(violations, [], 'get the NZB from grabSourceNzb (src/backends/sourceNzb.ts) instead');
});

// #200: the code stops saying NzbDAV. Only the code that reads what older versions
// saved may name it: the config migrations and the dead marks' old flag name.
const OLD_NAME_READERS = ['config/migrations.ts', 'config/playSettingsMigration.ts'];

test('no NzbDAV name in src/ outside the readers of old saved data', () => {
  const violations: string[] = [];
  for (const file of sourceFiles(SRC)) {
    if (OLD_NAME_READERS.includes(rel(file))) continue;
    const lines = fs.readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, i) => {
      if (!/nzbdav/i.test(line)) return;
      if (rel(file) === 'play/streamCache.ts' && /isNzbdavFailure/.test(line) && !/nzbdav/i.test(line.replace(/isNzbdavFailure/g, ''))) return;
      violations.push(`${rel(file)}:${i + 1}`);
    });
  }
  assert.deepEqual(violations, []);
});

test('the play routes are mounted under /play and /api/play, and the old paths are not', () => {
  const server = fs.readFileSync(path.join(SRC, 'server.ts'), 'utf8');
  const mounts = [...server.matchAll(/app\.use\('([^']+)'/g)].map(m => m[1]);
  for (const p of ['/api/play', '/stremio/:manifestKey/play', '/:manifestKey/play']) assert.ok(mounts.includes(p), `${p} is mounted`);
  assert.deepEqual(mounts.filter(p => /nzbdav/i.test(p)), []);
});
