# Next session — KaijuFlow (as of 2026-11-07)

Older handoffs are in git history. Replace this section; don't append below it.

**Where it stands**
- Findings 1–4 are fixed and merged (PRs #6, #7, #8). Finding 5 is in PR #9. Status per finding: [AUDIT.md](../AUDIT.md).
- None of the fixes has been tested on Brain or the TV yet.
- Tests: `npm run test:unit`; the A4 and integration workflows (run by hand on the branch). All green as of PR #9.
- How the app works: [NNTP](../references/nntp/README.md), [NzbDAV](../references/nzbdav/README.md).

**Next action**
1. Check that PR #9 is merged. Ask the owner whether Ultimate Fallback is on (PR #9 only applies when it is).
2. Fix finding 6, then 7, then 8. One PR each, with a test that fails on old code and passes on new.
3. Then run KaijuFlow as a test container on Brain on a different port, with a test copy of PTP pointed at it (owner's OK first).

**Never without the owner's OK:** change, restart or replace the working containers on Brain; install on a TV.
