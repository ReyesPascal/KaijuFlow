// Fake Newznab indexers for the Kaiju Search tests (Releases #299, the list deadline #301): each answers a name search
// with a set answer (a real one from tests/fixtures/indexer-answers/, or one built with `rss`), and
// every other query with an empty answer. `delayMs` makes one slow, as DrunkenSlug is beside NinjaCentral.
import http from 'node:http';
import { after } from 'node:test';
import { configData } from '../../src/config/index.ts';
import { captureLogs } from './capture-logs.ts';

export const ANSWERS = 'tests/fixtures/indexer-answers';
const EMPTY = `<?xml version="1.0"?><rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"><channel><newznab:response offset="0" total="0"/></channel></rss>`;

/** A fake indexer that answers every name search with `body` (`@@STANDIN@@` becomes its own address, as the
 *  stand-in served it), `delayMs` after it was asked, and every other query with an empty answer at once. */
function fakeIndexer(body: string, delayMs = 0) {
  return http.createServer((req, res) => {
    const p = new URL(req.url ?? '', 'http://x').searchParams;
    const base = `http://${req.headers.host}`;
    const answer = () => {
      res.writeHead(200, { 'Content-Type': 'text/xml;charset=UTF-8' });
      res.end(p.get('t') === 'search' ? body.replaceAll('@@STANDIN@@', base) : EMPTY);
    };
    if (p.get('t') === 'search' && delayMs > 0) setTimeout(answer, delayMs); else answer();
  });
}

export const item = (title: string, guid: string, size: number) =>
  `<item><title>${title}</title><guid>${guid}</guid><link>@@STANDIN@@/getnzb/${guid}.nzb</link>`
  + `<pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate><enclosure url="@@STANDIN@@/getnzb/${guid}.nzb" length="${size}" type="application/x-nzb"/>`
  + `<newznab:attr name="size" value="${size}"/></item>`;
export const rss = (items: string[]) => `<?xml version="1.0"?><rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">`
  + `<channel><newznab:response offset="0" total="${items.length}"/>${items.join('')}</channel></rss>`;

const servers: http.Server[] = [];
async function listen(server: http.Server): Promise<string> {
  servers.push(server);
  await new Promise<void>(r => server.listen(0, '127.0.0.1', () => r()));
  return `http://127.0.0.1:${(server.address() as { port: number }).port}/api`;
}
after(() => servers.forEach(s => { s.closeAllConnections(); s.close(); }));

/** Run fn with KaijuFlow's console lines kept out of the test's output. */
export async function quiet<T>(fn: () => Promise<T>): Promise<T> {
  let out: T | undefined;
  await captureLogs(async () => { out = await fn(); });
  return out as T;
}

const saved = { indexManager: configData.indexManager, indexers: configData.indexers, searchConfig: configData.searchConfig, devDiagnostics: configData.devDiagnostics, easynewsEnabled: configData.easynewsEnabled };
after(() => Object.assign(configData, saved));
/** The settings every Kaiju Search test starts from: Newznab, no packs, no alias fallback, no EasyNews. */
export function plainSettings(): void {
  configData.indexManager = 'newznab';
  configData.searchConfig = { includeSeasonPacks: false, includeMultiSeasonPacks: false, aliasTitleFallback: false };
  configData.devDiagnostics = false;
  configData.easynewsEnabled = false;
}

/** Two indexers, NinjaCentral first (the owner's order), each asked by name only; `slugDelayMs` makes DrunkenSlug
 *  answer its name search that long after it was asked. */
export async function twoIndexers(ninja: string, slug: string, slugDelayMs = 0) {
  configData.indexers = [
    { name: 'NinjaCentral', url: await listen(fakeIndexer(ninja)), apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q'], tvSearchParams: ['q'] } },
    { name: 'DrunkenSlug', url: await listen(fakeIndexer(slug, slugDelayMs)), apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q'], tvSearchParams: ['q'] } },
  ];
}
