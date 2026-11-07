# A4 official closure — 2026-11-07

**Status: CLOSED as a bounded isolated synthetic validation milestone.** Closure records completed validation and unresolved findings; it does not establish production readiness or resolve any defect. Issue [#2](https://github.com/ReyesPascal/KaijuFlow/issues/2) remains the open project handoff tracker. No additional A4 cases or application fixes are authorized by this closure.

Original application source: `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`. Audit checkpoint: `25e7971a2dc5cd53985173fe178cf95dac608230`. Evidence identifier: `EV-KF-A4-CLOSURE-001`; preceding case evidence includes `EV-KF-A4-EXPANDED-017` and `EV-KF-A4-REACT-004`.

## Verified CI and actual results

Inspected existing [Actions run 42372236463](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42372236463), [job 128402557244](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42372236463/job/128402557244), on the checkpoint above. Node runtime was `v20.20.2`, npm `10.8.2`.

| Group | Actual outcome | Bounded coverage |
| --- | --- | --- |
| Backend synthetic fixtures | 15 PASS / 2 intentional RED | Auth, SDK routes, settings, deletion assertions, provider/indexer CRUD and sync, fake NNTP auth/STAT fallback, archive grouping/yEnc, health sampling, proxy/Range/fallback and cache markers |
| Original React hook | 3 PASS / 1 intentional RED | 300 ms debounce, HTTP 500 and transport-error local-edit retention pass; reversed successful responses violate shared-state ordering |
| Smart/Fixed/disabled coordinator | 3 PASS | Original coordinator control flow using pre-existing synthetic health verdicts |
| Cache restart/corruption | 2 PASS | Ready/dead entries survive separate-process restart; corrupt synthetic JSON loads empty without crashing |
| Isolation and original source | PASS | Injected gate denial prevented app import; positive namespace had only loopback, denied external TCP/DNS; original `src/` and `ui/src/` SHA-256 before/after identical |

The overall A4 workflow conclusion is **failure intentionally**, preserving the original behavior assertions. This is not an isolation failure. The overlapping indexer CRUD fixtures count as recorded test cases, not independent product subsystems.

At the same audit checkpoint, existing [Node 20 build 42372236515](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42372236515) and [evidence-index integrity 42372236457](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42372236457) completed successfully. Later audit commits must be checked separately; these are not blanket claims about future heads.

A4 artifact: [13573598386](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42372236463/artifacts/13573598386), ZIP SHA-256 `8bfd56925f3a5a182be216f3c9681e0df0032db6875ebf3ffa94692933300d13`, four JSON reports, 14-day Actions retention. Permanent reports and fixtures preserve interpretation and reproducibility after artifact expiry.

## Unresolved findings — record only

1. **Destructive HEAD:** original GET library-delete handling also accepts HEAD and invokes WebDAV DELETE. Latest log records `headRemoteDeletes:1`. Source: [`src/routes/nzbdav.ts`, `createNzbdavStreamRoutes`, `/library-delete`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/routes/nzbdav.ts). Classification: **tested**, `A4-DELETE-003`; [finding](../../../evidence/findings/F-KF-A4-DELETE-001.md).
2. **Failed-delete deduplication:** failed HTTP 503 single-delete and delete-all requests can be deduplicated on immediate replay rather than retried. Classification: **tested within the historical named fixtures**, not measured production frequency. The latest single-delete case shows `failedFirst:1, failedReplay:1`. **Evidence caveat:** the newest delete-all log returned HTTP **204**, so its RED assertion does not independently reproduce the 503 claim. The earlier explicitly recorded 503 reproduction is [run 42369553150](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42369553150), job `128394646047`, documented in [the existing case report](A4-ADDITIONAL-SYNTHETIC-2026-11-07.md). Preserve that distinction; no fixture changes or retests were added to resolve it. Source: same original route module, `/library-delete-all`, `A4-DELETEALL-007`.
3. **Stale React autosave success:** older successful response overwrites newer shared configuration (`configTTL:9300` while local edit remains `9400`). Classification: **tested**, `A4-REACT-ORDER`, `EV-KF-A4-REACT-004`; [`useAppConfig`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/ui/src/hooks/useAppConfig.ts), [finding](../../../evidence/findings/F-KF-A4-AUTOSAVE-001.md). Server persistence ordering and production frequency are not established.

No application defect was fixed. Original source and production remain outside the change scope.

## Limits, reproduction and stop point

The fixtures validate selected original modules and routes against fabricated protocol responses. They do not prove full server/search orchestration, live NNTP behavior, complete archives, real NzbDAV processing, sustained playback, seeking under load, original-quality 4K performance, or complete security coverage. See [validation gaps](VALIDATION_GAPS.md) and the permanent [NNTP](../references/nntp/README.md) / [NzbDAV](../references/nzbdav/README.md) references.

Existing automatic push/PR triggers inadvertently scheduled A4 again when the separate integration commit was saved. No new A4 cases were introduced. The closure changes A4 to **manual-only** dispatch to prevent further documentation-triggered runs; intentionally RED assertions remain intact. Reproduction, if separately requested, uses `.github/workflows/a4-isolated.yml` and the existing `tests/a4/run-ci.sh` fail-closed disposable environment. Do not run against Brain or live services.

The one separate post-A4 scenario is [INT-DISCOVERY-STREAM-001](INTEGRATION-DISCOVERY-STREAM.md). Performance comparison is a distinct planning milestone in [Issue #4](https://github.com/ReyesPascal/KaijuFlow/issues/4), not reopened A4 work. PR #1 and draft PR #3 must remain unmerged.
