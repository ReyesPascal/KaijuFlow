# A3-ROUTE-003 — React cross-module callback binding audit

Status: completed **bounded source-only/type-aware pass**, with unresolved transitive/dynamic edges explicitly retained. Date: November 7, 2026. Application source pin: c83a3c733b6394eb140a1c0a1dc500010a9f22e5. This is NOT proof of all 603 JSX event-to-HTTP paths or runtime reachability.

## Reproducible static analysis

- Implementation: tools/audit/extract_callback_edges.cjs. It uses the original locked TypeScript 5.9.3 compiler/type checker, traverses original ui/src, resolves imported component function declarations, binds destructured child callback props, follows source-level hook-return object properties, records child calls/forwarding, and keeps dynamic URL syntax unevaluated.
- Independent GitHub-hosted run 42363448497: PASS on audit commit 451593b1df3e1cfdcd5140513c0efba9060ac242. Node 20, no app boot. Original src and ui/src diff against pinned import: empty.
- 38 UI TS/TSX files, 0 parser errors; 243 function definitions discovered, 113 source-level hook bindings.
- 261 callback-prop assignment candidates, with 261 syntactic child destructuring bindings identified; 167 have mapped hook-return origin expressions. 235 assignments refer to child bindings used as calls; 37 refer to bindings forwarded or referenced directly as JSX events. These categories can overlap.
- 22 nonliteral frontend network URL expressions retained with placeholder syntax; not runtime-resolved URLs.
- 244 unresolved uppercase JSX tag occurrences include external component/icon references. The count is of occurrences, NOT 244 distinct missing KaijuFlow components. Do not use it to claim full callback closure or specific coverage gaps without triage.
- Machine graph: private artifact 13570284887 from run 42363448497, ZIP SHA-256 6c0651817f8b1af43e31265b8064c40cfb14b2bce4cc1362c4c1da87e49b728b, expires November 21, 2026; callback-edges.json SHA-256 1a97c60529efc3c456c71136b09f182b5fc8bf8c25fd0cb0c43ac8e3443036e7. Reproducible script committed permanently.

## Source-verified cross-file chains (all potential effects, not observed execution)

| Origin | Bound child/action | HTTP or state effect | Verification/limit |
| --- | --- | --- | --- |
| App.tsx:61,75,861-871 | useAppConfig(apiFetch, authStatus) -> HealthChecksOverlay.setHealthChecks and apiFetch | Shared hook-owned healthChecks state | Source linkage; effect timing untested |
| HealthChecksOverlay.tsx:38-41,233-237 | handleProvidersChange -> ProviderManager.onProvidersChange | setHealthChecks(prev => ({...prev,providers})) | Source linkage; user interaction untested |
| App.tsx:879-895 | UltimateFallbackOverlay receives the same hook state and fetch function | Shared provider state with distinct overlay | Source linkage; no independent provider store |
| UltimateFallbackOverlay.tsx:149-152,750-754 | handleProvidersChange -> ProviderManager.onProvidersChange | setHealthChecks(prev => ({...prev,providers})) | Source linkage |
| ProviderManager.tsx:160-184,232 | drag/drop -> handleProviderDrop -> onProvidersChange, then apiFetch | POST /api/health-check/providers/reorder; UI updates BEFORE response | No response.ok check in reorder handler. Non-2xx may leave optimistic state; runtime not tested |
| ProviderManager.tsx:69-145 | add, edit, delete and toggle provider callbacks | POST/PUT/DELETE /api/health-check/providers, state updates conditional on response.ok | Distinct from reorder behavior; error UX not measured |
| App.tsx:716,385-405; IndexManagerOverlay.tsx:1529,1537,1866,1874 | handleReorderSyncedIndexer passed as prop, called by click handlers | setSyncedIndexers(newOrder), POST /api/synced-indexers/reorder immediately | Error logs but no rollback in this source; test pending |
| useAppConfig.ts:513-518 | setSyncedIndexers changes invoke a separate effect | Debounced 500ms PUT /api/settings with syncedIndexers | Two write paths exist; ordering/idempotence not tested |
| App.tsx:75 and named set* props; useAppConfig.ts:283-351 | Overlay setters -> independent 300/500ms effects -> saveSettings | PUT /api/settings; on success response.json then setConfig(data) | Network responses are not globally serialized; stale-response clobber is a plausible test hypothesis, NOT an observed failure |
| useAppConfig.ts:340-347 | healthChecks effect excludes providers | PUT /api/settings with healthChecks non-provider fields | Explicitly excludes provider CRUD, avoiding claim that this effect saves provider list |
| useAppConfig.ts:520-542 | edit form change via hook/overlay | 500ms PUT /api/indexers/{name}, followed by fetchIndexers on success | Dynamic encoded name; last-request winner untested |
| App.tsx:61,75; components accepting apiFetch | apiFetch handed to child overlays and controls | Child local HTTP call sites already enumerated in A3-ROUTE-002 | No claim that every inline callback transits to a fetch |

Pinned paths and blobs supporting key chains:
- https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/ui/src/App.tsx#L861-L895
- https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/ui/src/components/overlays/HealthChecksOverlay.tsx#L38-L41
- https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/ui/src/components/overlays/UltimateFallbackOverlay.tsx#L149-L152
- https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/ui/src/components/shared/ProviderManager.tsx#L160-L184
- https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/ui/src/hooks/useAppConfig.ts#L283-L351

## Dynamic network URL classifications

The original 22 sites remain visible in A3-ROUTE-002-AST.md; A3-ROUTE-003 retains a new unevaluated template projection. High-value shapes include encoded indexer/provider/manifest identifiers, stats deletion, NZB cache entry keys, optional SSE token query, and proxy status URL query. Dynamic URL segments do not imply arbitrary route registration; app routes and authorization are separately source-mapped in A3-ROUTE-002. Invalid IDs, query encoding, and actual SDK prefix matching remain A4 cases.

## Independent bounded agent reviews

- Codex CLI 0.167.0 ran ephemeral read-only in the existing sanitized source-only 47-file workspace. This session's completed review was constrained to ui/src/App.tsx and ui/src/hooks/useAppConfig.ts: source-traced overlay setters, debounced settings PUT, immediate synced reorder POST, and edit-form PUT. It did not run app or modify files.
- Claude Code 2.1.319, model claude-sonnet-5-5 Medium, was given selected original-source excerpts through stdin with tools disabled. Its response highlighted reorder response handling, overlapping autosave requests and silent failures. The limited excerpt format reduced review strength; it is an independent hypothesis review, NOT comprehensive semantic confirmation. We cross-checked the principal reorder and settings claims directly against pinned source.
- No agent was given REA, Fusion, unrelated project material, live credentials/configuration, or write access to the audit repository.

## Remaining honest boundaries

The 261 child parameter bindings are not 261 complete UI-to-network execution paths; indirect closures/aliases, child-to-child forwarding beyond direct syntactic references, values returned from hooks, computed JSX, third-party components, dynamic request values and scheduling can still require runtime instrumentation. Existing 603 JSX sites and 64 UI network calls are A3-ROUTE-002 results and were not re-enumerated. Neither agent nor the compiler has established runtime effects, exploitability or playable streams. Escalate source ambiguity to targeted A4 tests, not another broad AST rerun. See A4_ISOLATED_TEST_PLAN.md.
