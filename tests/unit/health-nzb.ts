// Shared setup for the health-check tests: a cached NZB with the named files and
// a fake news server holding (or not holding) every article. Not a test file.
import { after } from 'node:test';
import { readFileSync } from 'node:fs';
import { cacheNzbContent } from '../../src/health/nzbContentCache.ts';
import { rar5FirstArticle, startFakeNntp } from '../integration/parity/fake-nntp.mjs';

const servers: Array<{ close(): Promise<void> }> = [];
after(async () => { for (const s of servers) await s.close(); });

/**
 * A file in the NZB. `data`: the file's bytes, cut into `segs` articles (one
 * segment each); without it every article is filler (a RAR5 first article for
 * a `.rar` name).
 */
export type F = { name: string; segs?: number; bytes?: number; data?: Buffer; /** list the segments last first in the NZB, as some posters do */ reversed?: boolean };

function chunks(f: F): Buffer[] {
  const n = f.segs ?? 1;
  if (!f.data) return Array.from({ length: n }, () => /\.rar$/.test(f.name) ? rar5FirstArticle(0) : Buffer.alloc(100, 0x41));
  const size = Math.ceil(f.data.length / n);
  return Array.from({ length: n }, (_, i) => f.data!.subarray(i * size, (i + 1) * size));
}

function nzbXml(files: F[], tag: string, password?: string): string {
  const head = password ? `<head><meta type="password">${password}</meta></head>` : '';
  const body = files.map(f => {
    const parts = chunks(f);
    const listed = parts.map((c, i) =>
      `<segment bytes="${f.data ? c.length : f.bytes ?? 1000}" number="${i + 1}">${tag}-${f.name}-${i + 1}@fake</segment>`);
    const segs = (f.reversed ? listed.reverse() : listed).join('');
    return `<file subject="&quot;${f.name}&quot; yEnc (1/${parts.length})"><segments>${segs}</segments></file>`;
  }).join('');
  return `<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">${head}${body}</nzb>`;
}

let n = 0;
/**
 * Cache an NZB with these files and start a fake news server for it.
 * `served` false leaves every article missing; `missing` names files whose
 * articles are missing. Returns the NZB URL, the news provider and the server
 * state (`reads`: ids whose bodies were read; `stats`: ids sampled with STAT).
 */
export async function nzbWithNews(files: F[], { served = true, password, missing = [] }: { served?: boolean; password?: string; missing?: string[] } = {}) {
  const tag = `t${++n}`;
  const articles = new Map<string, Buffer>();
  if (served) {
    for (const f of files) {
      if (missing.includes(f.name)) continue;
      chunks(f).forEach((c, i) => articles.set(`${tag}-${f.name}-${i + 1}@fake`, c));
    }
  }
  const news = await startFakeNntp({ articles });
  servers.push(news);
  const url = `http://indexer.invalid/${tag}.nzb`;
  cacheNzbContent(url, nzbXml(files, tag, password));
  return { url, provider: news.provider(), state: news.state };
}

/** A real archive from tests/fixtures/archives (see make.sh there). */
export function archiveFixture(name: string): Buffer {
  return readFileSync(new URL(`../fixtures/archives/${name}`, import.meta.url));
}
