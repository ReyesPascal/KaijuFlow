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
