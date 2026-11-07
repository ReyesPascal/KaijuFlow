# A4 — isolated synthetic behavior test design and execution gate

Status: TEST MATRIX PREPARED, **NO APPLICATION RUNTIME TESTS EXECUTED** as of November 7, 2026. Source baseline: c83a3c733b6394eb140a1c0a1dc500010a9f22e5. A4 does not imply production 4K or NNTP reliability.

## Non-negotiable isolation gate A4-ISO-000

1. Execute only on a disposable GitHub-hosted/other non-Brain runner with temporary, synthetic config and no production volume, Docker socket, host secret, or credentials. A true separately network-restricted container/namespace is required for the application and all mocks. Never attach it to Brain's Docker daemon.
2. Prior to importing or starting any application code, demonstrate actual network denial: outbound TCP to a documentation-only non-loopback address and arbitrary DNS must fail; in-container loopback must work for local fake servers. Record egress-denial commands, exit codes and container/namespace identity. If the gate fails, stop all runtime activity.
3. All fake NNTP, Newznab, Stremio, NzbDAV/WebDAV and proxy endpoints listen on loopback inside the same restricted network namespace. URL allowlist and test fail-fast instrumentation reject any other destination. Use fabricated tokens, NZB message IDs and text/binary samples only. No copyrighted media or live provider NZBs.
4. Use an isolated temporary working directory for config, users, cache, logs, temp downloads, database, and generated outputs. Record before/after directory hashes; prevent writes outside the directory. Stop and destroy only disposable test processes; do not touch the running Brain stack.
5. Confirm the working tree's original src/ and ui/src match the pinned import SHA before and after each test. Tests and instrumentation live under tests/a4 or tools/audit, never inside imported original source. Never merge/deploy as part of test execution.

## Planned test harness

Use Node 20 and pinned backend/UI lockfiles. Build once in a dedicated isolated runner if needed (prior CI build evidence already covers compilation). Test HTTP with fetch/supertest where appropriate and UI timing with a browser harness and controlled timers. Introduce fake NNTP TCP responder, fake Newznab XML/NZB server, fake WebDAV/NzbDAV HTTP responder supporting 200/206/416, and synthetic temporary file persistence. Do NOT start server.ts just because it compiles: confirm environment variables, bind address, startup file effects and denial gate first. Consider a subprocess boundary to reliably kill only the isolated app.

A4 matrix lives in tests/a4/cases.json. All cases are specified-not-run; expected properties are desired acceptance criteria, not claims about the original application.

## Prioritized test order

1. ISO-000 must pass first; after that test A4-HTTP-001/API JWT and manifest-key precedence; A4-SDK-002 real SDK getRouter route evaluation (both /stremio/:key and /:key), invalid key, dynamic resource/extra JSON patterns and CORS.
2. A4-DELETE-003 checks GET and HEAD with a fake WebDAV DELETE counter, legal/illegal content paths, duplicate requests, concurrent requests, failed first DELETE and 30-second dedup. Explicitly observe whether HEAD ever triggers a state-changing GET handler.
3. A4-AUTOSAVE-004 and A4-PROVIDER-005 check settings 300/500ms timers, concurrent/out-of-order responses, 400/413/500 failures, disk vs memory divergence, provider optimistic reorder, failed HTTP status and UI rollback behavior. A4-SYNC-006 checks immediate POST followed by debounced PUT on synced indexers.
4. A4-NNTP-007 and A4-ARCHIVE-008 use fabricated articles and NZBs to compare Smart/Fixed sampling, pool/backup behavior, nonresponse, missing article, yEnc/bad decode, archive inspection and cancellation.
5. A4-RANGE-009 and A4-RECOVERY-010 verify WebDAV/NzbDAV 200/206/416, Content-Range/range forwarding, seek/cancel, ready/dead/pending caches, fallback/retry/timeouts and recovery with fail-closed egress.
6. A4-PROXY-011 explores dynamic query destination handling only through fake allowlisted local endpoints and verifies that synthetic tests cannot egress.

## Evidence/exit policy

Each runtime scenario must record source commit, test harness commit, mock fixture digest, isolation proof, request method/path/status, side-effect counters, temporary file diff, start/end timing, actual result, expected invariant and any contradictory results. A pass on synthetic mocks is NOT a verified 4K benchmark or proof of compatibility with real NNTP providers. Add separate test-observed claims only after real CI/isolated execution, with a failing test recorded as a finding rather than hidden. Gate A4 runtime on an independently reviewed, fail-closed isolation implementation. Do not use REA/Ghidra or live credentials for A4 fixtures.
