# Next session: KaijuFlow (as of 2026-11-09)

Older handoffs are in git history. Replace this section; don't append below it.

**Where it stands**
- KaijuFlow is the owner's maintained fork of Usenet Ultimate v1.4.1. Upstream and NzbDAV are no longer maintained, so the priority is supporting maintained Backends.
- Terms are in [GLOSSARY.md](../../../GLOSSARY.md). Decisions are in [docs/adr](../../adr/). Read both before working.
- PTP and KaijuNNTP are out of scope.

**Done**
1. Audit findings 1 to 8 are fixed (findings 6 to 8: PRs #28 to #30).
2. The "Backend" setting, defaulting to NzbDAV (PR #31).
3. AltMount v0.4.0 as a Backend (spec #16, PR #33).
4. Brain check on 1338 against the real AltMount (PRs #35, #38). It found and fixed one bug: AltMount's queue fields sit at the top of the reply, not inside each stream. Parity on 10 titles: 9 serve the same bytes on both Backends, including seeking. Interstellar (NOSiViD) plays on NzbDAV but AltMount rejects it. Its RAR parts have scrambled number names (`<hash>.10` to `.103`, shuffled), so AltMount's check sees missing volumes. All video articles are present. Renaming the parts in real volume order (read from each part's first article) makes AltMount stream it with the same bytes as NzbDAV. Tools: [tools/brain](../../../tools/brain/README.md).

**Next, in order** (each step its own PR, with a test)
1. **Scrambled RAR fix, for every Backend.** Grilled 2026-11-09: terms in GLOSSARY.md (Scrambled RAR set, Unscramble), decision in [ADR 0005](../../adr/0005-unscramble-rar-sets-before-upload.md), all 15 answers in `/home/ryan/kaijuflow-notes/scrambled-rar/DECISIONS.md`. Next: `/to-spec` from DECISIONS.md; no code until the owner says go. After merge, Brain re-check on the 1338 test container (decision 13).
   **Every side-by-side test records the speed of each side** (prepare time, time to first byte, 50%/90% seek reads, Unscramble time; for search, time until the list shows), with the median per side. See DECISIONS.md.
2. Search side-by-side on the same 10 titles in Stremio, three setups: AltMount's own addon, KaijuFlow with AltMount as Backend, and AIOStreams as a reference. For each, count Sources shown, broken Streams (listed but won't play) and first-try plays, and time each side (list shown, first byte). This decides whether KaijuFlow keeps its own search or pairs AltMount's search with KaijuFlow's health checks. The 1338 test container is stopped and ready (see tools/brain).
3. Add InfiniDysk 1.x (stable) as a Backend; 2.x once it leaves beta.
4. Benchmarks later ([plan](../performance/BENCHMARK_PLAN.md)).

Out of scope for now: library page and library delete for new Backends; several Backends at once.

**Never without the owner's OK:** change, restart or replace the working containers on Brain (UU 1337, NzbDAV 3000, AltMount 8085); install on a TV.
