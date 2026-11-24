// A fake Cinemeta (Stremio's title metadata) on loopback, so a scenario's title has a name and a year, as a real list
// has (#282: Search Flow judges each release against them). It answers only the movies a scenario adds, with the
// reply captured from Cinemeta (tests/fixtures/cinemeta/), the title's own fields replaced; any other ID gets 404
// with Cinemeta's HTML page, so a title no scenario adds stays unnamed, as before there was a fake.

/** `capture`: the captured reply ({ meta }). Returns { url, add(imdbId, { name, year }) }. */
export async function createFakeCinemeta(listen, capture) {
  const titles = new Map();
  const url = await listen((req, res) => {
    const path = new URL(req.url, 'http://127.0.0.1').pathname;
    const m = /^\/meta\/(movie|series)\/([^/]+)\.json$/.exec(path);
    const t = m && m[1] === 'movie' ? titles.get(m[2]) : undefined;
    if (!t) {
      res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(`<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>Error</title>\n</head>\n<body>\n<pre>Cannot GET ${path.replace(/^\/meta/, '')}</pre>\n</body>\n</html>\n`);
      return;
    }
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ ...capture, meta: { ...capture.meta, id: m[2], imdb_id: m[2], name: t.name, releaseInfo: t.year, year: t.year, behaviorHints: { ...capture.meta.behaviorHints, defaultVideoId: m[2] } } }));
  });
  return { url, add(imdbId, { name, year }) { titles.set(imdbId, { name, year }); } };
}
