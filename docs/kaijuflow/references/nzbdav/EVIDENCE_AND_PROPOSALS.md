# NzbDAV evidence, unresolved behavior and comparison criteria

Source pin, labels and evidence IDs: see [README](README.md).

## Executed evidence

A4 is officially closed as a bounded synthetic milestone. Inspected canonical [run 42372236463](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42372236463), job `128402557244`, audit head `25e7971a2dc5cd53985173fe178cf95dac608230`: backend **15 PASS / 2 intentionally RED**, React **3 PASS / 1 intentionally RED**, coordinator **3 PASS**, restart/corruption **2 PASS**. Original source hashes and fail-closed gate passed. The failed workflow conclusion preserves the unresolved defects. `EV-KF-A4-CLOSURE-001` summarizes these observations; historical expanded evidence is `EV-KF-A4-EXPANDED-017`.

| Case / classification | Actual result | Limits and source rows |
| --- | --- | --- |
| A4-RANGE-PROXY-012 — tested | Fake WebDAV 200, 206 and 416 recovery pass | Small bytes/local HTTP; D08/D09, not sustained seek/playback evidence. |
| A4-PROXY-FALLBACK-014 — tested | Upstream 404 leads to 302 fallback URL with same origin/no-Range state | Redirect wiring only, not full UF candidate resolution; D12/D13. |
| A4-CACHE-015 — tested | Broken-path mark/clear and bypass one-shot behavior pass | Single-process markers only; D12. |
| A4-CACHE-RESTART-021 — tested | Separate writer/reloader retain ready=true, dead=true, counts 1/1 | Original save contract followed; D11, not power-loss proof. |
| A4-CACHE-CORRUPT-022 — tested | Invalid ready/dead JSON loads zero entries and process survives | No guarantee for all corruption/storage faults; D11. |
| A4-DELETE-003 — tested, intentionally red | HEAD causes one remote DELETE; failed single-delete HTTP 503 replay remains one attempt | Original defect remains untouched; D14. |
| A4-DELETEALL-007 — intentionally red, evidence caveat | Latest replay count 1→1, but upstream was 204 | Latest run does not re-demonstrate failed-503 replay; retain prior documented finding without inflating evidence; D14. |

Reproduction uses the saved `tests/a4/` fixtures and manual-only A4 workflow on the audit branch, with original modules compiled from the pin and no-egress namespace proved before imports. No additional A4 tests or reruns are required by this reference.

## Separate integration result

**Tested:** `INT-DISCOVERY-STREAM-001`, `EV-KF-INT-001`, [run 42373119985](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42373119985), job `128405137873`, audit fixture commit `ad402bcec957184bfdde91644dc5d00a06e6a7ea`, PASS. The [permanent sanitized JSON](../../../../evidence/results/INT-DISCOVERY-STREAM-001.json) records every fake request, metadata and byte digest. The original modules parsed fabricated Newznab XML, processed a result, consumed a pre-verified health verdict, built a NzbDAV URL, downloaded/uploaded the synthetic NZB, polled fake queue/history, discovered/probed WebDAV and proxied **64 exact bytes with HTTP 200**. SHA-256: `2f487e40e16653113a45fe0c0621d2b36e4bb2aac192a5169570977adfae9d95`.

**Simulated boundaries:** no actual NNTP health/retrieval or NzbDAV unpacking; fake job completes immediately; listing advertises 128 MiB solely to pass the original 100 MiB selection threshold. Actual body is 64 non-decodable bytes. Harness composes original modules; full server/search orchestration, manifest middleware, player decoding, seeking, direct/pipe mode comparison and Ultimate Fallback are outside this scenario. Reproduce only if explicitly requested using `tests/integration/` and its manual-only workflow; do not expand into another campaign.

## Performance and security decision ledger

| ID / classification | Source basis | Future evidence / proposal |
| --- | --- | --- |
| DP01 — unknown performance | D03–D10 | Measure search-to-tile, grab/upload, queued/processing, WebDAV listing/probe, first byte, player first frame and sustained byte rate separately. Immediate localhost responses cannot predict real processing time. |
| DP02 — unknown resources | D08/D10/D11 | Measure per-stream and concurrent CPU, RSS/heap, buffers, file descriptors, active sockets, disk read/write and network use. Configured 128/8 MiB buffers are not measurements or proof of faster playback. |
| DP03 — proposed NzbDAV optimization | D04–D10 | In a separately authorized benchmark environment, change one variable at a time (buffer/connection settings or retrieval path). Preserve original baseline and record version/config diffs; implement no tuning now. |
| DP04 — unknown reliability | D10–D13 | Measure real stalls, reconnect bytes, source/provider failure recovery, cache warm/cold, file eviction/replacement and fallback success. Synthetic 404 redirection is not continuous playback recovery. |
| DP05 — proposed direct/hybrid comparison | D01–D13 and [NNTP map](../nntp/ARCHITECTURE.md) | Require identical source bytes and original bitrate; evaluate startup/first frame, seeks, rebuffer, throughput headroom, archive compatibility, connection quotas, resource use, fallback, client compatibility and operational complexity. A faster STAT check alone is not a superior stream engine. |
| DP06 — proposed security review | D14/D15 | Separately review credential-bearing URLs, log/cache access, TLS peer validation, redirect destinations, auth/tenant boundaries and destructive route semantics. Findings remain documentation-only; no source fixes authorized. |

[Issue #4](https://github.com/ReyesPascal/KaijuFlow/issues/4) and the [benchmark plan](../../performance/BENCHMARK_PLAN.md) define the distinct future milestone. Keep NzbDAV as the known-good solution until alternatives meet measured acceptance criteria. Real service/playback evidence is missing as listed in the [gap report](../../audit/VALIDATION_GAPS.md); no production benchmarking or Brain access is authorized here.
