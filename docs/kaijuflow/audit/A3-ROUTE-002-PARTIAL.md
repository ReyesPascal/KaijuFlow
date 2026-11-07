# A3-ROUTE-002 — bounded continuation (source-observed, incomplete)

Date: 2026-11-07. Immutable source: `import/upstream-v1.4.1@c83a3c733b6394eb140a1c0a1dc500010a9f22e5`.
This is an incremental source review, **not** a completed TypeScript AST graph, Claude review, or runtime verification. Continue from A3-ROUTE-001 without repeating its 63 explicit declarations.

## Verified new cross-boundary chains

1. `ui/src/hooks/useAppConfig.ts:284-306`: `saveSettings` is a `useCallback` depending on `apiFetch`; it sends `PUT /api/settings` with JSON, replaces local `config` from successful response, logs errors otherwise. Subsequent auto-save effects begin at line 309. The full dependency/caller graph still needs AST extraction.
2. `src/routes/settings.ts:117-149`: `createSettingsRoutes` registers `GET /config` and a shared `handleSettingsUpdate` for `PUT /settings` and backwards-compatible `POST /settings`. The handler calls injected `updateSettings(req.body)`; conditionally invokes `recalculateTTLExpirations`, `clearMultiEpisodeDeadEntries`, `clearTimeoutDeadEntries`. The durable backing file/transaction and failure semantics remain to be traced.
3. `src/server.ts:188-214`: the Stremio router defines explicit `GET /manifest.json` and then delegates SDK-generated methods to `getRouter(addon)`. Both `/stremio/:manifestKey` and legacy `/:manifestKey` mount the same router after `validateManifestKey`; `contextMiddleware` attaches manifest key, base URL and path prefix. SDK-generated method/path coverage **cannot** be inferred solely from explicit Express declarations.
4. `src/addon/index.ts:194` defines the SDK stream handler; source shows branching by anime IDs, TVDB, TMDB and IMDB, with early empty-stream exits. Later stages use cache, filtering, health coordination, NzbDAV auto-queue and fallback. These are source-observed branches, not proven request outcomes.

## Unresolved A3-ROUTE-002 deliverables

- Run a pinned TypeScript compiler AST extractor against **all** `ui/src/**/*.{ts,tsx}`: `fetch`, `apiFetch`, `EventSource`, callback declarations/references, JSX event props, hook callsites, indirect handlers, dynamic URL construction, effect dependencies, and unresolvable edges. Emit machine-readable edges with file, line, symbol and confidence; cross-check counts.
- Map Stremio SDK `getRouter(addon)` generated route methods by pinned installed SDK version/source; distinguish SDK routes from custom manifest and WebDAV GET routes.
- Trace `updateSettings`, config serialization, manifest/indexer mutation, cache/database writes, file deletion, startup cleanup, and any async write behind GET, with exact sinks and guards. Verify mount precedence and auth scope.
- Have Codex perform mechanical AST extraction in a source-only isolated workspace; Claude Sonnet Medium independently review **only** sanitized original source/graph where available. Neither agent was run in this continuation. Do not expose REA/Fusion/unrelated materials.
- Add validated evidence-index JSONL records after the full graph is generated, and run `tools/audit/validate_index.py`; this checkpoint is deliberately not labeled complete.

## Safety and provenance

Original source untouched. No runtime boot, production access, build repetition, PR merge, REA or agent invocation in this continuation. Previous A3-ROUTE-001 evidence remains authoritative for completed first-pass inventory.