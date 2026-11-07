# A3-ROUTE-002 — TypeScript AST extraction

Immutable source `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`. TypeScript 5.9.3. Source AST only: not runtime or complete semantic symbol resolution.

## Counts

- uiFiles: 38
- backendFiles: 105
- uiFunctions: 160
- jsxEventBindings: 603
- jsxInlineHandlers: 520
- uiCallSites: 2878
- uiNetworkSites: 64
- dynamicNetworkSites: 22
- hookEffects: 40
- backendDeclaredRoutes: 64
- backendMounts: 23
- sdkReferences: 2
- writeCandidates: 105
- parseErrors: 0

## UI network calls

| Source | Owner | Method | Path expression | Static URL |
| --- | --- | --- | --- | --- |
| `ui/src/App.tsx:199` | discoverCaps | POST | `/api/indexers/caps` | yes |
| `ui/src/App.tsx:262` | handleDeleteIndexer | DELETE | ``/api/indexers/${encodeURIComponent(name)}`` | no |
| `ui/src/App.tsx:278` | handleAddIndexer | POST | `/api/indexers` | yes |
| `ui/src/App.tsx:330` | handleReorderIndexer | POST | `/api/indexers/reorder` | yes |
| `ui/src/App.tsx:365` | saveIndexerOrder | POST | `/api/indexers/reorder` | yes |
| `ui/src/App.tsx:394` | handleReorderSyncedIndexer | POST | `/api/synced-indexers/reorder` | yes |
| `ui/src/App.tsx:416` | handleTestIndexer | POST | `/api/indexers/test-new` | yes |
| `ui/src/App.tsx:427` | handleTestIndexer | POST | ``/api/indexers/${encodeURIComponent(indexerName)}/test?q=${encodeURIComponent(query)}`` | no |
| `ui/src/components/DashboardTab.tsx:127` | DashboardTab | GET(default) | `/api/nzbdav/cache` | yes |
| `ui/src/components/InstallTab.tsx:56` | addInstall | POST | `/api/manifests` | yes |
| `ui/src/components/InstallTab.tsx:73` | handleRegenerate | POST | ``/api/manifests/${id}/regenerate`` | no |
| `ui/src/components/InstallTab.tsx:84` | handleDelete | DELETE | ``/api/manifests/${id}`` | no |
| `ui/src/components/InstallTab.tsx:95` | handleRename | PUT | ``/api/manifests/${id}`` | no |
| `ui/src/components/overlays/CacheTTLOverlay.tsx:128` | inline@onClick | DELETE | `/api/search-cache` | yes |
| `ui/src/components/overlays/IndexManagerOverlay.tsx:439` | inline@onChange | POST | `/api/prowlarr/sync` | yes |
| `ui/src/components/overlays/IndexManagerOverlay.tsx:457` | inline@onChange | POST | `/api/nzbhydra/sync` | yes |
| `ui/src/components/overlays/IndexManagerOverlay.tsx:1367` | inline@onClick | POST | `/api/easynews/test` | yes |
| `ui/src/components/overlays/IndexManagerOverlay.tsx:1449` | inline@onClick | POST | `/api/prowlarr/sync` | yes |
| `ui/src/components/overlays/IndexManagerOverlay.tsx:1786` | inline@onClick | POST | `/api/nzbhydra/sync` | yes |
| `ui/src/components/overlays/IndexManagerOverlay.tsx:2125` | inline@onClick | PUT | ``/api/indexers/${encodeURIComponent(indexer.name)}`` | no |
| `ui/src/components/overlays/LogsOverlay.tsx:20` | LogsOverlay | GET(default) | `/api/logs` | yes |
| `ui/src/components/overlays/LogsOverlay.tsx:24` | LogsOverlay | GET-or-protocol | ``/api/logs/stream${token ? `?token=${token}` : ''}`` | no |
| `ui/src/components/overlays/NzbDatabaseOverlay.tsx:152` | fetchEntries | GET(default) | `/api/nzbdav/cache/entries` | yes |
| `ui/src/components/overlays/NzbDatabaseOverlay.tsx:153` | fetchEntries | GET(default) | `/api/nzbdav/cache` | yes |
| `ui/src/components/overlays/NzbDatabaseOverlay.tsx:180` | deleteEntry | DELETE | ``/api/nzbdav/cache/entry?key=${encodeURIComponent(key)}`` | no |
| `ui/src/components/overlays/NzbDatabaseOverlay.tsx:184` | deleteEntry | GET(default) | `/api/nzbdav/cache` | yes |
| `ui/src/components/overlays/NzbDatabaseOverlay.tsx:195` | clearReady | DELETE | `/api/nzbdav/cache/ready` | yes |
| `ui/src/components/overlays/NzbDatabaseOverlay.tsx:203` | clearFailed | DELETE | `/api/nzbdav/cache/failed` | yes |
| `ui/src/components/overlays/StatsOverlay.tsx:452` | inline@onClick | DELETE | ``/api/stats/${encodeURIComponent(indexer.indexerName)}`` | no |
| `ui/src/components/overlays/StatsOverlay.tsx:577` | inline@onClick | DELETE | `/api/stats` | yes |
| `ui/src/components/overlays/UserAgentOverlay.tsx:127` | inline@onClick | GET(default) | `/api/user-agents/latest` | yes |
| `ui/src/components/overlays/ZyclopsOverlay.tsx:119` | inline@onClick | POST | `/api/zyclops/test` | yes |
| `ui/src/components/overlays/ZyclopsOverlay.tsx:189` | inline@onChange | PUT | ``/api/indexers/${encodeURIComponent(indexer.name)}`` | no |
| `ui/src/components/overlays/ZyclopsOverlay.tsx:243` | inline@onChange | PUT | ``/api/indexers/${encodeURIComponent(indexer.name)}`` | no |
| `ui/src/components/overlays/ZyclopsOverlay.tsx:271` | inline@onChange | PUT | ``/api/indexers/${encodeURIComponent(indexer.name)}`` | no |
| `ui/src/components/overlays/ZyclopsOverlay.tsx:294` | inline@onChange | PUT | ``/api/indexers/${encodeURIComponent(indexer.name)}`` | no |
| `ui/src/components/overlays/ZyclopsOverlay.tsx:319` | inline@onChange | PUT | ``/api/indexers/${encodeURIComponent(indexer.name)}`` | no |
| `ui/src/components/overlays/ZyclopsOverlay.tsx:399` | inline@onClick | PUT | ``/api/indexers/${encodeURIComponent(indexerName)}`` | no |
| `ui/src/components/overlays/ZyclopsOverlay.tsx:475` | inline@onClick | PUT | ``/api/indexers/${encodeURIComponent(indexerName)}`` | no |
| `ui/src/components/overlays/rules/RulesSection.tsx:455` | callImport | POST | `/api/rules/import` | yes |
| `ui/src/components/overlays/rules/RulesSection.tsx:756` | LiveTestField | POST | `/api/rules/preview` | yes |
| `ui/src/components/shared/ProviderManager.tsx:45` | testProviderConnection | POST | `/api/health-check/test` | yes |
| `ui/src/components/shared/ProviderManager.tsx:72` | handleAddProvider | POST | `/api/health-check/providers` | yes |
| `ui/src/components/shared/ProviderManager.tsx:101` | handleUpdateProvider | PUT | ``/api/health-check/providers/${id}`` | no |
| `ui/src/components/shared/ProviderManager.tsx:120` | handleDeleteProvider | DELETE | ``/api/health-check/providers/${id}`` | no |
| `ui/src/components/shared/ProviderManager.tsx:135` | handleToggleProvider | PUT | ``/api/health-check/providers/${id}`` | no |
| `ui/src/components/shared/ProviderManager.tsx:177` | handleProviderDrop | POST | `/api/health-check/providers/reorder` | yes |
| `ui/src/hooks/useAppConfig.ts:286` | saveSettings | PUT | `/api/settings` | yes |
| `ui/src/hooks/useAppConfig.ts:528` | timer | PUT | ``/api/indexers/${encodeURIComponent(savedName)}`` | no |
| `ui/src/hooks/useAppConfig.ts:572` | fetchIndexers | GET(default) | `/api/indexers` | yes |
| `ui/src/hooks/useAppConfig.ts:582` | fetchConfig | GET(default) | `/api/config` | yes |
| `ui/src/hooks/useAppConfig.ts:919` | fetchConfig | POST | `/api/nzbdav/test` | yes |
| `ui/src/hooks/useAppConfig.ts:947` | fetchStats | GET(default) | `/api/stats` | yes |
| `ui/src/hooks/useAppConfig.ts:963` | fetchLocalIp | GET(default) | `/api/ip/local` | yes |
| `ui/src/hooks/useAppConfig.ts:973` | checkProxyStatus | GET(default) | ``/api/proxy/status?url=${encodeURIComponent(proxyUrl)}`` | no |
| `ui/src/hooks/useAppConfig.ts:1001` | checkNzbdavConnection | POST | `/api/nzbdav/test` | yes |
| `ui/src/hooks/useAppConfig.ts:1023` | sendNzbdavTestNzb | POST | `/api/nzbdav/test` | yes |
| `ui/src/hooks/useAppConfig.ts:1054` | testTmdbKey | POST | `/api/search-config/test-tmdb` | yes |
| `ui/src/hooks/useAppConfig.ts:1070` | testTvdbKey | POST | `/api/search-config/test-tvdb` | yes |
| `ui/src/hooks/useAppConfig.ts:1166` | handleCardDrop | PUT | `/api/settings` | yes |
| `ui/src/hooks/useAuth.ts:78` | handleSetup | POST | `/api/auth/setup` | yes |
| `ui/src/hooks/useAuth.ts:105` | handleLogin | POST | `/api/auth/login` | yes |
| `ui/src/hooks/useAuth.ts:133` | checkAuth | GET(default) | `/api/auth/status` | yes |
| `ui/src/utils/api.ts:13` | createApiFetch | GET(default) | `url` | no |

