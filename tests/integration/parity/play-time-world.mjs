// The world the Play-time check's suites play in (#190, spec #183): KaijuFlow with its fallback on, the owner's setup.
// The stream list is asked for through the addon's stream route and a fake indexer (as in discovery-stream),
// then played through the real play routes against fake AltMount; the fake news server is the only
// health-check provider. Application modules are real; indexer, news server and Backend are fake.
// One setup for every suite that plays in it (parity-play-time-check, parity-keep-alive, parity-go-back-preparing,
// parity-go-back-ready).
import fs from 'node:fs';
import { createFakeAltmount } from './fake-altmount.mjs';
import { useFakeNews } from './fake-nntp.mjs';
import { createFakeTvdb } from './fake-tvdb.mjs';
import { createFakeCinemeta } from './fake-cinemeta.mjs';

export const PLAY_TIME_BOUNDARIES = ['Fake indexer answers every search with the Sources a scenario offers for that IMDB id', 'Fake news server holds the articles of healthy Sources only', 'Fake TVDB knows only the shows a scenario adds', 'Fake AltMount prepares at once unless a scenario slows an import', 'Synthetic media bytes, not decodable video'];

/**
 * A Newznab indexer that answers a search with the Sources offered for its IMDB id; `searches` says when each came.
 * With `refuseGrabs` it also hands out its own NZB links (`nzbLink`) and refuses every grab of them, as an indexer at
 * its download limit does: `{ status: 429 }`, or `{ status: 200, body }` with a Newznab error payload as the body;
 * `grabbedTags` lists the tags of the grabs asked for (the fake AltMount's `grabs` holds each grab's times).
 * Without `refuseGrabs` it serves the copies it was given (`copy`, a Release's Source on this indexer, #300): the same
 * NZB as the upload's link on the suite's indexer; a copy set to refuse (`refuse`) answers as `refuseGrabs` does, and a
 * link it does not know answers 404, as an indexer does for a removed NZB.
 */
async function createFakeIndexer(listen, { refuseGrabs } = {}) {
  const offers = new Map(); // imdb id without "tt" -> [{ title, link, size }]
  const requests = [];
  const searches = []; // { imdbid, at }
  const grabbedTags = [];
  const copies = new Map(); // tag -> { from: the upload's NZB link, refuse?: { status, body? } }
  const xml = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const refuse = (res, how) => {
    if (how.body) {
      res.writeHead(how.status, { 'Content-Type': 'application/xml' });
      res.end(how.body);
    } else {
      res.writeHead(how.status, { 'Retry-After': '3600' });
      res.end('download limit reached');
    }
  };
  const url = await listen(async (req, res) => {
    const u = new URL(req.url, 'http://127.0.0.1');
    if (u.pathname.endsWith('.nzb')) {
      const tag = u.pathname.slice(1, -4);
      grabbedTags.push(tag);
      if (refuseGrabs) { refuse(res, refuseGrabs); return; }
      const copy = copies.get(tag);
      if (!copy) { res.writeHead(404); res.end(); return; }
      if (copy.refuse) { refuse(res, copy.refuse); return; }
      const nzb = await fetch(copy.from, { headers: { 'x-fake-copy': '1' } }).then(r => r.text());
      res.writeHead(200, { 'Content-Type': 'application/x-nzb' });
      res.end(nzb);
      return;
    }
    requests.push(u.searchParams.get('t'));
    searches.push({ imdbid: u.searchParams.get('imdbid'), at: Date.now() });
    const items = offers.get(u.searchParams.get('imdbid')) ?? [];
    const cat = u.searchParams.get('t') === 'tvsearch' ? 5040 : 2040;
    res.setHeader('Content-Type', 'application/xml');
    res.end(`<rss xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"><channel><newznab:response total="${items.length}" offset="0"/>` +
      items.map(i => `<item><title>${xml(i.title)}</title><link>${xml(i.link)}</link><pubDate>Sat, 07 Nov 2026 00:00:00 GMT</pubDate>` +
        `<newznab:attr name="size" value="${i.size}"/><newznab:attr name="category" value="${cat}"/></item>`).join('') + '</channel></rss>');
  });
  return {
    url, requests, searches, grabbedTags, nzbLink: tag => `${url}/${tag}.nzb`, offer(imdbId, items) { offers.set(imdbId.replace(/^tt/, ''), items); },
    /** This indexer's copy of an upload whose NZB is at `from`: its own link. `refuse`: answer every grab of it so. */
    copy(tag, from, { refuse } = {}) { copies.set(tag, { from, refuse }); return `${url}/${tag}.nzb`; },
    /** Grabs of this copy answer so from now on (`{ status: 429 }`), or serve again (undefined). */
    refuseCopy(tag, how) { copies.get(tag).refuse = how; },
  };
}

