# Runbook: a timed run on the test copies

Every command runs from the repo root. Long ones: shell background mode with a hard `timeout`, and watch the log (stop at the first `Error`).

**Rules.** This is the one place the rules are stated; other files point here, and [docs/rules.md](docs/rules.md) holds the detail.

- Every timed run, and every other Brain check, needs the owner's go.
- A test touches only the test copies. This machine has no live stacks (Usenet Ultimate, NzbDAV, AltMount); if they are rebuilt, no test ever touches them.
- Only NinjaCentral is used, on every side: DrunkenSlug is switched off in the test copies but left in place; delete nothing. The default key file `~/kaijuflow-test/indexers.json` holds NinjaCentral only, so never pass `--key-file`.
- Cap rule: if an indexer says "limit reached", the pass stops and its result is null; the work waits for NinjaCentral's reset, and DrunkenSlug is never switched on to finish it. The allowance is in `~/kaijuflow-test/limits.json` (step 1).
- Each test Backend is capped at 25 connections, and the caps of all test copies add up to at most the provider limit (100); the preflight checks the sum.
- Every run is recorded (its own run folder and an INDEX.md row; the run command does this), and its report opens with what changed since the last run.
- Rebuild the image only when the code in it changed (step 0).

`<store>` is the folder of recordings, `<list>` the title list's name, `<name>` a label for the folder.

**How far is it, and where did the time go.** While a record or a run goes, `tail -1` of its log says how far it is: every line of a play or of a reset starts with the UTC time and the plays done out of those planned, for example `05:46:35 [61/160] kaijuflow cold 2 Inception: ...` (the proof at the end of a record counts again from 1 and says `proof`). Afterwards the last section of `report.md`, "Where the time went", says how long the run took and on what.

## The recipe

0. A commit that changes the code in the image since the image was built? Add `--rebuild-image` to the first preflight below. The code in the image is the build inputs, listed once, in `BUILD_INPUTS` in `tools/brain/brainrun.py` ([rules.md](docs/rules.md) says what they are). A commit that touches only docs, tools or tests needs no rebuild; the preflight says when one is needed.
1. Allowance: `python3 -I tools/brain/brainrun.py usage` shows Used, Limit and Left per indexer (limits in `~/kaijuflow-test/limits.json`). Do this before any record.
2. Preflight: `python3 -I tools/brain/brainrun.py preflight --for record --store <store> --list <list> [--rebuild-image]`. Fix every sentence it prints; exit 0 means go. It also holds the sort and filter settings of KaijuFlow's and Usenet Ultimate's test copies against `tools/brain/expected-settings.json` and names every setting that differs.
3. Record: `python3 -I tools/brain/brainrun.py record --name <name> --store <store> --list <list> [--one-page] [--titles-file titles.json]`. It resets the test copies, sends every side through a cold round and a warm round (the only step that asks the real indexer), then proves the recording by replaying it with no indexer contacted. A second `record` of the same list only asks for what is missing (top-up).
4. Preflight for the run: `... preflight --for run --store <store> --list <list>`.
5. Run: `python3 -I tools/brain/brainrun.py run --name <name> --store <store> --list <list> [--one-page] [--no-wait]`. Four rounds per side (cold, warm, cold, warm) from the recording; no indexer is contacted. It ends by printing the check.
6. Check: `python3 -I tools/brain/brainrun.py check --run <run folder>`. Says whether the run can serve as a baseline, then prints one line per target: the target, the measured values, met or not met.

Other commands: `smoke --store <EMPTY folder> --list smoke` (reachability only), `python3 -I tools/brain/testbed.py settings|status|stop`.

## Flags that matter

- `--for run|record` (preflight): which setup to check. `--rebuild-image`: build `kaijuflow:test` from the current commit when the code in the image has changed since it was built (otherwise the image is left alone).
- `--one-page`: add the fourth side (KaijuFlow, one page per indexer). `--titles-file`: another title list (JSON). `--no-wait` (run): replay answers at once, for tuning runs only.
- `--runs-root DIR`: where run folders go (default `~/kaijuflow-notes/brain-runs`; use a temporary one for trials). `--provider-limit N`: connection cap, default 100.
- `--settle S`: the pause after every play, in seconds (default 3). With 160 plays that is 8 minutes of a run; the report's "Where the time went" shows it as its own part.

## Exit codes

- record: 0 complete (a run may use it); 1 setup problem or the pass broke (nothing recorded); 2 stopped by an indexer limit (stored answers kept; run the same command after the reset); 3 incomplete, the proof replay missed requests (not an error: run the same record command again to top up); 130 stopped by Ctrl-C or by SIGTERM from `timeout` (stored answers kept; run the same command again).
- run: 0 finished; 1 the preflight failed (sentences printed, no run folder); 130 stopped by Ctrl-C or by SIGTERM from `timeout` (the folder keeps the plays that finished; report and INDEX.md row say `stopped`; not a baseline). The run's own verdict is in the check.
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

Side, Pass, Round, Top pick, Target, Expected settings, Recording, Stand-in, Cap rule, Stopped run, Cold start and Warm start are defined once, in [GLOSSARY.md](../../GLOSSARY.md) ("Measuring").

## Reference

[docs/run-and-record.md](docs/run-and-record.md) (how run, record and smoke work), [docs/rules.md](docs/rules.md) (cap rule, preflight, settings, expected settings, allowance, how targets are judged), [docs/formats.md](docs/formats.md) (run folder, top picks, targets file, expected settings file, recording, step lines, the page's `story.html` and archive), [docs/testbed.md](docs/testbed.md) (test copies). Index: [README.md](README.md).
