# Brain tools

Scripts for live checks on Brain (the owner's server), written for the 1338 Brain check (2026-11-09). They read from the live services and change nothing on them. **The owner's OK is needed before any Brain check**, and the working containers (UU 1337, NzbDAV 3000, AltMount 8085) are never changed, restarted or replaced.

Run them with `python3 -I` from the repo root, wrapped in `timeout <seconds>`, in the shell tool's background mode. Each script prints one line per title as it goes and ends with `done in N s`; a log without that line is an unfinished run. Watch the log while it runs (a monitor that prints each title line and any line with `Error` or `Traceback`) and stop and report on the first error instead of waiting for the end.

`common.py` holds the ten titles, the timed HTTP read and the table helpers shared by `parity.py` and `search.py`; change the title list there only, so both tables stay comparable. `TITLES_FILE=<path.json>` (a JSON list of `[kind, id, label]`) swaps in another list for one run, e.g. fresh titles for a cold run. `<user-id>` is the id in UU's manifest URL, the key in the test container's `config/users.json`. AltMount's download key (the SHA-256 of its API key) is computed in `src/backends/altmount.ts` (`downloadKey`).

| Script | What it does | Cost |
|---|---|---|
| `parity.py <user-id> <out.json>` | Plays the first Source of 10 titles through UU 1337 (NzbDAV) and the test container on 1338. It reads 64 KiB at the start, 50% and 90%, notes the failure video, and compares bytes between the two sides. It records each side's speed (#46): time to the Stream being ready (response headers), time to the first byte, the start read, the 50% and 90% seek reads, and the test container's Unscramble time from `docker logs`; it prints a Markdown table with the median per side and writes it to `<out>.md`. `<user-id>` is the id in the manifest URL; `PARITY_TITLES="Interstellar,Game of Thrones"` reruns only those titles. | Starts real Streams on both Backends |
| `search.py <user-id> <download-key> <out.json>` | Search side-by-side: the same 10 titles through AltMount's own Stremio addon on 8085, the test container on 1338 and UU 1337. Per title and side it records the Sources shown, the time until the list arrived, whether the first Stream plays on the first try, the time to the first byte of the first Stream that plays, and how many of the first 3 Streams are broken (error or failure video); medians per side as a Markdown table in `<out>.md`. Sides run one after the other, order rotating per title. `<download-key>` is the lowercase hex SHA-256 of AltMount's API key (its addon URL is `/stremio/<download-key>/manifest.json`). `SEARCH_TITLES`, `SEARCH_TRIES` and `SEARCH_SIDES` narrow a run. | Starts real Streams on all three sides; the addon plays import NZBs into AltMount's library (categories Movies/TV) |
| `indexer_standin.py --mode record\|replay --config <indexers.json> --store <dir> --list <name>` | Indexer stand-in on port 1340 (#59). A side points its indexer URL at `http://<host>:1340/<indexer-slug>/api` with any dummy key. Record mode passes search and NZB requests to the real indexer (keys live only in the config outside the repo) and stores each answer per title list; NZB links in search answers are rewritten to lead back to the stand-in. Replay serves the stored answers byte-identical and never contacts the indexer; a miss is a 404 and a `MISS` log line. A "limit reached" answer while recording writes `<store>/LIMIT_REACHED.json`, logs `LIMIT_REACHED`, is not stored, and the process exits with status 3. Test: `test_indexer_standin.py` (CI runs it). | Record mode spends real indexer requests and grabs; replay spends none |
| `statcheck.py <file.nzb>` | NNTP `STAT` for every article; reports missing ones per file (video parts vs par2). | No downloads; about 9 min for 50k articles on 8 connections |
| `rarorder.py <file.nzb>` | Real RAR volume number of each scrambled, number-named part (first article of each part). | One article per part |

`nntp.py` holds the shared provider login, read from AltMount's `config.yaml` (`/home/ryan/altmount-stack/config/`).

## Test copies of every side (spec #58)

`compose.test.yaml` starts a test copy of every side in its own compose project `kaijuflow-test` (own container names, own network `kaijuflow-test-net`, own config folders), so no compose command on it can reach a live container:

| Service | Container | Port | Role |
|---|---|---|---|
| `kaijuflow` | `kaijuflow-test` | 1338 | KaijuFlow, Backend = `altmount-kf` |
| `uu` | `uu-test` | 1339 | Usenet Ultimate v1.4.1, Backend = `nzbdav` (alias `nzbdav` on the test network) |
| `nzbdav` | `nzbdav-test` | 3001 | NzbDAV for the UU copy |
| `altmount-addon` | `altmount-addon-test` | 8086 | AltMount for the addon side |
| `altmount-kf` | `altmount-kf-test` | 8087 | AltMount for KaijuFlow |

All config folders, with secrets, are in `/home/ryan/kaijuflow-test/` (`TEST_DIR`, outside the repo): `config/` (KaijuFlow), `uu/config/`, `nzbdav/config/`, `altmount-addon/config/`, `altmount-kf/config/`, `templates/` (the clean state a reset restores) and `.env` (`JWT_SECRET`, `TEST_DIR`). Every side's indexer URLs point at the stand-in (`http://host.docker.internal:1340/<slug>/api`, ticket #59). Settings per side: `/home/ryan/kaijuflow-notes/spec58/SETTINGS.md`.

Recipe (from the repo root; `testbed.py` runs every Docker command through the test project and refuses any other service):

1. Rebuild KaijuFlow's image from the commit under test: `docker build -t kaijuflow:test .`
2. Start: `python3 -I tools/brain/testbed.py up` (all five) or `... up uu nzbdav` (named services). Wait until `status` shows them healthy.
3. Cold reset before a cold run: `python3 -I tools/brain/testbed.py reset` (all sides) or `... reset altmount-kf kaijuflow`. It stops each side, restores it from `templates/` (NzbDAV database and blobs, AltMount database, metadata, `.nzbs` and segment cache, UU and KaijuFlow health/dead caches and stats), starts it again and runs the emptiness check. Settings, logins and users are kept. Exit code 0 and the line `EMPTY: ...` mean every checked Backend holds no imported item.
4. Emptiness check alone: `python3 -I tools/brain/testbed.py check [side ...]` (database tables, the Backend's own API/WebDAV listing, leftover files, cache files). Exit 1 and `NOT EMPTY: ...` lines otherwise.
5. Stop when done: `python3 -I tools/brain/testbed.py stop`. `status` lists the test containers.

Never run two test Backends at the same time (connection budget, see SETTINGS.md). Tests of the scripts (no Docker, run in CI): `python3 -I -m unittest discover -s tools/brain -p 'test_*.py'`.

## The one command: a full run with a report (spec #58, ticket #62)

`brainrun.py run` plays the top pick of every title on every side (KaijuFlow 1338, Usenet Ultimate 1339, AltMount's own addon 8086; with `--one-page` also "KaijuFlow, one page per indexer", which is the KaijuFlow config with pagination off), one side at a time, in four rounds: cold, warm, cold, warm. Each cold round first resets every test copy with `testbed.py` (and checks it is empty); warm rounds follow right after on the same state. It starts the indexer stand-in in **replay** mode itself (so every side sees the same recorded answers and no real indexer is contacted), reads KaijuFlow's `[KF-STEP]` lines and each Backend's import start/end from the test containers' own logs (`docker logs`, never `exec`), and stops the stand-in and all test copies at the end, also after an error.

    python3 -I tools/brain/brainrun.py run --name baseline --store <standin-store> --list <title-list> [--one-page] [--titles-file titles.json] [--runs-root DIR]

Run it in the background with a hard `timeout`, like the other tools; it prints one line per visit. `--user-id` defaults to the first user in the test container's `config/users.json`; the AltMount download key is computed from `templates/altmount.key`. The stand-in recording (`indexer_standin.py --mode record`) is a separate, earlier step and spends real indexer requests.

**Run records.** Every run gets its own folder `<runs-root>/<UTC date-time>-<name>/` (default runs root `/home/ryan/kaijuflow-notes/brain-runs`; use a temporary one for any trial) with `settings.json` (every side's settings, secrets replaced by `***`), `meta.json` (settings, KaijuFlow commit, titles, indexers, status, what changed), `raw.json` (every visit with its timings, step lines and imports), `logs/` (stand-in log and the test containers' logs, scrubbed of keys) and `report.md`. One row per run is appended to `<runs-root>/INDEX.md` (date, name, result, what changed, headline numbers, folder link). Nothing is overwritten: a rerun, even in the same second, gets a new folder, and INDEX.md is only ever appended to. The report opens with one sentence, then "What changed since the last run" (a diff of settings, KaijuFlow commit, titles, indexers, sides and time of day against the newest earlier finished run; the same list goes into the INDEX.md row), then the shared-steps table, the extras table, failures split into indexer limit / Backend rejection / failure video / other, and per-title detail; every column is defined under its table.

**Cap rule.** The first "limit reached" from any indexer aborts the run at once: the stand-in's `LIMIT_REACHED.json` (found at the start or after any visit), or a limit line in a side's own logs. The run is recorded as NULL in INDEX.md with the indexer and time, its report holds no numbers, and a null run is never used as the "previous run" for a diff. The stand-in and the test copies are stopped. Delete the marker only after the indexer has reset and the recording is redone.

`brainrun.py smoke --store <EMPTY folder> --list smoke` is the reachability check: stand-in in replay mode on an empty store (every request is a MISS, so nothing can be read from Usenet), one search per side, and it prints how many stand-in requests each side caused. Start the test copies with `testbed.py up` first and stop them with `testbed.py stop` afterwards.

Code: `brainreport.py` (log parsing, medians, failure split, diff, report, run folder and INDEX.md; pure logic), `brainrun.py` (orchestration), tests `test_brainreport.py` and `test_brainrun.py` (fakes and fixture logs, run in CI).

## The 1338 test container

`/home/ryan/kaijuflow-test/config` is the container's own copy of UU's config (`backend: altmount`, AltMount `http://192.168.4.40:8087`, category `kaijuflow`). To use it:

(Its compose file is now part of `compose.test.yaml` above, pointing at the KaijuFlow-side test AltMount on 8087 instead of the live AltMount; the old live-AltMount settings are in `config.bak-60-*`.)

1. Rebuild the image from the commit under test: `docker build -t kaijuflow:test .`
2. Start it: `python3 -I tools/brain/testbed.py up kaijuflow`. Stop it with `... stop kaijuflow` afterwards.
3. Sources that fail during a check are marked dead in `config/dead-nzbs.json`. If a KaijuFlow bug caused the failure, stop the container and remove those entries before checking again.

Results of the 2026-11-09 check, the scrambled RAR finding and the re-check after the Unscramble fix (#46, with speed per side): `/home/ryan/kaijuflow-notes/brain-1338/RESULTS.md` (outside the repo).