/**
 * Start KaijuFlow's real modules (from `root`/dist) with the fakes around them. Returns the world the scenarios take:
 * { kaijuflow, backend, news, indexer, second, refusing, limited, tvdb, cinemeta, list, config, configData, stats }.
 */
export async function createPlayTimeWorld({ root, listen }) {
  const load = p => import(root + '/dist/' + p + '.js');
  // KaijuFlow's address goes into the stream list's links (the request's baseUrl), so it listens first.
  let app;
  const kaijuflow = await listen((req, res) => app(req, res));
  const backend = await createFakeAltmount(listen);
  const { config, configData } = await load('config/index');
  backend.configure(configData);
  const news = await useFakeNews(configData, config);
  // Real archives (tests/fixtures/archives), copied next to the scenarios by in-namespace.sh.
  backend.useNews(news, { archiveFixture: name => fs.readFileSync(`${root}/fixtures/archives/${name}`) });
  const indexer = await createFakeIndexer(listen);
  // Two more indexers that refuse every grab: one answers 429, one 200 with a Newznab error payload (code 500, its
  // request limit). Each joins the settings only in the scenarios that use it.
  const refusing = await createFakeIndexer(listen, { refuseGrabs: { status: 429 } });
  const limited = await createFakeIndexer(listen, { refuseGrabs: { status: 200, body: '<?xml version="1.0" encoding="UTF-8"?>\n<error code="500" description="Request limit reached"/>' } });
  // Caps unknown: Kaiju Search asks each by IMDb and by name (#285); the fake answers a name query with nothing.
  const indexerEntry = (name, url) => ({ name, url, apiKey: 'synthetic-indexer-key', enabled: true });
  // A second indexer that serves its own links as the suite's does (Releases, #299: the same upload on two indexers).
  const second = await createFakeIndexer(listen);
  second.entry = indexerEntry('Second', second.url);
  refusing.entry = indexerEntry('Refusing', refusing.url);
  limited.entry = indexerEntry('Limited', limited.url);
  Object.assign(configData, {
    indexManager: 'manual',
    indexers: [indexerEntry('Parity', indexer.url)],
    // The owner's setup: health checks on, fallback on (tools/brain/expected-settings.json); everything else default.
    healthChecks: { ...configData.healthChecks, enabled: true },
    ultimateFallback: { enabled: true },
  });
  // TVDB answers on loopback (the network is lo only); a scenario turns it on with the TVDB key (withTvdb).
  const tvdb = await createFakeTvdb(listen);
  // Cinemeta on loopback too: it names only the titles a scenario adds (cinemeta.add), the rest stay unnamed.
  const cinemeta = await createFakeCinemeta(listen, JSON.parse(fs.readFileSync(`${root}/fixtures/cinemeta/movie-tt7286456.json`, 'utf8')));
  const { default: axios } = await import(root + '/node_modules/axios/index.js');
  axios.interceptors.request.use(cfg => {
    cfg.url = cfg.url?.replace('https://api4.thetvdb.com', tvdb.url).replace('https://v3-cinemeta.strem.io', cinemeta.url);
    return cfg;
  });
  const { default: express } = await import(root + '/node_modules/express/index.js');
  const { handleStream } = await load('play/streamHandler');
  const { createPlayStreamRoutes } = await load('routes/play');
  app = express();
  // The player's mount, as server.ts has it (KaijuFlow makes no self-request since #191 and #226).
  app.use('/stremio/:manifestKey/play', createPlayStreamRoutes({ config, handleStream, getLatestVersions: () => ({ chrome: 'synthetic' }) }));
  const { default: addon } = await load('addon/index');
  const { requestContext } = await load('requestContext');
  /** The stream list a player gets for a title (Stremio id, e.g. tt0000001 or tt0000002:1:2). */
  const list = async (type, id) => {
    const out = await requestContext.run({ baseUrl: kaijuflow, pathPrefix: '/stremio', manifestKey: 'synthetic-manifest' }, () => addon.get('stream', type, id));
    return out.streams;
  };
  // KaijuFlow's stats (config/stats.json): a scenario that sets which indexer's NZB downloads were fastest starts them fresh.
  const stats = await load('statsTracker');
  return { kaijuflow, backend, news, indexer, second, refusing, limited, tvdb, cinemeta, list, config, configData, stats };
}
