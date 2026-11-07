# A4 deletion expanded regression — independent GitHub CI verification

Date: 2026-11-07
Audit branch at verification: `audit/node20-a3-baseline@f1c75cefbdb62a896e6563e41ef11e028dcebeff`
Import source: `c83a3c733b6394eb140a1c0a1dc500010a9f22e5` (unchanged)
CI: https://github.com/ReyesPascal/KaijuFlow/actions/runs/42367643808
Job: `128388981743` (`a4-isolated`), conclusion **failure**, expected because original safety invariants fail.
Report artifact: `13572093462`, ZIP SHA256 `23d96c058e0ede2259c563aca49803a1e63757aec9c918a7fbb01773dd2743fe` (temporary, 14-day retention).

## Executed results

- Fail-closed A4-ISO-000: negative-control blocked import; only `lo`, external TCP IPv4/IPv6 and DNS denied, localhost permitted. Source SHA256 before/after identical.
- A4-HTTP-001: PASS. Authentication/setup, JWT, unauthorized and query-token assertions.
- A4-SDK-002: PASS. Both manifest-key mount patterns and extra resource routes.
- A4-AUTOSAVE-004: PASS **backend sequential subcase only**; values 9300 → 9400 persisted; malformed JSON 400, oversize 413. Does not establish UI concurrency.
- A4-DELETE-003: FAIL **two safety invariants**. A valid HEAD resulted in exactly one remote mock WebDAV DELETE; 503 failure did not trigger a second attempt on immediate repeat.
- Added deletion cases **executed**: traversal normalization and invalid pack depth rejected without remote DELETE; invalid manifest returned 404 without remote DELETE; four simultaneous same-key requests coalesced into one remote DELETE. Malformed envelope produced no new DELETE. Metrics in CI: `invalidAdditional:0`, `unauthorizedStatus:404`, `unauthorizedDeletes:0`, `concurrentDeletes:1`, `headRemoteDeletes:1`, `failedFirst:1`, `failedReplay:1`.
- A4 synthetic summary: 3 cases PASS, 1 case FAIL. Failure is a behavioral regression finding, not proof of broken isolation. No live WebDAV or production NNTP was touched.

## Evidence classification and next gates

**Test-observed**: all assertions above from original compiled source in the disposable namespace.
**Source-observed, untested**: delete-all route may deduplicate failed remote deletions before success.
**Not yet tested**: React `useAppConfig` 300/500ms debounce, overlapping PUT response ordering, 500/transport error and retry/rollback; provider/sync; Smart/Fixed NNTP; archive/yEnc; streaming Range 200/206/416; cache and fallback.

Keep existing red safety tests visible; do not patch imported application source without separate approval. Implement the actual React hook fixture under the existing A4 isolation gate, with controlled timers and deferred mock API responses. Add delete-all replay fixture separately, followed by provider/sync and other A4 scenarios. Preserve Brain-first/TV-light original-quality streaming target; benchmark NzbDAV alternatives before replacement. Do not alter Brain production, merge PRs, use live credentials/NZBs, or modify original source.
