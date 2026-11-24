# Runbook: a timed run on the test copies

Every command runs from the repo root. Long ones: shell background mode with a hard `timeout`, the output kept in a log that ends with the exit code, and the log watched through one filter (stop at the first `Error`):

```
timeout 3h python3 -I tools/brain/brainrun.py run ... > run.log 2>&1; echo "EXIT $?" >> run.log
grep -E ' FAILS |does not play|Error|limit|^EXIT ' run.log      # failed plays, errors, limits, the exit; nothing else
tail -1 run.log                                                  # how far it is
```

Works for `record` too (a play that does not play reads `does not play`). Never improvise another filter and never `cat` a whole log.

**The guard hook.** `.claude/settings.json` runs `tools/brain/guard.py` before every Bash, Read and Grep call (tests: `test_guard.py`, in `npm run check:brain`). It refuses anything that would show the test folder's key files (`indexers.json`, `limits.json`, `provider.json`, `*-secrets.json`, `metadata-keys.json`, `admin-login.json`, `db.sqlite`) or a test copy's config folder: `cat`, `jq`, `grep`, `python3 -c`, Read, Grep on a path into the test folder (relative paths judged from the call's folder and the line's `cd`s), a search from a folder holding it (`grep -r x ~`, `find / ...`, a Grep on `~`), and `docker`/`podman` `exec` or `cp` naming `/config` or a key file in any container. It allows the brain tools (`tools/brain/*.py` and `*.sh`, so runs, preflights and applying expected settings keep working), `store/` and `backups/`, commands that only name a key file or `uu/config` in the repo, and every unrelated command. Known limits (a guardrail, not a sandbox): paths built at run time, `pushd` or subshell `cd`s, symlinks, and another program's working folder (`git -C`, `docker exec -w`). The settings with secrets as `***`: `python3 -I tools/brain/testbed.py read-settings [side]`. It also refuses `gh issue view <n>` without `--json` or with `--comments`, `gh pr checks --json` (use `prwatch.py`), `gh pr edit` and `gh issue create --parent`, which fail here, and names the call that works ([issue-tracker.md](../../docs/agents/issue-tracker.md)).

**Rules.** This is the one place the rules are stated; other files point here, and [docs/rules.md](docs/rules.md) holds the detail.

