# Runbook: a timed run on the test copies

Every command runs from the repo root. Long ones: shell background mode with a hard `timeout`, the output kept in a log that ends with the exit code, and the log watched through one filter (stop at the first `Error`):

```
timeout 3h python3 -I tools/brain/brainrun.py run ... > run.log 2>&1; echo "EXIT $?" >> run.log
grep -E ' FAILS |does not play|Error|limit|^EXIT ' run.log      # failed plays, errors, limits, the exit; nothing else
tail -1 run.log                                                  # how far it is
```

Works for `record` too (a play that does not play reads `does not play`). Never improvise another filter and never `cat` a whole log.

**The guard hook.** `.claude/settings.json` runs `tools/brain/guard.py` before every Bash, Read and Grep call (tests: `test_guard.py`, in `npm run check:brain`). It refuses anything that would show the test folder's key files (`indexers.json`, `limits.json`, `provider.json`, `*-secrets.json`, `metadata-keys.json`, `admin-login.json`, `db.sqlite`) or a test copy's config folder: `cat`, `jq`, `grep`, `python3 -c`, Read, Grep on a path into the test folder (relative paths judged from the call's folder and the line's `cd`s), a search from a folder holding it (`grep -r x ~`, `find / ...`, a Grep on `~`), and `docker`/`podman` `exec` or `cp` naming `/config` or a key file in any container. It allows the brain tools (`tools/brain/*.py` and `*.sh`, so runs, preflights and applying expected settings keep working), `store/` and `backups/`, commands that only name a key file or `uu/config` in the repo, and every unrelated command. Known limits (a guardrail, not a sandbox): paths built at run time, `pushd` or subshell `cd`s, symlinks, and another program's working folder (`git -C`, `docker exec -w`). The settings with secrets as `***`: `python3 -I tools/brain/testbed.py read-settings [side]`. It also refuses `gh issue view <n> --comments`, `gh pr edit` and `gh issue create --parent`, which fail here, and names the call that works ([issue-tracker.md](../../docs/agents/issue-tracker.md)).

**Rules.** This is the one place the rules are stated; other files point here, and [docs/rules.md](docs/rules.md) holds the detail.

