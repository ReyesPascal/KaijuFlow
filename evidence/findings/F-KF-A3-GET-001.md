# F-KF-A3-GET-001 — state-changing library actions on manifest-key GET URLs

**Date:** 2026-11-07  
**Status:** source-observed, pending synthetic behavioral/security tests  
**Classification:** A3 authorization and side-effect seam; not an established vulnerability  
**Severity:** not assigned (impact depends on manifest-key secrecy, tile binding, path validation and replay guarantees)  
**Claim:** `CL-KF-A3-GET-DELETE-001`  
**Evidence:** `EV-KF-A3-ROUTE-001`  
**Pinned source:** `ReyesPascal/KaijuFlow@c83a3c733b6394eb140a1c0a1dc500010a9f22e5`

## Source anchors

- [`src/server.ts:205-212`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/server.ts#L205-L212): two mount families, both applying `validateManifestKey` before NzbDAV stream router.
- [`src/auth/authMiddleware.ts:39-47`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/auth/authMiddleware.ts#L39-L47): manifest-key lookup and last-used update, separate from the JWT-protected `/api` boundary.
- [`src/routes/nzbdav.ts:397-441`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/routes/nzbdav.ts#L397-L441): GET `/library-delete` parses packed tile input, requires path/marker fields, runs `validateDeletePath`, deduplicates repeat Range probes, calls `runWebdavDelete` and on success invalidates search/cache and history.
- [`src/routes/nzbdav.ts:441-491`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/routes/nzbdav.ts#L441-L491): GET `/library-delete-all` retrieves the target list by token, validates each target and invokes deletion in a loop; records success/failure counts.
- [`src/routes/nzbdav.ts:315`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/routes/nzbdav.ts#L315): outbound WebDAV deletion uses HTTP `DELETE` with a timeout.
- [`src/routes/nzbdav.ts:221-265`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/routes/nzbdav.ts#L221-L265): separate GET `/library-bypass` marks one-shot bypass state; depending on settings it can invalidate search cache (non-destructive but stateful).

## Proven versus unknown

**Verified in source:** A client GET under a valid manifest-key route may request a library action that eventually issues WebDAV DELETE; the handler includes validation and short-lived deduplication. Stremio action-tile playback makes GET requests a purposeful interaction model.

**NOT verified:** Whether arbitrary third-party GETs can pass packed-tile validation, any authorization boundary failure, cross-user leakage, path traversal, browser prerender/prefetch hazards, replay after dedup TTL, idempotence across restarts, or an unintended library deletion. No real credentials, video, NZB, WebDAV library or production request has been used in this audit.

## Required isolated A4 fixtures

1. Invalid/expired/revoked manifest key must be rejected before action, including both URL mount families.
2. Malformed packed token, missing `sk`/`p`, traversal, URL-encoded path and wrong-scope target must not delete synthetic files.
3. Valid one-file and pack deletion, repeated Range/seek probes, concurrent requests and delete-all multi-target handling.
4. Dedup window expiry, restart boundary, dangling delete-all token and target rotation; document exactly-once versus best-effort semantics.
5. Simulated external URL activation/prefetch and replay against fake WebDAV only; determine whether additional binding/confirmation is required while preserving supported Stremio controls.
6. Record outbound call count, expected/actual fake WebDAV state, HTTP status, response body identity and source/fixture digests.

## Action boundary

Do not change the working endpoint behavior until synthetic proof and product-compatible mitigation are reviewed. NzbDAV is retained as the known-good production path. Original source bytes remain unchanged. Record any future correction with a new evidence record, rather than replacing this observation.
