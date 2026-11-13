# Brain tools: test copies and the 1338 container

The test copies of every side and the 1338 test container. Back to the [runbook](../RUNBOOK.md) or the [index](../README.md).

## Test copies of every side (spec #58)

`compose.test.yaml` starts a test copy of every side in its own compose project `kaijuflow-test` (own container names, own network `kaijuflow-test-net`, own config folders), so no compose command on it can reach a live container:

| Service | Container | Port | Role |
|---|---|---|---|
| `kaijuflow` | `kaijuflow-test` | 1338 | KaijuFlow, Backend = `altmount-kf` |
| `uu` | `uu-test` | 1339 | Usenet Ultimate v1.4.1, Backend = `nzbdav` (alias `nzbdav` on the test network) |
| `nzbdav` | `nzbdav-test` | 3001 | NzbDAV for the UU copy (`LOG_LEVEL: information`) |
| `altmount-addon` | `altmount-addon-test` | 8086 | AltMount for the addon side |
| `altmount-kf` | `altmount-kf-test` | 8087 | AltMount for KaijuFlow |

All config folders, with secrets, are in `~/kaijuflow-test/` (`TEST_DIR`, outside the repo): `config/` (KaijuFlow), `uu/config/`, `nzbdav/config/`, `altmount-addon/config/`, `altmount-kf/config/`, `templates/` (the clean state a reset restores) and `.env` (`JWT_SECRET`, `TEST_DIR`, `HOST_IP`: this machine's LAN IP). Every side's indexer URLs point at the stand-in (`http://host.docker.internal:1340/<slug>/api`, ticket #59). Settings per side: `~/kaijuflow-notes/spec58/SETTINGS.md`.

Recipe (from the repo root; `testbed.py` runs every Docker command through the test project and refuses any other service):

1. Rebuild KaijuFlow's image from the commit under test: `docker build -t kaijuflow:test .`
2. Start: `python3 -I tools/brain/testbed.py up` (all five) or `... up uu nzbdav` (named services). Wait until `status` shows them healthy.
3. Cold reset before a cold run: `python3 -I tools/brain/testbed.py reset` (all sides) or `... reset altmount-kf kaijuflow`. It stops each side, restores it from `templates/` (NzbDAV database and blobs, AltMount database, metadata, `.nzbs` and segment cache, UU and KaijuFlow health/dead caches and stats), starts it again and runs the emptiness check. Settings, logins and users are kept. Exit code 0 and the line `EMPTY: ...` mean every checked Backend holds no imported item.
4. Emptiness check alone: `python3 -I tools/brain/testbed.py check [side ...]` (database tables, the Backend's own API/WebDAV listing, leftover files, cache files). Exit 1 and `NOT EMPTY: ...` lines otherwise.
5. Stop when done: `python3 -I tools/brain/testbed.py stop`. `status` lists the test containers.

Never run two test Backends at the same time (connection budget, see SETTINGS.md). Tests of the scripts (no Docker, run in CI): `python3 -I -m unittest discover -s tools/brain -p 'test_*.py'`.

## The 1338 test container

`~/kaijuflow-test/config` is the container's own copy of UU's config (`backend: altmount`, AltMount `http://<HOST_IP>:8087`, category `kaijuflow`). To use it:

(Its compose file is now part of `compose.test.yaml` above, pointing at the KaijuFlow-side test AltMount on 8087 instead of the live AltMount; the old live-AltMount settings are in `config.bak-60-*`.)

1. Rebuild the image from the commit under test: `docker build -t kaijuflow:test .`
2. Start it: `python3 -I tools/brain/testbed.py up kaijuflow`. Stop it with `... stop kaijuflow` afterwards.
3. Sources that fail during a check are marked dead in `config/dead-nzbs.json`. If a KaijuFlow bug caused the failure, stop the container and remove those entries before checking again.

Results of the 2026-11-09 check, the scrambled RAR finding and the re-check after the Unscramble fix (#46, with speed per side): `~/kaijuflow-notes/brain-1338/RESULTS.md` (outside the repo).
