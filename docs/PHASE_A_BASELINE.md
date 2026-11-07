# Phase A — upstream baseline audit and source import plan

Date: 2026-11-07. Status: **complete immutable source manifest checked (192 files / 12,132,917 bytes), partial static audit; actual full-app import, build, isolated tests, and Brain baseline capture remain pending**.

> **Scope correction:** KaijuFlow must preserve and operate the **entire** Usenet Ultimate v1.4.1 application. The health-check modules below were inspected first, but are only one subsystem in the full application. [Full-app capture contract](WHOLE_APP_CAPTURE.md) and [source manifest](upstream-v1.4.1-manifest.json) govern import fidelity, including all frontend/backend modules, binary UI media, install scripts, PDFs, dependency locks, runtime behavior, and provenance. **The complete source has NOT yet been imported.**

## Provenance and immutable reference
- Canonical upstream: `DSmart33/Usenet-Ultimate`, default branch `master`
- Release: `v1.4.1` (GitHub release); `package.json` and `ui/package.json` both say `1.4.1`.
- Exact release commit: `499efbdeb631b1b059f8aa70d07c12beaf504876`.
- Upstream `LICENSE`: MIT; `Copyright (c) 2026 Usenet Ultimate Contributors`. Git blob SHA: `5bc411160a82a757d004b351a290be3913320707`.
- This repository was already privately initialized with an independent MIT LICENSE, `Copyright (c) 2026 ReyesPascal`. **Do not overwrite or discard either notice.**
- Upstream release: https://github.com/DSmart33/Usenet-Ultimate/releases/tag/v1.4.1

## Initial source map (checked at exact tag)
| Concern | Entry points | Observed source contract |
| --- | --- | --- |
| Smart and fixed health orchestration | `src/addon/healthCheckCoordinator.ts` | Smart selects batches, stops after `smartMinHealthy` verified results or batch limit; fixed checks top N; NzbDAV library and dead-NZB pre-checks |
| Health check pipeline | `src/health/healthCheckPipeline.ts` | NZB parse, file classification, archive inspection, segment sampling and multi-provider checks |
| NNTP article verification | `src/health/articleChecker.ts` | Pipelined NNTP `STAT`, pool first then backup providers |
| Parallel worker lifecycle | `src/health/batchProcessor.ts`; `src/health/nntpConnection.ts` | Limited concurrent workers and authenticated connection reuse |
| Archive support | `src/archive/index.ts` | RAR4, RAR5, 7-Zip, ZIP signatures and header parsers |
| Stream fallback | `src/nzbdav/ultimateFallback.ts`; `src/nzbdav/fallbackManager.ts` | Existing recovery pipeline and fallback candidate tracking |
| Dead/ready caching | `src/nzbdav/streamCache.ts` | Separate pending, ready and dead-NZB caches |
| UI and settings | `src/config/accessors.ts`; `ui/src/components/overlays/HealthChecksOverlay.tsx` | Smart-mode defaults/settings and UI |
| Build | `package.json`; `ui/package.json`; `Dockerfile` | Node 20 / TypeScript backend, React/Vite frontend, multistage Docker |
| Data / credentials | `.gitignore`; `src/config/` | `.env` and `/config/` ignored; still perform independent secret scan before import |

**Observed Smart defaults:** inspectionMethod `smart`; smartBatchSize `3`; smartAdditionalRuns `1`; smartMinHealthy `1`. In the coordinator, max batches = 1 + additional runs, and successful early termination counts verified results in the inspected candidate prefix. Default health checking itself may be disabled; verify saved environment/settings rather than assuming it runs.

**Security item to investigate in Phase B:** `src/health/nntpConnection.ts` uses `rejectUnauthorized: false` on the TLS connection. That disables certificate verification and merits a scoped compatibility/security review. Do not quietly modify it during baseline import.

This is a **static partial audit only**: no isolated compilation/test run, full source-file inventory, SBOM, secrets scan, performance measurement, architecture equivalence test or Brain verification has been performed.

## Planned source import (A2) — no application code changes before A1 sign-off
1. In a **separate development checkout** with real Git binary transfer, verify all 192 files and their Git blob SHAs from the manifest (including videos, PDFs, images); verify the target `ReyesPascal/KaijuFlow` and the tag SHA; fetch and checkout the exact `v1.4.1` commit (not moving `master` or `latest`).
2. Preserve the current initial `main` commit as a rollback checkpoint (record SHA and optional `pre-import` tag). Branch `import/upstream-v1.4.1` from it.
3. Import **all 192 upstream file blobs** into the project root **without editing program behavior or dropping assets**, retaining source paths, file modes, binaries, manifests, lockfiles, Docker and installer files, docs and notices. Preserve the original upstream README exactly as `docs/upstream/README.v1.4.1.md`; preserve upstream LICENSE at the explicit third-party path below. Compare every imported file's Git blob SHA to the saved manifest. Record upstream commit and import method; do not silently overwrite the existing `README.md` or `LICENSE`.
4. Keep the existing KaijuFlow root `LICENSE` intact and preserve upstream `LICENSE` **verbatim** at `THIRD_PARTY_NOTICES/Usenet-Ultimate-LICENSE`; retain all copyright headers and attribution. Confirm both texts/hashes.
5. Exclude runtime files and credentials: `.env*` secrets, `config/`, API keys, tokens, saved provider credentials, TLS private keys, cookies and logs. Check the staged diff and scan contents before any push. Include no real NZBs or private media metadata.
6. Commit **source-only** upstream import as `chore(import): pin Usenet Ultimate v1.4.1`. Do not change Docker tags or deploy to Brain.
7. Run backend/UI builds and baseline test scenarios in an **isolated dev environment**. Compare behavior with source unchanged; record passing/failing tests, versions, hashes and immutable import SHA.
8. Merge source import only after A-phase review. Preserve a complete backout path: reset development branch to its recorded pre-import commit or revert the import commit. No Brain rollback is necessary because Brain remains untouched.

## Regression contract — to be tested, not assumed
- Smart mode: immediate stop at minimum healthy threshold, more batches if insufficient, correct max-batch limit, no unnecessary NNTP requests.
- Fixed mode: top-N inspection still works; unchanged preference and provider settings.
- NNTP: sample counts, `STAT` success/missing/timeout, connection pooling, pool+backup availability, proxy-circuit abort.
- Cache: known-ready and dead-NZB pre-checks, episode-specific filtering, timeout handling, persistence after process restart.
- Archives: RAR4, RAR5, ZIP and 7-Zip; passwords, nested archives, ISO rejection, malformed data.
- Search: multiple indexers, provider/indexer failures, deduplication and source ranking.
- Streaming: NzbDAV redirect, HTTP range/seek, no forced transcoding, original 4K quality; fallback on dead NZB and corrupted content.
- Controlled performance: identical source IDs, providers and hardware; track verified playable percentage, time to first usable stream, failed attempts, fallback recovery, first-frame delay, rebuffering and playback continuity.
- Security: secret scan and dependency audit; never log/auth-commit live secrets.

## Gate to Phase B
A1 repo/release/licensing verified plus entire 192-file tree manifest; A2 **full** source import (including non-text media) committed with each blob hash matching upstream and both license notices; A3 **whole-application** static and runtime baseline audit documented; A4 comparison test plan with isolated results and rollback verified. **Do not claim Phase A complete until all four are satisfied.**
