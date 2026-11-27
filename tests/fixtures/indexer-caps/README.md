# Indexer caps replies

Real `t=caps` replies, as the indexers sent them (HTTP 200, `text/xml;charset=UTF-8`); none holds a key.

- `drunkenslug-caps.xml`: DrunkenSlug, taken on 2026-11-24 for the review of #279 (a `t=caps` request; DrunkenSlug answers it the same with or without a valid key).
- `ninjacentral-caps.xml`: NinjaCentral, the stand-in's recording of it (`store/baseline/ninjacentral/`, request `api t=caps`), its links rewritten to `@@STANDIN@@` by the stand-in, nothing else changed.
- `drunkenslug-error-wrong-key.xml`: DrunkenSlug's answer to a search with a wrong key, taken the same day: a Newznab `<error>` sent with HTTP 200, which holds no caps.

`tests/unit/kaiju-search.test.ts` reads caps from them (`fetchIndexerCaps`, NZBHydra's sync): what Kaiju Search asks an indexer by. When an indexer changes its replies, capture new ones here.
