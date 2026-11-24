# The archive: the replayed Recording and its process (retired by ADR 0010)

[ADR 0010](../../../docs/adr/0010-testing-plays-as-a-real-viewer-watches.md) (owner, 2026-11-24) replaced the replayed Recording with real-use checks: new titles every time, the live indexers, one cold press of Best per title ([RUNBOOK.md](../RUNBOOK.md)). Everything below is retired and **soft-deleted**: kept here, not removed (#273; owner: "ARCHIVE THE OLD STUFF AND STOP IT FROM COMING BACK UNLESS WE TELL IT TO").

## What is here

| File | What it was |
|---|---|
| `retired_run.py` | The retired commands of `brainrun.py`: `run` (four cold and warm rounds on a replayed Recording, short runs, the one-page side), `record` (the cold and warm record pass, its top-ups, its proof replay and the recording state), `smoke` (the stand-in reachability check), the run and record preflights with their recording checks (the recording complete, no request missed by the last run on it) and the record preflight's allowance table, `check --run`. |
| `runcheck.py` | `check --run`: whether a run can serve as a baseline, and the judgement against the previous run (kept or not kept). |
| `build_page.py`, `startline.py`, `pagetargets.py`, `targets.json` | The Speed Check page of timed runs (the Starting line design), its one-page report and its targets. The live page shows real-use checks (`../checkpage.py`). |
| `pool_draw.py`, `pool.json` | The speed tests' pool and its commands, `pool.py draw` and `pool.py check-ids`. `../draw.py seed` still reads `pool.json` here to put the old speed tests' titles in the ledger. |
| `fixed-list.json`, `list-265.json` | The title lists of the Recordings `kf-189` and `kf-265`. |
| `RUNBOOK-timed-runs.md`, `run-and-record.md`, `rules-retired.md`, `formats-retired.md` | The runbook, rules and formats of the timed runs as they stood when they were retired. |
| `test_*.py` | Their tests, moved with them (the archived parts of `test_preflight.py`, `test_allowance.py` and `test_brainreport.py` subclass the live test classes and hold only the archived tests). |

Kept elsewhere, as they were:

- **The Recordings** `kf-189` and `kf-265` (and `baseline`): the stand-in store `~/kaijuflow-test/store/`, backed up in `~/kaijuflow-notes/recordings/` by `../backup.sh`. Never deleted.
- **Old run folders**: `~/kaijuflow-notes/brain-runs/archive/` (#144), and the timed runs of 2026-11-13 to 2026-11-24 in the runs root.
- **Shared parts still in use**: the stand-in (`../indexer_standin.py`; a check runs it in record mode, its replay mode was the Recording's), the run report and step-line readers (`../brainreport.py`), `../runs.py`, and the preflight's record and run modes (`brainrun.preflight`), which only this archive uses.

## Bringing a command back

Each retired command stops with one line, `... is retired by ADR 0010 ...`, exit code 5, and touches nothing (`../retired.py`). Only on the owner's word, add `--revive`:

```
python3 -I tools/brain/brainrun.py run --name x --store ~/kaijuflow-test/store --list kf-265 --titles-file tools/brain/archive/list-265.json --revive
python3 -I tools/brain/brainrun.py record ... --revive          # also: smoke, preflight --for run|record, check --run
python3 -I tools/brain/pool.py draw --test "Test 3" --out titles.json --revive
python3 -I tools/brain/archive/build_page.py <run folder> --out <folder> --revive
```

`npm run check:brain` leaves this folder out (no compile, lint or tests), and `../test_live_docs.py` fails when a live doc describes a retired command again. So before trusting a revived command, run its tests from here (they were green when archived, #273):

```
cd tools/brain/archive && PYTHONPATH=..:. python3 -m unittest discover -s . -t . -p 'test_*.py'
```
