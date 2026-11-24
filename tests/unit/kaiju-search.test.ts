// Kaiju Search (#285, spec #279; GLOSSARY: Kaiju Search): every indexer is asked by ID (the IDs its caps list) and by
// name at once; the answers are merged and each Source is listed once, then sorted by Search Flow.
// The fake indexers answer like a Newznab indexer: `t=movie` / `t=tvsearch` with an ID it supports, `t=search` with
// `q`, and an error for an ID its caps do not list (review rule 1).
// Run: npm run test:unit
import { test, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { configData } from '../../src/config/index.ts';
import { indexManagerSearch, type SearchContext } from '../../src/addon/searchOrchestrator.ts';

interface Asked { indexer: string; t: string; ids: Record<string, string>; q?: string }

const item = (title: string, guid: string) =>
  `<item><title>${title}</title><guid>${guid}</guid><link>http://idx.invalid/getnzb/${guid}.nzb</link>`
  + `<pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate><enclosure url="http://idx.invalid/getnzb/${guid}.nzb" length="4000000000" type="application/x-nzb"/></item>`;
const rss = (items: string[]) => `<?xml version="1.0"?><rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">`
  + `<channel><newznab:response offset="0" total="${items.length}"/>${items.join('')}</channel></rss>`;
const ERROR = `<?xml version="1.0"?><error code="201" description="Incorrect parameter"/>`;

/** One fake indexer: `byId` answers an ID query (keyed by the id param it was asked with), `byName` a name query. It
 *  holds every answer until it has been asked both ways (or 1.5 s passed), so asking one way after the other is seen. */
function fakeIndexer(name: string, supports: string[], byId: Record<string, string[]>, byName: string[], asked: Asked[]) {
  const held: (() => void)[] = [];
  let sawId = false, sawName = false;
  const release = () => { if (sawId && sawName) held.splice(0).forEach(go => go()); };
  const server = http.createServer((req, res) => {
    const p = new URL(req.url ?? '', 'http://x').searchParams;
    const t = p.get('t') ?? '';
    const ids = Object.fromEntries([...p].filter(([k]) => /^(imdb|tmdb|tvdb|tvmaze)id$/.test(k)));
    asked.push({ indexer: name, t, ids, q: p.get('q') ?? undefined });
    let body: string;
    if (t === 'search') { sawName = true; body = rss(byName.map((r, i) => item(r, `${name}-n${i}`))); }
    else if ((t === 'movie' || t === 'tvsearch') && Object.keys(ids).length > 0 && Object.keys(ids).every(k => supports.includes(k))) {
      sawId = true;
      body = rss(Object.keys(ids).flatMap(k => byId[k] ?? []).map(r => item(r, guidOf(name, r, byName))));
    } else body = ERROR;
    const answer = () => { res.writeHead(200, { 'Content-Type': 'application/xml' }); res.end(body); };
    held.push(answer);
    release();
    setTimeout(() => { const i = held.indexOf(answer); if (i >= 0) { held.splice(i, 1); answer(); } }, 1500);
  });
  return server;
}

/** The same release keeps its guid and link whichever way it was found (a Newznab indexer's guid is the release's). */
function guidOf(indexer: string, release: string, byName: string[]): string {
  const i = byName.indexOf(release);
  return i >= 0 ? `${indexer}-n${i}` : `${indexer}-id-${release.length}`;
}

const servers: http.Server[] = [];
async function listen(server: http.Server): Promise<string> {
  servers.push(server);
  await new Promise<void>(r => server.listen(0, '127.0.0.1', () => r()));
  return `http://127.0.0.1:${(server.address() as { port: number }).port}/api`;
}
after(() => servers.forEach(s => s.close()));

const saved = { indexManager: configData.indexManager, indexers: configData.indexers, searchConfig: configData.searchConfig };
after(() => Object.assign(configData, saved));
beforeEach(() => {
  configData.indexManager = 'newznab';
  configData.searchConfig = { includeSeasonPacks: false, includeMultiSeasonPacks: false, aliasTitleFallback: false };
});

const matrix: SearchContext = { type: 'movie', imdbId: 'tt0133093', title: 'The Matrix', year: '1999', isAnime: false, additionalTitles: [] };
const BOTH = 'The.Matrix.1999.1080p.BluRay.x264-GRP';
const ID_ONLY = 'TheMatrix.1999.2160p.UHD.Remux-XYZ'; // its name fits neither rule: only the ID finds it, and it stays
const NAME_ONLY = 'The.Matrix.1999.720p.WEB-DL.AAC-ABC';

test('every indexer is asked by ID and by name at once; a Source found both ways is listed once, one only an ID finds and one only a name finds both appear', async () => {
  const asked: Asked[] = [];
  const url = await listen(fakeIndexer('Ninja', ['imdbid'], { imdbid: [BOTH, ID_ONLY] }, [BOTH, NAME_ONLY], asked));
  configData.indexers = [{ name: 'Ninja', url, apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q', 'imdbid'], tvSearchParams: ['q'] } }];

  const t0 = Date.now();
  const results = await indexManagerSearch(matrix);
  assert.ok(Date.now() - t0 < 1400, 'both ways were asked at once: the fake answered as soon as it had seen both');

  assert.deepEqual(asked.map(a => [a.t, a.ids, a.q]).sort(), [['movie', { imdbid: '0133093' }, undefined], ['search', {}, 'The Matrix 1999']]);
  assert.deepEqual(results.map(r => r.title).sort(), [BOTH, NAME_ONLY, ID_ONLY].sort());
  const found = Object.fromEntries(results.map(r => [r.title, r.foundBy]));
  assert.deepEqual(found, { [BOTH]: ['id', 'name'], [ID_ONLY]: ['id'], [NAME_ONLY]: ['name'] });
});

test('the ID search asks with every ID the indexer supports; an indexer whose caps are unknown is asked by IMDb', async () => {
  const asked: Asked[] = [];
  const both = await listen(fakeIndexer('Both', ['imdbid', 'tmdbid'], { imdbid: [BOTH], tmdbid: [BOTH] }, [NAME_ONLY], asked));
  const plain = await listen(fakeIndexer('Plain', ['imdbid'], { imdbid: [BOTH] }, [NAME_ONLY], asked));
  configData.indexers = [
    { name: 'Both', url: both, apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q', 'imdbid', 'tmdbid'], tvSearchParams: [] } },
    { name: 'Plain', url: plain, apiKey: 'k', enabled: true },
  ];
  const results = await indexManagerSearch({ ...matrix, animeResolvedIds: { tmdbId: '603' } });

  const idAsks = asked.filter(a => a.t === 'movie').map(a => [a.indexer, a.ids]).sort();
  assert.deepEqual(idAsks, [['Both', { imdbid: '0133093' }], ['Both', { tmdbid: '603' }], ['Plain', { imdbid: '0133093' }]]);
  assert.deepEqual(asked.filter(a => a.t === 'search').map(a => a.indexer).sort(), ['Both', 'Plain']);
  assert.deepEqual(results.map(r => `${r.indexerName}: ${r.title}`).sort(), [
    `Both: ${BOTH}`, `Both: ${NAME_ONLY}`, `Plain: ${BOTH}`, `Plain: ${NAME_ONLY}`,
  ], 'found by two IDs, listed once per indexer');
});

// Search Flow decides what a name search keeps (#282 decision 4, done here): the loose rule keeps, and a release the
// strict rule passes is kept even where the loose rule would drop it. Real release names from the shared table.
test('a name search keeps a release the strict rule passes though the loose rule drops it; a wrong title is still dropped', async () => {
  const asked: Asked[] = [];
  const reacher = 'REACHER.TV.S01E01.Welcome.to.Margrave.1080p.AMZN.WEB-DL.DDP5.1.H.265-NINJACENTRAL'; // strict pass, loose drop
  const wrong = 'Jack.Reacher.Never.Go.Back.2016.1080p.BluRay.x264-SPARKS';
  const url = await listen(fakeIndexer('Ninja', [], {}, [reacher, wrong], asked));
  configData.indexers = [{ name: 'Ninja', url, apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q'], tvSearchParams: ['q'] } }];
  const results = await indexManagerSearch({ type: 'series', imdbId: 'tt9288030', title: 'Reacher', year: '2022', season: 1, episode: 1, isAnime: false, additionalTitles: [] });
  assert.deepEqual(asked.map(a => [a.t, a.q]), [['search', 'Reacher S01E01']], 'caps that list no ID: asked by name only');
  assert.deepEqual(results.map(r => r.title), [reacher]);
});
