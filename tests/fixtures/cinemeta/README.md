# Cinemeta replies

A real reply of Stremio's Cinemeta (`v3-cinemeta.strem.io`, keyless and public), captured on 2026-11-24 for #282: `GET /meta/movie/tt7286456.json` (Joker, 2019), saved as Cinemeta sent it. An ID Cinemeta does not know gets `404` with an HTML page (`Cannot GET /movie/<id>.json`), after a 307 to `cinemeta-live.strem.io`.

The fake Cinemeta (`tests/integration/parity/fake-cinemeta.mjs`) answers a title a scenario adds with this reply, its `id`, `imdb_id`, `name`, `releaseInfo`, `year` and `behaviorHints.defaultVideoId` replaced, so it keeps Cinemeta's layout (review rule 2), and answers any other ID 404 as Cinemeta does (rule 1). When Cinemeta changes its replies, capture a new one here.

`movie-tt0211915.json` (Amélie, 2001), captured the same way on 2026-11-24 for the review of #279: `tests/unit/tmdb-other-names.test.ts` resolves the film's title with it and TMDB's replies (`tests/fixtures/tmdb/`).
