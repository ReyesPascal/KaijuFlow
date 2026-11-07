# Development roadmap and checkpoints

All work is private. The stable Brain (ThinkPad) Usenet Ultimate + NzbDAV deployment and Hisense TV direct LAN/Wi-Fi playback are **untouchable without explicit approval**. Tailscale is not part of the known-good path. No production deployment is authorized.

| Phase | Scope | Required checkpoint / exit gate |
| --- | --- | --- |
| A — Baseline | Repository verification, upstream v1.4.1 pin, **complete 192-file application import including binary media**, MIT notices, **end-to-end application** audit and baseline tests | `A1-repos-upstream`, `A2-source-import`, `A3-static-audit`, `A4-baseline-tests`; immutable commit SHAs and evidence |
| B — Dependencies/security | Node/UI dependencies, vulnerabilities, sensitive data, licensing, API/compatibility; NNTP TLS validation review | `B1-dependency-review`, `B2-security-review`; documented fixes proposed separately |
| C — Smart health checks | Reliability, sampling, provider fallback, cache awareness, stop conditions, timeouts; no unjustified rewrites | `C1-regression-tests`, `C2-reliability-improvements`; pre/post metrics |
| D — Stream reliability | Ultimate Fallback, dead NZB cache, range/seek, NzbDAV, true 4K direct streaming, performance | `D1-fallback-cache`, `D2-playback-metrics`; stable configuration preserved |
| E — KaijuNNTP decision | Measure whether isolated verification service improves reliability/latency/maintainability | `E1-extraction-ADR`; implement separate engine only if justified |
| F — Integration/deployment | Isolated integration tests, private images, recovery rehearsal, controlled rollout proposal | `F1-isolated-integration`, `F2-rollback-ready`, `F3-deployment-approval`; explicit approval before any live change |

## Checkpoint procedure
Every checkpoint records: date/owner, phase/task ID, immutable upstream SHA, branch + resulting Git commit SHA, files changed, tests run and results, known risks, deployment state, **reversal instructions**, and the next executable step. Store current state in root `HANDOFF.md`, detailed findings under `docs/`, and use small descriptive Git commits or PRs. A proposed checkpoint is not 'complete' until artifacts are committed and independently verified on GitHub.

## Whole-application scope

The development baseline is the **entire Usenet Ultimate v1.4.1 release**, not merely Smart-mode checking. Preserve backend, frontend and static assets; search/indexers/providers; Smart and Fixed health modes; archive inspection; NzbDAV streaming; original-quality playback; fallback and caches; config/migrations; deployment scripts; docs; licensing and all binary assets. See [Whole App Capture](WHOLE_APP_CAPTURE.md) and [complete source manifest](upstream-v1.4.1-manifest.json). Phase A source import is not complete until all 192 original blobs match upstream hashes.

## REA investigative baseline (Phase A)

After the complete 192-file source import is hash-verified, run **Reverse Engineer Anything (REA)** in an isolated development environment. In A3, trace the complete application's modules and data flows; in A4, inspect an isolated instance's runtime behavior before any code modifications. Keep REA evidence linked to the exact upstream commit; supplement it with conventional source review, builds and regression tests. Repeat targeted traces in phases B–D after changes. **Do not install or run REA against Brain's working containers.** See [REA Audit Plan](REA_AUDIT_PLAN.md).

## Phased discipline
- Branches: `import/upstream-v1.4.1`, then `audit/<subject>`, `fix/<subject>`, `perf/<subject>`. Keep `main` stable.
- No code modifications until Phase A baseline is signed off. Separate changes from tests and measure against unchanged upstream.
- Use sanitized fixture NZBs and fake NNTP responses for unit tests; do not commit real account/provider configuration.
- Benchmark reproducibly: same hardware, network path and candidate NZBs; distinguish article availability from network/player performance.
- Keep KaijuNNTP independent but dormant until the Phase E architecture decision.
- Rollback priority: preserve the working Brain containers; for Git changes revert the scoped commit/PR; for later approved deployment keep prior image digest/config backup and explicit restoration procedure.
