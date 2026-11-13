# Brain tools: run, record, smoke

How `brainrun.py run`, `record` and `smoke` work in detail. Back to the [runbook](../RUNBOOK.md) or the [index](../README.md).

## The one command: a full run with a report (spec #58, ticket #62)

`brainrun.py run` plays the top pick of every title on every side (KaijuFlow 1338, Usenet Ultimate 1339, AltMount's own addon 8086; with `--one-page` also "KaijuFlow, one page per indexer", which is the KaijuFlow config with pagination off), one side at a time, in four rounds: cold, warm, cold, warm. Each cold round first resets every test copy with `testbed.py` (and checks it is empty); warm rounds follow right after on the same state. It starts the indexer stand-in in **replay** mode itself (so every side sees the same recorded answers and no real indexer is contacted), reads KaijuFlow's `[KF-STEP]` lines and each Backend's import start/end from the test containers' own logs (`docker logs`, never `exec`), and stops the stand-in and all test copies at the end, also after an error. The one-page side comes after the three main sides; one shared step (`switch_to_one_page`, used by run, record and smoke alike) patches KaijuFlow's config while its copy is stopped, then resets KaijuFlow and its AltMount so they come up again cold; the config is restored at the end.

    python3 -I tools/brain/brainrun.py run --name baseline --store <standin-store> --list <title-list> [--one-page] [--titles-file titles.json] [--runs-root DIR]

Run it in the background with a hard `timeout`, like the other tools; it prints one line per visit. `--no-wait` starts the stand-in with its replay wait off (see below). `--user-id` defaults to the first manifest id of the first user in the test container's `config/users.json`; the AltMount download key is computed from `templates/altmount.key`. The recording is made earlier by `brainrun.py record` (next section) and spends real indexer requests.



`brainrun.py smoke --store <EMPTY folder> --list smoke` is the reachability check: stand-in in replay mode on an empty store (every request is a MISS, so nothing can be read from Usenet), one search per side, and it prints for each side how many stand-in requests it caused, which address they came from, the address `docker inspect` gives for the side's test container, and whether the two match (then one plain sentence says whether every side arrived with its own address). That is the check that the runner can tell the sides apart by address. It tries the same sides as the planned run: add `--one-page` when the run will use the fourth side; it is switched on with the same step as in a run (its address may equal KaijuFlow's, since it is the same container) and switched off at the end, which leaves KaijuFlow's copy stopped. Start the test copies with `testbed.py up` first and stop them with `testbed.py stop` afterwards.

Code: `brainreport.py` (log parsing, medians, failure split, diff, report, run folder and INDEX.md; pure logic), `brainrun.py` (orchestration), tests `test_brainreport.py` and `test_brainrun.py` (fakes and fixture logs, run in CI).

## Record, top-up and misses (spec #72, ticket #75)

**The recipe, in order** (from the repo root; run the long ones in the background with a hard `timeout`):

1. Preflight: `python3 -I tools/brain/brainrun.py preflight --for record --store <store> --list <list>` (add `--rebuild-image` when it says the code that goes into the image has changed). Fix every sentence it prints.
2. Record: `python3 -I tools/brain/brainrun.py record --name <name> --store <store> --list <list> [--key-file PATH] [--one-page] [--titles-file titles.json]`. It runs the preflight itself, resets the test copies, starts the stand-in in **record** mode on the replay address, sends every side (KaijuFlow, Usenet Ultimate, AltMount's own addon, and with `--one-page` the fourth side) through every title in two rounds (#79): a cold round, then a warm round on the same state with no reset between (list, then play the top pick; sides one after another, order rotating per title). The warm round stores what only a warm visit asks for, such as KaijuFlow's health-check replacements for Sources that went dead in the cold round and the addon's second searches, so a run's warm list times are real numbers. The one-page side gets its own cold and warm round after the switch. Stops the stand-in and resets the test copies again. It ends with one sentence that also names any side that listed no Sources for some titles (a side whose copy did not answer shows up there). This spends real indexer requests and grabs.
3. Preflight for the run: `... preflight --for run --store <store> --list <list>`, then run: `python3 -I tools/brain/brainrun.py run --name <name> --store <store> --list <list> [--no-wait]` (it starts with the same preflight and refuses to start without a recording).

**Top-up.** Record mode serves a stored answer instead of asking the indexer again, so running `record` a second time (again both rounds) only asks for what is not stored yet (a second record of a complete list makes zero indexer requests). The report's "Not recorded" section prints the exact command.

**The proof and the record command's exit codes.** The record command ends with a proof: test copies reset, the stand-in in replay mode with the replay wait off (no indexer is contacted), every side through one cold and one warm round. Exit codes: 0 complete, 1 setup problem or failure, 2 stopped (limit reached), 3 incomplete (run the same command again). `brainrun.py --help` lists them.
