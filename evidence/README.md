# KaijuFlow evidence and findings index

**Canonical entry point for the whole-application A3/A4 audit.** This directory is **additive and source-adjacent**: all original Usenet Ultimate v1.4.1 paths, file bytes, Git blob IDs, executable modes and licenses remain unchanged. No inline audit notes should be inserted into original imported files.

**Immutable upstream source baseline:** `DSmart33/Usenet-Ultimate@499efbdeb631b1b059f8aa70d07c12beaf504876`. **Imported code baseline:** `ReyesPascal/KaijuFlow@c83a3c733b6394eb140a1c0a1dc500010a9f22e5`. **Audit branch:** `audit/node20-a3-baseline`; [draft PR #3](https://github.com/ReyesPascal/KaijuFlow/pull/3) targets the unchanged import branch, not `main`. Import review [PR #1](https://github.com/ReyesPascal/KaijuFlow/pull/1) remains unmerged.

## Navigate the audit

| Start here | Purpose |
| --- | --- |
| [Next-session runbook](../docs/kaijuflow/audit/NEXT_SESSION.md) | Exact saved checkpoint and first A3-ROUTE-001 analysis deliverable |
| [A3-ROUTE-001 first-pass route/UI matrix](../docs/kaijuflow/audit/A3-ROUTE-001.md) | 63 explicit endpoint declarations, 21 representative UI/action chains, side effects, guard classification and unknowns |
| [Execution plan](../docs/kaijuflow/audit/EXECUTION_PLAN.md) | Research-validated stages 0–5, tool choice and exit gates |
| [Original independent research report](../docs/kaijuflow/audit/RESEARCH_REPORT_2026-11-07.txt) | Exact user-supplied report archived for provenance; **illustrative commands may contain assumptions** and the corrected execution plan is authoritative |
| [Subsystem index](index/subsystems.jsonl) | Stable subsystem IDs, source anchors, status and coverage gaps |
| [Evidence manifest](index/manifest.jsonl) | Who/what produced each piece of evidence, source commit, tool version, and storage policy |
| [Claims ledger](index/claims.jsonl) | Atomic claims with evidence links, certainty, validation and staleness fields |
| [Artifact ledger](index/artifacts.jsonl) | Build/evidence artifacts, retention and SHA-256 identity (no fabricated hashes) |
| [Findings guidelines](findings/README.md) | Individual finding format, review workflow and security rules |
| [A3 v0.1 source architecture](../docs/kaijuflow/A3_STATIC_ARCHITECTURE.md) | Previously completed source-backed 13-subsystem inventory (NOT full A3) |
| [Earlier REA decision record](../docs/kaijuflow/REA_DECISION_AND_PLAN.md) | Original tool choice and alternatives; retained for history |
| [Import handoff](../docs/kaijuflow/HANDOFF.md) | Original import checkpoint and rollback; some steps have since advanced |
| [Issue #2](https://github.com/ReyesPascal/KaijuFlow/issues/2) | Durable session handoffs and current evidence updates |

> Relative links are relative to `evidence/`. The GitHub PR and Issue hold cross-session status. Check their latest comments before asserting a milestone; old documents may retain historical pending statuses.

## Current gate (2026-11-07)

| Work | State | Verified evidence |
| --- | --- | --- |
| A2 exact upstream import | Verified by independent tree comparison | 192/192 original blobs and modes, including all 14 binaries, import commit above |
| PR #1 review | Commented, awaiting owner merge decision | PR open and unmerged |
| Node 20 backend + UI build | Pass, independent GitHub-hosted execution | [Actions run 42355054013](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42355054013) |
| A3 whole-app static audit | Partial, 13 source-observed subsystem boundaries | [A3 v0.1](../docs/kaijuflow/A3_STATIC_ARCHITECTURE.md) |
| REA tool availability | Verified; existing REA 6.8.0 + separate Node 24.22.2 | Brain Tunnel CLI version command; **not** a REA app scan |
| REA KaijuFlow artifact inspection | Not yet run | Missing |
| A4 synthetic behavioral parity | Not yet tested | Missing |
| Live 4K throughput/seek reliability | Not benchmarked | Missing |

## Index contract

**One ID per subsystem, evidence record, claim and artifact.** Store small machine-readable JSONL records in `index/`. Write explanatory Markdown in `findings/` and `docs/kaijuflow/audit/`. Append new records only when real evidence is available; a `pending` item is not a success.

- Evidence types: `source-observed`, `REA-observed`, `test-observed`, `measured`, and `unverified`. These are *not interchangeable*. A static route candidate never proves execution; tests under fake services never prove 4K throughput.
- References use exact repo-relative source paths **plus pinned source commit**, optional symbol, line range, and Git blob SHA (when checked). Use GitHub blob permalinks (`/blob/<fullSHA>/path#Lx-Ly`) in human findings. When the source changes, mark old claims `stale` or `needs-revalidation`; don't silently retarget them to a new file.
- Preserve contradictory and negative results, unknown branches, analysis limits and parse failures. Never infer 100% coverage from exit 0.
- `manifest.jsonl` indexes the underlying evidence and whether it is recorded (human/source), independently reproduced (test), or only tool-reported.
- `artifacts.jsonl` can name expected artifacts but must not invent digests. A raw artifact without a real content hash is **not retained evidence**.

## What belongs in Git?

**Commit:** this index, schemas, reviewed source maps, small scrubbed REA projections, synthetic fixtures/test definitions, reproducible commands, verification summaries, test/benchmark aggregates and ADRs.

**Do not commit by default:** full raw REA Evidence (can be hundreds of MB), source dumps, unreviewed logs, huge browser traces, media/NZBs, real provider credentials, private request headers, host identifiers, secrets or live configuration. Raw output belongs in a restricted, non-production audit directory with hash, manifest, explicit retention/backup owner and reference in the index. Short-lived CI artifacts alone are **not long-term preservation**.

**Production protection:** Brain's working Usenet Ultimate, NzbDAV, Manifexus, PTP, Docker configuration, network and credentials are outside the audit. All application execution uses a separate, disposable clone with synthetic config and network-isolated mocks. Brain Tunnel host commands still require their exact local approval. No merge or deployment without owner approval.

## Local validation

See `index/schema/` for schema specifications. CI lint/consistency tests should detect duplicate IDs, malformed JSONL, dangling support IDs, missing source commit pins, and stale/absent SHA-256 for claims marked as retained/verified. Source coverage and documentation validity are separate from behavioral coverage and from performance.

**Append-only evidence history:** New analysis can supersede claims via explicit `supersedes` and `status` metadata; never erase an inconvenient observation just because code changed.

## New A3-ROUTE-001 source evidence (2026-11-07)

- [Pinned first-pass UI/HTTP matrix](../docs/kaijuflow/audit/A3-ROUTE-001.md) extends A3 v0.1 without modifying any original source file. The matrix covers 63 explicit route declarations and 21 high-value UI/action chains; SDK-generated routes, nested callbacks and runtime behavior remain unverified.
- Stage 0 private detached checkout verified at import SHA with clean Git status and both original lockfile SHA-256 identities. **No runtime boot or network-denial test has been conducted**, and no live services changed.
- New manifest IDs: `EV-KF-STAGE0-001`, `EV-KF-A3-ROUTE-001`. Claims: `CL-KF-STAGE0-CHECKOUT-001`, `CL-KF-A3-ROUTE-001`, `CL-KF-A3-GET-DELETE-001`. The latter records state-changing Stremio GET actions as a source observation; actual exploitability is unknown.
- A read-only Codex source review used only a sanitized 47-file original-source snapshot, separated from all audit notes and unrelated work. It verified a bounded auth-chain map; it did not run the app, change files or make network requests. The canonical evidence remains independently inspected source.
- Next: confirm frontend callback edges and Express/SDK routes using TypeScript AST, then synthetic auth, destructive-GET and range/fallback tests in a network-restricted disposable runtime. REA artifact inspection remains a distinct later gate; no KaijuFlow scan was performed.


## A3-ROUTE-002: original-source TypeScript AST checkpoint (2026-11-07)

- [A3-ROUTE-002 source map and side effects](../docs/kaijuflow/audit/A3-ROUTE-002.md) and [full AST UI network/route/mutation projection](../docs/kaijuflow/audit/A3-ROUTE-002-AST.md). The original-source-only extractor is [tools/audit/extract_route_graph.cjs](../tools/audit/extract_route_graph.cjs), executed by the [isolated A3 AST workflow](../.github/workflows/a3-ast.yml).
- [GitHub Actions 42361312353](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42361312353) PASS, TypeScript 5.9.3: 38 UI and 105 backend TS/TSX files, 0 parse errors, 603 JSX on-event bindings, 64 UI network expressions (22 dynamic), 40 React effects, and 64 explicit Express route declarations including the non-API SPA GET wildcard. This is **syntactic AST coverage**, not complete React cross-module callback reachability or runtime validation.
- Evidence records `EV-KF-A3-ROUTE-002`, `EV-KF-A3-ROUTE-002-AST`, `EV-KF-A3-SONNET-REVIEW-001`; four new claims `CL-KF-A3-UI-AST-002`, `CL-KF-A3-CONFIG-PERSIST-002`, `CL-KF-A3-STREMIO-002`, `CL-KF-A3-WEBDAV-DELETE-002`; hashed short-lived artifact `ART-KF-A3-ROUTE-002-AST-001`. The raw machine graph is reproducible, with a 14-day private CI artifact; the permanent compact projection is in Git.
- Independent Claude Sonnet 5.5 Medium source-excerpt review completed with tools disabled. Its suspected failure modes are hypotheses, not observed vulnerabilities, and source contradictions were corrected. Codex read-only scratch analysis is recorded as bounded/partial unless its final report is independently retrieved.
- Source-observed durable effects: settings/indexer/provider changes write `config/config.json` through temp+rename; auth/manifests write `config/users.json`; cache and fallback files persist separately; GET-triggered WebDAV media deletion is guarded and deduplicated but not runtime-tested.
- **SDK source check completed**: [locked SDK route implementation review](../docs/kaijuflow/audit/A3-ROUTE-002-SDK.md), [CI run 42362133211](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42362133211) PASS. New IDs: `EV-KF-A3-SDK-002`, `CL-KF-A3-SDK-GETROUTER-002`, `ART-KF-A3-SDK-AST-002` (artifact 13569588096, ZIP SHA-256 `3dcfeaa731e845d78d3f7b37516f367da73db4653c3e00fa17ee347226fdd0db`, expires 2026-11-21). SDK `getRouter` manifest and resource declarations verified from pinned package, not runtime-tested. `serveHTTP` helper routes are not mounted by KaijuFlow.
- **Next review gates:** resolve dynamic JSX prop/callback edges; test SDK 1.6.10-generated route matching with mock HTTP; isolated mock A4 tests of auth, delete replay/HEAD, settings write failure, Smart/Fixed, HTTP Range and fallback. Do not rerun completed builds, merge PRs, or touch Brain production.

## A3-ROUTE-003 / A4 design checkpoint (2026-11-07)

- [Typed callback evidence](../docs/kaijuflow/audit/A3-ROUTE-003.md): 261 syntactically bound React callback props (167 hook-return origins), 22 dynamic URLs; [isolated CI 42363448497](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42363448497) PASS, zero original-source changes. This is not complete interprocedural runtime closure.
- [A4 isolation plan](../docs/kaijuflow/audit/A4_ISOLATED_TEST_PLAN.md) and [12-case test matrix](../tests/a4/cases.json) are **planning only**; no application started, no network isolation gate executed, no synthetic behaviors tested.
- New evidence: EV-KF-A3-TYPED-003, EV-KF-A3-AGENTS-003 and EV-KF-A4-DESIGN-001. Claims: CL-KF-A3-CALLBACK-003, CL-KF-A3-PROVIDER-003, CL-KF-A3-AUTOSAVE-003 and CL-KF-A4-FIXTURES-001. Artifact: ART-KF-A3-TYPED-003 (CI ZIP SHA-256 preserved in ledger).
- Next gate: implement and separately validate disposable network-denied A4-ISO-000 before running the app, then run high-priority auth/SDK, deletion and autosave mock scenarios. Keep all original files immutable, Brain untouched and both PRs unmerged.


## A4-ISO-000 isolated runtime evidence — 2026-11-07

The [network-denial gate and behavior results](../docs/kaijuflow/audit/A4-ISO-000.md) are indexed as `EV-KF-A4-ISO-000` and `EV-KF-A4-BEHAVIOR-001`; [GitHub Actions 42366142956](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42366142956) proves A4-ISO-000 **PASS** even though the combined workflow is **FAIL** on an observed deletion safety assertion. In synthetic scoped module tests, JWT auth and SDK routes passed, backend sequential settings persisted, and [F-KF-A4-DELETE-001](findings/F-KF-A4-DELETE-001.md) records a HEAD-triggered mock WebDAV DELETE plus failed-request deduplication. No original files changed and no Brain production touched. Full React autosave races, NNTP, archives, Range and streaming remain unverified.
