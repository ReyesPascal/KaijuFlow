// Backend slot boundary (#17): only the Backend slot (src/backends/) and the
// NzbDAV module itself (src/nzbdav/) may import NzbDAV client code. Every
// other caller goes through getActiveBackend(). NzbDAV-only features that
// predate the slot are listed in ALLOWED and should shrink, not grow.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve('src');
const NZBDAV_CLIENT = ['nzbdavApi', 'videoDiscovery', 'librarySearch', 'webdavClient', 'historyApi', 'staleFolderCleanup'];
const OWNERS = ['backends/', 'nzbdav/'];

/** file (relative to src/) → NzbDAV client modules it may still import directly. */
const ALLOWED: Record<string, string[]> = {
  'server.ts': ['staleFolderCleanup'],                   // NzbDAV-only startup library cleanup
  'routes/nzbdav.ts': ['historyApi', 'videoDiscovery'],  // NzbDAV-only library delete screens
};

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? sourceFiles(p) : p.endsWith('.ts') ? [p] : [];
  });
}

test('only the Backend slot calls NzbDAV client code', () => {
  const importRe = /(?:from\s+|import\()\s*['"]([^'"]+)['"]/g;
  const violations: string[] = [];
  for (const file of sourceFiles(SRC)) {
    const rel = path.relative(SRC, file).split(path.sep).join('/');
    if (OWNERS.some(o => rel.startsWith(o))) continue;
    const text = fs.readFileSync(file, 'utf8');
    for (const m of text.matchAll(importRe)) {
      const mod = path.basename(m[1]).replace(/\.(js|ts)$/, '');
      if (!m[1].includes('nzbdav/') || !NZBDAV_CLIENT.includes(mod)) continue;
      if (ALLOWED[rel]?.includes(mod)) continue;
      violations.push(`${rel} imports ${m[1]}`);
    }
  }
  assert.deepEqual(violations, [], 'call the active Backend (src/backends/) instead');
});
