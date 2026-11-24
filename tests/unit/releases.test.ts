// Releases (#299, spec #298; GLOSSARY: Release, Source): the same upload found on several indexers is one Release,
// matched by a cleaned-up title (lower case, separators removed) and a size within 1 %, carrying its Source on each
// indexer. Kaiju Search hands the list Releases, so the list shows one entry per Release.
// The fake indexers answer a name search with real answers of NinjaCentral and DrunkenSlug
// (tests/fixtures/indexer-answers/, review rule 2), their links pointing back at the fake as the stand-in's did.
// Run: npm run test:unit
import { test, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import { configData } from '../../src/config/index.ts';
import { kaijuSearch, type SearchContext } from '../../src/addon/searchOrchestrator.ts';
import { captureLogs } from './capture-logs.ts';

const ANSWERS = 'tests/fixtures/indexer-answers';
const EMPTY = `<?xml version="1.0"?><rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"><channel><newznab:response offset="0" total="0"/></channel></rss>`;

/** A fake indexer that answers every name search with `body` (`@@STANDIN@@` becomes its own address, as the
 *  stand-in served it) and every other query with an empty answer. */
function fakeIndexer(body: string) {
  return http.createServer((req, res) => {
    const p = new URL(req.url ?? '', 'http://x').searchParams;
    const base = `http://${req.headers.host}`;
    res.writeHead(200, { 'Content-Type': 'text/xml;charset=UTF-8' });
    res.end(p.get('t') === 'search' ? body.replaceAll('@@STANDIN@@', base) : EMPTY);
  });
}

const item = (title: string, guid: string, size: number) =>
  `<item><title>${title}</title><guid>${guid}</guid><link>@@STANDIN@@/getnzb/${guid}.nzb</link>`
  + `<pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate><enclosure url="@@STANDIN@@/getnzb/${guid}.nzb" length="${size}" type="application/x-nzb"/>`
  + `<newznab:attr name="size" value="${size}"/></item>`;
const rss = (items: string[]) => `<?xml version="1.0"?><rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">`
  + `<channel><newznab:response offset="0" total="${items.length}"/>${items.join('')}</channel></rss>`;

const servers: http.Server[] = [];
async function listen(server: http.Server): Promise<string> {
  servers.push(server);
  await new Promise<void>(r => server.listen(0, '127.0.0.1', () => r()));
  return `http://127.0.0.1:${(server.address() as { port: number }).port}/api`;
}
after(() => servers.forEach(s => s.close()));

async function quiet<T>(fn: () => Promise<T>): Promise<T> {
  let out: T | undefined;
  await captureLogs(async () => { out = await fn(); });
  return out as T;
}

const saved = { indexManager: configData.indexManager, indexers: configData.indexers, searchConfig: configData.searchConfig, devDiagnostics: configData.devDiagnostics, easynewsEnabled: configData.easynewsEnabled };
after(() => Object.assign(configData, saved));
beforeEach(() => {
  configData.indexManager = 'newznab';
  configData.searchConfig = { includeSeasonPacks: false, includeMultiSeasonPacks: false, aliasTitleFallback: false };
  configData.devDiagnostics = false;
  configData.easynewsEnabled = false;
});

/** Two indexers, NinjaCentral first (the owner's order), each asked by name only. */
async function twoIndexers(ninja: string, slug: string) {
  configData.indexers = [
    { name: 'NinjaCentral', url: await listen(fakeIndexer(ninja)), apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q'], tvSearchParams: ['q'] } },
    { name: 'DrunkenSlug', url: await listen(fakeIndexer(slug)), apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q'], tvSearchParams: ['q'] } },
  ];
}

const girlfriends: SearchContext = { type: 'series', imdbId: 'tt0247102', title: 'Girlfriends', year: '2000', season: 4, episode: 4, isAnime: false, additionalTitles: [] };
const SQUALOR = 'Girlfriends.S04E04.You.Aint.Gotta.Go.Home.But.You.Know.the.Rest.WEB-DL.DDP2.0.H.264-squalor';
const REGRET = 'Girlfriends.S04E04.720p.HDTV.x264-REGRET';

/** A Release as the test reads it: its name, and each Source's indexer and size. */
const shown = (r: { title: string; sources: { indexerName: string; size: number }[] }) =>
  `${r.title} ${r.sources.map(s => `${s.indexerName}:${s.size}`).join(' ')}`;

test('real answers of NinjaCentral and DrunkenSlug: an upload both have is one Release carrying both Sources; a copy more than 1 % apart in size stays its own', async () => {
  await twoIndexers(fs.readFileSync(`${ANSWERS}/ninjacentral-search-girlfriends-s04e04.xml`, 'utf8'),
    fs.readFileSync(`${ANSWERS}/drunkenslug-search-girlfriends-s04e04.xml`, 'utf8'));
  const { indexer } = await quiet(() => kaijuSearch(girlfriends));

  const mine = indexer.filter(r => r.title === SQUALOR || r.title === REGRET).map(shown);
  assert.deepEqual(mine.sort(), [
    // The same upload on both (same size): one Release, NinjaCentral's Source first.
    `${SQUALOR} NinjaCentral:193428257 DrunkenSlug:193428257`,
    // DrunkenSlug holds two REGRET uploads: the one 0.11 % from NinjaCentral's joins it, the one 1.5 % off does not.
    `${REGRET} DrunkenSlug:600661974`,
    `${REGRET} NinjaCentral:609810415 DrunkenSlug:610490962`,
  ].sort());

  const squalor = indexer.find(r => r.title === SQUALOR);
  // Different guids and links (the parser keeps the link, which holds the guid): each Source keeps its own.
  assert.match(squalor.sources[0].link, /^http:\/\/127\.0\.0\.1:\d+\/nzb\//);
  assert.notEqual(squalor.sources[0].link, squalor.sources[1].link, 'each Source keeps its own indexer\'s link');
  assert.equal(squalor.link, squalor.sources[0].link, 'the Release is listed with its first Source\'s link');
  assert.equal(squalor.indexerName, 'NinjaCentral');
});

test('the same name on two indexers matches with case and separators ignored, at a size within 1 %; more than 1 % apart is two Releases', async () => {
  const GB = 1_000_000_000;
  await twoIndexers(
    rss([item('Girlfriends.S04E04.1080p.WEB-DL.H264-AAA', 'nc-a', 2 * GB), item('Girlfriends.S04E04.2160p.WEB-DL.H265-BBB', 'nc-b', 5 * GB)]),
    rss([item('girlfriends s04e04 1080p web_dl h264-aaa', 'ds-a', 2 * GB + 20_000_000), item('Girlfriends.S04E04.2160p.WEB-DL.H265-BBB', 'ds-b', 5 * GB + 51_000_000)]),
  );
  const { indexer } = await quiet(() => kaijuSearch(girlfriends));
  assert.deepEqual(indexer.map(shown).sort(), [
    `Girlfriends.S04E04.1080p.WEB-DL.H264-AAA NinjaCentral:${2 * GB} DrunkenSlug:${2 * GB + 20_000_000}`, // 1 % exactly: one Release
    `Girlfriends.S04E04.2160p.WEB-DL.H265-BBB DrunkenSlug:${5 * GB + 51_000_000}`, // 1.01 %: two
    `Girlfriends.S04E04.2160p.WEB-DL.H265-BBB NinjaCentral:${5 * GB}`,
  ].sort());
});

test('two uploads of one name on the same indexer stay two Releases, even at the same size', async () => {
  const GB = 1_000_000_000;
  await twoIndexers(rss([item('Girlfriends.S04E04.1080p.WEB-DL.H264-AAA', 'nc-1', 2 * GB), item('Girlfriends.S04E04.1080p.WEB-DL.H264-AAA', 'nc-2', 2 * GB + 1)]), rss([]));
  const { indexer } = await quiet(() => kaijuSearch(girlfriends));
  assert.equal(indexer.length, 2);
  assert.deepEqual(indexer.map(r => r.sources.length), [1, 1]);
});
