# Phase A REA investigation plan (Reverse Engineer Anything)

**Decision:** Run REA in **Phase A** after the complete v1.4.1 application import (A2) is hash-verified, before modifying app code. Track findings under **A3** (static) and **A4** (isolated runtime). This plan is **not yet executed**. Use REA as supporting evidence, not a substitute for source review, builds and integration tests.

## A3 — full-application architecture and code mapping
- Only in an **isolated developer environment**, install/evaluate REA with explicit approval of its installation plan, inspect tool permissions/dependencies and check CLI or MCP readiness.
- Give REA the complete pinned upstream source and/or a locally built JavaScript target where appropriate. Trace UI actions through APIs, indexer searching, metadata/title resolution, ranking, archive checks, Smart/Fixed NNTP verification, NzbDAV/WebDAV redirects, fallback, caching and settings.
- Produce a documented module-and-data-flow map identifying service boundaries, side effects, error paths, settings persistence, cache persistence and concurrency.
- REA's JavaScript analysis may apply to built code; the TypeScript source itself remains the primary reference. A generic REA scan does **not** prove complete coverage. Maintain a per-subsystem coverage checklist with explicit `observed` / `unverified` labels.

## A4 — isolated behavior baseline
- Run a disposable instance of the exact v1.4.1 checkout, in an isolated dev namespace, with fabricated credentials, synthetic NZBs, stub NNTP/provider responses and no private runtime data.
- Trace real request flows, cold/warm cache, timeout and failure cases, HTTP range/seek, fallback behavior, UI settings, and provider/indexer errors.
- Record REA version, source SHA, artifact SHA, experiment setup, observation evidence, API/runtime traces with secrets scrubbed, and independent test outcomes. Compare with the static architecture map. Keep sensitive headers and tokens out of logs and git.
- Keep current working Brain Usenet Ultimate and NzbDAV containers unchanged. No live profiling or attaching REA to Brain without separate explicit approval. A lab instance, not Brain, is the default target.

## After improvements
- Re-run targeted REA probes for changed workflows in Phases B–D; in Phase F use the original baseline for acceptance comparisons.
- Measure the same sources/hardware to establish any performance claims; REA does not itself prove improved 4K streaming or reliability.

## Acceptance gate
A3 passes when the complete feature inventory has a source-linked architecture map and documented REA/static gaps. A4 passes when the unmodified release has repeatable integration outcomes and behavioral traces in the isolated test environment. **Neither is complete until executed and validated.**

Reference: https://rea.tools/ and https://github.com/morluto/rea
