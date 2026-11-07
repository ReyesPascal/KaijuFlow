# One post-A4 discovery-to-stream scenario — 2026-11-07

**Result: PASS for one bounded composed integration scenario**, `INT-DISCOVERY-STREAM-001`, evidence `EV-KF-INT-001`. This is outside the closed A4 suite. No further scenario or test campaign is part of this assignment.

Original source: `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`. Test commit: `ad402bcec957184bfdde91644dc5d00a06e6a7ea` on `audit/node20-a3-baseline`. Actual inspected [Actions run 42373119985](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42373119985), [job 128405137873](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42373119985/job/128405137873), completed successfully using Node `v20.20.2`, npm `10.8.2`. The permanent [sanitized result JSON](../../../evidence/results/INT-DISCOVERY-STREAM-001.json) retains stages, boundaries, exact requests, metadata and digest.

## Executed original application stages

All original application links below pin the immutable source commit. The harness supplies external HTTP services; it does not replace the application functions listed here.

| Stage | Actual execution / assertion | Classification and gap |
| --- | --- | --- |
| Fabricated discovery | Harness fetched one localhost Newznab RSS response; original [`parseNewznabXmlWithMeta`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/parsers/newznabClient.ts) parsed total=1, title, NZB link and size | **Tested** parser; real indexer/search orchestration omitted |
| Result processing | Original [`deduplicateAndPreFilter` and `applyUserFilters`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/addon/resultProcessor.ts) retained the one fabricated movie result | **Tested** composition; one result does not exhaust filters/ranking |
| Health coordinator | Original [`coordinateHealthChecks`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/addon/healthCheckCoordinator.ts) consumed a supplied verified verdict in Fixed mode | **Tested** cached-verdict handling; NNTP checks explicitly simulated/bypassed |
| Stream construction | Original [`buildStreams`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/addon/streamBuilder.ts) generated NzbDAV tile URL, title/name, `notWebReady:false` and envelope containing original NZB URL/title | **Tested** URL/envelope and nonempty metadata; harness supplies request context |
| Route and preparation | Original [`createNzbdavStreamRoutes`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/routes/nzbdav.ts) called original [`handleStream` / `prepareStream`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/nzbdav/streamHandler.ts); initial library lookup missed, then NZB was fetched, uploaded and monitored through original [`submitNzb` / `waitForJobCompletion`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/nzbdav/nzbdavApi.ts) | **Tested** protocol interaction with fake localhost NzbDAV; no real download/unpack job |
| Discovery and delivery | Original [`findVideoFile` / `waitForVideoFile`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/nzbdav/videoDiscovery.ts) selected fake WebDAV file, preparation issued a first-byte probe, original route proxy delivered exact bytes and cache contained the selected path | **Tested** happy-path discovery/probe/proxy; no player, seek/reconnect or performance assertions |

Observed external sequence: `GET /search`; initial `PROPFIND` library miss; `GET /fixture.nzb`; multipart `POST /api?mode=addfile`; queue/history GETs; successful `PROPFIND`; `GET` with `Range: bytes=0-0`; final full-file `GET`. Synthetic API key and Basic authentication were checked by the fake service.

## Exact output and important boundaries

- Delivered HTTP **200**, `Content-Type: video/x-matroska`, `Content-Length: 64`, exact expected **64 bytes**.
- Delivered byte SHA-256: `2f487e40e16653113a45fe0c0621d2b36e4bb2aac192a5169570977adfae9d95`.
- Fake WebDAV metadata advertises **134217728 bytes (128 MiB)** to satisfy the original 100 MiB file-selection threshold. The payload remains 64 bytes. The tile's 4K/WEB-DL/HEVC and size display derive from fabricated title/metadata; they do not describe actual playable media. The observed title includes `indexer: undefined` because this harness does not add search-orchestrator provenance; no defect or metadata-completeness claim is inferred.
- The bytes are **not a decodable video**. No playback, first-frame, real bitrate, sustained throughput or 4K claim is made.
- The harness composes original compiled modules. It does **not** boot the complete server, execute the original top-level search orchestrator, or exercise manifest authentication middleware.
- The supplied verified health result bypasses real NNTP verification. Fake NzbDAV immediately reports completion; retrieval, repair, extraction and archive compatibility remain outside the executed boundary.

This is a discovery-response-to-delivered-bytes integration through original modules with explicit service simulations, not complete production end-to-end validation. Remaining evidence is listed in [VALIDATION_GAPS.md](VALIDATION_GAPS.md).

## Isolation, evidence and reproduction

The existing fail-closed network-namespace design was reused: injected failure exited before application import; the positive namespace had only loopback and proved external TCP v4/v6 and DNS denial before original modules loaded. Disposable files and cleared environment ran as `nobody`. Original `src/` and `ui/src/` SHA-256 before/after matched, and source comparison to the immutable import passed. No Brain service, production configuration, real credential, live provider/indexer or private NZB was accessed.

[Artifact 13574073895](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42373119985/artifacts/13574073895), ZIP SHA-256 `c0ef23166582cbf3dde87763cb054dc17d9f44a069403630ba5ede6fdd593aed`, contains the result JSON with 14-day retention. The permanent sanitized JSON above preserves reviewable evidence after expiry.

Reproduction, only if later explicitly requested: manually dispatch `.github/workflows/integration-isolated.yml` on the audit branch. It builds the original locked backend, then runs `tests/integration/run-ci.sh`, `in-namespace.sh` and `discovery-stream.mjs` under the existing isolation probe. Automatic triggers are removed after completion to prevent repeated runs on documentation changes. No A4 suite execution is part of this scenario's runner. The workflow initially had push/PR triggers, so the single scenario could be scheduled more than once; this report identifies the exact independently inspected run and does not count scheduling duplicates as additional coverage.

**Stop point reached:** one scenario implemented and verified; no expanded integration matrix, application fixes or performance measurements. Next authorized work is the separate [performance planning milestone](../performance/BENCHMARK_PLAN.md), tracked in [Issue #4](https://github.com/ReyesPascal/KaijuFlow/issues/4).
