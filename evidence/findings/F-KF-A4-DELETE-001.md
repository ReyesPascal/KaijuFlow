# F-KF-A4-DELETE-001 — HEAD triggers destructive WebDAV DELETE; failed call deduplicated as handled

**Classification:** test-observed synthetic runtime. **Status:** reproducible bounded finding; no patch. **Date:** 2026-11-07. **Severity for review:** high for unintended state-changing HEAD under a valid manifest-key URL; exploitability/security impact depends on URL exposure and other controls (not proven). **Source baseline:** `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`.

## Evidence

Original [`src/routes/nzbdav.ts:274-324`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/routes/nzbdav.ts#L274-L324) records dedup immediately, before the async remote call. Original [`src/routes/nzbdav.ts:397-490`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/routes/nzbdav.ts#L397-L490) defines `router.get('/library-delete')`; Express handles HEAD for a GET route when no earlier HEAD handler exists. These facts previously constituted the A3 **source-observed** concern; the following are new test observations.

In a disposable network namespace with non-loopback IPv4/IPv6/DNS blocked, an unprivileged process mounted **the actual original route implementation** behind manifest validation and directed its WebDAV DELETE requests to a synthetic local HTTP server. Test ran with original placeholder MP4 copies; no real assets were deleted. [CI run 42366142956](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42366142956):
- Invalid non-`/content/` path: 0 remote DELETE requests.
- HEAD `/stremio/<valid synthetic manifest>/nzbdav/library-delete?t=<synthetic envelope>`: HTTP 200; **1 remote DELETE**.
- GET to the same path immediately after HEAD: still **1 total remote DELETE**, showing dedup from the HEAD request.
- GET deletion to synthetic `/content/movies/FailPack` receives WebDAV HTTP 503; immediately repeated GET still results in **1 remote DELETE**, rather than retrying.

The synthetic test expected HEAD to be read-only and a remote failure to be retryable. **A4-DELETE-003 failed on those assertions.** No live server or provider was contacted; neither production exposure nor external exploitability is asserted. This is distinct from the original GET tile interaction, which deliberately deletes upon click.

## Recommendations for later separate source-change PR (NOT applied here)

Consider disallowing DELETE effects on HEAD, refusing destructive requests via unsafe method semantics only after UX/protocol review, retaining dedup only after successful deletion or marking retryable failures separately, and adding tests for concurrency, collision keys, 30-second TTL, /library-delete-all, escaped paths and unauthorized manifest access. Preserve the working Stremio action-tile flow until a tested replacement is designed. Do not silently alter the original imported baseline or merge PRs without approval.

**Reproduction:** `tests/a4/run-ci.sh` only on the GitHub-hosted, capability-isolated A4 workflow; no attempt on Brain. **Evidence:** `EV-KF-A4-BEHAVIOR-001`; **claims ledger:** `CL-KF-A4-DELETE-003`; current synthetic report artifact ZIP SHA-256 `0773c69cc29381259e9cf11d004a851bfecc4a09b9bcd5283ccb070ea04d9857`.
