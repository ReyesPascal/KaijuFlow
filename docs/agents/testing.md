# Running the tests

Commands are the `package.json` scripts. The things they don't tell you:

- **Integration and A4 runners test committed code.** Commit, then run `npm run test:integration` / `npm run test:a4`: they rebuild `dist/` first. Calling a `run-ci.sh` directly stops with STALE-DIST when `dist/` is older than `src/`.
- **Fresh worktree:** run `npm ci` at the root *and* in `ui/`.
- **Memory:** each integration scenario runs under a 4G cap (`tests/integration/in-namespace.sh`) and prints `INTEGRATION MEMORY <name> peak_rss_kb=…`. When running several suites at once (parallel agents), wrap each run too: `systemd-run --user --scope -q -p MemoryMax=6G -p MemorySwapMax=0 bash -c "…"`.
- **Comparing bytes:** use `assertBytes` from `tests/integration/parity/bytes.mjs`. `tests/unit/byte-compare-guard.test.ts` fails on `deepEqual` over bytes, because its mismatch diff can take tens of GB.
- **Parity:** shared scenarios live in `tests/integration/parity/scenarios.mjs` and run against every fake Backend (`parity-nzbdav.mjs`, `parity-altmount.mjs`).
- **Fake Backends:** their replies must keep the real Backend's layout. `tests/unit/fake-backend-shape.test.ts` compares them with replies captured on Brain (`tests/fixtures/backends/`); when a real Backend changes, capture a new reply there.
