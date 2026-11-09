# Next session: KaijuFlow (as of 2026-11-09)

Older handoffs are in git history. Replace this section; don't append below it.

**Where it stands**
- KaijuFlow is the owner's maintained fork of Usenet Ultimate v1.4.1. Upstream and NzbDAV are no longer maintained, so the priority is supporting maintained Backends.
- Audit findings 1 to 5 are fixed (PRs #6 to #9). Findings 6 to 8 are open. See [AUDIT.md](../AUDIT.md).
- Terms are in [GLOSSARY.md](../../../GLOSSARY.md). Decisions are in [docs/adr](../../adr/). Read both before working.
- PTP and KaijuNNTP are out of scope.

**Plan, in order** (each step its own PR, with a test)
1. Fix findings 6, 7 and 8, one PR each.
2. Add a "Backend" setting, defaulting to NzbDAV. Move the NzbDAV code behind it with no behavior change; existing NzbDAV settings keep working.
3. Add AltMount (v0.4.0) as a Backend. KaijuFlow keeps search, health checks, ranking and fallback; AltMount only turns the chosen Source into a Stream (`POST /api/nzb/streams`). See [ALTMOUNT_INTEGRATION.md](../research/ALTMOUNT_INTEGRATION.md).
4. Run a KaijuFlow test container on Brain on port 1338, using the existing AltMount (port 8085) with its own category `kaijuflow`. Get the owner's OK first. Check Parity on 10 titles: every title that plays through NzbDAV plays through AltMount, seeking works, and a Source that fails shows the failure video and is not offered again. Ultimate Fallback is not required for new Backends (owner does not use it).
5. Search side-by-side on the same 10 titles in Stremio, three setups: AltMount's own addon, KaijuFlow with AltMount as Backend, and AIOStreams as a reference. For each, count Sources shown, broken Streams (listed but won't play) and first-try plays. This decides whether KaijuFlow keeps its own search or pairs AltMount's search with KaijuFlow's health checks.
6. Add InfiniDysk 1.x (stable) as a Backend; 2.x once it leaves beta.
7. Benchmarks later ([plan](../performance/BENCHMARK_PLAN.md)).

Out of scope for now: library page and library delete for new Backends; several Backends at once.

**Never without the owner's OK:** change, restart or replace the working containers on Brain (UU 1337, NzbDAV 3000, AltMount 8085); install on a TV.
