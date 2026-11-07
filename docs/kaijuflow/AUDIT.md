# Audit findings and development decisions

## Initial static findings

This preserves the prior partial audit, not a complete runtime or security assessment.

| Area | Source entry points | Finding / follow-up |
| --- | --- | --- |
| Health orchestration | `src/addon/healthCheckCoordinator.ts` | Smart batching and early stop, Fixed top-N, NzbDAV/dead-NZB pre-checks; verify all modes independently |
| Verification | `src/health/healthCheckPipeline.ts`, `articleChecker.ts`, `batchProcessor.ts`, `nntpConnection.ts` | Classification, archive inspection, segment sampling, pipelined STAT, pool/backup providers, reused connections |
| TLS | `src/health/nntpConnection.ts` | `rejectUnauthorized: false` disables certificate validation; review compatibility and security in Phase B; preserve baseline behavior during import |
| Archives | `src/archive/` | RAR4, RAR5, 7-Zip, and ZIP parsers; malformed, nested, and encrypted archive behavior needs fixtures |
| Streaming and fallback | `src/nzbdav/ultimateFallback.ts`, `fallbackManager.ts`, `streamCache.ts` | Recovery pipeline, candidate state, pending/ready/dead caches; runtime parity remains unverified |
| Settings and UI | `src/config/`, `ui/src/` | Config accessors/migrations and complete React UI must remain in scope |
| Builds | Root/UI manifests and locks, `Dockerfile` | TypeScript backend, React/Vite frontend, upstream Node 20 multistage build |

Prior inspection found Smart defaults: inspection method `smart`, batch size 3, one additional run, minimum healthy 1. Max batches are 1 + additional runs; stop counting uses verified results in the inspected prefix. Health checking may itself be disabled; verify saved settings in synthetic tests rather than assuming it runs.

## Decisions retained

- Capture the whole release before targeted changes. Smart mode is one protected subsystem.
- Preserve every original file byte and executable bit. Only upstream README moves; provenance and exact path mappings live in root `UPSTREAM.md`.
- Keep upstream MIT text at root and retain the previous ReyesPascal MIT notice separately. The archive and Git history preserve all prior work.
- Replace overlapping preliminary planning documents with these current records. Retain the original import helper outside the final tree as checkpoint material; do not keep conflicting license/import instructions active.
- Keep KaijuNNTP independent and dormant until Phase E evidence supports extraction. Keep this repository separate from Droidusion and Pascal The Popcorn source.
- Use isolated fixtures and scrubbed traces. No private configuration, credentials, NZBs, media metadata, or runtime data belong in Git.
- No access to Brain, container changes, production profiling, or deployment is authorized by this import.

Dependency vulnerabilities, complete licensing review, whole-application architecture coverage, performance, and behavioral parity remain future work. Import checks are recorded separately in `import-verification.json`; they do not establish production safety or runtime equivalence.

Additional source-review follow-up: `src/idResolver.ts` logs part of a TVDB login response when a token is missing. Review sensitive-data logging during Phase B; the baseline remains unchanged.
