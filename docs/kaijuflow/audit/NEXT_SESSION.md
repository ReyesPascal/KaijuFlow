# Next session: KaijuFlow (as of 2026-11-09, after #46)

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
5. **Scrambled RAR sets Unscrambled before upload, for every Backend** (spec #42, [ADR 0005](../../adr/0005-unscramble-rar-sets-before-upload.md)): shared grab step #43 (PR #47), Unscramble module + Parity scenario #44 (PR #48), the upload-unchanged cases, time limit, connection cap and logs #45 (PR #49), Brain re-check #46. Re-check on 1338 (2026-11-09): Interstellar NOSiViD now plays on AltMount with bytes identical to NzbDAV at the start, 50% and 90%; `Unscrambled RAR set: 94 parts (3091 ms)`, about 33 ms per part on 8 connections. 8 of the other 9 titles matched as before; Game of Thrones S02E03 played on both sides but with different first picks after an altHUB `429` on the NZB grab (not a Backend issue). Speed medians per side (NzbDAV / AltMount): ready 0.41 / 0.04 s, seek 50% 0.23 / 0.01 s, seek 90% 0.22 / 0.01 s (both sides warm). Full table: `/home/ryan/kaijuflow-notes/brain-1338/RESULTS.md`. `parity.py` now records each side's speed and the Unscramble time, and `PARITY_TITLES=…` reruns a subset.

**Open points for the owner** (no code until the owner decides)
- Unscramble's 15 s limit: measured 3.1 s for 94 parts. Recommendation: keep 15 s (it only matters when a news server is slow, and a set with more, smaller parts needs the room).
- An indexer `429 Too Many Requests` on the NZB grab marks the Source dead for ever (`expiresAt: 0`), pre-existing UU behaviour; the config holds dozens of such altHUB entries. A short TTL, or no dead mark on 429, would keep those Sources. Worth an issue if the owner agrees.
- Health check grouping of number-named parts: #40. AltMount bug report: draft in the owner's notes, posting is the owner's call.

**Next, in order** (each step its own PR, with a test)
1. Search side-by-side on the same 10 titles in Stremio, three setups: AltMount's own addon, KaijuFlow with AltMount as Backend, and AIOStreams as a reference. For each, count Sources shown, broken Streams (listed but won't play) and first-try plays, and time each side (list shown, first byte), with the median per side. This decides whether KaijuFlow keeps its own search or pairs AltMount's search with KaijuFlow's health checks. The 1338 test container is stopped and ready (see tools/brain).
2. Add InfiniDysk 1.x (stable) as a Backend; 2.x once it leaves beta. It gets the same Unscrambled NZB through the shared step.
3. Benchmarks later ([plan](../performance/BENCHMARK_PLAN.md)).

Out of scope for now: library page and library delete for new Backends; several Backends at once; RAR4 Scrambled RAR sets (uploaded unchanged, logged).

**Never without the owner's OK:** change, restart or replace the working containers on Brain (UU 1337, NzbDAV 3000, AltMount 8085); install on a TV.
