# Indexer search answers

Real name-search answers (`t=search&q=Girlfriends S04E04&cat=5000&extended=1`, HTTP 200, `text/xml;charset=UTF-8`), kept by the quick check of 2026-11-24 (`~/kaijuflow-notes/brain-runs/2026-11-24T122253Z-quick-check/evidence/05-girlfriends-s04e04/answers/`, request hash `80f33d8f…`). Links are the stand-in's (`@@STANDIN@@/nzb/<base64url of the indexer's link>`); the indexer links hold `{KEY}` for the key, and the account number (`i=`) was replaced by `{USER}` when they were copied here. Nothing else changed.

- `ninjacentral-search-girlfriends-s04e04.xml`: NinjaCentral, 7 items.
- `drunkenslug-search-girlfriends-s04e04.xml`: DrunkenSlug, 18 items.

They share uploads under different guids and links: `…squalor` at the same size, and `Girlfriends.S04E04.720p.HDTV.x264-REGRET`, which DrunkenSlug holds twice (0.11 % and 1.5 % from NinjaCentral's size). `tests/unit/releases.test.ts` serves them from two fake indexers: what Kaiju Search merges into one Release.

`tools/brain/test_search_ping.py` answers the preflight's search with them (a search answer, whatever it holds), and the Release rule's shared table (`tests/fixtures/release-rule/`) takes its pairs from them.