## Explicit backend route declarations

| Source | Method | Path |
| --- | --- | --- |
| `src/routes/auth.ts:29` | GET | `/auth/status` |
| `src/routes/auth.ts:53` | POST | `/auth/setup` |
| `src/routes/auth.ts:75` | POST | `/auth/login` |
| `src/routes/auth.ts:95` | GET | `/favicon` |
| `src/routes/easynewsProxy.ts:25` | GET | `/resolve` |
| `src/routes/easynewsProxy.ts:108` | GET | `/nzb` |
| `src/routes/externalApis.ts:15` | POST | `/test-tmdb` |
| `src/routes/externalApis.ts:51` | POST | `/test-tvdb` |
| `src/routes/healthCheck.ts:30` | POST | `/test` |
| `src/routes/healthCheck.ts:126` | GET | `/providers` |
| `src/routes/healthCheck.ts:130` | POST | `/providers` |
| `src/routes/healthCheck.ts:154` | PUT | `/providers/:id` |
| `src/routes/healthCheck.ts:163` | DELETE | `/providers/:id` |
| `src/routes/healthCheck.ts:172` | POST | `/providers/reorder` |
| `src/routes/indexers.ts:65` | GET | `/` |
| `src/routes/indexers.ts:69` | POST | `/` |
| `src/routes/indexers.ts:101` | PUT | `/:name` |
| `src/routes/indexers.ts:185` | DELETE | `/:name` |
| `src/routes/indexers.ts:195` | POST | `/:name/test` |
| `src/routes/indexers.ts:271` | POST | `/test-new` |
| `src/routes/indexers.ts:325` | POST | `/reorder` |
| `src/routes/indexers.ts:342` | POST | `/caps` |
| `src/routes/integrations.ts:42` | POST | `/prowlarr/sync` |
| `src/routes/integrations.ts:125` | POST | `/nzbhydra/sync` |
| `src/routes/integrations.ts:288` | POST | `/zyclops/test` |
| `src/routes/integrations.ts:317` | POST | `/easynews/test` |
| `src/routes/integrations.ts:350` | PUT | `/synced-indexers/:id` |
| `src/routes/integrations.ts:364` | PUT | `/synced-indexers` |
| `src/routes/integrations.ts:374` | POST | `/synced-indexers/reorder` |
| `src/routes/logs.ts:20` | GET | `/` |
| `src/routes/logs.ts:24` | GET | `/stream` |
| `src/routes/manifests.ts:23` | GET | `/` |
| `src/routes/manifests.ts:29` | POST | `/` |
| `src/routes/manifests.ts:45` | PUT | `/:id` |
| `src/routes/manifests.ts:60` | POST | `/:id/regenerate` |
| `src/routes/manifests.ts:71` | DELETE | `/:id` |
| `src/routes/nzbdav.ts:50` | POST | `/test` |
| `src/routes/nzbdav.ts:158` | GET | `/cache` |
| `src/routes/nzbdav.ts:163` | DELETE | `/cache` |
| `src/routes/nzbdav.ts:169` | GET | `/cache/entries` |
| `src/routes/nzbdav.ts:174` | DELETE | `/cache/ready` |
| `src/routes/nzbdav.ts:180` | DELETE | `/cache/failed` |
| `src/routes/nzbdav.ts:186` | DELETE | `/cache/entry` |
| `src/routes/nzbdav.ts:221` | GET | `/library-bypass` |
| `src/routes/nzbdav.ts:397` | GET | `/library-delete` |
| `src/routes/nzbdav.ts:441` | GET | `/library-delete-all` |
| `src/routes/nzbdav.ts:496` | GET | `/stream/:filename?` |
| `src/routes/nzbdav.ts:1022` | GET | `/v` |
| `src/routes/rules.ts:28` | POST | `/import` |
| `src/routes/rules.ts:85` | POST | `/preview` |
| `src/routes/settings.ts:117` | GET | `/config` |
| `src/routes/settings.ts:147` | PUT | `/settings` |
| `src/routes/settings.ts:149` | POST | `/settings` |
| `src/routes/settings.ts:152` | GET | `/user-agents/latest` |
| `src/routes/settings.ts:169` | GET | `/proxy/status` |
| `src/routes/settings.ts:180` | GET | `/ip/local` |
| `src/routes/settings.ts:191` | DELETE | `/search-cache` |
| `src/routes/stats.ts:24` | GET | `/` |
| `src/routes/stats.ts:33` | GET | `/:indexerName` |
| `src/routes/stats.ts:45` | DELETE | `/:indexerName` |
| `src/routes/stats.ts:54` | DELETE | `/` |
| `src/server.ts:76` | GET | `/health` |
| `src/server.ts:192` | GET | `/manifest.json` |
| `src/server.ts:215` | GET | `*` |

