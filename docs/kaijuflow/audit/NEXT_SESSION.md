# Next session — KaijuFlow (as of 2026-11-07)

Older handoffs are in git history. Replace this section; don't append below it.

**Where it stands**
- PR #1 (upstream v1.4.1 import) and PR #3 (tests + audit docs) are merged into `main`.
- The audit is finished (A4 closed). The "document only, don't fix" rule is lifted. Fixes are now allowed one at a time, each with a test, each in its own PR.
- App code is still the original v1.4.1. No fixes merged yet.
- Findings and their status: [AUDIT.md](../AUDIT.md). How the app works: [NNTP](../references/nntp/README.md), [NzbDAV](../references/nzbdav/README.md).

**Next action**
1. Fix finding 1 (`localhost` → `127.0.0.1` for self-requests). Then fix findings 2–4; the existing red tests should turn green. Then fix findings 5–8.
2. Run KaijuFlow as a test container on Brain on a different port, with a test copy of PTP pointed at it. Get the owner's OK before touching Brain.
3. Then: pluggable backends (NzbDAV first, then InfiniDysk and AltMount), better ranking, and benchmarks ([plan](../performance/BENCHMARK_PLAN.md)).

**Never without the owner's OK:** change, restart or replace the working containers on Brain; install on a TV.
