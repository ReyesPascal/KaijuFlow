# Current scope override — 2026-11-07

A4 is officially closed; see [closure](A4-CLOSURE.md). One separate composed discovery-to-stream integration passed; see [result and boundaries](INTEGRATION-DISCOVERY-STREAM.md). Do not execute historical expansion instructions below. Original application defects are record-only. Remaining live-service uncertainty is enumerated in [validation gaps](VALIDATION_GAPS.md). Future performance work is a distinct [planning milestone](../performance/BENCHMARK_PLAN.md), Issue #4; no benchmarking, production changes, deployment or source implementation authorized.

---

# KaijuFlow REA execution and indexed-evidence strategy

**Adopted from the independent November 7, 2026 deep-research assessment; execution roadmap, not a claim that tests/scans have run.** This document supersedes the *process* in [REA_DECISION_AND_PLAN.md](../REA_DECISION_AND_PLAN.md) while preserving it as historical evidence. It does not supersede the pinned original upstream code or licenses.

## Governing decision

Source architecture (TypeScript compiler API / ts-morph and dependency-cruiser) is **canonical**. REA 6.8.0 is an **independent built-artifact witness** that can establish artifact identity, reconstructed structural relationships, source locations, coverage and limitations, but not necessarily runtime reachability. Deterministic synthetic tests prove behavior; controlled benchmarks prove performance. CodeQL/Semgrep are scoped security tools, Playwright the UI behavior tool, and Ghidra is reserved for specific, important native artifacts.

### Preserved identities and confirmed environment

- Original: `DSmart33/Usenet-Ultimate` tag `v1.4.1`, commit `499efbdeb631b1b059f8aa70d07c12beaf504876`. 192/192 file blob IDs, byte sizes and executable bits matched an independent Git tree comparison, including 14 binaries.
- Import: `ReyesPascal/KaijuFlow@c83a3c733b6394eb140a1c0a1dc500010a9f22e5`, PR #1 still unmerged. A3 audit branch `audit/node20-a3-baseline`, draft PR #3 targeting the import branch.
- Node 20 backend/frontend build PASS independently in [Actions run 42355054013](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42355054013). This is build-only, **not a runtime/NNTP/4K test**. Node 20 EOL means this does not make it the preferred REA runtime.
- Host CLI verified via Brain Tunnel: `/home/ryan/fusion-android-analysis/rea-runtime/bin/rea-agents` = 6.8.0; separate `/home/ryan/fusion-android-analysis/tools/node-v24.22.2-linux-x64/bin/node` = v24.22.2; Ghidra exists at `/home/ryan/fusion-android-analysis/tools/ghidra_12.1.4_PUBLIC`. Normal host Node is v22.22.1, **not** the REA runtime.
- Source compilation output is **verified** from `tsconfig.json`: backend `dist/`; from `ui/vite.config.ts`: frontend `ui/dist/`. Verify actual emitted files before source selection. The backend enables source maps; Vite source maps must not be assumed.
- **Correction to the research report:** `/home/ryan/kaijuflow-a2` is an import-artifact directory, *not a Git checkout*. Do **not** run `git worktree add` there. Use an authenticated separate clone of the exact **private KaijuFlow import commit**, created outside production paths, or a Git repository whose remote/commit has been independently verified.
- **Correction to REA CLI examples:** use the already-installed pinned `rea-agents` CLI with its observed syntax `--format json`, `--detail summary`, `--evidence_output` and explicit `--source-path` / `--source-paths-json`. Do not assume `--json` or use `npx -y @latest` without checking version and flags. The CLI's `--help` was independently queried on Brain.

## Stage 0 — Identity, isolation, provenance

