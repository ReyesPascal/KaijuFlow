# NNTP evidence and future decisions

Source pin, labels and evidence IDs: see [README](README.md).

## Executed evidence

All A4 rows below are **tested**, bounded to the stated fixture. Canonical A4 run [42372236463](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42372236463), job `128402557244`, inspected logs at audit head `25e7971a2dc5cd53985173fe178cf95dac608230`; suite conclusion intentionally failure. Evidence `EV-KF-A4-CLOSURE-001`, with historical `EV-KF-A4-EXPANDED-017`.

| Case | Actual observation | Limits / reproduction |
| --- | --- | --- |
| A4-PROVIDER-005 | CRUD, reorder and unauthorized access assertions pass | In-memory callbacks; no real provider. Source N02. |
| A4-NNTP-HANDSHAKE-008 | Fake 200/381/281 exchange, two credential commands; missing fields 400, authenticated endpoint 200 | Plain loopback only; N03. |
| A4-STAT-FALLBACK-009 | Two pool commands, one backup command; two IDs found, zero remaining | One fabricated fallback topology; N06/N08. |
| A4-ARCHIVE-GROUP-010 | One group, three parts, three samples and ordered segments pass | No exhaustive real archives; N07/N11. |
| A4-YENC-011 | Three BODY bytes decode to ABC; 430 rejected; four signature detectors pass | No whole-file CRC or reassembly coverage; N10. |
| A4-HEALTH-SAMPLING-016 | Three and seven STAT samples pass; missing sample yields blocked | Availability sampling only; N07. |
| A4 coordinator cases | Three pass with pre-existing synthetic verdicts | No actual NNTP orchestration in these cases; N13. |

Reproduction: inspect `tests/a4/synthetic.mjs`, `coordinator.mjs`, and the manual-only `.github/workflows/a4-isolated.yml` at the audit branch. They compile original modules, run under the existing network namespace gate and leave known assertions red. A4 is closed: do not rerun or expand without a new explicit instruction. Source links in N01–N13 pin the app inputs independently of the audit fixture commits.

The separate **tested** integration `INT-DISCOVERY-STREAM-001` passed [42373119985](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42373119985), job `128405137873`, audit test commit `ad402bcec957184bfdde91644dc5d00a06e6a7ea`; `EV-KF-INT-001`. It proves composed discovery-to-byte delivery with a synthetic prior health verdict. It does not add NNTP throughput or live verification evidence. Permanent [sanitized result](../../../../evidence/results/INT-DISCOVERY-STREAM-001.json).

## Concerns and proposals

| ID | Classification and source basis | Decision / missing evidence |
| --- | --- | --- |
| P01 / engine extraction | **Proposed**; N01/N05/N10 reveal separable verification, retrieval and archive seams | Potential KaijuNNTP API could expose bounded connection acquisition, STAT, BODY, cancellation, typed errors and metrics. No implementation, compatibility guarantee or direct media engine is established here. Keep the repository private and dormant until measured benefit justifies extraction. |
| P02 / TLS and secrets | **Source-observed concern**, N02/N03/N04; [F-KF-SEC-001](../../../../evidence/findings/F-KF-SEC-001.md) | TLS peer validation is disabled, TCP sends credential commands without TLS, pool key omits TLS/password. Credential storage/access/log review remains incomplete. Propose a separately reviewed security design, with certificate and rotation tests; no fixes authorized now. |
| P03 / concurrency | **Proposed**, N04/N05/N08 | Measure active/idle sockets, wait time, quota responses and worker fanout before proposing provider-aware bounds, backpressure or reuse changes. Pool stack size is not evidence of an enforced provider cap. |
| P04 / retrieval and parser cost | **Unknown**, N09/N10/N11 | Record BODY latency, decoded bytes/s, XML/archive parsing CPU/heap, memory held per request, failed checks and retries. No performance measurements were made. Propose bounded incremental decode/reassembly only after baseline evidence. |
| P05 / sampling reliability | **Proposed**, N07/N12 | Compare sample decisions with complete legally controlled retrievals and failures before changing sampling/retry policy. Do not interpret verified status as full NZB completeness. |
| P06 / direct or hybrid media delivery | **Proposed**, N01/N10 and [NzbDAV delivery map](../nzbdav/ARCHITECTURE.md) | Evaluate seek mapping, archive constraints, full integrity and recovery against baseline in Issue #4. Preserve NzbDAV until alternatives meet the measurement gates. |

No concern above establishes production incident frequency. Remaining unknowns require the [gap report](../../audit/VALIDATION_GAPS.md), not another synthetic campaign in this assignment.
