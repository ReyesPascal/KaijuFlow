# Running the tests

Commands are the `package.json` scripts. The things they don't tell you:

- **Integration and A4 runners test committed code.** Commit, then run `npm run test:integration` / `npm run test:a4`: they rebuild `dist/` first. Calling a `run-ci.sh` directly stops with STALE-DIST when `dist/` is older than `src/`.
- **Fresh worktree:** run `npm ci` at the root *and* in `ui/`.
- **Node for `nobody`:** the isolated runners run node as user `nobody`, which cannot enter `/home`. They stop with NODE-UNREACHABLE when it can't run node from your PATH. On Brain a root-owned copy sits at `/opt/node-20`, linked as `/usr/local/bin/node`: `nobody` is denied `~/.local/node` and finds that one later in PATH. After upgrading `~/.local/node`, refresh the copy (`sudo cp -a`, then `chown -R root:root`).
- **Memory:** each integration scenario runs under a 4G cap (`tests/integration/in-namespace.sh`) and prints `INTEGRATION MEMORY <name> peak_rss_kb=…`. When running several suites at once (parallel agents), wrap each run too: `systemd-run --user --scope -q -p MemoryMax=6G -p MemorySwapMax=0 bash -c "…"`.
- **Comparing bytes:** use `assertBytes` from `tests/integration/parity/bytes.mjs`. `tests/unit/byte-compare-guard.test.ts` fails on `deepEqual` over bytes, because its mismatch diff can take tens of GB.
- **Parity:** shared scenarios live in `tests/integration/parity/scenarios.mjs` and run against the fake AltMount (`parity-altmount.mjs`, `parity-altmount-delivery.mjs`), the one Backend.
- **Fake news server:** `tests/integration/parity/fake-nntp.mjs` serves synthetic RAR5 first articles over loopback and is KaijuFlow's only health-check provider in the Parity suites (`useFakeNews`). `scrambledRarSet` builds a Scrambled RAR set NZB; the Unscramble unit tests use the same helpers.
- **Fake Backends:** their replies must keep the real Backend's layout. `tests/unit/fake-backend-shape.test.ts` compares them with replies captured on Brain (`tests/fixtures/backends/`); when a real Backend changes, capture a new reply there.
- **Brain tools** (`tools/brain/*.py`): `npm run check:brain` runs CI's compile, lint (ruff 0.6.9) and tests in one go; use it in agent briefs instead of spelling out the commands.
- **One brain test:** `python3 -I -m unittest discover -s tools/brain -p 'test_frontier.py' -k test_leaves_out_spec_issues` (the file in `-p`, optionally one test or class name in `-k`; run from the repo root).
- **Guard hook:** `.claude/settings.json` runs `tools/brain/guard.py` on Bash, Read and Grep. It refuses reading the test folder's key files or a test copy's config (use `python3 -I tools/brain/testbed.py read-settings [side]`, secrets as `***`) and the `gh` calls that fail here; it allows the brain tools and everything unrelated. Details in the runbook.
- **Live checks on Brain** (timed runs, article checks): `tools/brain/README.md`; the rules (the owner's go first) are in `tools/brain/RUNBOOK.md`.
