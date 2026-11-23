# Handoff: where KaijuFlow stands (2026-11-20, end of phase 1)

This is the one state note. Replace it; do not append. Older versions are in git history.
Terms: [GLOSSARY.md](../../../GLOSSARY.md). Decisions: [docs/adr](../../adr/).

**Rules:** [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md), "Rules" (detail in [tools/brain/docs/rules.md](../../../tools/brain/docs/rules.md)). This note holds state only.

## Goal
KaijuFlow with AltMount as its one Backend, as fast and lean as possible; KaijuFlow does the health check, archives AltMount can stream allowed; no more speed tests against Usenet Ultimate or AltMount direct (owner, 2026-11-20; spec #183, the map). Owner's words: "I just want altmount to be the fast backend and want KF to do the healthcheck, even if its RARS, find a way to make them work together as fast as possible forget speed testing against the rest"; "i want it to be as fast and lean as possible". ADR 0009 replaces ADR 0008.

## Next command
What the owner types next (the `/kf` report ends with it, `docs/agents/resume.md`). Keep it current; empty when nothing waits on the owner.

    /kf phase 2 of #183

Phase 2 of spec #183's "Building it": the runs, one at a time, on Wi-Fi, on an idle machine (close the builder panes and anything else busy first; the preflight now refuses a 1-minute load of 1.0 or more). Under the standing go: #218 the official baseline from `main`, then #219 the grouped run from `tuning-183`, then halving runs if #219 is not kept. The preflight says whether a run needs the image rebuilt or `testbed.py apply`.

**Alerts:** `~/.local/bin/kf-alert "<what to type next>"` (Pocket TTS voice "azelma", repeats until the notification is closed) at every stop-and-ask and when #219 is done. Questions in the session: AskUserQuestion (herdr plays its "request" voice) plus a short red sidebar line, `~/.local/bin/kf-ask "<question>"`, `kf-ask clear` once answered. herdr's own "done" sound and its pop-ups are off (owner, 2026-11-20).

## Phase 1, done (2026-11-20)
Built with `/mattpocock-skills:implement-spec #183` inside herdr (implementers and fix-ups as Claude Code panes, Opus high; reviews `/code-review` Fable high + `/codex-review`).
- **On main:** #217 preflight (PR #224: refuses a busy machine, a stale `HOST_IP`/`altmountUrl`, a sinkholed Newshosting DNS; the address and DNS checks also before a `record`, owner's decision on #217; `meta.json` keeps the start load) and #190 Play-time check (PR #210). Both closed.
- **On `tuning-183`, draft PR #225** (reviewed, fixed, CI green; stays a draft until #219 is kept, then ready and merged on green): #193 Unscramble skip, #211 segment order, #203 sample the wanted episode, #192 prepare only the played Source, #226 Delete Auto-queue (split from #206 on 2026-11-20, owner's "yes"), #206 Head start, #191 delete the list-time checks. Each ticket has a "Merged into `tuning-183`" comment; their own PRs are closed.
- **Owner's decisions during phase 1:** #206 split into #206 + #226 (comment on #183; #219 now plays seven tickets' changes, and in a halving run #226 goes with #206); the 25 s first-Source switch stays as the one exception to "prepare only the played Source" (comment on #192); address and DNS checks before a record too (comment on #217).
- **Not done:** `/retro` on this session (owner's to start; candidates: review findings kept only in a session log, herdr's done sound mistaken for a call, the watcher missing wrapped `DONE` lines).

## The machine
- Machine `brain` (user `brain`) since 2026-11-12; everything only on the old machine is gone (run records up to 2026-11-10, old test settings, the architecture review).
- Five test containers exist (`kaijuflow-test`, `uu-test`, `nzbdav-test`, `altmount-addon-test`, `altmount-kf-test`); the brain tools know only `kaijuflow-test` and `altmount-kf-test`; the other three are to be stopped and kept (a live step, owner's go). No live stack here.
- **Tests run on Wi-Fi** (192.168.4.48), owner's decision of 2026-11-20 (evening); `HOST_IP` in `~/kaijuflow-test/.env` and KaijuFlow's `altmountUrl` are pinned to it, and the preflight now checks both. The ethernet runs (#189 baseline, #205 re-run) are never compared with.
- **A timed run needs an idle machine**; the preflight enforces it (#217).
- The isolated test suites run node as `nobody` via `/opt/node-20` (`docs/agents/testing.md`).

## The tracker
Spec #183 is the map; `python3 -I tools/brain/frontier.py` prints what can start (after phase 1: #218). Phase 2 order: #218 → #219 (blocked by #218 and the seven) → #194 (owner's, AltMount settings) → #195 (Speed Check page).

**Baseline (#189), 2026-11-20, ethernet, never compared with:** `~/kaijuflow-notes/brain-runs/2026-11-20T223814Z-baseline-189`; recording `--store ~/kaijuflow-test/store --list kf-189`, titles `tools/brain/fixed-list.json`; pass all three to every run. 78 of 80 plays; the only fail The Twilight Zone S02E06 (unchecked dead season pack; fixed by #190). Report https://claude.ai/artifact/3e8rDSigAqokBbQDdhxHg3; #205's re-run report https://claude.ai/artifact/KAD1JtyC63P82rXXocnkuJ. Each run's change report goes in its run folder as `change-report.html` and is published as its own page, built on the #189 report's style.

Owner's ideas waiting for a `/grill-with-docs` (not tickets): redo the settings UI, its flow, first-time setup and the name "Ultimate Fallback". Research: `~/kaijuflow-notes/reports/KF UI design.md`, screenshots https://claude.ai/artifact/9uLC6XHL1c8nVW3jVLpr5U.

## Runs and recordings on this machine
- Everything before 2026-11-20 compared three setups and is not compared with: Test 1 (`2026-11-15T115540Z-baseline`, #153), `~/kaijuflow-notes/brain-runs/archive/`, the 2026-11-13 baseline recording.
- Pool: Test 2's 20 drawn titles stay marked used (owner: "dont redo same things").
- Speed Check page (https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD, version 8, Test 1) waits for #195.

## Owner's decisions
- 2026-11-20 (spec #183, all "yes"): the health-check pass list (ADR 0009); no fails first, then fastest cold title to video; fallback on (from #190); one fixed recording replayed every run; comparison code deleted; NzbDAV removed; other test copies stopped and kept; tuning may cut any part of the path.
- 2026-11-20 (evening): tests on Wi-Fi; no official baseline until #190 was in; one grouped run, no noise band, every run idle; merge plan PRs on green without asking (`gh pr merge` allowed in settings).
- Standard filter rules (#109), secrets outside both repos (#114, `tools/brain/backup.sh`): as before, see git history of this note.

## Gotchas
- #184's archive-parser fixes: Test 1's "stored"/"compressed" labels came from the old parsers; don't trust them. Real-archive fixtures: `tests/fixtures/archives/make.sh` (RAR 7.23 and 6.24 under `~/.local/share/rarlab`).
- AltMount's refusal reasons appear only in its log, not in the HTTP answer (500 "NZB processing failed").
- The first title after a reset (The Batman) swings between about 9 and 14 s of cold list on an idle machine; not explained (comment on #205).
- `unscramble-queue.test.ts` can fail once under load and pass on a rerun.
- A project hook (`tools/brain/guard.py`) refuses reads of the test folder's key files and the test copies' configs; `testbed.py read-settings` prints settings with secrets as `***`.
- 2026-11-15: the Newshosting login was printed into a session log by mistake; the owner was advised to change the password.

## Where things live
- Run records: `~/kaijuflow-notes/brain-runs/` and its `INDEX.md`; backed up with the recordings to the private repo `ReyesPascal/kaijuflow-notes` (`tools/brain/backup.sh`).
- Test folder (compose, configs, key files; secrets): `~/kaijuflow-test`.
- Runbook: [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md). Tools index: [tools/brain/README.md](../../../tools/brain/README.md).
- `tuning-183`'s worktree: `.claude/worktrees/tuning-183` (kept for phase 2).

## How to update
Leave whether to rebuild the image or run `testbed.py apply` to the preflight, which decides both; the note does not restate them. Every run goes in the note, a stopped one too (`tools/brain/unreported.py` lists the ones it misses).
Keep "Next command" right: whenever the next step needs the owner to type something, write it there.
Update this note after every run or merge. Keep issue lists out of it: the tracker holds them. A gotcha that needs work goes on its ticket; this note keeps only a pointer.
