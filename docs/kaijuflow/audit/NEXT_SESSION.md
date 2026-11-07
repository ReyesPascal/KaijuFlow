# KaijuFlow — next session: begin A3 analysis

**Checkpoint date:** 2026-11-07
**Purpose:** Start source-level A3 whole-app audit without redoing the completed import checks, Node20 compile, REA installation discovery, or evidence-index setup. The *first executable analysis* has **not** yet started. This is the exact recovery/runbook.

## GitHub source of truth (verify again before acting)

| Item | Verified at handoff |
| --- | --- |
| Private main repo | `ReyesPascal/KaijuFlow` |
| Main planning checkpoint | `main@1d35e9088f7abb5a8b907605b4b06a8960557540` |
| Rollback | `archive/pre-upstream-import` retains original planning checkpoint |
| Upstream imported baseline | `import/upstream-v1.4.1@c83a3c733b6394eb140a1c0a1dc500010a9f22e5` |
| Upstream provenance | `DSmart33/Usenet-Ultimate` v1.4.1 @ `499efbdeb631b1b059f8aa70d07c12beaf504876` |
| Import PR | [#1](https://github.com/ReyesPascal/KaijuFlow/pull/1) — open, unmerged, targets `main` |
| A3 audit branch | `audit/node20-a3-baseline` |
| Audit PR | [#3](https://github.com/ReyesPascal/KaijuFlow/pull/3) — **draft**, open, unmerged, targets *import branch*, current head at time of handoff: see PR/GitHub because this document itself adds a commit |
| Tracking issue | [#2](https://github.com/ReyesPascal/KaijuFlow/issues/2) |
| KaijuNNTP | Private, not yet a separate implemented engine; no work here this session |

**Prior independent checks remain valid where their input SHA has not changed:** 192/192 pinned original upstream files match Git blobs/size/mode (including 14 binary assets); root MIT and ReyesPascal notices preserved. The imported original source remains unchanged on audit PR #3. Do not redo the whole import or merge without owner approval.

## What is done (do not repeat)

1. Import integrity and licensing review on [PR #1](https://github.com/ReyesPascal/KaijuFlow/pull/1); no import blockers identified. Security risks are **not** cleared by the import review.
2. Independent Node20 backend + UI npm ci/tsc/Vite build PASS: [run 42355054013](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42355054013). The latest branch also ran a Node20 build [run 42358166971](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42358166971) PASS. This is **compilation**, not application/playback verification.
3. A3 v0.1 13-subsystem static source map: [A3_STATIC_ARCHITECTURE.md](../A3_STATIC_ARCHITECTURE.md), still **partial**.
4. Independent deep-research assessment adopted, with corrections and original user-pasted report archived: [EXECUTION_PLAN.md](EXECUTION_PLAN.md) and [RESEARCH_REPORT_2026-11-07.txt](RESEARCH_REPORT_2026-11-07.txt).
5. Source-adjacent [`evidence/` index](../../../evidence/README.md): 13 subsystems, 5 evidence records, 8 claims, 3 artifact rows, schema, findings guideline, and pinned first finding [F-KF-SEC-001](../../../evidence/findings/F-KF-SEC-001.md) on `rejectUnauthorized: false`. The finding is **source-observed**, not demonstrated by attack, fixed or runtime-tested.
6. Read-only source/index validation script `tools/audit/validate_index.py` and [index CI run 42358166881](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42358166881) **PASS** on the latest pre-handoff audit head (29 index records); recheck CI after this handoff change.
7. Existing REA/Ghidra **found, not reinstalled:** REA `6.8.0` in `/home/ryan/fusion-android-analysis/rea-runtime/bin/rea-agents`; isolated Node `v24.22.2` in `/home/ryan/fusion-android-analysis/tools/node-v24.22.2-linux-x64/bin/node`; Ghidra 12.1.4 under Fusion `tools/`. `rea-agents --version` exited zero. **No REA KaijuFlow application analysis has yet run**.
8. No actual A4 synthetic NNTP/NzbDAV/Range or 4K benchmark yet. Unverified outcomes remain explicit in the evidence index.

## Start of next session: exact order

**0. Read this checkpoint, the evidence index and current Issue #2.** Read current PR #1 and PR #3 metadata/heads/CI. If GitHub has advanced, reconcile rather than overwriting new work.

**1. Verify isolation before executing code.** Brain Tunnel has been confirmed operational, but host shell commands require local owner review for *each exact command*, even with user approval for development. Check `brain_status` without changes. Do not touch running containers or production volume, credentials, networks or installed app versions.

**2. Establish source checkout properly.** The previously explored `/home/ryan/kaijuflow-a2` contains saved import scripts/manifests/logs, **not a Git repository**. Do not run `git worktree add` inside it. Use an existing verified separate clone if one is found, or create a fresh **private authenticated clone** to a new directory after checking it does not exist and does not overlap production or Fusion. Select the immutable import commit `c83a3c733b6394eb140a1c0a1dc500010a9f22e5` for code analysis. Never print saved Git credentials.

**3. Record reproducible environment identity.** `git rev-parse HEAD`, `git status --porcelain`, source/lockfile SHA-256, node/npm/REA versions, build commands, output directories. Backend `dist/` comes from `tsconfig.json`, and frontend `ui/dist/` comes from `ui/vite.config.ts`. Inspect actual emission before any REA `--source-path` selection.

**4. Begin **Stage 1 canonical source analysis** before REA.** First bounded work unit: extract exact Express/Stremio route mounts in `src/server.ts` / `src/addon/index.ts`, `src/routes/*`, and corresponding UI `ui/src` API invocation points; create a route/control/auth/side-effect table with exact pinned file/symbol/line anchors. Expand to Smart/Fixed coordinator and NNTP provider relationships next. Distinguish parsed static edges from inferred runtime behavior. Use TypeScript compiler API/ts-morph and dependency-cruiser where helpful, never edit original upstream source files just for annotations.

**5. Write findings immediately into the established index** (`evidence/index/{subsystems,manifest,claims,artifacts}.jsonl` and `evidence/findings/`), including unknowns, source SHA, exact anchors, code/build artifact digest, tool/version, claim classification, contradictions, severity and revalidation status. Use `python3 tools/audit/validate_index.py`; review CI on the audit branch. Only commit sanitized docs, scripts, tests and small summaries. Keep raw REA Evidence outside the repository under an access-controlled, **backed-up** dedicated evidence root with SHA-256 and explicit retention.

**6. Stage 2 after source-map progress:** compile source in the isolated checkout (original lockfiles; no production environment). Use existing REA 6.8.0 with its *separate* Node 24 runtime and observed `--format json`, `--detail summary`, `--evidence_output`, `--source-path` syntax. Start with a bounded backend artifact pilot (Smart/Fixed and NNTP verification, then NzbDAV/stream/fallback). Record coverage/limits; do not treat tool exit 0 as complete analysis or static candidates as runtime truth. Ghidra is only for a proven material native binary.

**7. Stage 3/4 later:** develop fake Newznab/NNTP/NzbDAV/WebDAV + isolated browser fixtures, error/cancellation/seek/cache tests; reserve production-impacting 4K benchmarks and any NzbDAV replacement/deploy for a separately approved gate.

## Next-session first actionable target

**Deliverable A3-ROUTE-001:** a complete first-pass **UI control → HTTP route → handler → external I/O/persistent side effect** matrix, plus coverage and open-question ledger, source-pinned to the unchanged imported commit. Begin by mapping `src/server.ts`, `src/routes/*`, `src/addon/index.ts`, `ui/src/App.tsx` and the UI hooks. Commit **only added audit files or scripts** on `audit/node20-a3-baseline` and keep PR #3 draft.

If local private clone/auth is blocked, make useful progress through the GitHub connector's source-file inspection and commit the first bounded source map. Do not block all of A3 on a new local tool installation.

## Safety, permissions and rollback

User has authorized isolated dev analysis/installation where needed, but **not** restarts, changes or redeployments of the working Brain services. Brain Tunnel still imposes approval for each exact shell command. There is no permission to merge either PR, change live Docker/volumes/network, introduce production credentials, force-push, move original source paths, or modify upstream bytes during this baseline.

Proven source rollback points: `main@1d35e908...` and `archive/pre-upstream-import`; PR #3 is review-only and can be closed without production change. Preserve both repos private.

## Suggested next user message

> Resume KaijuFlow from Issue #2 and the A3 next-session runbook. Verify current GitHub state; begin Stage 0 isolated checkout verification and deliver A3-ROUTE-001 (UI→route→handler→side-effect matrix) with evidence-index entries. Do not repeat prior import/build/index work, merge PRs, or change Brain production. Use the existing REA only after source-map progress.
