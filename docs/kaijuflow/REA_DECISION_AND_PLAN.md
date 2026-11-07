# REA decision and execution plan for KaijuFlow (A3/A4)

**Decision:** Use a combined, evidence-gated toolchain. Native TypeScript/AST import analysis and executable isolated tests remain the primary means of understanding **source-owned** KaijuFlow. Use REA selectively as an independent evidence-producing static analyzer on **built JavaScript/UI assets** and, only when necessary, controlled runtime/browser captures. Reserve Ghidra for unexplained native code. Do not install or update REA/Ghidra without need.

**Status:** PLAN only; REA application scans, analysis sessions and A4 synthetic behavior tests are not yet claimed. Source audit v0.1 is separately documented in `A3_STATIC_ARCHITECTURE.md`. This plan introduces no application implementation changes.

## Provenance and initial setup facts

- Source: `ReyesPascal/KaijuFlow@c83a3c733b6394eb140a1c0a1dc500010a9f22e5`, preserving upstream `DSmart33/Usenet-Ultimate@499efbdeb631b1b059f8aa70d07c12beaf504876` (v1.4.1).
- The import is 192/192 previously independently matched original blobs, permissions and 14 binary assets; do not redo this import.
- A Node 20 backend/UI compilation passed independently in GitHub Actions run `42355054013` / job `128351208444` on draft PR #3. It does **not** verify behavior or image runtime.
- The Brain Tunnel host's existing Fusion environment contains `/home/ryan/fusion-android-analysis/rea-runtime/bin/rea-agents` and `/home/ryan/fusion-android-analysis/tools/node-v24.22.2-linux-x64/bin/node`; `rea-agents --version` returned `6.8.0`. Existing Ghidra install is `/home/ryan/fusion-android-analysis/tools/ghidra_12.1.4_PUBLIC`. The tools are not on the normal PATH. No reinstalls, REA scans or MCP agent setup were performed when recovering them.
- Brain Tunnel requires owner-reviewed authorization for each exact command. The owner has authorized isolated development analysis, but **do not alter working Usenet Ultimate, NzbDAV, Manifexus, PTP or other production services**, Docker settings/volumes, live credentials/network, or merge/deploy without specific production approval.

## Why this combination, not a single tool?

| Candidate | Best question answered | Limitation for this job | Decision |
| --- | --- | --- | --- |
| TypeScript compiler API / ts-morph, source search and import-call tracing | Exact source-level function, type, import, route and mutation inventory | Static analysis cannot prove runtime scheduling, config-dependent paths or client interactions | **Primary A3** |
| dependency-cruiser | Dependency graph, cycles, boundary violations, missing/orphan imports | Dependency edges are not a runtime call graph or performance measurement | **Primary A3 supplement** |
| REA 6.8 JavaScript application analysis | Evidence-backed static observations on built artifacts; source/bundle comparison, explicit coverage and unknowns | Heuristic static route candidates and partial analysis do not establish runtime reachability; may cost CPU/RAM/disk | **Targeted A3 supplement** |
| Vitest / node:test with fabricated data, fake NNTP and HTTP stubs | Actual bounded Smart/Fixed logic, error/fallback behavior, cache persistence, protocol edge cases | Mocked integrations cannot establish real-world provider reliability or 4K performance | **Primary A4** |
| Playwright / controlled browser requests | UI-to-API behavior, auth/setup, client errors, request traces, controlled screen tests | Browser tests alone cannot verify lower-level NNTP protocol or sustained playback | **A4 UI** |
| CodeQL / Semgrep | Taint, dataflow, risky sinks, TLS/auth/security review | Security-focused, not comprehensive feature semantics or playback behavior; private-repo GitHub CodeQL setup may depend on code-security eligibility | **Phase B, plus scoped A3 risks** |
| Ghidra / IDA / Hopper / Cutter | Native code paths, disassembly and decompilation | KaijuFlow's core is TypeScript/React; adds little for source-owned JS | **Defer until native-binary evidence** |
| Frida / process instrumentation, Wireshark/tcpdump | Actual runtime call/network timings and protocol observations | More intrusive; privacy and resource risks; not justified for initial architecture pass | **Only with targeted isolated question** |

REA was first attractive because it links observations to structured Evidence and can inspect packaged code without executing it. That is valuable, but it **does not replace source understanding and tests**.

## Phase 0 — Environment boundary and integrity gate