1. Verify import and audit branch heads, open PRs and Issue #2. Never restart/redeploy/change Brain services; no merge without owner approval.
2. Establish an **isolated clone** (not the existing `kaijuflow-a2` manifest folder) at a new, disposable path. Checkout exactly `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`. Preserve original source files unchanged; audit additions remain on draft PR #3.
3. Explicitly deny production network endpoints. Use synthetic provider URLs, loopback fakes, temp config directories, nonexistent credentials and isolated ports. **Check startup side effects first:** `src/config/schema.ts` creates `config/config.json` on import. Never start the app directly in or against live directories.
4. Verify `git status`, exact `git rev-parse HEAD`, Node/REA/npm/ps versions; record platform, tool versions, package-lock hashes, selected configs, build command/exit and source SHA.
5. Keep full raw Evidence outside Git, in a restricted, dedicated, persistent audit-results directory that is not a Docker mount; assign backup/retention policy. Do not rely on 7-day GitHub Actions artifacts for irreplaceable evidence. Hash originals, sanitize reports and publish only reviewed summaries.

**Gate 0:** source identity, separate workspace, network boundary and evidence provenance verified; no production write path.

## Stage 1 — Whole-app canonical source architecture (A3)

Retain [A3 v0.1](../A3_STATIC_ARCHITECTURE.md) as a preliminary 13-subsystem map. Complete, rather than redo, it:

- AST/symbol inventory using TypeScript compiler API or ts-morph on both root `tsconfig.json` and `ui/tsconfig.json`; imports/exports, route declarations, event callbacks, async call edges, dynamic imports, config reads/writes and startup side effects. No changes to original source files.
- Use dependency-cruiser for backend/UI dependency edges, cycles, unresolved imports and boundary violations. Interpret dynamic dispatch as unknown, not absent.
- For each module: stable subsystem ID; full source path and pinned SHA; entry points and HTTP routes; output/side effects; outbound services; state/file/cache mutations; timeout/error paths; settings and UI control mapping; testable contract; unknowns.
- Trace the complete pipeline: indexers and title/episode metadata → filter/dedup/rank → Smart/Fixed article checks and archives → provider pool/backup → NzbDAV lookup or NZB submission → WebDAV/HTTP Range and seeks → cache/Ultimate Fallback → UI and logs.
- Include Docker, installers, auth, proxy/circuit, migrations and third-party dependencies, not only Smart mode or streaming.
- Record findings as `source-observed`; do not infer behavior merely from import graphs.

**Gate 1:** subsystem coverage map is complete, high-value entrypoint-to-side-effect rows have exact source anchors, and unanswered branches are in the claims ledger.

## Stage 2 — REA built-artifact inspection (bounded A3 corroboration)

**Rationale:** original TS/TSX already exists, so REA's benefit is independent **emitted JS identity, build/source differences, source-map paths, candidate relationships and declared unknowns**. It is not the primary A3 tool.

1. Build backend and UI only in the isolated checkout using original lockfiles; record output file SHA-256 and build environment. REA is not an app dependency.
2. Use **pinned** existing Node 24.22.2 only for REA. For example, after verifying paths and existence:
   ```bash
   REA_ROOT="$HOME/fusion-android-analysis"
   export PATH="$REA_ROOT/tools/node-v24.22.2-linux-x64/bin:$REA_ROOT/rea-runtime/bin:$PATH"
   rea-agents --version
   rea-agents analyze-javascript-application --help
   ```
3. Start with a bounded full **artifact inventory** where resource use permits; `--detail summary --evidence_output <new-absent-path> --format json` keeps complete canonical Evidence separate from printed summary. Bound `--max-semantic-nodes`, heap and timeout when appropriate; record partial coverage if admission limits are hit. A successful process does not prove completeness.
4. Run explicit pilot selection for Smart/Fixed coordinator, healthCheckPipeline/articleChecker/NNTP connection, and NzbDAV streamHandler/Ultimate Fallback/streamCache. Resolve exact compiled paths from `dist/`, and include relevant imports and manifests in `--source-path` lists **explicitly**. Selected-source mode does not pull dependencies automatically.
5. Analyze `ui/dist/` separately, only if output inspection promises information not already available from TypeScript. Do not assume source maps for Vite output.
6. Store full raw Evidence only in the restricted local evidence store; hash it. Review summary, unknowns, parse errors, coverage and limitations before adding a scrubbed record to `evidence/index/`. Investigate mismatches rather than declaring them bugs.
7. **Stop criterion:** if REA gives no new useful artifact/provenance information, stop expanding that subsystem's REA work. Prefer source analysis and executable tests.

