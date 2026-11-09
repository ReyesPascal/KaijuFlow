# Next session: KaijuFlow (as of 2026-11-09, after #46 and #51)

Older handoffs are in git history. Replace this section; don't append below it.

**Where it stands**
- KaijuFlow is the owner's maintained fork of Usenet Ultimate v1.4.1. Upstream and NzbDAV are no longer maintained, so the priority is supporting maintained Backends.
- Terms are in [GLOSSARY.md](../../../GLOSSARY.md). Decisions are in [docs/adr](../../adr/). Read both before working.
- PTP and KaijuNNTP are out of scope.

**Done**
1. Audit findings 1 to 8 are fixed (findings 6 to 8: PRs #28 to #30).
2. The "Backend" setting, defaulting to NzbDAV (PR #31).
3. AltMount v0.4.0 as a Backend (spec #16, PR #33).
4. Brain check on 1338 against the real AltMount (PRs #35, #38). Parity on 10 titles: 9 served the same bytes on both Backends; Interstellar (NOSiViD) was a Scrambled RAR set that AltMount rejected. Tools: [tools/brain](../../../tools/brain/README.md).
5. **Scrambled RAR sets Unscrambled before upload, for every Backend** (spec #42, [ADR 0005](../../adr/0005-unscramble-rar-sets-before-upload.md)): shared grab step #43 (PR #47), Unscramble module + Parity scenario #44 (PR #48), the upload-unchanged cases, time limit, connection cap and logs #45 (PR #49), Brain re-check #46. Re-check on 1338 (2026-11-09): Interstellar NOSiViD now plays on AltMount with bytes identical to NzbDAV at the start, 50% and 90%; `Unscrambled RAR set: 94 parts (3091 ms)`, about 33 ms per part on 8 connections. 8 of the other 9 titles matched as before; Game of Thrones S02E03 played on both sides but with different first picks after an altHUB `429` on the NZB grab (not a Backend issue). Speed medians per side (NzbDAV / AltMount): ready 0.41 / 0.04 s, seek 50% 0.23 / 0.01 s, seek 90% 0.22 / 0.01 s; 9 of the 10 Sources were already imported on both Backends from the earlier check, so these are warm numbers. The one cold first import on AltMount (Interstellar) took 4.72 s, 3.09 s of it Unscramble. Full table: `/home/ryan/kaijuflow-notes/brain-1338/RESULTS.md`. `parity.py` now records each side's speed and the Unscramble time, and `PARITY_TITLES=…` reruns a subset.

**Open points for the owner** (no code until the owner decides)
- (Decided 2026-11-09) Unscramble's 15 s limit stays: measured 3.1 s for 94 parts; the limit only matters when a news server is slow, and a set with more, smaller parts needs the room. ADR 0005.
- (Done 2026-11-09, #51, PR #52) An indexer `429`/5xx/network error on the NZB grab no longer marks the Source dead, and stale marks are dropped on load. ADR 0004.
- Health check grouping of number-named parts: #40. AltMount bug report: draft in the owner's notes, posting is the owner's call.

6. **Search side-by-side done (2026-11-09, `tools/brain/search.py`).** 10 titles through AltMount's own Stremio addon (8085, 1 indexer), KaijuFlow + AltMount (1338, 3 indexers) and UU + NzbDAV (1337, what the owner uses today). Medians (addon / KaijuFlow / UU): list shown 0.55 / 4.77 / 4.12 s; first-try plays 8 / 10 / 10 of 10; broken among the first 3 Streams 5 / 3 / 4 of 30; first byte of the first playing Stream 5.24 / 0.04 / 0.62 s (KaijuFlow and UU warm, the addon's plays were cold imports). The addon is fast because it lists unchecked indexer results and fails at play time (HTTP 503 after its segment check); KaijuFlow spends the 4 s on health checks and every first pick played. Parity run 3 the same day: all 10 titles play on both Backends, 9 byte-identical. Tables and caveats: `/home/ryan/kaijuflow-notes/brain-1338/RESULTS.md`.

**Open point for the owner:** keep KaijuFlow's own search (health-checked, 3 indexers), or pair AltMount's search with KaijuFlow's health checks? The numbers favour keeping KaijuFlow's search; AltMount's addon only wins on list time. Also: the addon test left 44 items in AltMount's import queue (categories Movies/TV, 22 failed); removing them is the owner's call.

**Decided 2026-11-09:** AltMount stays in plain HTTP mode (`mount_type: none`, no FUSE or rclone mount) and KaijuFlow keeps its one read path (AltMount's REST stream endpoint); no switchable read modes. Third-party aggregator addons are out of scope as references for any comparison.

**Next, in order** (each step its own PR, with a test)
0. **Cold speed run (owner said "go cold" on 2026-11-09; the Brain run is approved).** Runbook, nothing to decide:
   - Setup already done: AltMount's Stremio search has the same three indexers as KaijuFlow (drunkenslug and althub added next to ninja in `stremio.indexers.newsnab` of `/home/ryan/altmount-stack/config/config.yaml`, all three with `timeout_seconds: 15` like KaijuFlow's indexers, and `stremio.fallback_timeout_ms` raised from 3500 to 15000 because that value is the deadline of AltMount's whole Stremio search (`internal/stremio/search.go`, `SearchInspect`) and 3.5 s cut DrunkenSlug off every time; backup `config.yaml.bak-pre-3idx-*`; AltMount restarted 2026-11-09). This makes the addon's list time comparable with KaijuFlow's, so the earlier 0.55 s figure no longer applies. The addon's Source count will still sit near 100: AltMount asks each indexer for one page of 100 results and then removes duplicates across indexers (`internal/newsnab/client.go` limit=100, `internal/stremio/search.go` dedupeResults), while KaijuFlow pages through all results. Compare reliability and times, and say this about the counts in the report. altHUB answered `429 Request limit` to AltMount late on 2026-11-09: that is the shared altHUB key's daily limit and hits every side equally; if it persists during the run, say so in the report. Fresh titles that no Backend has played: `/home/ryan/kaijuflow-notes/brain-1338/fresh-titles.json` (The Martian, Blade Runner 2049, Mad Max: Fury Road, The Prestige, Whiplash, The Wire S01E01, Severance S01E01, The Bear S01E01, Better Call Saul S01E01, Band of Brothers S01E02).
   - `cd /home/ryan/KaijuFlow && git pull`; `cd /home/ryan/kaijuflow-test && docker compose start` (image kaijuflow:test is main a809872; `src/` has not changed since). User id = key in `/home/ryan/kaijuflow-test/config/users.json`; download key = sha256 of AltMount's API key (`sqlite3 "file:/home/ryan/altmount-stack/config/altmount.db?mode=ro" "select api_key from users"`).
   - Run 1, cold, all three sides, 3 Streams tried: `TITLES_FILE=…/fresh-titles.json timeout 1800 python3 -I tools/brain/search.py <uid> <dk> …/cold-search.json` in the background, with a monitor on the log (one line per title, stop and tell the owner on the first error).
   - Run 2, warm, right after, top pick only: same with `SEARCH_TRIES=1` and `…/warm-search.json`.
   - Run 3, seeks and same bytes on the fresh titles (warm by then): `TITLES_FILE=… timeout 1200 python3 -I tools/brain/parity.py <uid> …/parity-fresh.json`.
   - Then `docker compose stop` in kaijuflow-test. Results: append to `…/RESULTS.md`; update the page with `…/build_page.py` (copy in the notes folder, add a "Cold run" answer with cold vs warm start per side and the three-indexer search comparison) and republish it to the existing artifact https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD (pass its URL), then open it in the browser. Report in plain language: answer first, then numbers, define every column. Cleanup of the addon's imports in AltMount's queue (categories Movies/TV) stays the owner's call; list how many were added.
1. Add InfiniDysk 1.x (stable) as a Backend; 2.x once it leaves beta. It gets the same Unscrambled NZB through the shared step.
3. Benchmarks later ([plan](../performance/BENCHMARK_PLAN.md)).

Out of scope for now: library page and library delete for new Backends; several Backends at once; RAR4 Scrambled RAR sets (uploaded unchanged, logged).

**Never without the owner's OK:** change, restart or replace the working containers on Brain (UU 1337, NzbDAV 3000, AltMount 8085); install on a TV.
