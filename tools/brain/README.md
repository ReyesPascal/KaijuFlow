# Brain tools

Scripts for live checks on Brain (the owner's server), written for the 1338 Brain check (2026-11-09). They read from the live services and change nothing on them. **The owner's OK is needed before any Brain check**, and the working containers (UU 1337, NzbDAV 3000, AltMount 8085) are never changed, restarted or replaced.

Run them with `python3 -I` from the repo root. Long runs go in the shell tool's background mode, which reports when they finish.

| Script | What it does | Cost |
|---|---|---|
| `parity.py <user-id> <out.json>` | Plays the first Source of 10 titles through UU 1337 (NzbDAV) and the test container on 1338. It reads 64 KiB at the start, 50% and 90%, notes the failure video, and compares bytes between the two sides. It records each side's speed (#46): time to the Stream being ready (response headers), time to the first byte, the start read, the 50% and 90% seek reads, and the test container's Unscramble time from `docker logs`; it prints a Markdown table with the median per side and writes it to `<out>.md`. `<user-id>` is the id in the manifest URL; `PARITY_TITLES="Interstellar,Game of Thrones"` reruns only those titles. | Starts real Streams on both Backends |
| `statcheck.py <file.nzb>` | NNTP `STAT` for every article; reports missing ones per file (video parts vs par2). | No downloads; about 9 min for 50k articles on 8 connections |
| `rarorder.py <file.nzb>` | Real RAR volume number of each scrambled, number-named part (first article of each part). | One article per part |

`nntp.py` holds the shared provider login, read from AltMount's `config.yaml` (`/home/ryan/altmount-stack/config/`).

## The 1338 test container

`/home/ryan/kaijuflow-test` holds a compose file and its own copy of UU's config (`backend: altmount`, AltMount `http://192.168.4.40:8085`, category `kaijuflow`). To use it:

1. Rebuild the image from the commit under test: `docker build -t kaijuflow:test .`
2. Start it: `docker compose up -d --force-recreate` in that folder. Stop it with `docker compose stop` afterwards.
3. Sources that fail during a check are marked dead in `config/dead-nzbs.json`. If a KaijuFlow bug caused the failure, stop the container and remove those entries before checking again.

Results of the 2026-11-09 check, the scrambled RAR finding and the re-check after the Unscramble fix (#46, with speed per side): `/home/ryan/kaijuflow-notes/brain-1338/RESULTS.md` (outside the repo).