1. Verify GitHub branches, PRs and the import SHA before acting; keep PR #1 and draft PR #3 unmerged.
2. Create a disposable KaijuFlow checkout/worktree outside every live container volume. Start from exact import commit, not an arbitrary working tree. Use no live `.env`, auth DB, NZBs, media files, providers or certificates.
3. Use a distinct test config directory, ports and loopback-only mock services. Avoid app startup in the checkout if module initialization can create `config/config.json` until it is isolated.
4. Record Node/npm, REA, Ghidra version, git commit, config and fixture digest, command, exit code and relevant warnings.
5. Reuse the existing REA CLI with **temporary PATH** set to Fusion's Node 24 and REA paths; never alter system Node or agent-level MCP configuration merely to run the CLI.
6. Prioritize completed GitHub evidence; do not repeat the Node 20 build unless new source/toolchain inputs require it.

**Gate:** analysis cannot touch any production service, host credentials or live data, and cannot result in an unreviewed merge.

## Phase 1 — Finish A3 source architecture, without REA

Build an inventory of all tracked app files (not just Smart mode) grouped by discovery, verification, retrieval, streaming, recovery, UI, metadata, rules, auth, config, integration and deployment.

- Extract TS imports/exports, route and callback registration, state mutation and persistence paths. Use a compiler/AST pass and dependency-cruiser on a disposable copy.
- Produce an **entrypoint-to-side-effect matrix**: browser control -> HTTP route -> service/function -> outbound call -> cache/file state -> return/error.
- Include `src/server.ts`, all `src/routes/`, `src/addon/`, `src/searchers/`, `src/parsers/`, `src/health/`, `src/archive/`, `src/nzbdav/`, `src/config/`, `src/rules/`, `src/auth/`, `src/proxy.ts`, `src/idResolver.ts`, and `ui/src/`.
- Specifically trace Smart batch size/runs/min-healthy; Fixed top-N; provider pool/backups; NZB parser and archive choices; NNTP connection pool/STAT; NzbDAV job submission/WebDAV; proxy/pipe/direct and HTTP Range; Ultimate Fallback; ready/dead/pending caches and disk persistence; UI config, auth and migration paths.
- For each flow, mark **SOURCE-OBSERVED**, **REA-OBSERVED**, **TEST-OBSERVED**, **MEASURED** or **UNVERIFIED**, not a single misleading “verified” category.
- Create a list of unresolved questions (e.g., async call targets, conditional paths, client redirect behavior) that REA or tests might answer better.

**Gate:** Every requested subsystem is inventoried, and each relevant flow has a source anchor and explicitly identified unknowns.

## Phase 2 — Small REA pilot on exact built artifacts

1. Build *isolated* `dist/` and `ui/dist/` from the pinned source. Do not edit the original import tree. Record artifact hashes.
2. Run REA static JS analysis first on a limited selection of built backend modules, using `analyze-javascript-application` against the chosen **built-artifact directory**, with `--source-path` for exact inventoried files, `--detail summary` and a new `--evidence_output`. The CLI requires that the Evidence output path not already exist.
3. Pilot targets:
   - `dist/server.js` and `dist/addon/index.js`: server/Stremio entrypoints.
   - `dist/addon/healthCheckCoordinator.js`, `dist/health/{healthCheckPipeline,articleChecker,nntpConnection}.js`: Smart/Fixed and article verification.
   - `dist/nzbdav/{streamHandler,ultimateFallback,streamCache}.js`: delivery, fallback and caching.
4. If the pilot shows meaningful new facts or discrepancies, examine compiled UI `ui/dist/assets/*.js` with source maps *only if generated for the isolated audit*; avoid modifying the production UI build settings.
5. Save full Evidence privately on the isolated host. Extract small, scrubbed route/edge/source/unknown summaries and link them to source anchors.
6. Do not run an unbounded “analyze everything” pass as a proxy for coverage. Use REA's returned coverage counts, unknown scopes, per-file and total memory/time admission limits to decide whether expansion is justified.
7. **Comparison:** check REA-derived route/export/module observations against the TypeScript source inventory. A mismatch is an investigation item, not automatically a bug.

**REA effectiveness gate:** If the pilot confirms only facts already obvious from source and adds no useful artifact/unknown/behavior distinction, **stop using REA for that subsystem**. Retain its evidence as a negative-cost/benefit result and move to tests.

## Phase 3 — Answer targeted questions using REA or another tool