- Every timed run, and every other Brain check, needs the owner's go.
- A test touches only the test copies. This machine has no live stacks (Usenet Ultimate, NzbDAV, AltMount); if they are rebuilt, no test ever touches them.
- Only NinjaCentral is used, on every side: DrunkenSlug is switched off in the test copies but left in place; delete nothing. The default key file `~/kaijuflow-test/indexers.json` holds NinjaCentral only, so never pass `--key-file`.
- Cap rule: if an indexer says "limit reached", the pass stops and its result is null; the work waits for NinjaCentral's reset, and DrunkenSlug is never switched on to finish it. The allowance is in `~/kaijuflow-test/limits.json` (step 1).
- Each test Backend is capped at 25 connections, and the caps of all test copies add up to at most the provider limit (100); the preflight checks the sum.
- Every run is recorded (its own run folder and an INDEX.md row; the run command does this), and its report opens with what changed since the last run.
- Archived runs are never compared with (#144): every run from before the like-for-like rules (#142) sits in `~/kaijuflow-notes/brain-runs/archive/`, the 2026-11-13 baseline included. #127 is the first like-for-like baseline, so its report says "No earlier run to compare with: this is the first one." Recordings stay in the runs root: indexer answers do not depend on the setups' settings.
- Rebuild the image only when the code in it changed (step 0).

`<store>` is the folder of recordings, `<list>` the title list's name, `<name>` a label for the folder.

**How far is it, and where did the time go.** While a record or a run goes, `tail -1` of its log says how far it is: every line of a play or of a reset starts with the UTC time and the plays done out of those planned, for example `05:46:35 [61/160] kaijuflow cold 2 Inception: ...` (the proof at the end of a record counts again from 1 and says `proof`). Afterwards the last section of `report.md`, "Where the time went", says how long the run took and on what.

## The recipe

0. A commit that changes the code in the image since the image was built? Add `--rebuild-image` to the first preflight below. The code in the image is the build inputs, listed once, in `BUILD_INPUTS` in `tools/brain/brainrun.py` ([rules.md](docs/rules.md) says what they are). A commit that touches only docs, tools or tests needs no rebuild; the preflight says when one is needed.
1. Allowance: `python3 -I tools/brain/brainrun.py usage` shows Used, Limit and Left per indexer (limits in `~/kaijuflow-test/limits.json`). Do this before any record.
2. Preflight: `python3 -I tools/brain/brainrun.py preflight --for record --store <store> --list <list> [--rebuild-image]`. Fix every sentence it prints; exit 0 means go. It also holds the test copies to `tools/brain/expected-settings.json` and names every setting that differs: KaijuFlow's and Usenet Ultimate's sort and filter rules, and AltMount direct's one try and 4K-first scoring. To make a copy like for like ([rules.md](docs/rules.md#like-for-like-142)), do not edit it by hand: with the owner's go, stop the copy (`python3 -I tools/brain/testbed.py stop <copy>`), run `python3 -I tools/brain/testbed.py apply <copy>` (`kaijuflow`, `uu` or `altmount-addon`), then run the preflight again. The command backs the copy's config up into `~/kaijuflow-test/backups/`, writes the file's values (KaijuFlow and Usenet Ultimate: `movieFilters` and `tvFilters` in `config.json`; AltMount direct: the `stremio` settings in `altmount-addon/config/config.yaml`: `max_fallback_releases: 0`, `include_library_streams: false` and the `scoring` custom formats, 2160p 400, 1080p 300, 720p 200, "4K words beside 1080p or 720p" -400 since #154, "No disc images" as a drop), leaves every other setting as it was, and prints each setting it changed, never a secret; a copy that already matches gets "nothing changed" and no backup. Changing a test copy is the owner's go.
3. Record: `python3 -I tools/brain/brainrun.py record --name <name> --store <store> --list <list> [--one-page] [--titles-file titles.json]`. It resets the test copies, sends every side through a cold round and a warm round (the only step that asks the real indexer), then proves the recording by replaying it with no indexer contacted. A second `record` of the same list only asks for what is missing (top-up).
4. Preflight for the run: `... preflight --for run --store <store> --list <list>`.
5. Run: `python3 -I tools/brain/brainrun.py run --name <name> --store <store> --list <list> [--one-page] [--no-wait]`. Four rounds per side (cold, warm, cold, warm) from the recording; no indexer is contacted. It ends by printing the check.
6. Check: `python3 -I tools/brain/brainrun.py check --run <run folder>`. Says whether the run can serve as a baseline, then prints one line per target: the target, the measured values, met or not met.
7. Back up: `tools/brain/backup.sh`, after every record (also a stopped or incomplete one) and every run. It copies `~/kaijuflow-test/store` into `~/kaijuflow-notes/recordings/`, commits `~/kaijuflow-notes` and pushes it to the private repo `ReyesPascal/kaijuflow-notes` (#114). It refuses to push if any value from the key files in `~/kaijuflow-test` turns up in the store or the run folders. The secrets themselves are never in either repository; they are backed up in the owner's password manager. On a new machine: `git clone https://github.com/ReyesPascal/kaijuflow-notes ~/kaijuflow-notes` and copy `recordings/` back to `~/kaijuflow-test/store`.

Other commands: `smoke --store <EMPTY folder> --list smoke` (reachability only), `python3 -I tools/brain/testbed.py settings|status|stop`, `python3 -I tools/brain/testbed.py apply <copy>` (step 2; the owner's go).

What to work on next: `python3 -I tools/brain/frontier.py` prints the tickets that can start now, the open sub-issues of the map #183 with no open blocker and no assignee, in map order, each with all its labels. It reads the tracker only.

## Flags that matter

- `--for run|record` (preflight): which setup to check. `--rebuild-image`: build `kaijuflow:test` from the current commit when the code in the image has changed since it was built (otherwise the image is left alone).
- `--sides LIST`, `--rounds 1|2`, `--quick` (run only): a short run. `--sides` takes `kaijuflow`, `uu`, `altmount-addon` (AltMount direct) and `kaijuflow-1page`, comma-separated; `--rounds 1` plays cold 1 and warm 1 only; `--quick` is `--sides kaijuflow --rounds 1` (about 5 minutes; it does not turn on `--no-wait`). A short run is never a baseline: its report's first line, `meta.json`, its INDEX.md row and `check` (exit 1, "short run") say what it played, and its "What changed" compares it with the last baseline, as far as it played. So does a `--titles-file` that leaves out titles of the list. `record` has no such flags. Wrong values stop before anything runs.
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

1. Findings: write `findings.html` into the run folder: the findings and the next step ([docs/formats.md](docs/formats.md), "The page"). Without it the page has neither; every number and verdict comes from the run by itself.
2. Build: `python3 -I tools/brain/build_page.py <run folder> [<the run it is compared with>] [<recording folder>] --out <folder>`. It writes `index.html` (the page) and `report.html` (the one-page Letter report, #133) into `<folder>` and publishes nothing. The newest run given is the page's run and must be finished; the newest finished run before it is what it is compared with; every run given gets a row in "Every run so far". Both files come from the same numbers and verdicts.
3. Look before publishing: `cd ~/.local/share/kf-render && node <repo>/tools/brain/render.mjs <folder>/index.html <folder>/shots 1280 390` and `node <repo>/tools/brain/render.mjs <folder>/report.html <folder>/shots 816`, fix anything it flags (TOO WIDE, CUT OFF, SQUEEZED), and open the screenshots. The report is a fixed Letter sheet, so CUT OFF on it means the run's words do not fit on one page: shorten `findings.html` (one line under each finding heading) and build again. Printed or saved as PDF from a browser, `report.html` is one Letter page with no margin of the printer's own.
4. Read what is published, with the Artifact tool (`action: read` with the URL above). A publish that replaces a page nobody read in this session is refused. Version 7 and earlier also had a `tables.json` beside the page; the Starting line page needs none, and an unused one may stay.
5. Publish over the same page: `index.html` as the page and `url` set to the URL above. Without `url` a second page is made.
6. Open the page and look at it at phone width and in dark mode.

## Measuring words

Side, Pass, Round, Top pick, Target, Expected settings, Recording, Stand-in, Cap rule, Stopped run, Cold start and Warm start are defined once, in [GLOSSARY.md](../../GLOSSARY.md) ("Measuring").

## Reference

[docs/run-and-record.md](docs/run-and-record.md) (how run, record and smoke work), [docs/rules.md](docs/rules.md) (cap rule, preflight, settings, expected settings, allowance, how targets are judged), [docs/formats.md](docs/formats.md) (run folder, top picks, targets file, expected settings file, recording, step lines, the page's `findings.html`), [docs/testbed.md](docs/testbed.md) (test copies). Index: [README.md](README.md).
