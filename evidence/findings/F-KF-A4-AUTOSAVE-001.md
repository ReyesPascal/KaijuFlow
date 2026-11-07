# F-KF-A4-AUTOSAVE-001 — Original React hook accepts stale successful PUT response

**Status:** test-observed, synthetic and isolated. **Disposition:** no source patch authorized.
**Date:** 2026-11-07. **Original source:** `ui/src/hooks/useAppConfig.ts` on immutable import `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`.

## Independent runtime reproduction
GitHub Actions [run 42368292063](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42368292063), job `128390937109`, Node 20, disposable verified network namespace (loopback only, denial probe before original hook import). Actual original React `useAppConfig` was bundled in CI with esbuild without editing imported source. `react-test-renderer@18.3.1` mounted the real hook with virtual 300/500ms timers and deferred fake `apiFetch('/api/settings')` responses. All responses synthetic; no production network. Source SHA256 before/after identical.

**Observed:** two local cacheTTL edits issued PUTs with 9300 then 9400. The fixture resolved the second successful response first, setting shared config.cacheTTL=9400. It then resolved the earlier successful response; `saveSettings` unconditionally called `setConfig(data)`, resulting in local `cacheTTL=9400` while `config.cacheTTL=9300`. **A4-REACT-ORDER FAIL** desired latest-write invariant.

Other subcases: **A4-REACT-300 PASS** 299ms quiet/PUT at 300ms for addonEnabled; **A4-REACT-500 PASS** local 9500 edit retained and error logged; **A4-REACT-TRANSPORT PASS** local 9600 retained and transport exception logged. Existing backend sequential settings pass is separate; it does not refute this client response race.

CI overall intentionally red for two independent original behavioral findings: deletion HEAD/503 dedup and React stale response. Artifact `13572687206`, ZIP SHA-256 `9841987a4f2f86853e7ba0f74a108fa20f165a114b1e68776a5a4ab56d5d38ff`, 14-day retention. The committed fixture `tests/a4/react-autosave.cjs` and CI workflow are permanent reproduction sources.

## Scope / caveats
- Proves state regression under deliberately inverted successful fake responses in the actual hook; not a measured production occurrence, persisted-write order, UI browser integration, or user data loss.
- No server persistence order proof or rollback test. The 500 and transport failure cases verify local edit retention, not eventual successful retry.
- Recommendation for later scoped change (requires owner approval): serialize or version settings writes, ensure response commits cannot overwrite newer edits, and verify backend persistence with write generation/ordering. Preserve distinct setting-group merging.
- No original source, Brain production, live credentials, NZBs, provider networks, Docker services, PR merges, or deployment changed.
