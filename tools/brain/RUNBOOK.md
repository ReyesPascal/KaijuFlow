# Runbook: real-use checks on the test copies

KaijuFlow is tested by real-use checks ([ADR 0010](../../docs/adr/0010-testing-plays-as-a-real-viewer-watches.md)): new titles every time, the live indexers, one cold press of Best per title. The replayed Recording and its timed runs are retired and archived ([archive/README.md](archive/README.md)); their commands stop unless run with `--revive`, on the owner's word.

Every command runs from the repo root. Long ones: shell background mode with a hard `timeout`, the output kept in a log that ends with the exit code, and the log watched through one filter (stop at the first `Error`):

```
timeout 1h python3 -I tools/brain/brainrun.py check --quick --rebuild-image > check.log 2>&1; echo "EXIT $?" >> check.log
grep -E 'no video|Error|limit|^Pass|^Fail|^No verdict|^EXIT ' check.log    # failed plays, errors, limits, the verdict, the exit
tail -1 check.log                                                         # how far it is
```

Never improvise another filter and never `cat` a whole log.

**The guard hook.** `.claude/settings.json` runs `tools/brain/guard.py` before every Bash, Read and Grep call (tests: `test_guard.py`, in `npm run check:brain`). It refuses anything that would show the test folder's key files (`indexers.json`, `limits.json`, `provider.json`, `*-secrets.json`, `metadata-keys.json`, `admin-login.json`, `db.sqlite`) or a test copy's config folder: `cat`, `jq`, `grep`, `python3 -c`, Read, Grep on a path into the test folder (relative paths judged from the call's folder and the line's `cd`s), a search from a folder holding it (`grep -r x ~`, `find / ...`, a Grep on `~`), and `docker`/`podman` `exec` or `cp` naming `/config` or a key file in any container. It allows the brain tools (`tools/brain/*.py` and `*.sh`, so checks, preflights and applying expected settings keep working), `store/` and `backups/`, commands that only name a key file or `uu/config` in the repo, and every unrelated command. Known limits (a guardrail, not a sandbox): paths built at run time, `pushd` or subshell `cd`s, symlinks, and another program's working folder (`git -C`, `docker exec -w`). The settings with secrets as `***`: `python3 -I tools/brain/testbed.py read-settings [side]`. It also refuses `gh issue view <n>` without `--json` or with `--comments`, `gh pr checks --json` (use `prwatch.py`), `gh pr edit` and `gh issue create --parent`, which fail here, and names the call that works ([issue-tracker.md](../../docs/agents/issue-tracker.md)).

**Rules.** This is the one place the rules are stated; other files point here, and [docs/rules.md](docs/rules.md) holds the detail.

