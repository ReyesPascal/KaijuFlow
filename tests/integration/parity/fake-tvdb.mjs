// Fake TVDB (API v4) for the Parity play-time suite: the episodes of the shows a scenario adds, so a daily show's
// aired date reaches the list as it does from real TVDB. It answers only the calls the title resolver makes for an
// IMDB id (login, /search/remoteid, /series/:id/episodes/default) and refuses what real TVDB refuses: a wrong API
// key at login and any other call without the token (401), an unknown series (404). Its replies keep the layout of
// real TVDB's, captured in tests/fixtures/tvdb/ (tests/unit/fake-tvdb-shape.test.ts holds it to them).
// Contract: { url, key, addShow(imdbId, name, episodes[{ season, episode, aired }]), asked[] }.

const TOKEN = 'synthetic-tvdb-token';
export const TVDB_KEY = 'synthetic-tvdb-key';
const PAGE_SIZE = 500;

/** A series record as real TVDB writes it (search and episodes replies), synthetic values. */
function seriesRecord(show) {
  const aired = show.episodes.map(e => e.aired).sort();
  return {
    id: show.id, name: show.name, slug: show.name.toLowerCase().replace(/[^a-z0-9]+/g, '-'), image: null,
    nameTranslations: ['eng'], overviewTranslations: ['eng'], aliases: [],
    firstAired: aired[0] ?? '', lastAired: aired.at(-1) ?? '', nextAired: '', score: 1,
    status: { id: 1, name: 'Continuing', recordType: 'series', keepUpdated: true },
    originalCountry: 'usa', originalLanguage: 'eng', defaultSeasonType: 1, isOrderRandomized: false,
    lastUpdated: '2026-11-23 00:00:00', averageRuntime: 45, episodes: null, overview: `${show.name}, a synthetic show.`, year: '2026',
  };
}

/** An episode as real TVDB writes it in a series' episodes page, synthetic values. */
function episodeRecord(show, e, i) {
  return {
    id: show.id * 100 + i, seriesId: show.id, name: `Episode ${e.episode}`, aired: e.aired, runtime: 45,
    nameTranslations: ['eng'], overview: null, overviewTranslations: [], image: null, imageType: null, isMovie: 0,
    seasons: null, number: e.episode, absoluteNumber: 0, seasonNumber: e.season, lastUpdated: '2026-11-23 00:00:00',
    finaleType: null, year: e.aired.slice(0, 4),
  };
}

export async function createFakeTvdb(listen) {
  const shows = new Map(); // imdb id (with "tt") -> { id, name, episodes }
  const byId = new Map();
  const asked = [];
  let nextId = 900001;
  const url = await listen(async (req, res) => {
    const chunks = []; for await (const c of req) chunks.push(c);
    const path = new URL(req.url, 'http://127.0.0.1').pathname;
    asked.push(`${req.method} ${path}`);
    const json = (status, x) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(x)); };
    const refuse = (status, message) => json(status, { status: 'failure', message, data: null });
    if (req.method === 'POST' && path === '/v4/login') {
      let apikey;
      try { apikey = JSON.parse(Buffer.concat(chunks).toString()).apikey; } catch { /* no body */ }
      return apikey === TVDB_KEY ? json(200, { status: 'success', data: { token: TOKEN } }) : refuse(401, 'InvalidAPIKey: apikey invalid');
    }
    if (req.headers.authorization !== `Bearer ${TOKEN}`) return json(401, { message: 'Unauthorized' });
    const remote = /^\/v4\/search\/remoteid\/([^/]+)$/.exec(path);
    if (remote) {
      const show = shows.get(decodeURIComponent(remote[1]));
      return json(200, { status: 'success', data: show ? [{ series: seriesRecord(show) }] : [] });
    }
    const eps = /^\/v4\/series\/(\d+)\/episodes\/default$/.exec(path);
    if (eps) {
      const show = byId.get(Number(eps[1]));
      if (!show) return refuse(404, 'NotFoundException: Season not found');
      return json(200, {
        status: 'success',
        data: { series: seriesRecord(show), episodes: show.episodes.map((e, i) => episodeRecord(show, e, i)) },
        links: { prev: null, self: `${url}${path}?page=0`, next: null, total_items: show.episodes.length, page_size: PAGE_SIZE },
      });
    }
    return refuse(404, 'NotFoundException');
  });
  return {
    url,
    key: TVDB_KEY,
    asked,
    /** A show TVDB knows under this IMDB id, with its episodes ({ season, episode, aired: 'YYYY-MM-DD' }). */
    addShow(imdbId, name, episodes) {
      const show = { id: nextId++, name, episodes };
      shows.set(imdbId, show);
      byId.set(show.id, show);
    },
  };
}
