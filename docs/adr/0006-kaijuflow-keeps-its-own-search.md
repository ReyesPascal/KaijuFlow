# KaijuFlow keeps its own search

KaijuFlow searches the indexers, health-checks the Sources and keeps the dead marks itself, for every Backend. AltMount's own Stremio addon is not used as a search, not even paired with KaijuFlow's health checks. Decided by the owner on 2026-11-09 after two side-by-side runs on Brain (`tools/brain/search.py`; results in the owner's notes, `brain-1338/RESULTS.md`, and on the speed-check page).

## Why

The addon lists faster because it checks nothing, and that is the whole difference. With the same three indexers on both sides, on 10 fresh titles played cold and then warm:

| | List shows after, cold → warm | Top pick plays, cold → warm |
|---|---|---|
| AltMount's addon | 1.2 → 0.7 s | 8 → 8 of 10 |
| KaijuFlow with AltMount | 9.2 → 4.7 s | 9 → 10 of 10 |
| Usenet Ultimate with NzbDAV (today) | 8.9 → 4.4 s | 8 → 10 of 10 |

- The addon failed the same two top picks in both runs (HTTP 503 after its own article check): it keeps no dead marks, so a bad Source stays at the top. KaijuFlow marked its one cold miss dead and played 10 of 10 the second time, like Usenet Ultimate.
- The addon asks each indexer for one page of 100 results and removes duplicates; KaijuFlow pages through everything (281 Sources against 156 at the median).
- The addon's relevance filter dropped 191 of 193 results for Blade Runner 2049 (`Dropped irrelevant Stremio releases`, the year-like "2049" in the title). Not reported upstream: it does not affect KaijuFlow.
- A health-checked list costs 4 to 9 s. On a TV a list that takes a few seconds beats a play button that fails.

## Consequences

- The Stremio addon settings of a Backend (AltMount's `stremio.indexers`, its `fallback_timeout_ms`) have no part in KaijuFlow's behaviour; they only matter for Brain comparisons.
- The search side of `tools/brain/search.py` stays as a yardstick: any future Backend's own search is compared the same way before it is considered.
- Faster lists come from KaijuFlow's own health checks (the benchmark plan), not from delegating the search.