**Gate 2:** REA's incremental value and complete limitations documented, with artifact digest and pinned build identity; findings are `REA-observed`, not runtime claims.

## Stage 3 — Synthetic behavioral baseline (A4)

Use Vitest or Node's test runner; add protocol-level fakes where practical (not just mocked internal methods). No live credentials/NZBs/media or real provider requests; default deny external network.

- Indexers: Newznab, Prowlarr, NZBHydra, EasyNews and metadata/title/episode cases including error, timeout, dedup, sorting, ranking and rules.
- Verification: Smart batch budget, min-healthy early stop, Fixed top-N, bypass modes, pool and backup provider ordering, article `STAT`, zero/missing samples, concurrency, cancellation, timed-out/reconnected sockets and teardown.
- Archives: generated safe RAR4/RAR5/7z/ZIP, malformed headers, encrypted/multipart/obfuscated cases and segment boundaries.
- Caches and recovery: pending→ready/dead, TTL, concurrent same-title, persistence/restart/corruption, proxy circuit changes, Ultimate Fallback ordering and cancellations.
- Settings/UI: auth boundaries, per-user manifest keys, config migrations/defaults, provider management, endpoint status and React controls. Use Playwright isolated browser contexts when browser semantics matter.

**Gate 3:** each case has fabricated input, reproducible expected/actual output, pass/fail, fixture digest, source/test SHA and preserved negative cases.

## Stage 4 — Stream/seek/fallback protocol baseline

Use local fake NzbDAV queue and WebDAV endpoints plus an isolated KaijuFlow server. Validate status `200`, `206`, `416`, valid/invalid/suffix ranges, content-length/content-range/body identity, nonblocking byte-stream behavior, cancellation/disconnect, redirect/pipe/proxy/direct modes, sequential/concurrent seeks, stalled/missing job and recovery. No-transcode means byte-for-byte passthrough only on matching source material; it does not imply real 4K performance.

**Gate 4:** deterministic protocol behavior with synthetic bytes and documented client differences; no claims about real-world throughput or reliability.

## Stage 5 — Comparative NNTP/4K measurements

Preserve NzbDAV as the known-good baseline. Only after correctness/security gates, compare unchanged baseline to direct/hybrid/optimized retrieval using repeatable sources, cache warm/cold splits, controlled concurrency, provider profiles and hardware/network fingerprint. Collect distributions of playable success rate, source-to-stream and time-to-first-frame latency, sustained throughput vs 4K bitrate, seek delay, rebuffer count/duration, recovery, CPU/RAM/disk and NNTP connections. Protect existing Brain service; any live benchmark/deployment needs explicit owner approval for its *production impact*.

**Gate 5:** independent repeated measurements justify any architecture change or separate KaijuNNTP engine, otherwise retain/optimize NzbDAV.

## Tool selection rules

| Question | Primary evidence method | Secondary tool |
| --- | --- | --- |
| Exact TS symbol, module, config, route, import | TypeScript AST/ts-morph + source inspection | dependency-cruiser |
| Which built modules/routes were emitted? | REA 6.8.0 and hashes of emitted JS | source-to-build comparison |
| NNTP reliability, timeouts, provider failover | Fake protocol servers + executable tests | REA for unexplained built-artifact gaps |
| HTTP Range/seek/fallback behavior | HTTP integration tests | Playwright client checks |
| Credential leakage, untrusted input to sink | CodeQL (where private-repo entitlements permit), Semgrep and manual code review | synthetic security tests |
| Native machine-code logic | Source/dependency inventory first | REA + existing Ghidra 12.1.4 only if material |
| Real-world 4K throughput/startup/buffering | Repeated benchmarks with source/hardware controls | runtime metrics/traces |

