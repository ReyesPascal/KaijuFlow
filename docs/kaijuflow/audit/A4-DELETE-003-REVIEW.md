# A4-DELETE-003 — independent source review and expanded regression checkpoint

Date: 2026-11-07. Immutable original application source: `c83a3c733b6394eb140a1c0a1dc500010a9f22e5`. Audit-only test expansion commit: `f838c16fb9fa5a5896553088816617d46fc158cf`.

## Independently inspected original behavior (source-observed)

- `src/routes/nzbdav.ts:397` and `:455` register destructive tile actions with Express `router.get('/library-delete')` and `router.get('/library-delete-all')`. Express implicitly accepts HEAD for a GET handler when no explicit HEAD route is installed. This explains the previously **test-observed** HEAD side effect without requiring any production access.
- `src/routes/nzbdav.ts:273-285` stores a 30-second deduplication deadline **before** network deletion. The single-delete route calls this before `runWebdavDelete` at `:424-433`; a 503 leaves the dedup entry until TTL expiration. A repeated request can therefore receive the success placeholder even though the prior deletion failed.
- The delete-all route likewise records dedup before looking up its `tk` targets and before remote deletes. An absent/expired token or a completely failed batch can be marked handled and a subsequent request may return a success placeholder. **This is a source-derived hypothesis, not an executed delete-all test.**
- For individual file-scope deletions, a successful deletion may also cause ancestor pruning and history/cache side effects. Do not interpret the WebDAV DELETE count as a complete side-effect audit.
- The tile envelope's `sk` is presently checked for being a nonempty string in the reviewed route; no route-local comparison to a server-side `sk` is apparent. Manifest-key validation still gates routing. Whether the `sk` is intended as an independent proof is unverified.

## Expanded synthetic assertions added

`tests/a4/synthetic.mjs` now probes path traversal, too-deep pack paths, malformed tile envelopes, invalid manifest-key access, and four concurrent identical deletion requests in addition to earlier invalid-path/HEAD/GET replay/503 assertions. Each uses the already proven disposable network namespace, fake loopback WebDAV, fabricated manifest and original unmodified router. Concurrent requests use a unique target to avoid the earlier key's 30-second dedup window. The expected count for a coalesced same-key burst is one remote DELETE. The prior HEAD and failed-503 expectations are deliberately kept red to preserve safety-regression visibility.

**Execution status:** these added tests are committed but not yet independently confirmed by a new GitHub Actions result at the time of this review; do not mark them passed. Earlier A4-ISO-000 gate and 2026-11-07 observed failures remain anchored to run 42366142956.

## Risk, suggested subsequent tests, boundaries

Destructive HEAD may be triggered by HTTP/media-client metadata probes, *if* the valid action URL is available. This is plausible impact, not proven production exploitation. A 503 may be transient, but current dedup can mask failure until TTL expiry. Before any fix proposal, validate `/library-delete-all`, overlapping keys, 404/410 idempotence, real clock/TTL expiration, concurrent slow DELETE failures, Range requests, partial failures and ancestor pruning using synthetic fixtures.

The original imported source was not modified. No production calls, real provider credentials, private NZBs, Brain changes, PR merges or deployment occurred. React `useAppConfig` 300/500ms timers and overlapping in-flight requests remain a separate **not-run** A4-AUTOSAVE-004 task; backend sequential settings success does not validate UI concurrency.
