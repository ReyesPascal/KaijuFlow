# Runbook: a timed run on the test copies

Every command runs from the repo root. Long ones: shell background mode with a hard `timeout`, and watch the log (stop at the first `Error`).

**Rules.** Every timed run needs the owner's go. Live containers (UU 1337, NzbDAV 3000, AltMount 8085) are never touched. Only NinjaCentral is used: DrunkenSlug is switched off in the test copies but left in place. The default key file `~/kaijuflow-test/indexers.json` holds NinjaCentral only, so never pass `--key-file`. If an indexer says "limit reached", the work waits for NinjaCentral's reset (cap rule: the pass stops and the recording is null).

`<store>` is the folder of recordings, `<list>` the title list's name, `<name>` a label for the folder.

## The recipe

0. A commit that changes the code in the image since the image was built? Add `--rebuild-image` to the first preflight below. The code in the image is `src/`, `ui/`, `package.json`, `package-lock.json`, `tsconfig.json`, `scripts/docker-entrypoint.sh`, the `Dockerfile` and `.dockerignore`. A commit that touches only docs, tools or tests needs no rebuild; the preflight says when one is needed.
1. Allowance: `python3 -I tools/brain/brainrun.py usage` shows Used, Limit and Left per indexer (limits in `~/kaijuflow-test/limits.json`). Do this before any record.
2. Preflight: `python3 -I tools/brain/brainrun.py preflight --for record --store <store> --list <list> [--rebuild-image]`. Fix every sentence it prints; exit 0 means go.
3. Record: `python3 -I tools/brain/brainrun.py record --name <name> --store <store> --list <list> [--one-page] [--titles-file titles.json]`. It resets the test copies, sends every side through a cold round and a warm round (the only step that asks the real indexer), then proves the recording by replaying it with no indexer contacted. A second `record` of the same list only asks for what is missing (top-up).
4. Preflight for the run: `... preflight --for run --store <store> --list <list>`.
5. Run: `python3 -I tools/brain/brainrun.py run --name <name> --store <store> --list <list> [--one-page] [--no-wait]`. Four rounds per side (cold, warm, cold, warm) from the recording; no indexer is contacted. It ends by printing the check.
6. Check: `python3 -I tools/brain/brainrun.py check --run <run folder>`. Says whether the run can serve as a baseline, then prints one line per target: the target, the measured values, met or not met.

Other commands: `smoke --store <EMPTY folder> --list smoke` (reachability only), `python3 -I tools/brain/testbed.py settings|status|stop`.

## Flags that matter

- `--for run|record` (preflight): which setup to check. `--rebuild-image`: build `kaijuflow:test` from the current commit when the code in the image has changed since it was built (otherwise the image is left alone).
- `--one-page`: add the fourth side (KaijuFlow, one page per indexer). `--titles-file`: another title list (JSON). `--no-wait` (run): replay answers at once, for tuning runs only.
- `--runs-root DIR`: where run folders go (default `~/kaijuflow-notes/brain-runs`; use a temporary one for trials). `--provider-limit N`: connection cap, default 100.

## Exit codes

- record: 0 complete (a run may use it); 1 setup problem or the pass broke (nothing recorded); 2 stopped by an indexer limit (stored answers kept; run the same command after the reset); 3 incomplete, the proof replay missed requests (not an error: run the same record command again to top up); 130 stopped by hand with Ctrl-C (stored answers kept; run the same command again).
- run: 0 finished; 1 the preflight failed (sentences printed, no run folder); 130 stopped by hand with Ctrl-C (the folder keeps the plays that finished; report and INDEX.md row say `stopped`; not a baseline). The run's own verdict is in the check.
- preflight: 0 setup is right; 1 problems printed.
- check: 0 usable as a baseline; 1 not usable. Met or missed targets do not change it.
- usage: 0. smoke: 0 (its verdict is printed).

## What spends indexer requests

Only `record` and a top-up of it. The proof, `run`, `check`, `usage`, `smoke` and the preflights spend none.

## Publish the page

The "KaijuFlow Speed Check" page is https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD. Publish only when the owner asks for it.

1. Findings: write `story.html` into the run folder ([docs/formats.md](docs/formats.md), "The page"). Without it the run's section says "Numbers only".
2. Build: `python3 -I tools/brain/build_page.py <run folder> <its recording folder> --out <folder>`. It writes `index.html` and `tables.json` into `<folder>` and publishes nothing. Name every run folder that should be on the page; the runs whose folders are gone (2026-11-10, 2026-11-09) come from `tools/brain/page-archive/` by themselves. The header's words (`HEADER_FOR`, `EYEBROW`, `LEDE` in `build_page.py`) were written for the 2026-11-13 run alone; with other runs the page gets a plain header until they are rewritten.
3. Read what is published, with the Artifact tool: the page (`action: read` with the URL above), then its data file (the same with `path: tables.json`). A publish that replaces a file nobody read in this session is refused. Check that every section of the published page is in the new `index.html`.
4. Publish over the same page: `index.html` as the page, `files: {"tables.json": "<folder>/tables.json"}`, and `url` set to the URL above. Without `url` a second page is made.
5. Open the page: every "All numbers" block must show its table, not "Loading the table..." or "missing".

## Measuring words

- **Side**: one setup that is played: KaijuFlow, Usenet Ultimate, AltMount's own addon, or KaijuFlow with one page per indexer.
- **Round**: one pass of every title on one side, cold or warm.
- **Recording**: the indexer answers stored once, then replayed by the stand-in in every run.
- **Stand-in**: the stand-in indexer on port 1340 that records or replays answers.
- **Cap rule**: the first "limit reached" stops the pass; the result is null.
- **Target**: one of the goals KaijuFlow is measured against, kept in `tools/brain/targets.json`. "Inside the noise" means KaijuFlow's own two rounds differ by more than the target is met or missed by.

## Reference

[docs/run-and-record.md](docs/run-and-record.md) (how run, record and smoke work), [docs/rules.md](docs/rules.md) (cap rule, preflight, settings, allowance, how targets are judged), [docs/formats.md](docs/formats.md) (run folder, targets file, recording, step lines, the page's `story.html` and archive), [docs/testbed.md](docs/testbed.md) (test copies). Index: [README.md](README.md).
