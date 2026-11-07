# Development roadmap

KaijuFlow preserves the entire upstream application. Each phase uses scoped branches and recorded evidence before moving to the next gate.

| Phase | Work | Acceptance gate |
| --- | --- | --- |
| A — Baseline | A1 provenance; A2 full source import; A3 architecture audit; A4 behavioral baseline | 192 verified blobs and modes, both notices, secret scan, isolated backend/UI builds, reviewed import, complete architecture map and regression evidence |
| B — Dependencies and security | Dependency/licensing review, sensitive-data handling, API compatibility, NNTP TLS validation | Scoped fixes and compatibility/security evidence |
| C — Health reliability | Smart and Fixed modes, sampling, multi-provider fallback, cache awareness, stop conditions, timeouts | Synthetic regression fixtures and comparable pre/post metrics |
| D — Streaming reliability | Ultimate Fallback, ready/dead caches, NzbDAV, HTTP range/seek, original-quality 4K playback | Failure recovery and playback measurements on equivalent hardware and sources |
| E — KaijuNNTP decision | Evaluate service extraction against measured latency, reliability, and maintainability | Written architecture decision before implementing a separate verifier |
| F — Integration and deployment | Isolated integration, private images, recovery rehearsal, rollout proposal | Recorded image/config rollback procedure and explicit production approval |

## Remaining baseline work

After A2, retain the planned Reverse Engineer Anything (REA) investigation for A3/A4. Evaluate its installation and permissions separately before use. Trace UI → APIs → search/ranking → archive and NNTP verification → NzbDAV/fallback/caches/settings in an isolated development instance. Record tool versions, source/artifact hashes, observed and unverified subsystems, and scrubbed traces. Supplement REA with conventional source review and independent tests; a scan alone cannot establish full coverage.

A4 uses fabricated credentials, synthetic NZBs, and stub NNTP/provider responses. Cover Smart early termination and batch limits, Fixed top-N behavior, pool/backup providers, timeout and cancellation, ready/dead cache persistence, episode filtering, RAR4/RAR5/7-Zip/ZIP and malformed/password-protected archives, search failures/deduplication, fallback, range/seek, and original-quality playback. Measure verified playable percentage, time to first usable stream, failed attempts, fallback recovery, first-frame delay, rebuffering, and continuity with equivalent inputs and hardware.

Checkpoint records belong in [HANDOFF.md](HANDOFF.md); technical findings and decisions belong in [AUDIT.md](AUDIT.md). Record immutable commits, tests/results, risks, rollback, and the next executable step. A2 does not establish A3/A4 completion. Do not modify application behavior before the Phase A baseline is reviewed. Brain, its containers, and production configuration remain untouched; stable direct LAN/Wi-Fi playback is a protected requirement.
