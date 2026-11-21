# Handoff: where KaijuFlow stands (2026-11-20)

This is the one state note. Replace it; do not append. Older versions are in git history.
Terms: [GLOSSARY.md](../../../GLOSSARY.md). Decisions: [docs/adr](../../adr/).

**Rules:** [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md), "Rules" (detail in [tools/brain/docs/rules.md](../../../tools/brain/docs/rules.md)). This note holds state only.

## Goal
KaijuFlow with AltMount as its one Backend, as fast and lean as possible; KaijuFlow does the health check, archives AltMount can stream allowed; no more speed tests against Usenet Ultimate or AltMount direct (owner, 2026-11-20; spec #183, the map). Owner's words: "I just want altmount to be the fast backend and want KF to do the healthcheck, even if its RARS, find a way to make them work together as fast as possible forget speed testing against the rest"; "i want it to be as fast and lean as possible". Spec #159 and its last tickets (#179 plain video only, #180, #156 Test 2) were closed on 2026-11-20; ADR 0009 replaces ADR 0008.

## Next command
What the owner types next (the `/kf` report ends with it, `docs/agents/resume.md`). Keep it current; empty when nothing waits on the owner.

    /mattpocock-skills:implement-spec #183

**First, before phase 1: the voice test** (owner, 2026-11-20: "save the voices to test next session when i start with kf"). The run's owner alert (`~/.local/bin/kf-alert`, spec #183) speaks with a Piper voice; the owner has not picked one. Play the three, one at a time, each waiting for the owner to close its notification (X) before the next: `KF_VOICE=<voice> ~/.local/bin/kf-alert "voice one"` (then two, three) with `en_GB-jenny_dioco-medium` (now the default), `en_US-amy-medium`, `en_US-hfc_female-medium`. Ask which they want, set it as the default `voice=` in `~/.local/bin/kf-alert`, clear this paragraph, then give the command above.

Phase 1 of spec #183's "Building it": builds #217, #190, and the six tuning tickets into `tuning-183`; merges #217's PR and PR #210 itself once ready and green. After it reports phase 1 done: `/kf phase 2 of #183` (runs, idle machine).

## The machine
- New machine `brain` (user `brain`) since 2026-11-12. The old machine is gone, and everything that was only on it went with it: the run records up to 2026-11-10, the old test settings and templates, and the architecture review.
- On this machine there are only the five test containers (`kaijuflow-test`, `uu-test`, `nzbdav-test`, `altmount-addon-test`, `altmount-kf-test`). Since #187 the brain tools and `compose.test.yaml` know only `kaijuflow-test` and `altmount-kf-test`; the other three are to be stopped and kept (a live step, owner's go). No live stack (Usenet Ultimate, NzbDAV, AltMount) exists here.
- Docker works directly for user `brain` (no wrapper; #118 closed 2026-11-14).
- **Tests run on Wi-Fi** (address 192.168.4.48), by the owner's decision of 2026-11-20 (evening); the baseline #189 and the #205 re-run were on ethernet (192.168.4.34) and are not like for like with Wi-Fi runs. The test setup is pinned to the machine's address in two places, both now the Wi-Fi one: `HOST_IP` in `~/kaijuflow-test/.env` and KaijuFlow's `altmountUrl` (`http://192.168.4.48:8087`) in its copy's `config.json`. Before a run: `ip -br addr` shows 192.168.4.48. The preflight does not check `altmountUrl` (on 2026-11-20 a stale one made every play fail with "AltMount is not reachable" while the preflight passed).
- **A timed run needs an idle machine**: no agents building, no `npm ci`, no test suites beside it; the suite lock alone is not enough (diagnosis on #205).
- The isolated test suites run node as `nobody`: a root-owned copy sits at `/opt/node-20`, linked as `/usr/local/bin/node` (`docs/agents/testing.md`). The integration suite runs locally again (10 of 10 on 2026-11-15).

## The tracker
The work order lives in the tracker, not here. Spec #183 is the map: its sub-issues (#184 to #195, plus #200 between #188 and #189) are the tickets, in order, with native blocked-by links. The next step is whatever this prints, first in map order wins (on 2026-11-20 evening: #190):

    python3 -I tools/brain/frontier.py

Done on 2026-11-20: #184 (pass rule, PR #197), and #185 to #188 in the first `implement-spec` run (integration branch `kf-alone-183`, PR #199; reviewed by `/code-review` with Fable high and `/codex-review`, fixes merged). #200 (NzbDAV leftovers renamed to "play": `src/play/`, routes `/play/...` and `/api/play/*`, settings `play*`, env `PLAY_*`; streaming-mode choice deleted; old configs migrated once at startup) on branch `play-200`, reviewed by `/code-review` high and `/codex-review`. #200 is on main (PR #201).

**Baseline (#189), 2026-11-20, on ethernet:** run `~/kaijuflow-notes/brain-runs/2026-11-20T223814Z-baseline-189` (`check`: usable; marked never compared with since the Wi-Fi decision). Recording `--store ~/kaijuflow-test/store --list kf-189`, titles `tools/brain/fixed-list.json` (20 titles drawn as "Baseline #189"); pass both, plus `--titles-file`, to every later run. Result: 78 of 80 plays; cold title to video easy 9.19 s, hard 8.31 s; warm 2.10 s and 1.23 s; the only fail is The Twilight Zone S02E06 in both cold rounds (AltMount refused a season pack the health check passed). Report page: https://claude.ai/artifact/3e8rDSigAqokBbQDdhxHg3.

**Browse pause (#205), done:** PR #209 is on main and #205 is closed. Its re-run with the 5 s pause, `~/kaijuflow-notes/brain-runs/2026-11-21T002421Z-baseline-205-browse-pause` (ethernet), played the same 78 of 80; play to first byte fell to about 0.1 s for most titles, but its cold lists were slower (KaijuFlow's own work 5.3 s to 6.6 s). Diagnosed the same evening (comment on #205): not the pause but a busy machine, five agents were building beside the run. So its cold timings are no yardstick. Report: https://claude.ai/artifact/KAD1JtyC63P82rXXocnkuJ.

**How the rest is built (owner, 2026-11-20 grilling; spec #183, "Building it"):** two phases.
- **Phase 1, build** (`/mattpocock-skills:implement-spec #183`, no runs): #217 (preflight refuses a busy machine, a stale address or sinkholed DNS; own PR to main), #190 (finish the fix-up on PR #210 from `wip-play-time-check-190`), and #193, #211, #203, #191, #192, #206 merged into integration branch `tuning-183` (one PR; their PRs #208, #213, #212, #214, #215 and the `wip-*` branches are where the work is). Review: `/code-review` Fable high, `/codex-review`, one Opus-high fix-up. Ends at the owner's one stop: merge #217's PR, then PR #210.
- **Phase 2, runs** (standing go, one at a time, idle machine, Wi-Fi): #218 the official baseline from `main`, then #219 one grouped run of the six from `tuning-183`; if not kept, halving runs until the cause shows. The ethernet runs are marked never compared with (notes repo 8b19509). Kept rule unchanged, no noise band. Then #194 and #195, the owner's.

Owner's ideas waiting for a `/grill-with-docs` (not tickets): start the health check when a title is opened (after #190's run; comment on #190); redo the settings UI, its flow, first-time setup and the name "Ultimate Fallback" (after #200 is on main). Research for the UI: `~/kaijuflow-notes/reports/KF UI design.md` (16 decisions for the owner), screenshots page https://claude.ai/artifact/9uLC6XHL1c8nVW3jVLpr5U.

## Runs and recordings on this machine
- Everything before 2026-11-20 compared three setups and is not compared with any more: Test 1 (`~/kaijuflow-notes/brain-runs/2026-11-15T115540Z-baseline`, never compared with, #153), the archived runs in `~/kaijuflow-notes/brain-runs/archive/`, and the 2026-11-13 baseline recording. Test 1's facts shaped spec #183: KaijuFlow already used AltMount (port 8087, container `altmount-kf-test`); its cold list took 7.1 s (about 5.8 s health check before the list) against AltMount direct's 0.8 s; click to video about 3.2 s for both.
- Pool: Test 2's 20 drawn titles stay marked used (owner: "dont redo same things"); the baseline (#189) draws the fixed lists.
- Speed Check page (https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD, version 8, Test 1) is not updated until #195.

## Owner's decisions
- 2026-11-20 (spec #183, all with the owner's "yes"): the health-check pass list (ADR 0009); no fails first, then fastest cold title to video; fallback on (in effect only from #190: Ultimate Fallback stays off for AltMount until then, so the baseline #189 plays one try per title; owner, review of PR #199); one fixed recording replayed every run, a new draw only when the owner asks; the stand-in passes answers untouched; comparison code deleted, not switched off; NzbDAV removed in its own ticket; other test copies stopped and kept; tuning may cut any part of the path, AltMount's settings too, one change per run.
- Standard filter rules (#109), secrets outside both repos (#114, `tools/brain/backup.sh`), the third side's name "AltMount direct": as before, see git history of this note.
- 2026-11-20 (evening): "i want to do the rest of the tests on wifi and also not do official baseline until the fix is in for the failures"; then "no tests until 190 is in" (comments on #183).
- Workflow: one PR per ticket, merged on green CI; the owner runs `gh pr merge` (auto mode blocks it); stop before every live step.

## Gotchas
- #184 fixed three archive-parser faults found on real archives: RAR5 compression read from the version bits (every RAR5 looked stored), RAR5 file encryption missed, 7z never reported stored. Test 1's "stored"/"compressed" health-check labels came from the old parsers, so don't trust them. Real-archive fixtures: `tests/fixtures/archives/make.sh` (RAR 7.23 and 6.24 for RAR4 at `~/.local/share/rarlab`, from rarlab.com).
- AltMount's refusal reasons appear only in its log, not in the HTTP answer (500 "NZB processing failed"); Test 1's logs hold none, and the texts in ADR 0008 are all that's left. No disc-image text was kept.
- `healthChecks.maxConnections` already sets the health-check worker count (#131).
- Auto-queue (`autoQueueMode`, GLOSSARY) is what prepared about 35 imports for 20 cold plays in Test 1; #192 starts there.
- Ultimate Fallback already health-checks Sources at play time through the Backend interface but is on for NzbDAV only (`backendCapabilities().ultimateFallback`); #190 builds the play-time check on it, and #188 keeps its engine.
- The first title after a reset (The Batman) swings between about 9 and 14 s of cold list on an idle machine; not explained yet (comment on #205).
- Newshosting DNS: the router has answered `news.newshosting.com` with a dead 10.x address (2026-11-17); check before a run (`dig +short news.newshosting.com @192.168.4.1`).
- A project hook (`tools/brain/guard.py`) refuses reads of the test folder's key files and the test copies' configs, and the `gh` calls that fail here; `testbed.py read-settings` prints settings with secrets as `***`.
- 2026-11-15: the Newshosting login was printed into a session log by mistake; the owner was advised to change the password.

## Where things live
- Run records: `~/kaijuflow-notes/brain-runs/` and its `INDEX.md`; backed up with the recordings to the private repo `ReyesPascal/kaijuflow-notes` (`tools/brain/backup.sh`).
- Test folder (compose, configs, key files; outside the repo; secrets): `~/kaijuflow-test`.
- Runbook: [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md). Tools index: [tools/brain/README.md](../../../tools/brain/README.md).
- Speed-check page: https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD.
- Open issues: `gh issue list`; what can start now: `python3 -I tools/brain/frontier.py` (map #183).

## How to update
Keep "Next command" right: whenever the next step needs the owner to type something, write it there.
Update this note after every run or merge. Keep issue lists out of it: the tracker holds them (close a ticket in the session its work is done, `docs/agents/issue-tracker.md`). A gotcha that needs work goes on its ticket; this note keeps only a pointer.