- Every timed run, and every other Brain check, needs the owner's go. A standing go written on a spec counts for the runs it names, and only those: spec #183's "Building it", phase 2 (2026-11-20 grilling), covers the official baseline #218, the grouped run #219 and its halving runs, never a `record` or a top-up.
- Real-use checks (spec #268, ADR 0010): a quick check (`brainrun.py check --quick`) and a drill-down have a standing go (owner, 2026-11-24): run them without asking, the allowance check and the cap rule still applying. A full check needs the owner's go each time. A check asks the live indexer, so it spends real requests ([rules.md](docs/rules.md#real-use-checks-270-spec-268-adr-0010)).
- A test touches only the test copies. This machine has no live stacks (Usenet Ultimate, NzbDAV, AltMount); if they are rebuilt, no test ever touches them.
- A run measures one setup, KaijuFlow with its AltMount copy (`kaijuflow-test`, `altmount-kf-test`), with untouched indexer answers. The baseline (#189) played one try per title: Ultimate Fallback was off for AltMount until #190. Since #190 KaijuFlow's fallback is the Play-time check, and a round plays the Best entry on top of its list ([rules.md](docs/rules.md#what-a-run-is-185)). The Usenet Ultimate, NzbDAV and AltMount direct test copies are no part of a run: they stay stopped and are kept, never deleted, configs included. Since #187 `testbed.py` and `compose.test.yaml` no longer know them; stopping one that is still up is a live step and needs the owner's go: `docker stop uu-test nzbdav-test altmount-addon-test`.
- NinjaCentral and DrunkenSlug are both switched on, on every side (owner, 2026-11-24: "turn drunkenslug on"); altHUB stays off but in place; delete nothing. The default key file `~/kaijuflow-test/indexers.json` holds both, so never pass `--key-file`. Limits: NinjaCentral 2000 searches and 450 downloads a day, DrunkenSlug 1000 and 100. Add, switch or remove an indexer with `python3 -I tools/brain/testbed.py indexer add|on|off|remove` (#302; agents may run it, with the test copies stopped): it takes the key from the owner's stash and keeps KaijuFlow's config and the key file in step ([testbed.md](docs/testbed.md#indexers-302)). The test copy of AltMount has no indexers switched on.
- Every run waits the Browse pause between a title's list and its play ([rules.md](docs/rules.md#browse-pause-205)).
- Every record and every run is made plugged in (#262): the preflight refuses a machine on battery, and a run keeps its power state and CPU probe in `meta.json` `machine`, so two runs' machines can be compared.
- Cap rule: if an indexer says "limit reached", the pass stops and its result is null; the work waits for that indexer's reset. The allowance is in the key file's entries (step 1).
- KaijuFlow's AltMount copy is capped at 25 connections, and its caps and KaijuFlow's add up to at most the provider limit (100); the preflight checks the sum.
- Every run is recorded (its own run folder and an INDEX.md row; the run command does this), and its report opens with what changed since the last run.
- Archived runs are never compared with (#144): every run from before the like-for-like rules (#142) sits in `~/kaijuflow-notes/brain-runs/archive/`, the 2026-11-13 baseline included. #127 is the first like-for-like baseline, so its report says "No earlier run to compare with: this is the first one." Recordings stay in the runs root: indexer answers do not depend on the setups' settings.
- Rebuild the image only when the code in it changed (step 0).

`<store>` is the folder of recordings, `<list>` the title list's name, `<name>` a label for the folder.

**How far is it, and where did the time go.** While a record or a run goes, `tail -1` of its log says how far it is: every line of a play or of a reset starts with the UTC time and the plays done out of those planned, for example `05:46:35 [61/160] kaijuflow cold 2 Inception: ...` (the proof at the end of a record counts again from 1 and says `proof`). Afterwards the last section of `report.md`, "Where the time went", says how long the run took and on what.

## A quick check

```
timeout 1h python3 -I tools/brain/brainrun.py check --quick --rebuild-image > check.log 2>&1; echo "EXIT $?" >> check.log
grep -E 'no video|Error|limit|^Pass|^Fail|^No verdict|^EXIT ' check.log
```

About 10 minutes: the preflight for a check (key file, idle, plugged in, allowance), 5 new titles drawn, one reset, then one press of Best per title on the live indexer. `EXIT 0` pass, `4` fail, `2` the cap rule stopped it (no verdict), `130` stopped, `1` a setup problem. Read the folder's `report.md`, file its ticket texts (one per fail and check miss), then back up with `tools/brain/backup.sh`. Diagnosis files the fix ticket of a proved KaijuFlow cause by itself (`fix-tickets/` in the folder; the report's Diagnosis section names it, #288); `--tickets-dry-run` writes the text only. Then `python3 -I tools/brain/diagnosis.py record <folder>` in a worktree puts the check's occurrences, comebacks and filed tickets on the Casebook, for review.

## A drill-down

```
timeout 30m python3 -I tools/brain/brainrun.py drill --title tt5180504 --episode S01E01 > drill.log 2>&1; echo "EXIT $?" >> drill.log
grep -E 'no video|Error|limit|^Pass|^Fail|^No verdict|^EXIT ' drill.log
```

The command a fix ticket names (#272), once its fix is merged (rebuild the image with `--rebuild-image` when the fix is in it). It plays that one title as a quick check plays a title (the preflight for one title, one reset, one press of Best on the live indexer, the same verdict, report and exit codes), never draws one and never adds it to the ledger. Its play always keeps an evidence folder; Diagnosis runs on it, the suspected cause's recipe of Clues runs on its failures, and the report's Drill-down section says what each entry is marked: **proved fixed** (it played with no failure), **reopened** (a failure, the cause again or a new one), or not marked (no fix to prove, or no confirming test that runs). `--entry <id>` names an entry besides the ones proved on the title before. Then `python3 -I tools/brain/diagnosis.py record <folder>` in a worktree writes the marks on the entries (status and History), for review; a KaijuFlow cause it proved again then gets its new fix ticket from `diagnosis.py fix <folder>`. `--full` (watched with a skip) comes with the full check's watch (#271).

## The recipe

0. A commit that changes the code in the image since the image was built? Add `--rebuild-image` to the first preflight below. The code in the image is the build inputs, listed once, in `BUILD_INPUTS` in `tools/brain/brainrun.py` ([rules.md](docs/rules.md) says what they are). A commit that touches only docs, tools or tests needs no rebuild; the preflight says when one is needed.
1. Allowance: `python3 -I tools/brain/brainrun.py usage` shows Used, Limit and Left per indexer (limits in the key file's entries, written by `testbed.py indexer add`). Do this before any record.
2. Preflight: `python3 -I tools/brain/brainrun.py preflight --for record --store <store> --list <list> [--rebuild-image]`. Fix every sentence it prints; exit 0 means go. It also holds the test copies to `tools/brain/expected-settings.json` and names every setting that differs: KaijuFlow's sort and filter rules and its fallback on (`ultimateFallback.enabled` and the Play-time check's settings, #190). To put KaijuFlow's copy right, do not edit it by hand: with the owner's go, stop the copy (`python3 -I tools/brain/testbed.py stop kaijuflow`), run `python3 -I tools/brain/testbed.py apply kaijuflow`, then run the preflight again. The command backs the copy's config up into `~/kaijuflow-test/backups/`, writes the file's values (KaijuFlow: `movieFilters`, `tvFilters` and the `ultimateFallback` settings in `config.json`), leaves every other setting as it was, and prints each setting it changed, never a secret; a copy that already matches gets "nothing changed" and no backup. Changing a test copy is the owner's go.
3. Record: `python3 -I tools/brain/brainrun.py record --name <name> --store <store> --list <list> [--one-page] [--titles-file titles.json]`. It resets KaijuFlow's two test copies, sends KaijuFlow through a cold round and a warm round (the only step that asks the real indexer; later pages are recorded like any request), then proves the recording by replaying it with no indexer contacted. A second `record` of the same list only asks for what is missing (top-up).
4. Preflight for the run: `... preflight --for run --store <store> --list <list>`. Besides the setup it refuses a busy machine (stop agents, suites and builds, and wait), a machine on battery (plug it in), a stale pinned address (`HOST_IP` or KaijuFlow's `altmountUrl`) and sinkholed or failing DNS for Newshosting, each in one sentence; the record's preflight (step 2) refuses the last three as well. Once the load is judged it takes the CPU probe (about 1 s, the same work every run) and prints it; the run keeps it with the power state in `meta.json` `machine`, and the report holds it against the previous run's. The limits and how each is read are in [rules.md](docs/rules.md#settings-table-and-preflight-spec-72-ticket-74), checks 7 to 9 and 11, the one list of these checks.
5. Run: `python3 -I tools/brain/brainrun.py run --name <name> --store <store> --list <list> [--one-page] [--no-wait]`. Four rounds of KaijuFlow (cold, warm, cold, warm) from the recording; no indexer is contacted. It ends by printing the check.
6. Check: `python3 -I tools/brain/brainrun.py check --run <run folder>`. Says whether the run can serve as a baseline, lists the fallbacks (counted as played, each with its extra seconds), then per list: fails (titles and plays), fallbacks, and the median cold and warm title to video. Last, the run judged against the previous run on the same recording: per list, fails, cold and warm title to video, fallbacks and fallback time, each better, same or worse, and kept or not kept (on fails and cold title to video alone; a stopped or short run is not judged) ([rules.md](docs/rules.md#judged-against-the-previous-run-186)).
7. Back up: `tools/brain/backup.sh`, after every record (also a stopped or incomplete one) and every run. It copies `~/kaijuflow-test/store` into `~/kaijuflow-notes/recordings/`, commits `~/kaijuflow-notes` and pushes it to the private repo `ReyesPascal/kaijuflow-notes` (#114). It refuses to push if any value from the key files in `~/kaijuflow-test` turns up in the store or the run folders. The secrets themselves are never in either repository; they are backed up in the owner's password manager. On a new machine: `git clone https://github.com/ReyesPascal/kaijuflow-notes ~/kaijuflow-notes` and copy `recordings/` back to `~/kaijuflow-test/store`.

Other commands: `smoke --store <EMPTY folder> --list smoke` (reachability only), `python3 -I tools/brain/testbed.py settings|status|stop`, `python3 -I tools/brain/testbed.py apply <copy>` (step 2; the owner's go).

What to work on next: `python3 -I tools/brain/frontier.py` prints the tickets that can start now, the open sub-issues of the map #183 with no open blocker and no assignee, in map order, each with all its labels. It reads the tracker only.

## Flags that matter

- `--for run|record` (preflight): which setup to check. `--rebuild-image`: build `kaijuflow:test` from the current commit when the code in the image has changed since it was built (otherwise the image is left alone).
- `--sides LIST`, `--rounds 1|2`, `--quick` (run only): a short run. `--sides` takes `kaijuflow` and `kaijuflow-1page`, comma-separated; `--rounds 1` plays cold 1 and warm 1 only; `--quick` is `--sides kaijuflow --rounds 1` (about 5 minutes; it does not turn on `--no-wait`). A short run is never a baseline: its report's first line, `meta.json`, its INDEX.md row and `check` (exit 1, "short run") say what it played, and its "What changed" compares it with its previous run, as far as it played. So does a `--titles-file` that leaves out titles of the list. `record` has no such flags. Wrong values stop before anything runs.
- `--one-page`: add the fourth side (KaijuFlow, one page per indexer). `--titles-file`: another title list (JSON). `--no-wait` (run): replay answers at once, for tuning runs only.
- `--runs-root DIR`: where run folders go (default `~/kaijuflow-notes/brain-runs`; use a temporary one for trials). `--provider-limit N`: connection cap, default 100.
- `--settle S`: the pause after every play, in seconds (default 3). With 160 plays that is 8 minutes of a run; the report's "Where the time went" shows it as its own part.

## Exit codes

- record: 0 complete (a run may use it); 1 setup problem or the pass broke (nothing recorded); 2 stopped by an indexer limit (stored answers kept; run the same command after the reset); 3 incomplete, the proof replay missed requests (not an error: run the same record command again to top up); 130 stopped by Ctrl-C or by SIGTERM from `timeout` (stored answers kept; run the same command again).
- run: 0 finished; 1 the preflight failed (sentences printed, no run folder); 130 stopped by Ctrl-C or by SIGTERM from `timeout` (the folder keeps the plays that finished; report and INDEX.md row say `stopped`; not a baseline). The run's own verdict is in the check.
- preflight: 0 setup is right; 1 problems printed.
- check: 0 usable as a baseline; 1 not usable. Kept or not kept against the previous run does not change it.
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

[docs/run-and-record.md](docs/run-and-record.md) (how run, record and smoke work), [docs/rules.md](docs/rules.md) (cap rule, preflight, settings, expected settings, allowance, how a run is judged against the previous run), [docs/formats.md](docs/formats.md) (run folder, top picks, the page's targets file, expected settings file, recording, step lines, the page's `findings.html`), [docs/testbed.md](docs/testbed.md) (test copies). Index: [README.md](README.md).
