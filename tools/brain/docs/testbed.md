# Brain tools: test copies and the 1338 container

The test copies of the one setup and the 1338 test container. Back to the [runbook](../RUNBOOK.md) or the [index](../README.md).

## Test copies of the one setup (spec #58, #187)

`compose.test.yaml` starts the test copies of the one setup a check plays (#185), KaijuFlow and its AltMount, in their own compose project `kaijuflow-test` (own container names, own network `kaijuflow-test-net`, own config folders), so no compose command on it can reach a live container:

| Service | Container | Port | Role |
|---|---|---|---|
| `kaijuflow` | `kaijuflow-test` | 1338 | KaijuFlow, Backend = `altmount-kf` |
| `altmount-kf` | `altmount-kf-test` | 8087 | AltMount for KaijuFlow |

The test copies of the runs before #185 (`uu-test`, `nzbdav-test`, `altmount-addon-test`, with their config folders `uu/config/`, `nzbdav/config/`, `altmount-addon/config/`) stay stopped and on disk, kept, not deleted; since #187 neither `compose.test.yaml` nor `testbed.py` sets them up, resets or reads them. Their compose entries are in git history (`compose.test.yaml` before #187).

All config folders, with secrets, are in `~/kaijuflow-test/` (`TEST_DIR`, outside the repo): `config/` (KaijuFlow), `altmount-kf/config/`, `templates/` (the clean state a reset restores) and `.env` (`JWT_SECRET`, `TEST_DIR`, `HOST_IP`: this machine's LAN IP). KaijuFlow's indexer URLs point at the stand-in (`http://host.docker.internal:1340/<slug>/api`, ticket #59); the test copy of AltMount has its indexers switched off (#302). Settings per copy: `python3 -I tools/brain/testbed.py settings` (the hand-written `SETTINGS.md` was lost with the old machine). `python3 -I tools/brain/testbed.py apply <copy>` writes the expected settings into one copy, its config backed up into `backups/` first ([formats.md](formats.md#expected-settings-expected-settingsjson); the owner's go, [runbook](../RUNBOOK.md) step 2).

Recipe (from the repo root; `testbed.py` runs every Docker command through the test project and refuses any other service):

1. Rebuild KaijuFlow's image from the commit under test: `docker build -t kaijuflow:test .`
2. Start: `python3 -I tools/brain/testbed.py up` (both) or `... up kaijuflow` (named services). Wait until `status` shows them healthy.
3. Cold reset (a check does it by itself): `python3 -I tools/brain/testbed.py reset` (both) or `... reset altmount-kf`. It stops each copy, restores it from `templates/` (AltMount's database, metadata, `.nzbs` and segment cache, KaijuFlow's health/dead caches and stats), starts it again and runs the emptiness check. Settings, logins and users are kept. Exit code 0 and the line `EMPTY: ...` mean every checked Backend holds no imported item.
4. Emptiness check alone: `python3 -I tools/brain/testbed.py check [side ...]` (database tables, the Backend's own API/WebDAV listing, leftover files, cache files). Exit 1 and `NOT EMPTY: ...` lines otherwise.
5. Stop when done: `python3 -I tools/brain/testbed.py stop`. `status` lists the test containers.

Never start a stopped test copy of before #185 beside them (connection budget: [rules.md](rules.md#settings-table-and-preflight-spec-72-ticket-74), `testbed.py settings`). Tests of the scripts (no Docker): `npm run check:brain`, as CI runs them.

## Indexers (#302)

One command adds, switches and removes an indexer in the test setup, so no file is edited by hand. Agents may run it (a brain tool, allowed by the guard). Stop the test copies first (`testbed.py stop`), as for `apply`, and start them after (`testbed.py up`), so a running copy does not write over the change.

- `python3 -I tools/brain/testbed.py indexer add <slug> --stash <entry> --searches <n a day> --downloads <n a day> [--drop o] [--reset rolling-24h|HH:MM] [--timezone ZONE] [--name NAME]`: reads the indexer's key and address from the owner's stash entry (the `API key:` and `API URL:` lines; part of the name is enough, as with `stash get`), and writes its whole entry into the key file (`<test dir>/indexers.json`, readable only by the owner): address (without `/api`), key, `"enabled": true`, the stand-in's dropped parameters (`--drop`, once per parameter: DrunkenSlug's `o`, #73), and the daily limits the allowance reads (`search_per_day`, `download_per_day`, `reset`, `timezone`). KaijuFlow's config gets an entry pointing at the stand-in (`http://host.docker.internal:1340/<slug>/api`, a placeholder key; pages and timeout copied from its first indexer), or its entry is switched on. Run it again to change an indexer's key or limits.
- `indexer on|off <slug>`: switches it in both the key file and KaijuFlow's config. `indexer remove <slug>`: takes it out of both.
- `indexer list`: each indexer's switches and limits.

Every change backs each file it changes up into `<test dir>/backups/` first, writes nothing when the command cannot be done (one sentence says why), and prints only names, switches and limits, never a key or an address. Every change also switches the test copy of AltMount's indexers off (only its `stremio.indexers.newsnab[n].enabled` lines; once they are off, nothing more): KaijuFlow searches and AltMount only streams, and the preflight reads KaijuFlow's indexers only.

## The 1338 test container

`~/kaijuflow-test/config` is the container's own config, first copied from Usenet Ultimate's (`backend: altmount`, AltMount `http://<HOST_IP>:8087`, category `kaijuflow`). To use it:

(Its compose file is now part of `compose.test.yaml` above, pointing at the KaijuFlow-side test AltMount on 8087 instead of the live AltMount; the old live-AltMount settings are in `config.bak-60-*`.)

1. Rebuild the image from the commit under test: `docker build -t kaijuflow:test .`
2. Start it: `python3 -I tools/brain/testbed.py up kaijuflow`. Stop it with `... stop kaijuflow` afterwards.
3. Sources that fail during a check are marked dead in `config/dead-nzbs.json`. If a KaijuFlow bug caused the failure, stop the container and remove those entries before checking again.

Results of the 2026-11-09 check, the scrambled RAR finding and the re-check after the Unscramble fix (#46, with speed per side): `~/kaijuflow-notes/brain-1338/RESULTS.md` (outside the repo).
