# A4 isolated synthetic CI verification — 2026-11-07 (continuation)

## Provenance and scope
- Source under test: immutable original import `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`; audit-only head `17822864583a09917b65c46aaaeae02b67e9e1e6`.
- Independently inspected GitHub Actions [run 42370377554](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42370377554), job `128397091476`, raw completed job log.
- Network gate: negative-control blocked import; disposable namespace had only loopback and denied external IPv4/IPv6 TCP/DNS; source SHA-256 identical before/after.
- Overall A4 CI **failure is intentional** for reproduced original-behavior invariants, not test infrastructure. Logs establish 15 passed backend synthetic cases and 2 failed backend cases; 3 React passes and 1 expected race failure.

## Exact synthetic results (job log)
| Case | Outcome | Observation |
| --- | --- | --- |
| A4-HTTP-001 / A4-SDK-002 | PASS / PASS | auth/JWT and dual Stremio route assertions |
| A4-DELETEALL-007 | FAIL | fake 503 WebDAV delete-all first attempt=1, replay total=1 (required 2); missing target token 0 remote deletes; invalid manifest 404/0 deletes |
| A4-DELETE-003 | FAIL | HEAD triggered one remote DELETE; 503 replay total=1; four concurrent same-key calls coalesced to one; invalid/traversal and manifest boundaries blocked |
| A4-AUTOSAVE-004 | PASS | sequential persisted 9300 then 9400, invalid JSON 400, oversize 413 |
| A4-NNTP-HANDSHAKE-008 / A4-STAT-FALLBACK-009 | PASS / PASS | synthetic authenticated handshake and backup-provider STAT path |
| A4-ARCHIVE-GROUP-010 / A4-YENC-011 | PASS / PASS | 3-part grouping, `ABC` decoded and missing article response 430 |
| A4-PROXY-FALLBACK-014 / A4-RANGE-PROXY-012 | PASS / PASS | upstream 404, redirect 302, HTTP full 200, partial 206, recovered 416->200, missing 404 |
| A4-SYNC-013 / A4-CACHE-015 | PASS / PASS | synthetic sync and cache state transitions |
| A4-HEALTH-SAMPLING-016 | PASS | 3/7 sample paths and blocked status |
| A4-PROVIDER-005 / A4-INDEXER-006 | PASS / PASS | synthetic CRUD/reorder, caps; unauthorized provider access 401 |
| A4-INDEXER-CRUD-006 | PASS | additional original indexer route CRUD/reorder validation; zero external network calls |
| A4-REACT-300 / A4-REACT-500 / A4-REACT-TRANSPORT | PASS | timer and error-preserves-local-edit cases |
| A4-REACT-ORDER | FAIL | returning older PUT 9300 after newer 9400 leaves shared config stale at 9300, local edit 9400 |

## Interpretation / nonclaims
Results are isolated synthetic contract tests of selected compiled original handlers and utilities, **not** production playback, bandwidth/4K, live provider compatibility, complete source coverage, full end-to-end behavior, real archive streaming, or proof of disk-level autosave races. The 416->200 recovery outcome is fixture-specific, not broad HTTP 416 compliance proof. Do not mark behavior defects as resolved without approved source changes and fresh regressions.

## Recovery
Keep this report and the existing finding/evidence ledgers as durable history. Run [A4 CI](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42370377554) was checked after correction of a duplicate-test declaration exposed by earlier run 42370253462. PR #1 and draft PR #3 are unmerged; no application source or Brain production change, deployments, secrets or live NZBs were used.