## Indexed evidence, source adjacency and retention

The **Git-visible** audit index is rooted at [`evidence/README.md`](../../../evidence/README.md). Its `index/subsystems.jsonl` has stable subsystem IDs, `manifest.jsonl` records evidence and provenance, `claims.jsonl` records hypotheses/results with supporting evidence IDs and validation status, and `artifacts.jsonl` tracks cryptographic digests and retention. Use an immutable, exact source commit+file+line URL; the source SHA and any available blob/hash must be checked before claiming a match.

Sidecar Markdown finding documents live under `evidence/findings/` and can link directly to original code. The original upstream tree stays byte-for-byte unchanged. Avoid inline modifications to imported files, Git notes (inaccessible to ordinary reviews), solely GitHub Issues (not a versioned artifact), Wiki (not reliably adjacent to exact commits), or a new separate repo (adds synchronization and privacy risk). Issues and PRs track workflow, while the repo sidecars track facts.

Record in every evidence/claim entry: unique ID, schema version, captured date, source SHA, source path/symbol/lines when known, producer and version, classification, coverage/limitations, hash, storage class and location, status, severity for findings, confidence, support/contradiction IDs, reviewer, `supersedes` and staleness or revalidation flag. **Do not create a fake test-observed claim from illustrative sample data.**

Raw canonical REA Evidence may be large and expose source paths or secrets. Hash before redaction, keep original locally in an access-controlled, *backed-up* audit area, and only commit reviewed concise sanitized projections. GitHub Actions artifacts with seven-day retention are diagnostics, **not** a durable source of truth. Maintain an explicit restore path for any raw evidence referenced from Git.

## CI safety and change gates

- Start with a small, dependency-free JSONL/schema/referential-consistency validator; fail on duplicate IDs and dangling evidence references. Then check source path/SHA pinning and reviewed artifact hash presence. Always distinguish `not collected` from `verified`.
- For future REA CI, begin with `workflow_dispatch` using read-only `contents: read`; inspect actions and pin revision SHA where feasible. Never execute untrusted PR code under `pull_request_target`.
- CI must not contain Brain credentials, private providers, NZBs, Docker-host sockets, host mount points or workflow permissions allowing production changes.
- Keep PR #1 and draft PR #3 unmerged. Add findings only through small reviewable audit commits. Never auto-rewrite upstream files or replace NzbDAV based on this audit.

## Reporting and session recovery

Update `evidence/README.md`, per-subsystem entries, Issue #2 and `docs/kaijuflow/HANDOFF.md` only when a gate meaningfully advances. At every session record branch/head, evidence IDs/hashes, source/tool/test provenance, unresolved questions, rollback and the next single action. Never call an A3 static map a passing A4 behavior test.

## Verified external reference docs

- [REA JavaScript artifact reconstruction](https://github.com/morluto/rea/blob/main/docs/javascript-artifact-reconstruction.md)
- [REA CLI and evidence](https://github.com/morluto/rea/blob/main/docs/cli.md)
- [REA CI analysis guidance](https://github.com/morluto/rea/blob/main/docs/ci-analysis.md)
- [ts-morph](https://ts-morph.com/setup/index) and [dependency-cruiser](https://github.com/sverweij/dependency-cruiser)
- [Vitest mocking](https://vitest.dev/guide/mocking.html), [Playwright browser tests](https://playwright.dev/docs/writing-tests), [CodeQL JS/TS data flow](https://codeql.github.com/docs/codeql-language-guides/analyzing-data-flow-in-javascript-and-typescript/)
- [GitHub Actions safe workflow practices](https://docs.github.com/en/actions/reference/security/secure-use) and [artifact retention](https://docs.github.com/en/actions/tutorials/store-and-share-data)
