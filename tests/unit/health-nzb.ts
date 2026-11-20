// Shared setup for the health-check tests: a cached NZB with the named files and
// a fake news server holding (or not holding) every article. Not a test file.
import { after } from 'node:test';
import { cacheNzbContent } from '../../src/health/nzbContentCache.ts';
import { rar5FirstArticle, startFakeNntp } from '../integration/parity/fake-nntp.mjs';

const servers: Array<{ close(): Promise<void> }> = [];
after(async () => { for (const s of servers) await s.close(); });

export type F = { name: string; segs?: number; bytes?: number };

function nzbXml(files: F[], tag: string, password?: string): string {
  const head = password ? `<head><meta type="password">${password}</meta></head>` : '';
  const body = files.map(f => {
    const n = f.segs ?? 1;
    const segs = Array.from({ length: n }, (_, i) =>
      `<segment bytes="${f.bytes ?? 1000}" number="${i + 1}">${tag}-${f.name}-${i + 1}@fake</segment>`).join('');
    return `<file subject="&quot;${f.name}&quot; yEnc (1/${n})"><segments>${segs}</segments></file>`;
  }).join('');
  return `<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">${head}${body}</nzb>`;
}

let n = 0;
/**
 * Cache an NZB with these files and start a fake news server for it.
 * `served` false leaves every article missing. Returns the NZB URL, the news
 * provider and the server state (`reads`: message ids whose bodies were read).
 */
export async function nzbWithNews(files: F[], { served = true, password }: { served?: boolean; password?: string } = {}) {
  const tag = `t${++n}`;
  const articles = new Map<string, Buffer>();
  if (served) {
    for (const f of files) {
      for (let i = 1; i <= (f.segs ?? 1); i++) {
        articles.set(`${tag}-${f.name}-${i}@fake`, /\.rar$/.test(f.name) ? rar5FirstArticle(0) : Buffer.alloc(100, 0x41));
      }
    }
  }
  const news = await startFakeNntp({ articles });
  servers.push(news);
  const url = `http://indexer.invalid/${tag}.nzb`;
  cacheNzbContent(url, nzbXml(files, tag, password));
  return { url, provider: news.provider(), state: news.state };
}