## SDK and mounted routers
- src/addon/index.ts:194 builder.defineStreamHandler
- src/server.ts:197 getRouter
- src/server.ts:59 app.use(cors())
- src/server.ts:63 app.use(express.json({ limit: '5mb' }))
- src/server.ts:72 app.use(staticMiddleware)
- src/server.ts:73 app.use('/stremio', staticMiddleware)
- src/server.ts:92 app.use('/api', createAuthRoutes({ config, hasAnyUsers, createUser, authenticateUser, generateToken, verifyToken, getUserById, getLatestVersions, }))
- src/server.ts:104 app.use('/api', requireAuth)
- src/server.ts:107 app.use('/api/manifests', createManifestRoutes({ getManifests, createManifest, updateManifest, regenerateManifest, deleteManifest, }))
- src/server.ts:131 app.use('/api/indexers', createIndexerRoutes({ config, getIndexers, addIndexer, updateIndexer, deleteIndexer, reorderIndexers, fetchIndexerCaps, pro)
- src/server.ts:143 app.use('/api', createIntegrationRoutes({ config, updateSettings, reorderSyncedIndexers, getLatestVersions, }))
- src/server.ts:150 app.use('/api', createSettingsRoutes({ config, updateSettings, fetchLatestVersions, getLatestVersions, testProxyConnection, clearSearchCache, }))
- src/server.ts:159 app.use('/api/nzbdav', createNzbdavRoutes(nzbdavDeps))
- src/server.ts:161 app.use('/api/health-check', createHealthCheckRoutes({ getProviders, addProvider, updateProvider, deleteProvider, reorderProviders, }))
- src/server.ts:169 app.use('/api/search-config', createExternalApiRoutes())
- src/server.ts:171 app.use('/api/stats', createStatsRoutes({ getAllStats, getIndexerStats, resetIndexerStats, resetAllStats, }))
- src/server.ts:178 app.use('/api/logs', createLogRoutes({ getLogBuffer, subscribeToLogs, }))
- src/server.ts:183 app.use('/api/rules', createRulesRoutes())
- src/server.ts:197 stremioRouter.use(getRouter(addon))
- src/server.ts:205 app.use('/stremio/:manifestKey/easynews', validateManifestKey, easynewsRoutes)
- src/server.ts:206 app.use('/stremio/:manifestKey/nzbdav', validateManifestKey, nzbdavRoutes)
- src/server.ts:207 app.use('/stremio/:manifestKey', validateManifestKey, contextMiddleware('/stremio'), stremioRouter)
- src/server.ts:210 app.use('/:manifestKey/easynews', validateManifestKey, easynewsRoutes)
- src/server.ts:211 app.use('/:manifestKey/nzbdav', validateManifestKey, nzbdavRoutes)
- src/server.ts:212 app.use('/:manifestKey', validateManifestKey, contextMiddleware(''), stremioRouter)

## Mutation candidates
- ui/src/components/overlays/LogsOverlay.tsx:49 browser-storage: localStorage.setItem
- ui/src/components/overlays/LogsOverlay.tsx:53 browser-storage: localStorage.setItem
- ui/src/hooks/useAuth.ts:50 browser-storage: localStorage.setItem
- ui/src/hooks/useAuth.ts:124 browser-storage: localStorage.removeItem
- ui/src/hooks/useAuth.ts:145 browser-storage: localStorage.removeItem
- ui/src/utils/api.ts:15 browser-storage: localStorage.removeItem
- src/addon/index.ts:80 heuristic: cache.del
- src/addon/index.ts:504 heuristic: cache.set
- src/addon/index.ts:582 heuristic: cache.set
- src/anime/animeDatabase.ts:138 operation-name: fs.mkdirSync
- src/anime/animeDatabase.ts:140 operation-name: fs.writeFileSync
- src/anime/animeDatabase.ts:153 heuristic: idx.fribbByAnidb.set
- src/anime/animeDatabase.ts:154 heuristic: idx.fribbByImdb.set
- src/anime/animeDatabase.ts:155 heuristic: idx.fribbByTmdb.set
- src/anime/animeDatabase.ts:156 heuristic: idx.fribbByTvdb.set
- src/anime/animeDatabase.ts:165 heuristic: idx.kitsuImdbByKitsu.set
- src/anime/animeDatabase.ts:214 heuristic: idx.animeListsByAnidb.set
- src/auth/auth.ts:62 operation-name: fs.mkdirSync
- src/auth/auth.ts:64 operation-name: fs.writeFileSync
- src/config/schema.ts:167 operation-name: fs.writeFileSync
- src/config/schema.ts:168 operation-name: fs.renameSync
- src/config/schema.ts:170 operation-name: fs.unlinkSync
- src/config/schema.ts:186 operation-name: fs.mkdirSync
- src/health/nzbContentCache.ts:25 heuristic: cache.delete
- src/health/nzbContentCache.ts:31 heuristic: cache.delete
- src/health/nzbContentCache.ts:33 heuristic: cache.set
- src/health/nzbContentCache.ts:41 heuristic: cache.delete
- src/idResolver.ts:49 heuristic: idCache.set
- src/idResolver.ts:116 heuristic: idCache.set
- src/idResolver.ts:119 heuristic: idCache.set
- src/idResolver.ts:157 heuristic: idCache.set
- src/idResolver.ts:199 heuristic: idCache.set
- src/idResolver.ts:201 heuristic: idCache.set
- src/idResolver.ts:207 heuristic: idCache.set
- src/idResolver.ts:265 heuristic: idCache.set
- src/idResolver.ts:272 heuristic: idCache.set
- src/idResolver.ts:317 heuristic: idCache.set
- src/idResolver.ts:337 heuristic: idCache.set
- src/idResolver.ts:342 heuristic: idCache.set
- src/idResolver.ts:436 heuristic: idCache.del
- src/idResolver.ts:481 heuristic: idCache.set
- src/idResolver.ts:489 heuristic: idCache.set
- src/idResolver.ts:632 heuristic: idCache.del
- src/idResolver.ts:660 heuristic: idCache.set
- src/idResolver.ts:683 heuristic: idCache.set
- src/idResolver.ts:686 heuristic: idCache.set
- src/idResolver.ts:724 heuristic: idCache.set
- src/idResolver.ts:726 heuristic: idCache.set
- src/idResolver.ts:729 heuristic: idCache.set
- src/idResolver.ts:731 heuristic: idCache.set
- src/idResolver.ts:736 heuristic: idCache.set
- src/idResolver.ts:764 heuristic: idCache.del
- src/idResolver.ts:779 heuristic: idCache.del
- src/idResolver.ts:824 heuristic: idCache.set
- src/idResolver.ts:926 heuristic: idCache.del
- src/idResolver.ts:1002 heuristic: idCache.set
- src/nzbdav/bdmvResolver.ts:90 heuristic: bdmvMapCache.set
- src/nzbdav/bdmvResolver.ts:214 heuristic: bdmvMapCache.set
- src/nzbdav/fallbackManager.ts:71 operation-name: fs.writeFileSync
- src/nzbdav/streamCache.ts:136 heuristic: cache.delete
- src/nzbdav/streamCache.ts:176 heuristic: readyCache.set
- src/nzbdav/streamCache.ts:204 heuristic: deadNzbCache.set
- src/nzbdav/streamCache.ts:213 heuristic: deadNzbCache.set
- src/nzbdav/streamCache.ts:229 operation-name: fs.writeFileSync
- src/nzbdav/streamCache.ts:250 operation-name: fs.writeFileSync
- src/nzbdav/streamCache.ts:293 heuristic: readyCache.set
- src/nzbdav/streamCache.ts:316 heuristic: deadNzbCache.set
- src/nzbdav/streamCache.ts:324 heuristic: pendingCache.delete
- src/nzbdav/streamCache.ts:327 heuristic: readyCache.delete
- src/nzbdav/streamCache.ts:330 heuristic: deadNzbCache.delete
- src/nzbdav/streamCache.ts:404 heuristic: pendingCache.delete
- src/nzbdav/streamCache.ts:430 heuristic: pendingCache.set
- src/nzbdav/streamCache.ts:437 heuristic: pendingCache.delete
- src/nzbdav/streamCache.ts:439 heuristic: readyCache.set
- src/nzbdav/streamCache.ts:450 heuristic: pendingCache.delete
- src/nzbdav/streamCache.ts:464 heuristic: deadNzbCache.set
- src/nzbdav/streamCache.ts:501 heuristic: deadNzbCache.delete
- src/nzbdav/streamCache.ts:517 heuristic: readyCache.clear
- src/nzbdav/streamCache.ts:530 heuristic: deadNzbCache.clear
- src/nzbdav/streamCache.ts:543 heuristic: deadNzbCache.delete
- src/nzbdav/streamCache.ts:563 heuristic: deadNzbCache.delete
- src/nzbdav/streamCache.ts:579 heuristic: deadNzbCache.delete
- src/nzbdav/streamCache.ts:595 heuristic: readyCache.delete
- src/nzbdav/streamCache.ts:596 heuristic: deadNzbCache.delete
- src/nzbdav/streamCache.ts:597 heuristic: pendingCache.delete
- src/nzbdav/streamCache.ts:614 heuristic: readyCache.delete
- src/nzbdav/streamCache.ts:629 heuristic: deadNzbCache.set
- src/nzbdav/streamCache.ts:664 heuristic: deadNzbCache.delete
- src/nzbdav/streamCache.ts:685 heuristic: readyCache.delete
- src/nzbdav/streamCache.ts:699 heuristic: deadNzbCache.set
- src/nzbdav/streamCache.ts:720 heuristic: deadNzbCache.delete
- src/nzbdav/streamCache.ts:866 heuristic: deadNzbCache.set
- src/nzbdav/ultimateFallback.ts:170 operation-name: fs.writeFileSync
- src/proxy.ts:583 heuristic: exitIpCache.delete
- src/proxy.ts:591 heuristic: exitIpCache.set
- src/proxy.ts:640 heuristic: exitIpCache.delete
- src/proxy.ts:665 heuristic: exitIpCache.clear
- src/routes/nzbdav.ts:257 heuristic: recentLoggedBypassKeys.delete
- src/rules/rankEngine.ts:153 heuristic: compileCache.delete
- src/rules/rankEngine.ts:155 heuristic: compileCache.set
- src/rules/rankEngine.ts:159 heuristic: compileCache.delete
- src/rules/rankEngine.ts:160 heuristic: compileCache.clear
- src/server.ts:223 operation-name: fs.unlinkSync
- src/statsTracker.ts:83 operation-name: fs.writeFileSync
- src/versionFetcher.ts:42 operation-name: fs.writeFileSync

## Limitations
- JSX prop aliasing, dynamic URLs, cross-module symbol references, dependencies, and persistent store targets require additional resolution.
- SDK-generated Stremio routes are not explicitly declared in app AST.
- Heuristic mutation methods are candidates, not proven durable sinks.
- No application, credentials, NNTP, NzbDAV, or production access.