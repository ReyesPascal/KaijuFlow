# A3-ROUTE-002 — pinned Stremio SDK router implementation evidence

**Date:** 2026-11-07. **App source pin:** `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`. **Installed package:** `stremio-addon-sdk@1.6.10` from the original root package lock. **Type:** read-only source-observed AST; **NOT** a runtime test.

## Verified isolated extraction

- [GitHub Actions run 42362133211](https://github.com/ReyesPascal/KaijuFlow/actions/runs/42362133211) completed **successfully** on audit commit `37e6408e0769786e2879d87e6b9a114eba16f054`. CI installed locked dependencies with `npm ci --ignore-scripts`; it did not import or execute KaijuFlow or the SDK HTTP server.
- The committed, reproducible extractor is `tools/audit/inspect_stremio_sdk.cjs`. TypeScript parser scanned **10 JS files** in the SDK package, with **zero parse errors**, identified **11 candidate calls** (`get/post/use` etc., including **SDK test and standalone serveHTTP** usages) and **three getRouter name references**. These counts are **not** the number of routes mounted in KaijuFlow.
- Stored private CI artifact `a3-route-002-ast`, ID **13569588096**, contains `sdk-routes.json`, `ast-edges.json`, and `AST_SUMMARY.md`; expires 2026-11-21. ZIP SHA-256: `3dcfeaa731e845d78d3f7b37516f367da73db4653c3e00fa17ee347226fdd0db`. `sdk-routes.json` SHA-256: `072de76a94e7e35179f0504428e269ddfedbf24cd45e227a4415c5f214cc629f`. All identities derive from successful workflow metadata/logs.

## Relevant getRouter(app) registrations

The installed SDK `src/getRouter.js` contains these router registrations, distinct from the standalone SDK `serveHTTP` helper:

| SDK location | AST-observed implementation |
| --- | --- |
| `src/getRouter.js:5` | `getRouter({ manifest, get })` constructs an Express Router |
| `src/getRouter.js:9` | `router.use(cors())` |
| `src/getRouter.js:38` | `router.get(`\${configPrefix}/manifest.json`, manifestHandler)` |
| `src/getRouter.js:49` | `router.get(`\${configPrefix}/:resource\${ResourcesRegex}/:type/:id/:extra?.json`, handler)` |

The template-expression prefix and resource regex are **not static literal strings**. The AST identifies the exact declaration forms but does not establish values of `configPrefix`/`ResourcesRegex` for every configuration. The SDK `serveHTTP` also defines `GET /` and `GET /configure` in `src/serveHTTP.js:37,47`; **KaijuFlow calls `getRouter(addon)`, not `serveHTTP`**, so those standalone helper routes must not be counted as app routes.

KaijuFlow's [`src/server.ts:190-213`](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/server.ts#L190-L213) separately registers `GET /manifest.json` **before** `stremioRouter.use(getRouter(addon))`, and mounts the router behind manifest-key validation at **both** `/stremio/:manifestKey` and `/:manifestKey`. The app's explicit custom manifest route normally takes priority on that path by Express registration order; need synthetic request tests for route precedence and optional SDK config prefix. The SDK resource route is a single Express declaration matching resource types and optional extra, **not** 1 endpoint per individual Stremio resource.

## Confidence boundaries

- Source route declarations and mount relationships verified. Runtime matching, authorization, optional SDK config and all ID/path variants remain untested.
- No original files changed, no application boot, no REA/Fusion or production activity, no deployment or merges.
- Preserve the separate A3 AST totals of **64 explicit app declarations including SPA fallback**, **603 JSX event sites**, and **64 UI network sites**. Do **not** add SDK test/serveHTTP calls to application route totals.
