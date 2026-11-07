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
