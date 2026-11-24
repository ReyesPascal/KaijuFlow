// Kaiju Search (#285, spec #279; GLOSSARY: Kaiju Search): every indexer is asked by ID (the IDs its caps list) and by
// name at once; the answers are merged and each Source is listed once, then sorted by Search Flow.
// The fake indexers answer like a Newznab indexer: `t=movie` / `t=tvsearch` with an ID it supports, `t=search` with
// `q`, and an error for an ID its caps do not list (review rule 1).
// Run: npm run test:unit
import { test, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { configData } from '../../src/config/index.ts';
import { indexManagerSearch, kaijuSearch, type SearchContext } from '../../src/addon/searchOrchestrator.ts';
import { mergeFound, type FoundBy } from '../../src/addon/kaijuSearch.ts';
import { parseStepLine } from '../../src/utils/stepTiming.ts';
import { captureLogs } from './capture-logs.ts';

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

const saved = { indexManager: configData.indexManager, indexers: configData.indexers, searchConfig: configData.searchConfig, devDiagnostics: configData.devDiagnostics };
after(() => Object.assign(configData, saved));
beforeEach(() => {
  configData.indexManager = 'newznab';
  configData.searchConfig = { includeSeasonPacks: false, includeMultiSeasonPacks: false, aliasTitleFallback: false };
  configData.devDiagnostics = false;
});

const matrix: SearchContext = { type: 'movie', imdbId: 'tt0133093', title: 'The Matrix', year: '1999', isAnime: false, additionalTitles: [] };
const BOTH = 'The.Matrix.1999.1080p.BluRay.x264-GRP';
const ID_ONLY = 'TheMatrix.1999.2160p.UHD.Remux-XYZ'; // the strict rule does not fit its name: a maybe only the ID finds
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

// With the dev switch on (#280), a `search` step line per indexer and way of asking: what it was asked, how many
// results came back, how many stayed, and each result sure / maybe / dropped with why; and a line whenever the strict
// rule alone would have left nothing. With it off, none: a release logs what it logs today.
const searchLines = (logs: string) => logs.split('\n').map(l => parseStepLine(l)).filter((r): r is NonNullable<typeof r> => r?.step === 'search');
const WRONG = 'The.Matrix.Resurrections.2021.1080p.WEB-DL.DDP5.1.Atmos.H.264-FLUX';

test('with the dev switch off, a search writes no search line', async () => {
  const url = await listen(fakeIndexer('Ninja', ['imdbid'], { imdbid: [BOTH, ID_ONLY] }, [BOTH, NAME_ONLY, WRONG], []));
  configData.indexers = [{ name: 'Ninja', url, apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q', 'imdbid'], tvSearchParams: ['q'] } }];
  const logs = await captureLogs(() => kaijuSearch(matrix));
  assert.deepEqual(searchLines(logs), []);
  assert.doesNotMatch(logs, /"dev":true/);
});

test('with the dev switch on, a search line per indexer and way of asking, each result sure, maybe or dropped with why', async () => {
  configData.devDiagnostics = true;
  const url = await listen(fakeIndexer('Ninja', ['imdbid'], { imdbid: [BOTH, ID_ONLY] }, [BOTH, NAME_ONLY, WRONG], []));
  configData.indexers = [{ name: 'Ninja', url, apiKey: 'SECRETKEY123', enabled: true, caps: { movieSearchParams: ['q', 'imdbid'], tvSearchParams: ['q'] } }];
  const logs = await captureLogs(() => kaijuSearch(matrix));
  const lines = searchLines(logs).map(({ t, ms, ...rest }) => rest);
  assert.deepEqual(lines, [
    { step: 'search', source: 'Ninja', ok: true, title: 'The Matrix', dev: true, way: 'id', asked: ['imdb'], count: 2, kept: 2, sure: 1, maybe: 1, results: [
      { release: BOTH, flow: 'sure', why: 'the name and year fit' },
      { release: ID_ONLY, flow: 'maybe', why: 'the name "The Matrix" is not in it' },
    ] },
    { step: 'search', source: 'Ninja', ok: true, title: 'The Matrix', dev: true, way: 'name', asked: ['name'], count: 3, kept: 2, sure: 2, maybe: 0, results: [
      { release: BOTH, flow: 'sure', why: 'the name and year fit' },
      { release: NAME_ONLY, flow: 'sure', why: 'the name and year fit' },
      { release: WRONG, flow: 'dropped', why: 'the name "The Matrix" is not followed by a year (1999 wanted)' },
    ] },
  ]);
  assert.doesNotMatch(logs.split('\n').filter(l => l.includes('"step":"search"')).join('\n'), /SECRETKEY123|127\.0\.0\.1|apikey/i);
});

test('with the dev switch on, a line whenever the strict rule alone would have left nothing', async () => {
  configData.devDiagnostics = true;
  const joker = 'Joker 1080p WEB-DL DD5.1 H264 (2019) NL Subs'; // the shared table's obscure real release: loose only
  const url = await listen(fakeIndexer('Ninja', [], {}, [joker], []));
  configData.indexers = [{ name: 'Ninja', url, apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q'], tvSearchParams: ['q'] } }];
  const joke: SearchContext = { type: 'movie', imdbId: 'tt7286456', title: 'Joker', year: '2019', isAnime: false, additionalTitles: [] };
  const lines = searchLines(await captureLogs(() => kaijuSearch(joke)));
  assert.deepEqual(lines.filter(l => l.strict_alone).map(({ t, ms, ...rest }) => rest), [
    { step: 'search', ok: true, title: 'Joker', dev: true, strict_alone: 'nothing', kept: 1, sure: 0, maybe: 1 },
  ]);

  const url2 = await listen(fakeIndexer('Ninja', ['imdbid'], { imdbid: [BOTH] }, [], []));
  configData.indexers = [{ name: 'Ninja', url: url2, apiKey: 'k', enabled: true, caps: { movieSearchParams: ['q', 'imdbid'], tvSearchParams: ['q'] } }];
  const sure = searchLines(await captureLogs(() => kaijuSearch(matrix)));
  assert.deepEqual(sure.filter(l => l.strict_alone), [], 'a sure Source: strict alone leaves it');
});

// Prowlarr's per-indexer Newznab proxy (the ID search) and its aggregate search (the name search) hand out a different
// download link for the same release, and write its date differently (RFC-822, ISO-8601): it is still one Source.
test('one release found by ID through Prowlarr\'s Newznab proxy and by name through its aggregate search is listed once', () => {
  const release = { title: BOTH, size: 4000000000, indexerName: 'NinjaCentral', category: 'Movies', attributes: {} };
  const merged = mergeFound([
    { ...release, link: 'http://prowlarr:9696/1/download?apikey=x&link=AAA&file=a', pubDate: 'Mon, 01 Jan 2024 00:00:00 +0000', foundBy: ['id'] as FoundBy[] },
    { ...release, link: 'http://prowlarr:9696/1/download?apikey=x&link=BBB&file=a', pubDate: '2024-01-01T00:00:00Z', foundBy: ['name'] as FoundBy[] },
    { ...release, title: NAME_ONLY, link: 'http://prowlarr:9696/1/download?apikey=x&link=CCC&file=b', pubDate: '2024-01-01T00:00:00Z', foundBy: ['name'] as FoundBy[] },
  ]);
  assert.deepEqual(merged.map(r => [r.title, r.foundBy]), [[BOTH, ['id', 'name']], [NAME_ONLY, ['name']]]);
});
