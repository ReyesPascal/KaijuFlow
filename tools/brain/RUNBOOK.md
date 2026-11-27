# Runbook: real-use checks on the test copies

KaijuFlow is tested by real-use checks ([ADR 0010](../../docs/adr/0010-testing-plays-as-a-real-viewer-watches.md)): new titles every time, the live indexers, one cold press of Best per title. This page gives the steps. Every rule they follow is in [docs/rules.md](docs/rules.md), linked here by its name; this page restates none.

**The rules a check runs under:** [When to check, and who says go](docs/rules.md#when-to-check-and-who-says-go), [Indexers change only through the indexer command](docs/rules.md#indexers-change-only-through-the-indexer-command), [Every indexer request goes through the stand-in, untouched](docs/rules.md#every-indexer-request-goes-through-the-stand-in-untouched), [The allowance](docs/rules.md#the-allowance), [Connection caps](docs/rules.md#connection-caps), [How a title is played](docs/rules.md#how-a-title-is-played), [The verdict and the report](docs/rules.md#the-verdict-and-the-report), [After a check](docs/rules.md#after-a-check), [The guard](docs/rules.md#the-guard), [Retired commands stay retired](docs/rules.md#retired-commands-stay-retired) (the archived recording path: [archive/README.md](archive/README.md)).

Every command runs from the repo root. Long ones use this one filter:

```
timeout 1h python3 -I tools/brain/brainrun.py check --quick --rebuild-image > check.log 2>&1; echo "EXIT $?" >> check.log
grep -E 'no video|Error|limit|^Pass|^Fail|^No verdict|^EXIT ' check.log    # failed plays, errors, limits, the verdict, the exit
tail -1 check.log                                                         # how far it is
```

**How far is it.** While a check goes, `tail -1` of its log says how far it is: every line of a play or of the reset starts with the UTC time and the titles done out of those drawn, for example `05:46:35 [3/5] Inception: video list 2.1 s start 4.0 s`.

**Reading the test setup.** The settings with secrets as `***`: `python3 -I tools/brain/testbed.py read-settings [side]`; the indexers, their switches and limits: `python3 -I tools/brain/testbed.py indexer list`.

## A quick check

```
timeout 1h python3 -I tools/brain/brainrun.py check --quick --rebuild-image > check.log 2>&1; echo "EXIT $?" >> check.log
grep -E 'no video|Error|limit|^Pass|^Fail|^No verdict|^EXIT ' check.log
```

About 10 minutes: the preflight for a check, then the new titles played on the live indexers ([New titles every time](docs/rules.md#new-titles-every-time), [One reset per check](docs/rules.md#one-reset-per-check), [How a title is played](docs/rules.md#how-a-title-is-played)). Add `--fix` to run the preflight's safe fixes first. Then, in order:

1. Read the folder's `report.md` and file its ticket texts (one per fail and check miss). Diagnosis files the fix ticket of a proved KaijuFlow cause by itself (`fix-tickets/` in the folder; the report's Diagnosis section names it, #288); `--tickets-dry-run` writes the text only.
2. In a worktree, `python3 -I tools/brain/diagnosis.py record <folder>` puts the check's occurrences, comebacks and filed tickets on the Casebook; commit them for review.
3. Back up with `tools/brain/backup.sh` ([below](#before-a-check), step 3).
4. Name the check in the handoff note.

## A drill-down

```
timeout 30m python3 -I tools/brain/brainrun.py drill --title tt5180504 --episode S01E01 > drill.log 2>&1; echo "EXIT $?" >> drill.log
grep -E 'no video|Error|limit|^Pass|^Fail|^No verdict|^EXIT ' drill.log
```

The command a fix ticket names (#272), once its fix is merged; [A fix is proved by a drill-down](docs/rules.md#a-fix-is-proved-by-a-drill-down). Add `--rebuild-image` when the fix is in the image. It plays that one title as a quick check plays a title ([How a title is played](docs/rules.md#how-a-title-is-played)) and the report's Drill-down section says what each suspected cause is marked. `--entry <id>` names an entry besides the ones proved on the title before. Then `python3 -I tools/brain/diagnosis.py record <folder>` in a worktree writes the marks on the entries, for review; a KaijuFlow cause it proved again gets its new fix ticket from `diagnosis.py fix <folder>`. `--full` (watched with a skip) comes with the full check's watch (#271).

## Before a check

0. A commit that changes the code in the image since it was built? Add `--rebuild-image` ([The test image holds the commit's code](docs/rules.md#the-test-image-holds-the-commits-code); the build inputs are `BUILD_INPUTS` in `tools/brain/brainrun.py`). The preflight says when one is needed.
1. Allowance: `python3 -I tools/brain/brainrun.py usage` shows Used, Limit and Left per indexer ([testbed.md](docs/testbed.md#indexers-302)).
2. Preflight: `python3 -I tools/brain/brainrun.py preflight [--for check [--full [--standing-go]]] [--rebuild-image] [--fix]` (a check runs it first by itself). Exit 0 means go; otherwise do what each sentence says ([Every refusal names its fix](docs/rules.md#every-refusal-names-its-fix)), or add `--fix` for the safe ones. To put a test copy's settings right without `--fix` ([A test copy changes only through the tools](docs/rules.md#a-test-copy-changes-only-through-the-tools)): `python3 -I tools/brain/testbed.py stop kaijuflow`, `python3 -I tools/brain/testbed.py apply kaijuflow`, then the preflight again. `apply` backs the config up into `~/kaijuflow-test/backups/`, writes the expected settings, leaves every other setting as it was and prints each one it changed; a copy that matches gets "nothing changed".
3. Back up after every check: `tools/brain/backup.sh` commits `~/kaijuflow-notes` (the check folders and the ledger) and pushes it to the private repo `ReyesPascal/kaijuflow-notes` (#114); it refuses to push when a key value turns up in the check folders ([Secrets stay out of both repos](docs/rules.md#secrets-stay-out-of-both-repos)). On a new machine: `git clone https://github.com/ReyesPascal/kaijuflow-notes ~/kaijuflow-notes`.

Other commands: `python3 -I tools/brain/testbed.py settings|status|stop|up`, `python3 -I tools/brain/testbed.py apply <copy>` (step 2), `python3 -I tools/brain/testbed.py indexer add|on|off|remove|list` ([testbed.md](docs/testbed.md#indexers-302)).

What to work on next: `python3 -I tools/brain/frontier.py` prints the tickets that can start now, the open sub-issues of the map #183 with no open blocker and no assignee, in map order, each with all its labels. It reads the tracker only.

## Flags that matter

- `--rebuild-image` (check, drill, preflight): build `kaijuflow:test` from the current commit when the code in the image has changed since it was built (otherwise the image is left alone).
- `--fix` (check, drill, preflight): run the preflight's safe fixes first, then the preflight again (#303).
- `--full`, `--standing-go` (preflight): the full check's preflight, and the lead's standing go for it (#303).
- `--tickets-dry-run` (check, drill): write the fix tickets of proved KaijuFlow causes into the check folder, file none.
- `--runs-root DIR`: where check folders go (default `~/kaijuflow-notes/brain-runs`; use a temporary one for trials). `--ledger FILE`: the titles already played (default `<runs root>/titles-played.json`). `--provider-limit N`: connection cap, default 100.

## Exit codes

- check and drill: 0 pass; 4 a play failed; 2 the cap rule stopped it (no verdict); 130 stopped by Ctrl-C or by SIGTERM from `timeout` (the folder keeps the titles that finished); 1 a setup problem (sentences printed, no check folder) or a failure.
- preflight: 0 setup is right; 1 problems printed.
- usage: 0.
- A retired command run without `--revive`: 5, with one line saying it is retired by ADR 0010.

## What spends indexer requests

A quick check, a drill-down and the preflight, through the stand-in on the live indexers; how many each may spend is [The allowance](docs/rules.md#the-allowance). `usage` spends none.

## Publish the page

The "KaijuFlow Speed Check" page is https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD. It shows real-use checks: the newest check's verdict, its fails and its totals, then every check given.

1. Build: `python3 -I tools/brain/checkpage.py <check folder> [<check folder> ...] --out <folder>`. It writes `index.html` into `<folder>` and publishes nothing ([formats](docs/formats.md#the-speed-check-page-checkpagepy)).
2. Look before publishing: `cd ~/.local/share/kf-render && node <repo>/tools/brain/render.mjs <folder>/index.html <folder>/shots 1280 390`, fix anything it flags (TOO WIDE, CUT OFF, SQUEEZED), and open the screenshots.
3. Read what is published, with the Artifact tool (`action: read` with the URL above). A publish that replaces a page nobody read in this session is refused.
4. Publish over the same page: `index.html` as the page and `url` set to the URL above. Without `url` a second page is made.
5. Open the page and look at it at phone width and in dark mode.

## Measuring words

Real-use check, Quick check, Full check, Drill-down, Fail, Slow play, Check miss, Nothing to play, Browse pause, Stand-in, Cap rule, Expected settings, Cold start are defined once, in [GLOSSARY.md](../../GLOSSARY.md) ("Measuring"); the retired words are marked there as retired by ADR 0010.

## Reference

[docs/rules.md](docs/rules.md) (every rule), [docs/formats.md](docs/formats.md) (check folder, evidence folder, Diagnosis, the title draw and ledger, the page, expected settings file, step lines), [docs/testbed.md](docs/testbed.md) (test copies, the indexer command, the key file's limits and `usage`). The retired recording path: [archive/README.md](archive/README.md). Index: [README.md](README.md).
