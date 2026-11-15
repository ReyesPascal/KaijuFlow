# Handoff: where KaijuFlow stands (2026-11-15)

This is the one state note. Replace it; do not append. Older versions are in git history.
Terms: [GLOSSARY.md](../../../GLOSSARY.md). Decisions: [docs/adr](../../adr/).

**Rules:** [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md), "Rules" (detail in [tools/brain/docs/rules.md](../../../tools/brain/docs/rules.md)). This note holds state only.

## Goal
Speed tests that show KaijuFlow plays every title with no fails, then fastest (spec #159, the map). On 2026-11-15 the owner closed the old map #58 and its tuning, optimizing and final-run tickets (#64, #65, #66, #68) as not planned.

## The machine
- New machine `brain` (user `brain`) since 2026-11-12. The old machine is gone, and everything that was only on it went with it: the run records up to 2026-11-10, the old test settings and templates, and the architecture review.
- On this machine there are only the five test containers (`kaijuflow-test`, `uu-test`, `nzbdav-test`, `altmount-addon-test`, `altmount-kf-test`). No live stack (Usenet Ultimate, NzbDAV, AltMount) exists here.
- Docker works directly for user `brain` (no wrapper; #118 closed 2026-11-14).
- The isolated test suites run node as `nobody`: a root-owned copy sits at `/opt/node-20`, linked as `/usr/local/bin/node` (`docs/agents/testing.md`). The integration suite runs locally again (10 of 10 on 2026-11-15).

## The tracker
The work order lives in the tracker, not here. Spec #159 is the map: its sub-issues are the tickets, in order, with native blocked-by links (#125). The next step is whatever this prints, first in map order wins:

    python3 -I tools/brain/frontier.py

It lists #159's open sub-issues with no open blocker and no assignee, each with all its labels. Which tickets are open, closed or waiting is in the tracker (closed ones carry their done comments; `gh issue list` shows the rest).

## Runs and recordings on this machine
- 2026-11-10 baseline (#63, old machine): its run record is lost; its section of the speed-check page is kept in `tools/brain/page-archive/2026-11-10-baseline-nc/`.
- Recording `~/kaijuflow-notes/brain-runs/2026-11-13T035846Z-baseline-record`: complete (no misses, 174 stored answers). #127 tops it up; later runs replay it.
- **Archived (#144, done 2026-11-15):** every run from before like for like sits in `~/kaijuflow-notes/brain-runs/archive/` (the 2026-11-13 baseline `…053200Z-baseline`, which was not like for like: AltMount direct played smaller files and its hidden fallback covered four failed top picks, 36 of 40 on first tries; and `…044542Z-baseline`, a run that never wrote its record). The tools never use an archived run as a baseline or comparison, and the page refuses one. The 2026-11-09/10 page-archive sections are archived the same way.
- **Test 1 (#127, done 2026-11-15):** `~/kaijuflow-notes/brain-runs/2026-11-15T115540Z-baseline`, image from 1ed817e, #142 settings applied to AltMount direct (original config in `~/kaijuflow-test/backups/`), top-up 37 NZBs (recording complete, no misses), 120 plays, every target met, KaijuFlow and Usenet Ultimate 40 of 40, AltMount direct 36 of 40 (Chernobyl S01E02 HTTP 503 every round). **Owner: Test 1 is not the official baseline and is never compared with** (#153: `meta.json` `label`/`never_compared`). The Speed Check page (version 8) is published from it, with findings (#150).
- **Speed tests redesigned (owner, 2026-11-15):** spec #159 and ADR 0007 (amended twice): new easy and hard titles every speed test, every setup one try per title (no retries for anyone), judged per list on fails then title to video; Test 2 (#156) is the first and becomes the baseline if it works. **Built (2026-11-15, `/mattpocock-skills:implement-spec #159`):** the seven build tickets #154, #161, #163, #165, #167, #169, #171, merged to `main` in PR #177 and closed; reviewed by `/code-review` (two Fable reviewers) and `/codex-review`. #151 done: the expected settings applied to AltMount direct's test copy (`testbed.py apply`, owner's go; it added the #154 format, backup `backups/altmount-addon-20261115T154858Z-config.yaml`), the preflight passes, and the fixture is a capture. **Test 2, first attempt (cancelled 2026-11-15):** 20 titles drawn (pool marks them "used by Test 2"; owner: "dont redo same things", so they stay used and the next draw takes new ones; the list is in `~/kaijuflow-notes/speed-tests/test-2-titles.json`). The record played all 120 plays and was cancelled in its proof replay; at the owner's word its recording (`store/test-2`), run folder and INDEX.md row were deleted, nothing backed up. What it showed led to ADR 0008 (below). The pool was topped up by kind with 11 titles (IDs checked against TMDB) to keep three speed tests' worth unused. **Next:** #179 and #180 (frontier), then Test 2 again (#156: a new draw, a full new record; `kaijuflow:test` rebuilt after #179).
- **Test 1 is not like for like for AltMount direct:** "1080p UHD BluRay" outscored real 4K (AltMount v0.4.0 sums every matching custom format), so it played 1080p on 7 of 10 titles. #154 adds a -400 format and makes a stated resolution number win in the like-for-like check; the format is applied to the test copy (#151).

## Owner's decisions
- Standard filter rules (#109): applied to both test copies; what they are and how `preflight` holds the copies to them is in `tools/brain/docs/rules.md`, "Expected settings (#109)".
- Secrets are kept outside both repos (#114, closed): the run records and recordings are pushed to the private repo `ReyesPascal/kaijuflow-notes` (runbook step 7, `tools/brain/backup.sh`).
- 2026-11-15: every frontier ticket is done in its simplest form, one ticket per session, one PR each, merged on green CI. The cuts are on each ticket as "Owner's decision (2026-11-15)" comments (#119, #120, #111, #132, #127; #133 split from #132). The third side is called **AltMount direct** in text people read; its code ID stays `altmount-addon`.
- 2026-11-15, spec #135 is in (PR #139): Unscramble one at a time (#119), the health check blocks a bare disc image (#120), short runs `--sides/--rounds/--quick` (#111), the Speed Check page and one-page Letter report in the Starting line design (`tools/brain/startline.py`, #132, #133). A tie at the maximum plays counts as met (spec #58, `targets.json`).
- 2026-11-15, like for like: every setup gets the same Sources (the stand-in filters size caps and disc images and serves the same first 100 results), 4K first, one try (#142).
- 2026-11-15, how a speed test is judged ("Owner's decision" comments on #169 and #167; the rules live in `tools/brain/docs/rules.md`): fails are counted per play and every count names both ("2 titles failed · 4 of 40 plays"); target 2 holds KaijuFlow only against setups with as few fails or fewer; any tie on fails counts as fewest; "under 1 s" is strict; the final bar: on both lists, the fewest fails and the fastest title to video among setups with as few fails.
- 2026-11-15, **KaijuFlow plays plain video only** (ADR 0008, owner's words quoted there): its health check blocks every archive (stored RAR included) and every NZB with no file named as video or archive; Usenet Ultimate and AltMount direct are unchanged. A title where KaijuFlow's pick is the lower resolution is counted, not left out (#180). Built by #179 (health check) and #180 (like for like per title).
- Not confirmed by the owner: the architecture candidates proposed on the old machine (the review itself is lost): Source marks + stream-list pipeline before #65; Usenet reader + Backend slot with #66.

## Gotchas
- `healthChecks.maxConnections` already sets the health-check worker count (#131); #64's older comment saying otherwise is out of date.
- 2026-11-15: the Newshosting login was printed into a session log by mistake; the owner was advised to change the password (then update `~/kaijuflow-test/provider.json` and the test copies).
- Like for like (#142, done 2026-11-15) is in `tools/brain/docs/rules.md`: the stand-in serves every setup the same filtered first 100 (size caps, no disc images; later pages empty), so KaijuFlow gets one page per search in the test. Season packs are exempt from the 10 GB episode cap, as in KaijuFlow's own `maxFileSize`; the owner has not confirmed that. The setups still send their own queries (title text vs IMDb/TVDB ID).
- First-try plays and like for like per title (#143, done 2026-11-15): `tools/brain/docs/rules.md`, "First-try plays and like for like per title". A top pick whose own import failed before video arrived is a fallback, not a play; a title whose top picks differ in resolution, or break the cap or the disc-image rule, is left out of the targets against that setup. The 2026-11-13 baseline replayed this way (fixture `tools/brain/fixtures/run-2026-11-13-imports`) gives AltMount direct 36 of 40, and none of its titles is like for like with AltMount direct.
- On the Speed Check page each speed-test verdict shows the counts it was judged on, who it was held against and the titles left out (not like for like), while the rulers' lanes are medians over every title. Test 1's page (untagged) keeps the old six targets.
- The real-run page test (`RealBaseline` in `tools/brain/test_build_page.py`) points at Test 1 (#150).
- Test 1 is a popular, well-kept title list, so it rarely tests health checks; the owner raised a hard-titles list (no ticket yet: `/grill-with-docs` first).
- The page no longer shows `tools/brain/page-archive/`; readable side names live in three tables (`brainreport.SIDE_NAMES`, `SHORT_NAMES`, `startline.SETUP_NAMES`), not yet one; all say "AltMount direct" since the #159 build.
- A project hook (`.claude/settings.json`, `tools/brain/guard.py`, #161) refuses reads of the test folder's key files and the test copies' configs outside the brain tools, and the `gh` calls that fail here; it takes effect in a new session. `testbed.py read-settings` prints the settings with secrets as `***`.

## Where things live
- Run records: `~/kaijuflow-notes/brain-runs/` and its `INDEX.md`; backed up with the recordings to the private repo `ReyesPascal/kaijuflow-notes` (`tools/brain/backup.sh`).
- Test folder (compose, configs, key files; outside the repo; secrets): `~/kaijuflow-test`.
- Runbook: [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md). Tools index: [tools/brain/README.md](../../../tools/brain/README.md).
- Speed-check page: https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD.
- Open issues: `gh issue list`; what can start now: `python3 -I tools/brain/frontier.py`.

## How to update
Update this note after every run or merge. Keep issue lists out of it: the tracker holds them (close a ticket in the session its work is done, `docs/agents/issue-tracker.md`). A gotcha that needs work goes on its ticket; this note keeps only a pointer.