- Every Brain check needs the owner's go. A standing go written on a spec counts for the checks it names, and only those.
- Real-use checks (spec #268, ADR 0010): a quick check (`brainrun.py check --quick`) and a drill-down have a standing go (owner, 2026-11-24): run them without asking, the allowance check and the cap rule still applying. A full check needs the owner's go each time. A check asks the live indexer, so it spends real requests ([rules.md](docs/rules.md#real-use-checks-270-spec-268-adr-0010)).
- A retired command (the record, run and smoke commands, `pool.py`'s draw, the page of timed runs) runs only when the owner asks for it, with `--revive` ([archive/README.md](archive/README.md)).
- A test touches only the test copies. This machine has no live stacks (Usenet Ultimate, NzbDAV, AltMount); if they are rebuilt, no test ever touches them.
- A check plays one setup, KaijuFlow with its AltMount copy (`kaijuflow-test`, `altmount-kf-test`), with untouched indexer answers, and presses the Best entry on top of each list ([rules.md](docs/rules.md#real-use-checks-270-spec-268-adr-0010)). The Usenet Ultimate, NzbDAV and AltMount direct test copies are no part of it: they stay stopped and are kept, never deleted, configs included. Since #187 `testbed.py` and `compose.test.yaml` no longer know them; stopping one that is still up is a live step and needs the owner's go: `docker stop uu-test nzbdav-test altmount-addon-test`.
- NinjaCentral and DrunkenSlug are both switched on, on every side (owner, 2026-11-24: "turn drunkenslug on"); altHUB stays off but in place; delete nothing. The default key file `~/kaijuflow-test/indexers.json` holds both, so never pass `--key-file`. Limits: NinjaCentral 2000 searches and 450 downloads a day, DrunkenSlug 1000 and 100. Add, switch or remove an indexer with `python3 -I tools/brain/testbed.py indexer add|on|off|remove` (#302; agents may run it, with the test copies stopped): it takes the key from the owner's stash and keeps KaijuFlow's config and the key file in step ([testbed.md](docs/testbed.md#indexers-302)). The test copy of AltMount has no indexers switched on.
- Every check waits the Browse pause between a title's list and its press of Best ([rules.md](docs/rules.md#browse-pause-205)).
- Every check is made plugged in (#262): the preflight refuses a machine on battery, and a check keeps its power state and CPU probe in `meta.json` `machine`.
- Cap rule: if an indexer says "limit reached", the check stops with no verdict; the work waits for that indexer's reset. The allowance is in the key file's entries (`brainrun.py usage`).
- KaijuFlow's AltMount copy is capped at 25 connections, and its caps and KaijuFlow's add up to at most the provider limit (100); the preflight checks the sum.
- Every check is recorded: its own check folder and an INDEX.md row (the check command does this). Checks are never compared with each other: each plays new titles (ADR 0010).
- Old run folders stay in `~/kaijuflow-notes/brain-runs/archive/` (#144), and the old recordings stay on disk: archived, never deleted.
- Rebuild the image only when the code in it changed (`--rebuild-image`; the preflight says when one is needed).

**How far is it.** While a check goes, `tail -1` of its log says how far it is: every line of a play or of the reset starts with the UTC time and the titles done out of those drawn, for example `05:46:35 [3/5] Inception: video list 2.1 s start 4.0 s`.

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

## Before a check

0. A commit that changes the code in the image since the image was built? Add `--rebuild-image`. The code in the image is the build inputs, listed once, in `BUILD_INPUTS` in `tools/brain/brainrun.py` ([rules.md](docs/rules.md#settings-table-and-preflight-spec-72-ticket-74) says what they are). A commit that touches only docs, tools or tests needs no rebuild; the preflight says when one is needed.
1. Allowance: `python3 -I tools/brain/brainrun.py usage` shows Used, Limit and Left per indexer (limits in the key file's entries, written by `testbed.py indexer add`).
2. Preflight: `python3 -I tools/brain/brainrun.py preflight [--rebuild-image]` (a check runs it first by itself). Fix every sentence it prints; exit 0 means go. It refuses a busy machine (stop agents, suites and builds, and wait), a machine on battery (plug it in), a stale pinned address (`HOST_IP` or KaijuFlow's `altmountUrl`), sinkholed or failing DNS for Newshosting, and too little allowance, each in one sentence ([rules.md](docs/rules.md#settings-table-and-preflight-spec-72-ticket-74), the one list of these checks). It also holds the test copies to `tools/brain/expected-settings.json` and names every setting that differs: KaijuFlow's sort and filter rules and its fallback on (`ultimateFallback.enabled` and the Play-time check's settings, #190). To put KaijuFlow's copy right, do not edit it by hand: with the owner's go, stop the copy (`python3 -I tools/brain/testbed.py stop kaijuflow`), run `python3 -I tools/brain/testbed.py apply kaijuflow`, then run the preflight again. The command backs the copy's config up into `~/kaijuflow-test/backups/`, writes the file's values (KaijuFlow: `movieFilters`, `tvFilters` and the `ultimateFallback` settings in `config.json`), leaves every other setting as it was, and prints each setting it changed, never a secret; a copy that already matches gets "nothing changed" and no backup. Changing a test copy is the owner's go.
3. Back up after every check: `tools/brain/backup.sh` copies `~/kaijuflow-test/store` (the archived recordings) into `~/kaijuflow-notes/recordings/`, commits `~/kaijuflow-notes` (the check folders and the ledger too) and pushes it to the private repo `ReyesPascal/kaijuflow-notes` (#114). It refuses to push if any value from the key files in `~/kaijuflow-test` turns up in what it pushes. The secrets themselves are never in either repository; they are backed up in the owner's password manager. On a new machine: `git clone https://github.com/ReyesPascal/kaijuflow-notes ~/kaijuflow-notes` and copy `recordings/` back to `~/kaijuflow-test/store`.

Other commands: `python3 -I tools/brain/testbed.py settings|status|stop`, `python3 -I tools/brain/testbed.py apply <copy>` (step 2; the owner's go).

What to work on next: `python3 -I tools/brain/frontier.py` prints the tickets that can start now, the open sub-issues of the map #183 with no open blocker and no assignee, in map order, each with all its labels. It reads the tracker only.

## Flags that matter

- `--rebuild-image` (check, drill, preflight): build `kaijuflow:test` from the current commit when the code in the image has changed since it was built (otherwise the image is left alone).
- `--tickets-dry-run` (check, drill): write the fix tickets of proved KaijuFlow causes into the check folder, file none.
- `--runs-root DIR`: where check folders go (default `~/kaijuflow-notes/brain-runs`; use a temporary one for trials). `--ledger FILE`: the titles already played (default `<runs root>/titles-played.json`). `--provider-limit N`: connection cap, default 100.
- `--settle S`: the pause after every play, in seconds (default 3).

## Exit codes

- check and drill: 0 pass; 4 a play failed; 2 the cap rule stopped it (no verdict); 130 stopped by Ctrl-C or by SIGTERM from `timeout` (the folder keeps the titles that finished); 1 a setup problem (sentences printed, no check folder) or a failure.
- preflight: 0 setup is right; 1 problems printed.
- usage: 0.
- A retired command run without `--revive`: 5, with one line saying it is retired by ADR 0010.

## What spends indexer requests

A quick check (up to 60 searches and 150 downloads) and a drill-down (12 and 30), through the stand-in on the live indexers; the preflight refuses a check the allowance cannot hold. `usage` and the preflight spend none.

## Publish the page

The "KaijuFlow Speed Check" page is https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD. It shows real-use checks: the newest check's verdict, its fails and its totals, then every check given. Publish only when the owner asks for it.

1. Build: `python3 -I tools/brain/checkpage.py <check folder> [<check folder> ...] --out <folder>`. It writes `index.html` into `<folder>` and publishes nothing ([formats](docs/formats.md#the-speed-check-page-checkpagepy)).
2. Look before publishing: `cd ~/.local/share/kf-render && node <repo>/tools/brain/render.mjs <folder>/index.html <folder>/shots 1280 390`, fix anything it flags (TOO WIDE, CUT OFF, SQUEEZED), and open the screenshots.
3. Read what is published, with the Artifact tool (`action: read` with the URL above). A publish that replaces a page nobody read in this session is refused.
4. Publish over the same page: `index.html` as the page and `url` set to the URL above. Without `url` a second page is made.
5. Open the page and look at it at phone width and in dark mode.

## Measuring words

Real-use check, Quick check, Full check, Drill-down, Fail, Slow play, Check miss, Nothing to play, Browse pause, Stand-in, Cap rule, Expected settings, Cold start are defined once, in [GLOSSARY.md](../../GLOSSARY.md) ("Measuring"); the retired words are marked there as retired by ADR 0010.

## Reference

[docs/rules.md](docs/rules.md) (how a check is judged, cap rule, preflight, settings, expected settings, allowance), [docs/formats.md](docs/formats.md) (check folder, evidence folder, Diagnosis, the title draw and ledger, the page, expected settings file, step lines), [docs/testbed.md](docs/testbed.md) (test copies). The retired recording path: [archive/README.md](archive/README.md). Index: [README.md](README.md).
