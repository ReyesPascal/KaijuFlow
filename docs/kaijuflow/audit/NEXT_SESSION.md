# Handoff: where KaijuFlow stands (2026-11-14)

This is the one state note. Replace it; do not append. Older versions are in git history.
Terms: [GLOSSARY.md](../../../GLOSSARY.md). Decisions: [docs/adr](../../adr/).

**Rules:** [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md), "Rules" (detail in [tools/brain/docs/rules.md](../../../tools/brain/docs/rules.md)). This note holds state only.

## Goal
Measure and optimize KaijuFlow with AltMount before InfiniDysk (spec #58). InfiniDysk 1.x waits until the owner is satisfied after the final run (#68).

## The machine
- New machine `brain` (user `brain`) since 2026-11-12. The old machine is gone, and everything that was only on it went with it: the run records up to 2026-11-10, the old test settings and templates, and the architecture review.
- On this machine there are only the five test containers (`kaijuflow-test`, `uu-test`, `nzbdav-test`, `altmount-addon-test`, `altmount-kf-test`). No live stack (Usenet Ultimate, NzbDAV, AltMount) exists here.
- Docker works only through the `sudo -n -u brain -g docker ...` wrapper until the owner logs out and in (#118).

## Done
- Spec #58 measuring tools (#59 to #62, #72 to #75) and spec #77 (#78 to #92, PRs #93 to #106): `preflight`, `record` (cold and warm round per side plus a proof replay), `run`, `check`, `usage`, the page builder, the runbook.
- #63 baseline, 2026-11-10, on the old machine. Its run record is lost; its section of the speed-check page is kept in `tools/brain/page-archive/2026-11-10-baseline-nc/`.
- 2026-11-13, on this machine:
  - Recording `~/kaijuflow-notes/brain-runs/2026-11-13T035846Z-baseline-record`: complete (no misses, 174 stored answers; the baseline below replayed it).
  - Baseline run `~/kaijuflow-notes/brain-runs/2026-11-13T053200Z-baseline`: usable as a baseline (CHECK.txt), 39 min, 160 plays. Results and findings: the run folder's `story.html` and the speed-check page, version 7, https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD.
  - Its open question, why KaijuFlow and Usenet Ultimate picked a 66 to 91 GB file for every film, is answered in #109: the test copies had no sort and filter rules, so the largest 4K remux came first.
- Standard filter rules (new, since the old ones are lost; #109 and its comments): films at most 30 GiB, episodes at most 10 GiB, disc images dropped, KaijuFlow's defaults otherwise. Applied to both test copies (KaijuFlow and Usenet Ultimate); `preflight` checks them against `tools/brain/expected-settings.json`. The 2026-11-13 baseline predates them.

- Retro of the 2026-11-13 baseline: PR #121, merged into `main` on 2026-11-13 (e3c28ad), closing #109, #110, #112, #113, #115, #116 and #117. It went through a code review (standards and spec) and one round of fixes. 346 tool tests; not yet exercised by a real run.
  - #110: a run or record stopped with Ctrl-C or SIGTERM (`timeout`) keeps the plays and answers it finished, ends the normal way and exits 130; a second Ctrl-C during the ending is ignored.
  - #112: every play and reset line starts with the UTC time and the play count, and `report.md` ends with "Where the time went".
  - #113: `preflight` asks for `--rebuild-image` only when the code in the image changed (runbook, step 0). #121 changed none, so the image built from 750c2eb is still current.
  - #115: `build_page.py` takes a run's `story.html`, keeps the lost runs' sections from `tools/brain/page-archive/`, and the runbook says how to publish. A run's tables are keyed by its run folder, so the next publish renames the 2026-11-13 run's table slots.
  - #116: `check` and the report judge the six targets from `tools/brain/targets.json` (finished runs only).
  - #109: `preflight` compares the test copies' sort and filter settings with `tools/brain/expected-settings.json`; the per-title table names each top pick and its size; a changed top pick is listed under "What changed since the last run".
  - #117: this note.

## In progress
Nothing is being built.

Triaged 2026-11-14, each with an agent brief as an issue comment (the brief is the contract):
- #119 `bug`: Unscramble one Source at a time, direct plays first, each with its own 15 s from its turn; ADR 0005 note and a glossary entry in the same PR.
- #120 `bug`: a bare `.iso` / `.img` in the health check's largest-file fallback becomes `blocked` "Disc image".
- #111 `enhancement`: `run --sides`, `--rounds 1|2`, `--quick`; a short run is never usable as a baseline.

Waiting on the owner:
- #114 backup: the run records and recordings are pushed to the private repo `ReyesPascal/kaijuflow-notes` (runbook step 7, `tools/brain/backup.sh`). Still with the owner: the secrets in `~/kaijuflow-test/*.json` (and `~/.stash`) into a password manager.
- #118 log out and in so Docker works without the wrapper.

Not triaged: #2 and #4 (look stale), #40 (health check misgroups `<hash>.NN` parts).

## Next
1. `/implement` #119, then #120 (a fresh session each). Both are `src` changes, so they land before the new baseline: #64 allows no `src` changes. Rebuild the image afterwards (runbook, step 0).
2. Top up the recording and run a new baseline with the standard filter rules (owner's go for both; the top-up spends NinjaCentral downloads). Follow the runbook. Later runs replay that recording. It checks #119: Inception's top pick plays in both cold rounds.
3. #111 before #64, so tuning runs can be short (`--quick`).
4. #64 tuning, one setting at a time. No `src` changes during #64. Note: `healthChecks.maxConnections` is saved but not read for the number of health-check workers (`src/addon/healthCheckCoordinator.ts` takes it from `smartBatchSize` or `nzbsToInspect`); fix it before tuning it.
5. #65 and #66, then #68 (final run). Architecture candidates proposed on the old machine (not confirmed by the owner; the review itself is lost): Source marks + stream-list pipeline before #65; Usenet reader + Backend slot with #66.
6. InfiniDysk 1.x.

## Where things live
- Run records: `~/kaijuflow-notes/brain-runs/` and its `INDEX.md`; backed up with the recordings to the private repo `ReyesPascal/kaijuflow-notes` (`tools/brain/backup.sh`).
- Test folder (compose, configs, key files; outside the repo; secrets): `~/kaijuflow-test`.
- Runbook: [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md). Tools index: [tools/brain/README.md](../../../tools/brain/README.md).
- Speed-check page: https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD.
- Open issues: `gh issue list`.

## How to update
Update this note after every run or merge.
