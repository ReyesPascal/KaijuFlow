# Next session: KaijuFlow (as of 2026-11-09, after the cold speed run)

Older handoffs are in git history. Replace this section; don't append below it.

**Where it stands**
- KaijuFlow is the owner's maintained fork of Usenet Ultimate v1.4.1. Upstream and NzbDAV are no longer maintained, so the priority is supporting maintained Backends.
- Terms are in [GLOSSARY.md](../../../GLOSSARY.md). Decisions are in [docs/adr](../../adr/). Read both before working.
- PTP and KaijuNNTP are out of scope.

**Done**
1. Audit findings 1 to 8 are fixed (findings 6 to 8: PRs #28 to #30).
2. The "Backend" setting, defaulting to NzbDAV (PR #31).
3. AltMount v0.4.0 as a Backend (spec #16, PR #33).
4. Brain check on 1338 against the real AltMount (PRs #35, #38). Tools: [tools/brain](../../../tools/brain/README.md).
5. **Scrambled RAR sets Unscrambled before upload, for every Backend** (spec #42, [ADR 0005](../../adr/0005-unscramble-rar-sets-before-upload.md); PRs #47 to #49, re-check #46). The 15 s limit stays (owner, 2026-11-09). An indexer `429`/5xx/network error on the NZB grab no longer marks the Source dead (#51, PR #52, [ADR 0004](../../adr/0004-dead-means-bad-source.md)).
6. **Search side-by-side** (2026-11-09 afternoon, `tools/brain/search.py`, PR #54): AltMount's own addon (1 indexer) against KaijuFlow + AltMount and UU + NzbDAV on 10 titles the Backends had seen. Parity run 3 the same day: 10 of 10 play on both Backends, 9 byte-identical.
7. **Cold speed run** (2026-11-09, 16:14 to 16:28 UTC, runbook was item 0 here; PRs #55, #56 for the tooling). 10 fresh titles through all three sides, the addon now with the same three indexers as KaijuFlow; run 1 cold with 3 Streams tried, run 2 warm with the top pick, run 3 parity. No errors. altHUB answered `429` (daily limit) to every side for the whole run, so all sides searched NinjaCentral and DrunkenSlug. Medians, addon / KaijuFlow + AltMount / UU + NzbDAV: list shown cold 1.19 / 9.24 / 8.94 s, warm 0.71 / 4.67 / 4.42 s; top pick plays cold 8 / 9 / 8 of 10, warm 8 / 10 / 10; start of the top pick cold 2.5 / 4.53 / 3.42 s, warm 0.04 / 0.06 / 0.28 s. Parity on the fresh titles: 10 of 10 play on both, 9 byte-identical (Band of Brothers S01E02 had different top picks). First jumps into unseen spots 0.29 / 0.33 s on NzbDAV and 0.45 / 0.41 s on AltMount; the afternoon's repeat jumps were 0.2 s against 0.01 s. KaijuFlow's extra cold second is the Unscramble step: `not-rar5` cost 0.6 to 1.6 s on seven imports, and three picks were Scrambled RAR sets (Blade Runner 2049 93 parts 4.0 s, Mad Max: Fury Road 110 parts 3.8 s, Severance S01E01 87 parts 3.3 s). Full tables and the per-title reasons: `/home/ryan/kaijuflow-notes/brain-1338/RESULTS.md` ("Cold speed run on fresh titles") and the owner's speed-check page.

**Decided 2026-11-09**
- **KaijuFlow keeps its own search** ([ADR 0006](../../adr/0006-kaijuflow-keeps-its-own-search.md)): health checks and dead marks beat the addon's 1 s list; the addon failed the same two top picks in both runs and its relevance filter dropped 191 Blade Runner 2049 results. That AltMount filter bug is not reported upstream (no effect on KaijuFlow). The health-check grouping draft (#40) stays the owner's call.
- AltMount stays in plain HTTP mode (`mount_type: none`, no FUSE or rclone mount); KaijuFlow keeps its one read path (AltMount's REST stream endpoint); no switchable read modes. Third-party aggregator addons are out of scope as references for any comparison.
- Unscramble's 15 s limit stays (ADR 0005).

**Open for the owner**
- AltMount queue cleanup (approved 2026-11-09, not yet done): remove the addon test imports under categories Movies and TV (99 rows after the two runs, 59 failed) and keep the `kaijuflow` category while Backend tests continue. The frontend's `DELETE /api/queue/...` routes need a JWT from `POST /api/auth/login` (the API key is not accepted there, and AltMount's SABnzbd API is disabled in its config), so this is done in AltMount's web UI (Queue, filter by category, Clear completed and Clear failed) or with the owner's login.

**Next, in order** (each step its own PR, with a test)
1. Add InfiniDysk 1.x (stable) as a Backend; 2.x once it leaves beta. It gets the same Unscrambled NZB through the shared step.
2. **Faster `not-rar5` answer in Unscramble** (owner approved 2026-11-09; after InfiniDysk unless pulled forward). `unscrambleSet` in `src/archive/unscramble.ts` reads the first article of every number-named part before it can say `not-rar5` (227 parts on 8 connections took 699 ms; 0.6 to 1.6 s per cold import in the cold run). Read one part first and fan out only when it is RAR5; the renamed path, the time limit and the Parity scenario stay as they are. Unit test in the Unscramble tests for the one-part short cut; `tools/brain/parity.py` shows the saving on a cold import.
3. Benchmarks later ([plan](../performance/BENCHMARK_PLAN.md)).

Out of scope for now: library page and library delete for new Backends; several Backends at once; RAR4 Scrambled RAR sets (uploaded unchanged, logged).

**Never without the owner's OK:** change, restart or replace the working containers on Brain (UU 1337, NzbDAV 3000, AltMount 8085); install on a TV.
