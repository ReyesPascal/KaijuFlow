// Parity suite for the Play-time check (#190, spec #183): KaijuFlow with its fallback on, the owner's setup.
// The stream list is asked for through the addon's stream route and a fake indexer (as in discovery-stream),
// then played through the real play routes against fake AltMount; the fake news server is the only
// health-check provider. Application modules are real; indexer, news server and Backend are fake.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { createFakeAltmount } from './parity/fake-altmount.mjs';
import { useFakeNews } from './parity/fake-nntp.mjs';
import { runPlayTimeParity } from './parity/play-time-scenarios.mjs';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const load = p => import(root + '/dist/' + p + '.js');
const report = { id: 'INT-PARITY-PLAY-TIME-CHECK-001', backend: 'altmount', boundaries: ['Fake indexer answers every search with the Sources a scenario offers for that IMDB id', 'Fake news server holds the articles of healthy Sources only', 'Fake AltMount prepares at once', 'Synthetic media bytes, not decodable video'] };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };

/** A Newznab indexer that answers a search with the Sources offered for its IMDB id. */
async function createFakeIndexer() {
  const offers = new Map(); // imdb id without "tt" -> [{ title, link, size }]
  const requests = [];
  const xml = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const url = await listen((req, res) => {
    const u = new URL(req.url, 'http://127.0.0.1');
    requests.push(u.searchParams.get('t'));
    const items = offers.get(u.searchParams.get('imdbid')) ?? [];
    const cat = u.searchParams.get('t') === 'tvsearch' ? 5040 : 2040;
    res.setHeader('Content-Type', 'application/xml');
    res.end(`<rss xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"><channel><newznab:response total="${items.length}" offset="0"/>` +
      items.map(i => `<item><title>${xml(i.title)}</title><link>${xml(i.link)}</link><pubDate>Sat, 07 Nov 2026 00:00:00 GMT</pubDate>` +
        `<newznab:attr name="size" value="${i.size}"/><newznab:attr name="category" value="${cat}"/></item>`).join('') + '</channel></rss>');
  });
  return { url, requests, offer(imdbId, items) { offers.set(imdbId.replace(/^tt/, ''), items); } };
}

try {
  // KaijuFlow's address goes into the stream list's links (the request's baseUrl), so it listens first.
  let app;
  const kaijuflow = await listen((req, res) => app(req, res));
  const backend = await createFakeAltmount(listen);
  const { config, configData } = await load('config/index');
  backend.configure(configData);
  const news = await useFakeNews(configData, config);
  // Real archives (tests/fixtures/archives), copied next to the scenarios by in-namespace.sh.
  backend.useNews(news, { archiveFixture: name => fs.readFileSync(`${root}/fixtures/archives/${name}`) });
  const indexer = await createFakeIndexer();
  Object.assign(configData, {
    indexManager: 'manual',
    indexers: [{ name: 'Parity', url: indexer.url, apiKey: 'synthetic-indexer-key', enabled: true, movieSearchMethod: ['imdb'], tvSearchMethod: ['imdb'] }],
    // The owner's setup: health checks on, fallback on (tools/brain/expected-settings.json); everything else default.
    healthChecks: { ...configData.healthChecks, enabled: true },
    ultimateFallback: { enabled: true },
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
  const results = await runPlayTimeParity({ kaijuflow, backend, news, indexer, list, configData });
  Object.assign(report, { status: results.every(r => r.status === 'pass') ? 'pass' : 'fail', results });
} catch (e) { Object.assign(report, { status: 'fail', error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
