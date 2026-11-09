# Brain tools

Scripts for live checks on Brain (the owner's server), written for the 1338 Brain check (2026-11-09). They read from the live services and change nothing on them. **The owner's OK is needed before any Brain check**, and the working containers (UU 1337, NzbDAV 3000, AltMount 8085) are never changed, restarted or replaced.

Run them with `python3 -I` from the repo root, wrapped in `timeout <seconds>`, in the shell tool's background mode. Each script prints one line per title as it goes and ends with `done in N s`; a log without that line is an unfinished run. Watch the log while it runs (a monitor that prints each title line and any line with `Error` or `Traceback`) and stop and report on the first error instead of waiting for the end.

`common.py` holds the ten titles, the timed HTTP read and the table helpers shared by `parity.py` and `search.py`; change the title list there only, so both tables stay comparable. `TITLES_FILE=<path.json>` (a JSON list of `[kind, id, label]`) swaps in another list for one run, e.g. fresh titles for a cold run. `<user-id>` is the id in UU's manifest URL, the key in the test container's `config/users.json`. AltMount's download key (the SHA-256 of its API key) is computed in `src/backends/altmount.ts` (`downloadKey`).

| Script | What it does | Cost |
|---|---|---|
| `parity.py <user-id> <out.json>` | Plays the first Source of 10 titles through UU 1337 (NzbDAV) and the test container on 1338. It reads 64 KiB at the start, 50% and 90%, notes the failure video, and compares bytes between the two sides. It records each side's speed (#46): time to the Stream being ready (response headers), time to the first byte, the start read, the 50% and 90% seek reads, and the test container's Unscramble time from `docker logs`; it prints a Markdown table with the median per side and writes it to `<out>.md`. `<user-id>` is the id in the manifest URL; `PARITY_TITLES="Interstellar,Game of Thrones"` reruns only those titles. | Starts real Streams on both Backends |
| `search.py <user-id> <download-key> <out.json>` | Search side-by-side: the same 10 titles through AltMount's own Stremio addon on 8085, the test container on 1338 and UU 1337. Per title and side it records the Sources shown, the time until the list arrived, whether the first Stream plays on the first try, the time to the first byte of the first Stream that plays, and how many of the first 3 Streams are broken (error or failure video); medians per side as a Markdown table in `<out>.md`. Sides run one after the other, order rotating per title. `<download-key>` is the lowercase hex SHA-256 of AltMount's API key (its addon URL is `/stremio/<download-key>/manifest.json`). `SEARCH_TITLES`, `SEARCH_TRIES` and `SEARCH_SIDES` narrow a run. | Starts real Streams on all three sides; the addon plays import NZBs into AltMount's library (categories Movies/TV) |
| `indexer_standin.py --mode record\|replay --config <indexers.json> --store <dir> --list <name>` | Indexer stand-in on port 1340 (#59). A side points its indexer URL at `http://<host>:1340/<indexer-slug>/api` with any dummy key. Record mode passes search and NZB requests to the real indexer (keys live only in the config outside the repo) and stores each answer per title list; NZB links in search answers (XML, and JSON with escaped `\/` or plain slashes) are rewritten to lead back to the stand-in, and no occurrence of the real key (plain, URL-encoded or JSON-escaped) is stored or sent to a side in any body; `/nzb/<token>` only resolves to the configured indexer's own host (anything else is a 403 `REFUSED`, nothing is sent). Replay serves the stored answers byte-identical and never contacts the indexer; a miss is a 404 and a `MISS` log line. A "limit reached" answer (XML `<error>` or newznab JSON `{"error":{"@attributes":{...}}}`, or HTTP 429) while recording writes `<store>/LIMIT_REACHED.json`, logs `LIMIT_REACHED`, is not stored, and the process exits with status 3. **Indexer time and dropped parameters (#73):** each stored answer keeps the milliseconds the real indexer took; replay waits that long before answering (search answers and NZB files) unless started with `--no-wait`, and every served stored answer logs `HIT <slug> <request> wait_ms=<n>` (0 when the wait is off or the recording has no time; older recordings still replay). An indexer entry in the key file may carry `"drop_params": ["o"]`: those request parameters are removed before the request is looked up or forwarded, as the live DrunkenSlug proxy (`ds-xml-proxy`, which strips `o=json` because AltMount 0.4.0 cannot read DrunkenSlug's JSON) does; the list is saved in the recording as `<store>/<list>/<slug>/indexer.json` (no key in it), so replay needs no key file. Test: `test_indexer_standin.py` (CI runs it). | Record mode spends real indexer requests and grabs; replay spends none |
| `statcheck.py <file.nzb>` | NNTP `STAT` for every article; reports missing ones per file (video parts vs par2). | No downloads; about 9 min for 50k articles on 8 connections |
| `rarorder.py <file.nzb>` | Real RAR volume number of each scrambled, number-named part (first article of each part). | One article per part |

`nntp.py` holds the shared provider login, read from AltMount's `config.yaml` (`/home/ryan/altmount-stack/config/`).

## Test copies of every side (spec #58)

`compose.test.yaml` starts a test copy of every side in its own compose project `kaijuflow-test` (own container names, own network `kaijuflow-test-net`, own config folders), so no compose command on it can reach a live container:

| Service | Container | Port | Role |
|---|---|---|---|
| `kaijuflow` | `kaijuflow-test` | 1338 | KaijuFlow, Backend = `altmount-kf` |
| `uu` | `uu-test` | 1339 | Usenet Ultimate v1.4.1, Backend = `nzbdav` (alias `nzbdav` on the test network) |
| `nzbdav` | `nzbdav-test` | 3001 | NzbDAV for the UU copy (`LOG_LEVEL: information`; live runs `warning`, which hides the import lines the report reads) |
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

Run it in the background with a hard `timeout`, like the other tools; it prints one line per visit. `--user-id` defaults to the first manifest id of the first user in the test container's `config/users.json`; the AltMount download key is computed from `templates/altmount.key`. The stand-in recording (`indexer_standin.py --mode record`) is a separate, earlier step and spends real indexer requests.

**Run records.** Every run gets its own folder `<runs-root>/<UTC date-time>-<name>/` (default runs root `/home/ryan/kaijuflow-notes/brain-runs`; use a temporary one for any trial) with `settings.json` (every side's settings, secrets replaced by `***`), `meta.json` (settings, KaijuFlow commit, titles, indexers, status, what changed), `raw.json` (every visit with its timings, step lines and imports), `logs/` (stand-in log and the test containers' logs, scrubbed of keys) and `report.md`. One row per run is appended to `<runs-root>/INDEX.md` (date, name, result, what changed, headline numbers, folder link). Nothing is overwritten: a rerun, even in the same second, gets a new folder, and INDEX.md is only ever appended to. The report opens with one sentence, then "What changed since the last run" (a diff of settings, KaijuFlow commit, titles, indexers and sides against the newest earlier finished run, always ending with the time of day of both runs, and with how many null runs lie between them and when; the same list goes into the INDEX.md row), then the shared-steps table, the extras table, failures split into indexer limit / Backend rejection / failure video / other, and per-title detail; every column is defined under its table.

**Cap rule.** The first "limit reached" from any indexer aborts the run at once: the stand-in's `LIMIT_REACHED.json` (found at the start or after any visit), or a limit line in a side's own logs. The log wordings matched are the ones the sides print (`brainreport.LIMIT_RE`): the indexer's "Request limit reached" text as AltMount and KaijuFlow pass it on, `HTTP 429`, Usenet Ultimate's "Status: 429", KaijuFlow's "Failed to download NZB from X: 429" and the stand-in's `LIMIT_REACHED indexer=`; loose phrases such as "api limit" are not matched. The run is recorded as NULL in INDEX.md with the indexer and time, its report holds no numbers, and a null run is never used as the "previous run" for a diff. The stand-in and the test copies are stopped. Delete the marker only after the indexer has reset and the recording is redone.

`brainrun.py smoke --store <EMPTY folder> --list smoke` is the reachability check: stand-in in replay mode on an empty store (every request is a MISS, so nothing can be read from Usenet), one search per side, and it prints how many stand-in requests each side caused. Start the test copies with `testbed.py up` first and stop them with `testbed.py stop` afterwards.

NzbDAV's import-line format (the `addfile` request and the "completed/finished/imported" line the report looks for) is confirmed only by the first real run (#63); until then the Import column of Usenet Ultimate may read "-".

Code: `brainreport.py` (log parsing, medians, failure split, diff, report, run folder and INDEX.md; pure logic), `brainrun.py` (orchestration), tests `test_brainreport.py` and `test_brainrun.py` (fakes and fixture logs, run in CI).

## Settings table and preflight (spec #72, ticket #74)

**Settings command.** `python3 -I tools/brain/testbed.py settings [--limit 100]` prints every test copy's settings as a table and the connection budget (per copy, total, provider limit), read straight from the copies' config files (KaijuFlow and Usenet Ultimate `config.json`, NzbDAV's database, each AltMount's `config.yaml`). Keys, logins and passwords are never printed. It replaces the hand-written table in SETTINGS.md. The run record's `settings.json` comes from the same reader (`testbed.read_settings`), so the table and the "what changed" list agree. The connection budget counts the NewsHosting login only: health-check cap (KaijuFlow, Usenet Ultimate), main providers (NzbDAV types 1 and 2; its backup login has its own limit and is shown beside it), enabled non-backup providers (AltMount).

**Preflight.** `python3 -I tools/brain/brainrun.py preflight [--for run|record] --store <store> --list <list> [--rebuild-image] [--provider-limit 100] [--key-file PATH]` prints one plain sentence per problem and exits 1, or exits 0 with `Setup is right ...`. `--store` and `--list` are only needed for `--for run`. `brainrun.py run` starts with the same check and stops before creating a run folder when it fails. Checks:

1. the `kaijuflow:test` image's `kaijuflow.commit` label equals the repository's commit and the tree is clean (`--rebuild-image` runs `docker build --label kaijuflow.commit=<commit> -t kaijuflow:test .` when the label differs; it never builds from a dirty tree);
2. record only: the key file (default `<test dir>/indexers.json`) exists, is readable only by the owner, and names exactly the indexers switched on in every test copy (only the names are read, so per-indexer settings added later are fine);
3. every indexer address in every test copy (also switched-off ones, plus Easynews or Prowlarr when on) is `http://host.docker.internal:1340/<slug>` with or without `/api`;
4. the caps add up to at most the provider limit (default 100);
5. the stand-in's port 1340 is free;
6. run only: the recording `<store>/<list>/<slug>/` holds at least one answer for each switched-on indexer.

Indexers are compared by the slug in the stand-in address, because each copy names them its own way (`NinjaCentral` vs `ninja`). The tools carry no indexer names. The run record's `commit` is the image label, not the repository's HEAD.

**For the record command (#75).** Call `brainrun.preflight('record', cfg, io)` (or `'run'`); it returns a list of sentences, `[]` meaning go, and `brainrun.preflight_command(mode, cfg, io)` prints them and returns the exit code. `cfg` needs `test_dir`, `store`, `listname`; optional `limit`, `standin_port`, `key_file`, `rebuild_image`. `io` is the runner's IO object (`RealIO`) and needs `git_info`, `image_label`, `rebuild_image`, `setup_report`, `key_state`, `port_free`, `recording`; `FakeIO` in the tests shows the shortcut (`io.preflight(mode)`). Tests: `test_settings.py`, `test_preflight.py`.

## Step lines (`[KF-STEP]`)

KaijuFlow writes one line per timed step to stdout (`src/utils/stepTiming.ts`): `[KF-STEP] ` followed by a one-line JSON object. `docker logs -t` prefixes are fine: parse from the first `[KF-STEP] ` (`json.loads(line.split("[KF-STEP] ", 1)[1])`). Lines carry names, titles and numbers only, never URLs or keys.

| Field | Meaning |
|---|---|
| `step` | `indexer_page`, `health_batch`, `nzb_fetch`, `unscramble`, `upload`, `import_wait`, `first_byte` |
| `source` | Source or indexer name (none for `health_batch`) |
| `ms` | whole milliseconds the step took |
| `ok` | false when the step threw (the line is still written) |
| `t` | end time, ISO UTC |
| `ref` | Stremio id (`tt0133093`, `tt1234567:1:2`), on the search-side steps `indexer_page` and `health_batch` only |
| `title` | release title of the Source, on the prepare-side steps (`nzb_fetch`, `unscramble`, `upload`, `import_wait`, `first_byte`) |
| `job` | Backend job id on `upload`, `import_wait`, `first_byte` |
| extras | `page` (`indexer_page`, 1 = first page); `count`, `checked`, `indexers` (`health_batch`); `result`, `parts` (`unscramble`); `includes_upload` (`import_wait` on AltMount: one request uploads and waits, so there is no `upload` line) |

`brainrun.py` ties lines to a title like this: search-side lines by `ref`, for that side's visit until the next visit that used the same KaijuFlow container starts (a late `health_batch` is kept); prepare-side lines to the Source that was played (its release title appears in the played Stream's text; otherwise the work that began after the visit began), so background work of the previous title cannot land in the next one. This runs once at the end of the run (`finalize_steps`).

## The 1338 test container

`/home/ryan/kaijuflow-test/config` is the container's own copy of UU's config (`backend: altmount`, AltMount `http://192.168.4.40:8087`, category `kaijuflow`). To use it:

(Its compose file is now part of `compose.test.yaml` above, pointing at the KaijuFlow-side test AltMount on 8087 instead of the live AltMount; the old live-AltMount settings are in `config.bak-60-*`.)

1. Rebuild the image from the commit under test: `docker build -t kaijuflow:test .`
2. Start it: `python3 -I tools/brain/testbed.py up kaijuflow`. Stop it with `... stop kaijuflow` afterwards.
3. Sources that fail during a check are marked dead in `config/dead-nzbs.json`. If a KaijuFlow bug caused the failure, stop the container and remove those entries before checking again.

Results of the 2026-11-09 check, the scrambled RAR finding and the re-check after the Unscramble fix (#46, with speed per side): `/home/ryan/kaijuflow-notes/brain-1338/RESULTS.md` (outside the repo).
