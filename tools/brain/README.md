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

## The 1338 test container

`/home/ryan/kaijuflow-test` holds a compose file and its own copy of UU's config (`backend: altmount`, AltMount `http://192.168.4.40:8085`, category `kaijuflow`). To use it:

1. Rebuild the image from the commit under test: `docker build -t kaijuflow:test .`
2. Start it: `docker compose up -d --force-recreate` in that folder. Stop it with `docker compose stop` afterwards.
3. Sources that fail during a check are marked dead in `config/dead-nzbs.json`. If a KaijuFlow bug caused the failure, stop the container and remove those entries before checking again.

Results of the 2026-11-09 check, the scrambled RAR finding and the re-check after the Unscramble fix (#46, with speed per side): `/home/ryan/kaijuflow-notes/brain-1338/RESULTS.md` (outside the repo).
