// The world the Play-time check's suites play in (#190, spec #183): KaijuFlow with its fallback on, the owner's setup.
// The stream list is asked for through the addon's stream route and a fake indexer (as in discovery-stream),
// then played through the real play routes against fake AltMount; the fake news server is the only
// health-check provider. Application modules are real; indexer, news server and Backend are fake.
// One setup for every suite that plays in it (parity-play-time-check, parity-keep-alive).
import fs from 'node:fs';
import { createFakeAltmount } from './fake-altmount.mjs';
import { useFakeNews } from './fake-nntp.mjs';
import { createFakeTvdb } from './fake-tvdb.mjs';

export const PLAY_TIME_BOUNDARIES = ['Fake indexer answers every search with the Sources a scenario offers for that IMDB id', 'Fake news server holds the articles of healthy Sources only', 'Fake TVDB knows only the shows a scenario adds', 'Fake AltMount prepares at once unless a scenario slows an import', 'Synthetic media bytes, not decodable video'];

/**
 * A Newznab indexer that answers a search with the Sources offered for its IMDB id; `searches` says when each came.
 * With `refuseGrabs` it also hands out its own NZB links (`nzbLink`) and refuses every grab of them, as an indexer at
 * its download limit does: `{ status: 429 }`, or `{ status: 200, body }` with a Newznab error payload as the body;
 * `grabs` lists the tags asked for.
 */
async function createFakeIndexer(listen, { refuseGrabs } = {}) {
  const offers = new Map(); // imdb id without "tt" -> [{ title, link, size }]
  const requests = [];
  const searches = []; // { imdbid, at }
  const grabs = [];
  const xml = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const url = await listen((req, res) => {
    const u = new URL(req.url, 'http://127.0.0.1');
    if (refuseGrabs && u.pathname.endsWith('.nzb')) {
      grabs.push(u.pathname.slice(1, -4));
      if (refuseGrabs.body) {
        res.writeHead(refuseGrabs.status, { 'Content-Type': 'application/xml' });
        res.end(refuseGrabs.body);
      } else {
        res.writeHead(refuseGrabs.status, { 'Retry-After': '3600' });
        res.end('download limit reached');
      }
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
  return { url, requests, searches, grabs, nzbLink: tag => `${url}/${tag}.nzb`, offer(imdbId, items) { offers.set(imdbId.replace(/^tt/, ''), items); } };
}

/**
 * Start KaijuFlow's real modules (from `root`/dist) with the fakes around them. Returns the world the scenarios take:
 * { kaijuflow, backend, news, indexer, refusing, limited, tvdb, list, configData }.
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
  const indexerEntry = (name, url) => ({ name, url, apiKey: 'synthetic-indexer-key', enabled: true, movieSearchMethod: ['imdb'], tvSearchMethod: ['imdb'] });
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
  const { default: axios } = await import(root + '/node_modules/axios/index.js');
  axios.interceptors.request.use(cfg => { cfg.url = cfg.url?.replace('https://api4.thetvdb.com', tvdb.url); return cfg; });
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
  return { kaijuflow, backend, news, indexer, refusing, limited, tvdb, list, configData };
}
