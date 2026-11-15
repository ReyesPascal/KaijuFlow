# Handoff: where KaijuFlow stands (2026-11-15)

This is the one state note. Replace it; do not append. Older versions are in git history.
Terms: [GLOSSARY.md](../../../GLOSSARY.md). Decisions: [docs/adr](../../adr/).

**Rules:** [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md), "Rules" (detail in [tools/brain/docs/rules.md](../../../tools/brain/docs/rules.md)). This note holds state only.

## Goal
Measure and optimize KaijuFlow with AltMount before InfiniDysk (spec #58). InfiniDysk 1.x waits until the owner is satisfied after the final run (#68).

## The machine
- New machine `brain` (user `brain`) since 2026-11-12. The old machine is gone, and everything that was only on it went with it: the run records up to 2026-11-10, the old test settings and templates, and the architecture review.
- On this machine there are only the five test containers (`kaijuflow-test`, `uu-test`, `nzbdav-test`, `altmount-addon-test`, `altmount-kf-test`). No live stack (Usenet Ultimate, NzbDAV, AltMount) exists here.
- Docker works directly for user `brain` (no wrapper; #118 closed 2026-11-14).
- The isolated test suites run node as `nobody`: a root-owned copy sits at `/opt/node-20`, linked as `/usr/local/bin/node` (`docs/agents/testing.md`). The integration suite runs locally again (10 of 10 on 2026-11-15).

## The tracker
The work order lives in the tracker, not here. Spec #58 is the map: its sub-issues are the tickets, in order, with native blocked-by links (#125). The next step is whatever this prints, first in map order wins:

    python3 -I tools/brain/frontier.py

It lists #58's open sub-issues with no open blocker and no assignee, each with all its labels. Which tickets are open, closed or waiting is in the tracker (closed ones carry their done comments; `gh issue list` shows the rest).

## Runs and recordings on this machine
- 2026-11-10 baseline (#63, old machine): its run record is lost; its section of the speed-check page is kept in `tools/brain/page-archive/2026-11-10-baseline-nc/`.
- Recording `~/kaijuflow-notes/brain-runs/2026-11-13T035846Z-baseline-record`: complete (no misses, 174 stored answers). #127 tops it up; later runs replay it.
- **Archived (#144, done 2026-11-15):** every run from before like for like sits in `~/kaijuflow-notes/brain-runs/archive/` (the 2026-11-13 baseline `…053200Z-baseline`, which was not like for like: AltMount direct played smaller files and its hidden fallback covered four failed top picks, 36 of 40 on first tries; and `…044542Z-baseline`, a run that never wrote its record). The tools never use an archived run as a baseline or comparison, and the page refuses one. The 2026-11-09/10 page-archive sections are archived the same way.
- **#127 is the first baseline**, compared with nothing (owner, 2026-11-15): its report will say "No earlier run to compare with: this is the first one." It waits for the rest of the like-for-like work (#142 rules, #143 first-try plays), then: `--rebuild-image` on its first preflight (the image is from 750c2eb; #131, #119 and #120 changed `src`), the #142 settings applied to the test copies, the run, and the page published in the new design from that run. Each live step needs the owner's go.

## Owner's decisions
- Standard filter rules (#109): applied to both test copies; what they are and how `preflight` holds the copies to them is in `tools/brain/docs/rules.md`, "Expected settings (#109)".
- Secrets are kept outside both repos (#114, closed): the run records and recordings are pushed to the private repo `ReyesPascal/kaijuflow-notes` (runbook step 7, `tools/brain/backup.sh`).
- 2026-11-15: every frontier ticket is done in its simplest form, one ticket per session, one PR each, merged on green CI. The cuts are on each ticket as "Owner's decision (2026-11-15)" comments (#119, #120, #111, #132, #127; #133 split from #132). The third side is called **AltMount direct** in text people read; its code ID stays `altmount-addon`.
- 2026-11-15, spec #135 is in (PR #139): Unscramble one at a time (#119), the health check blocks a bare disc image (#120), short runs `--sides/--rounds/--quick` (#111), the Speed Check page and one-page Letter report in the Starting line design (`tools/brain/startline.py`, #132, #133). A tie at the maximum plays counts as met (spec #58, `targets.json`).
- 2026-11-15, like for like: every setup gets the same Sources (the stand-in filters size caps and disc images and serves the same first 100 results), 4K first, one try (#142). The final bar is #141: KaijuFlow strictly faster than every setup, every top pick playing.
- Not confirmed by the owner: the architecture candidates proposed on the old machine (the review itself is lost): Source marks + stream-list pipeline before #65; Usenet reader + Backend slot with #66.

## Gotchas
- Fix `healthChecks.maxConnections` before tuning it: see #64's comments.
- The retro's tool changes (PR #121) have not yet been exercised by a real run.
- The page no longer shows `tools/brain/page-archive/`; readable side names live in three tables (`brainreport.SIDE_NAMES`, `SHORT_NAMES`, `startline.SETUP_NAMES`), not yet one.

## Where things live
- Run records: `~/kaijuflow-notes/brain-runs/` and its `INDEX.md`; backed up with the recordings to the private repo `ReyesPascal/kaijuflow-notes` (`tools/brain/backup.sh`).
- Test folder (compose, configs, key files; outside the repo; secrets): `~/kaijuflow-test`.
- Runbook: [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md). Tools index: [tools/brain/README.md](../../../tools/brain/README.md).
- Speed-check page: https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD.
- Open issues: `gh issue list`; what can start now: `python3 -I tools/brain/frontier.py`.

## How to update
Update this note after every run or merge. Keep issue lists out of it: the tracker holds them (close a ticket in the session its work is done, `docs/agents/issue-tracker.md`). A gotcha that needs work goes on its ticket; this note keeps only a pointer.
