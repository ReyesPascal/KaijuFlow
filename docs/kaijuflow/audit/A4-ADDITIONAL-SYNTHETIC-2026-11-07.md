# Final expanded A4 synthetic execution checkpoint — 2026-11-07

**Verified run:** [GitHub Actions 42370377554](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42370377554), job `128397091476`, original immutable source `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`. `synthetic.mjs`: **15 pass, 2 intentional red original behavior failures**; real React hook fixture: **3 pass, 1 intentional red stale-response ordering failure**. CI combined status FAIL *by design* for the reproduced safety/consistency regressions, not for isolation. Log reports fail-closed no-egress namespace gate PASS and original `src/` and `ui/src/` SHA-256 before/after unchanged. Artifact ID `13573805381`, ZIP SHA-256 `0c2169b10a838199f55f59083ba5b921ff955017dbdc60aae9e0557b635695f8`.

| Case IDs | Outcome | Bounded original-code observation |
| --- | --- | --- |
| A4-HTTP-001, A4-SDK-002, A4-AUTOSAVE-004 | PASS | Auth/JWT, SDK routes, sequential backend settings |
| A4-DELETE-003 | **RED** | HEAD invokes remote WebDAV DELETE; failed 503 DELETE not retried |
| A4-DELETEALL-007 | **RED** | Failed 503 delete-all attempt not retried (1→1), invalid token/manifest deny remote delete |
| A4-PROVIDER-005, A4-INDEXER-006, A4-INDEXER-CRUD-006 | PASS | Provider and indexer CRUD, validation, reordering; last indexer fixture overlaps coverage and is not a separate subsystem |
| A4-NNTP-HANDSHAKE-008, A4-STAT-FALLBACK-009 | PASS | Synthetic NNTP AUTHINFO and 223/430 STAT fallback |
| A4-ARCHIVE-GROUP-010, A4-YENC-011 | PASS | Split archive grouping/sampling, byte-accurate yEnc BODY and format signatures |
| A4-RANGE-PROXY-012, A4-PROXY-FALLBACK-014 | PASS | WebDAV proxy full/partial 200/206, 416 recovery, 404 same-origin fallback with Range reset |
| A4-SYNC-013 | PASS | Prowlarr + NZBHydra fake localhost sync, enabled filtering and settings preservation |
| A4-CACHE-015 | PASS | Broken video marker and one-shot library bypass |
| A4-HEALTH-SAMPLING-016 | PASS | Original pipeline verifies 3/7 samples and blocks synthetic 430 missing article |
| Real React useAppConfig fixture | **3 PASS, 1 RED** | 300 ms debounce, 500/transport retention pass; stale success response overwrites shared config |

**Coverage caveat:** These are isolated source-backed module/route fixtures, not a real-server integration benchmark, original-quality 4K playback test, TLS certificate assessment, or complete Smart/Fixed UI orchestration parity. Do not declare production release readiness. Continue source fixes only by separately approved PR after prioritizing destructive HEAD/deletion, delete-all dedup and autosave ordering. Keep CI intentionally red until actual source remediation is independently reviewed and regression tests pass.

**Evidence index:** `EV-KF-A4-EXPANDED-017`, `CL-KF-A4-EXPANDED-017`, `ART-KF-A4-EXPANDED-017`. Historical mid-run observations follow for provenance.

---

# A4 additional synthetic execution checkpoint — 2026-11-07

## Scope and boundaries
Original imported source pinned to `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`; only `tests/a4/synthetic.mjs` changed. Tests ran under the existing disposable, fail-closed GitHub-hosted no-egress Linux namespace, with synthetic localhost fixtures, temporary config and placeholder assets. Neither Brain production nor original source was modified.

## Independently inspected Actions evidence
- [Run 42369508567](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42369508567), job 128394515303: A4-PROVIDER-005 PASS (unauthenticated 401, two creates, reorder 200, update, delete); A4-INDEXER-006 PASS (invalid payload/timeout 400, two creates, /api URL normalization, update, reorder, delete and mocked capabilities 200). These exercise **original routers with injected in-memory storage callbacks**. They do not establish external provider or synchronized Prowlarr integration correctness.
- [Run 42369553150](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42369553150), job 128394646047: A4-DELETEALL-007 FAIL desired retry invariant. Invalid token had zero remote DELETE, unauthorized manifest 404/zero DELETE. One failing synthetic HTTP 503 DELETE attempt; immediate same-token replay resulted in only one cumulative attempt. Thus failed delete-all is deduplicated. Two pre-existing single-delete safety failures remain.
- [Run 42369608369](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42369608369), job 128394809722 on `1699e435af9a41f7f0f243a652fcc5def1a798dd`: A4-NNTP-HANDSHAKE-008 PASS (missing host/port 400, synthetic NNTP 200 greeting, AUTHINFO USER / 381 / AUTHINFO PASS / 281, authenticated 200; two commands); A4-PROVIDER-005 PASS; A4-INDEXER-006 PASS; A4-DELETEALL-007 intentionally FAIL (one 503 attempt, same request replay does not retry); A4-HTTP-001, A4-SDK-002, A4-AUTOSAVE-004 PASS. Log confirms six passes and two fails for `synthetic.mjs`. Existing React hook stale-success ordering violation is still intentionally RED separately.
- A4 combined CI is intentionally red due to observed **application behavioral invariants**, not a failed network-isolation gate; the job's negative control and positive namespace probes passed.
- [Evidence index CI 42369608614](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42369608614) PASS and [Node 20 build 42369608375](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42369608375) PASS on above head.

## Important interpretation
A missing delete-all token with identical `type/id` initially suppressed subsequent valid requests in the same 30-second dedup key. Test corrected by using unique item IDs for token-miss vs valid-target replay. The final measured 1→1 failed-503 attempt count is unambiguous and matches the previously source-observed pre-result dedup design in `src/routes/nzbdav.ts`.

The NNTP handshake is **not** an article STAT/availability check, TLS handshake, or Smart/Fixed evaluation. Indexer CRUD is **not** automatic synced-indexer behavior. None of the fixtures measure actual streaming.

## Remaining A4
Provider sync/indexer integrations, Smart/Fixed article availability with fake STAT and fallback providers, archive/yEnc, HTTP Range 200/206/416 and seek, cache eviction/fallback/proxy and byte-accurate streaming. Design tests and keep original application code read-only.

**Review gate:** Do not merge PR #1 or PR #3, apply source changes, change production, connect to external NNTP, or claim completion of these remaining cases.