Examples:
- Is a Stremio route present in the build and does a configured client actually reach it? **REA static candidate + isolated HTTP integration test**; do not equate candidate with reachability.
- Which dependency path updates dead/ready cache after NzbDAV failure? **Source/AST trace**, REA only if the compiled path differs or is difficult to trace, then synthetic tests.
- Does WebDAV proxy preserve Range semantics on seeks? **HTTP integration tests and byte comparisons**, not static REA alone.
- Which UI action changes health provider order? **Source/API map + Playwright mock network trace**; REA browser capture optional if a discrepancy remains.
- Does compiled bundle contain source-invisible behavior or unexpected packaged code? **REA built bundle static inventory**, source-map comparison, dependency lockfile review.
- Is native code governing a critical operation? Trace Node dependencies first; open existing Ghidra only if a specific native artifact is identified.

Avoid exposing credential-bearing URLs, raw request headers, media names or private logs in durable reports.

## Phase 4 — A4 isolated behavior baseline (independent of REA)

**Harness:** Fake Newznab/Prowlarr/NZBHydra/EasyNews responses, fake NNTP greeting/auth/STAT/BODY responses, synthetic small NZBs, fabricated providers, fake NzbDAV queue/history and WebDAV content, loopback-only services, isolated config/data directory.

**Suites:**
1. Discovery metadata, sort/dedup, rules, episode/season-pack selection, indexer errors/timeouts.
2. Smart batch stop semantics vs Fixed top-N; disabled checks; pool+backup providers, missing article and cancellation.
3. Archive RAR4/RAR5/7z/ZIP, malformed, multipart, encrypted/password cases.
4. NNTP connections, timeout, resource teardown, samples, multi-provider coverage, network failures (TLS behavior inventoried without real secrets).
5. NzbDAV submit/poll/cancel, WebDAV 404, wait timeout, file mismatch; direct/pipe/proxy.
6. HTTP 200/206/416, Range starts/ends/invalid, seeking, client abort, byte-for-byte passthrough.
7. Dead/ready/pending cache concurrency, TTL, restart persistence and corrupt-file handling; Ultimate Fallback ordering and failure modes.
8. UI settings/auth, manifest isolation, API errors and save/reload using Playwright/HTTP fixtures.

Every test records input fixture/hash, expected/actual behavior, logs stripped of sensitive data, test result, and uncovered branches.

**Gate:** A3 is complete only when every subsystem has traceable entrypoints/state boundaries and a coverage/unknown ledger. A4 is complete only when the agreed synthetic scenario matrix has a reproducible result; do not infer “original-quality 4K achieved” from mocks.

## Phase 5 — Streaming benchmark gate (later)

Compare unchanged NzbDAV baseline with prospective direct/hybrid retrieval only on equivalent sources/hardware and with explicit production change approval. Metrics: source playable success rate, time-to-usable-stream, time-to-first-frame, 4K sustained throughput vs bitrate, rebuffer count/duration, seek latency/success, provider fallback/recovery, CPU, memory, disk I/O, network and connection consumption. No architecture extraction or NzbDAV removal without evidence.

## Deliverables and archival conventions

- `docs/kaijuflow/A3_STATIC_ARCHITECTURE.md`: source inventory and entrypoint/side-effect matrix.
- `docs/kaijuflow/REA_DECISION_AND_PLAN.md`: this rationale and gated plan.
- Audit-branch follow-up: focused `REA_FINDINGS.md` (version, SHA, artifact hashes, evidence IDs, coverage, findings and unknowns); `A4_TEST_MATRIX.md`; synthetic fixtures/tests; benchmark plan.
- Retain full REA Evidence in a protected isolated local results directory, not automatically GitHub; commit only reviewed/sanitized summaries.
- Issue #2 and draft PR #3 track results and follow-ups; no merge without owner approval. Production untouched.

## Decision triggers

- **Use REA** when validating built artifact identity/route candidates, analyzing bundled/minified app behavior, locating source/bundle discrepancies, or producing structured evidence for a genuinely unresolved question.
- **Use source tools** when the original TS code clearly establishes a type/import/call/setting.
- **Use tests** when behavior depends on async events, timeouts, cache state, errors, NNTP responses, WebDAV ranges or player actions.
- **Use Ghidra** only when specific native code is implicated.
- **Stop REA** if pilot's incremental evidence does not justify its resource/maintenance cost.

Sources: REA official repository/docs (morluto/rea), dependency-cruiser, CodeQL JavaScript/TypeScript, Playwright mocking/traces, and Vitest mocking documentation. Confirm actual tool versions before installing any new component.
