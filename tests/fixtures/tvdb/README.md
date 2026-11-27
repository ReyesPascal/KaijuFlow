# TVDB v4 replies

Real replies of api4.thetvdb.com, captured on 2026-11-23 (the owner's go). Each file is `{ status, body }`. The API key and the token are replaced (`<token>`), and the episodes page is trimmed to its first 5 of 500 episodes.

- `tvdb-v4-login.json`: `POST /v4/login` with a good key.
- `tvdb-v4-login-wrong-key.json`: `POST /v4/login` with a wrong key (401).
- `tvdb-v4-no-token.json`: a call without the token (401).
- `tvdb-v4-search-remoteid.json`: `GET /v4/search/remoteid/tt0115147` (The Daily Show, series 71256).
- `tvdb-v4-series-episodes-default.json`: `GET /v4/series/71256/episodes/default?page=0`, trimmed.
- `tvdb-v4-series-unknown.json`: the episodes of a series TVDB does not know (404).

`tests/unit/fake-tvdb-shape.test.ts` holds the fake TVDB (`tests/integration/parity/fake-tvdb.mjs`) to their layout. When TVDB changes its replies, capture new ones here.
