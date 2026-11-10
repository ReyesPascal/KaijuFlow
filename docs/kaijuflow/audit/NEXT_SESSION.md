# Handoff: where KaijuFlow stands (2026-11-10)

This is the one state note. Replace it; do not append. Older versions are in git history.
Terms: [GLOSSARY.md](../../../GLOSSARY.md). Decisions: [docs/adr](../../adr/).

## Goal
Measure and optimize KaijuFlow with AltMount before InfiniDysk (spec #58). InfiniDysk 1.x waits until the owner is satisfied after the final run (#68).

## Done
- #59 to #62: the measuring tools (indexer stand-in, test copies, step timing, run report), PR #71.
- #72 (tickets #73 to #75): `preflight`, `record`, indexer timing, PR #76.
- #63 baseline run, 2026-11-10, NinjaCentral only. Run record `2026-11-10T073655Z-baseline-nc`.
  - Cold start: KaijuFlow 2.37 s, Usenet Ultimate 2.57 s, addon 4.19 s.
  - Warm start: 0.06 s, 0.18 s, 0.12 s.
  - Plays: KaijuFlow 18 of 20 cold and 20 of 20 warm; Usenet Ultimate 40 of 40; addon 30 of 38.
  - Targets: 4 of 6 met. 10 of 10 cold is NOT met (Oppenheimer, see below).
  - Unusable: the warm list times (the recording has no warm pass, so they are too low; 40 misses); the one-page side was not in the run; Usenet Ultimate's Import column is always "-".
  - Real bug found: a release name ending in `.mkv` is stored by AltMount as a folder, KaijuFlow gets a 400 and marks a good Source dead.
- #78 (PR #93) and #79 (PR #94): one shared one-page step, and a record pass now makes a cold and a warm round. Main is at 8bda508.

## In progress
Spec #77 (blocks #64): tickets #80 to #92, built in parallel today. #84 (capture AltMount's `.mkv` reply) and the #89 republish need the owner's go. #92 shows the owner three rewordings first. #91 brings the runbook.

## Rules
- Every timed run uses NinjaCentral only, on every side. DrunkenSlug stays switched off but in place; delete nothing.
- Cap rule: any indexer "limit reached" aborts the run and records it as null. Wait for NinjaCentral's reset; never switch DrunkenSlug on to finish. Limits: 2000 API hits and 450 downloads per day, treated as a rolling 24 hours (not confirmed).
- Test Backends are capped at 25 connections each.
- Live containers (Usenet Ultimate 1337, NzbDAV 3000, AltMount 8085) are never touched.
- Any Brain run needs the owner's go.
- Any commit on main needs `brainrun.py preflight --rebuild-image` before the next run.
- Every run is recorded, and every report opens with what changed since the last run.

## Next
1. Finish #77.
2. Redo the recording and the baseline (owner's go; spends NinjaCentral requests). Later runs must replay that same recording.
3. #64 tuning, one setting at a time. No `src` changes during #64.
4. #65 and #66, then #68 (final run).
5. InfiniDysk 1.x.

## Where things live
- Run records: `/home/ryan/kaijuflow-notes/brain-runs/` and its `INDEX.md`.
- Test folder (compose, configs, key files; outside the repo): `/home/ryan/kaijuflow-test`.
- Runbook: [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md) (lands with #91); recipe until then: [tools/brain/README.md](../../../tools/brain/README.md).
- Architecture review (7 candidates, none chosen, nothing lands before the measuring is settled): `/home/ryan/kaijuflow-notes/architecture-review-2026-11-10.html`.
- Open issues: `gh issue list`.

## How to update
Update this note after every run or merge.
