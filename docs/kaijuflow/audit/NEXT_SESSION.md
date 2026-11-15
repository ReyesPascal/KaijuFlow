# Handoff: where KaijuFlow stands (2026-11-14)

This is the one state note. Replace it; do not append. Older versions are in git history.
Terms: [GLOSSARY.md](../../../GLOSSARY.md). Decisions: [docs/adr](../../adr/).

**Rules:** [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md), "Rules" (detail in [tools/brain/docs/rules.md](../../../tools/brain/docs/rules.md)). This note holds state only.

## Goal
Measure and optimize KaijuFlow with AltMount before InfiniDysk (spec #58). InfiniDysk 1.x waits until the owner is satisfied after the final run (#68).

## The machine
- New machine `brain` (user `brain`) since 2026-11-12. The old machine is gone, and everything that was only on it went with it: the run records up to 2026-11-10, the old test settings and templates, and the architecture review.
- On this machine there are only the five test containers (`kaijuflow-test`, `uu-test`, `nzbdav-test`, `altmount-addon-test`, `altmount-kf-test`). No live stack (Usenet Ultimate, NzbDAV, AltMount) exists here.
- Docker works directly for user `brain` (no wrapper; #118 closed 2026-11-14).

## The tracker
The work order lives in the tracker, not here. Spec #58 is the map: its sub-issues are the tickets, in order, with native blocked-by links (#125). The next step is whatever this prints, first in map order wins:

    python3 -I tools/brain/frontier.py

It lists #58's open sub-issues with no open blocker and no assignee, each with all its labels. Which tickets are open, closed or waiting is in the tracker (closed ones carry their done comments; `gh issue list` shows the rest).

## Runs and recordings on this machine
- 2026-11-10 baseline (#63, old machine): its run record is lost; its section of the speed-check page is kept in `tools/brain/page-archive/2026-11-10-baseline-nc/`.
- Recording `~/kaijuflow-notes/brain-runs/2026-11-13T035846Z-baseline-record`: complete (no misses, 174 stored answers). #127 tops it up; later runs replay it.
- Baseline run `~/kaijuflow-notes/brain-runs/2026-11-13T053200Z-baseline`: usable as a baseline (CHECK.txt), 39 min, 160 plays; results in its `story.html` and the speed-check page, version 7. It predates the standard filter rules, so its top picks were the largest 4K remuxes (#109).
- The image was built from 750c2eb and is still current; the tool changes since then touch no build input. A ticket that changes `src` needs a rebuild afterwards (runbook, step 0).

## Owner's decisions
- Standard filter rules (#109): applied to both test copies; what they are and how `preflight` holds the copies to them is in `tools/brain/docs/rules.md`, "Expected settings (#109)".
- Secrets are kept outside both repos (#114, closed): the run records and recordings are pushed to the private repo `ReyesPascal/kaijuflow-notes` (runbook step 7, `tools/brain/backup.sh`).
- Not confirmed by the owner: the architecture candidates proposed on the old machine (the review itself is lost): Source marks + stream-list pipeline before #65; Usenet reader + Backend slot with #66.

## Gotchas
- Fix `healthChecks.maxConnections` before tuning it: see #64's comments.
- The retro's tool changes (PR #121) have not yet been exercised by a real run.
- A run's tables on the speed-check page are keyed by its run folder, so the next publish renames the 2026-11-13 run's table slots.

## Where things live
- Run records: `~/kaijuflow-notes/brain-runs/` and its `INDEX.md`; backed up with the recordings to the private repo `ReyesPascal/kaijuflow-notes` (`tools/brain/backup.sh`).
- Test folder (compose, configs, key files; outside the repo; secrets): `~/kaijuflow-test`.
- Runbook: [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md). Tools index: [tools/brain/README.md](../../../tools/brain/README.md).
- Speed-check page: https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD.
- Open issues: `gh issue list`; what can start now: `python3 -I tools/brain/frontier.py`.

## How to update
Update this note after every run or merge. Keep issue lists out of it: the tracker holds them (close a ticket in the session its work is done, `docs/agents/issue-tracker.md`). A gotcha that needs work goes on its ticket; this note keeps only a pointer.
