# Handoff: where KaijuFlow stands (2026-11-23, #239 built; review round 2 closing; the owner ran low on usage)

This is the one state note. Replace it; do not append. Older versions are in git history.
Terms: [GLOSSARY.md](../../../GLOSSARY.md). Decisions: [docs/adr](../../adr/).

**Rules:** [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md), "Rules" (detail in [tools/brain/docs/rules.md](../../../tools/brain/docs/rules.md)). This note holds state only.

## Goal
KaijuFlow with AltMount as its one Backend, as fast and lean as possible; KaijuFlow does the health check, archives AltMount can stream allowed; no more speed tests against Usenet Ultimate or AltMount direct (owner, 2026-11-20; spec #183, the map). Owner's words: "I just want altmount to be the fast backend and want KF to do the healthcheck, even if its RARS, find a way to make them work together as fast as possible forget speed testing against the rest"; "i want it to be as fast and lean as possible". ADR 0009 replaces ADR 0008.

## Next command
**The owner types**, in a fresh herdr pane once usage is back:

    start

## #239 build: where it stopped (2026-11-23, ~17:00)
- **Built:** all 10 tickets merged into `deepen-239` (draft PR #252, CI green at bd2d695), plus round 1's review fix-up (9 commits, Opus high; merged at bd2d695). #255 filed for later (a clicked entry's walk-on).
- **Round 2 review** (owner's design, all on #239's comments: six Fable agents, a lead, a scope-watcher with the final word): its fix plan is `~/kaijuflow-notes/reviews/239/round-2/fix-plan.md`; done when `round-2/COMPLETE` exists. Debate log `round-2/debate.log`, rulings `round-2/rulings.md`.
- **Sealed measurement:** `~/.local/share/kf-review-239-sealed/plan.md`. Round 2 reviewed `review-target-239` (local), which holds three planted bugs (walk.ts:211 `>`, ultimateFallback.ts:446 signal, playTimeCheck.ts:62 guard). Their fixes are NOT applied to `deepen-239` (it never had them). Codex controls' results are in the same folder: verify its four real findings against the fix plan and add any the plan lacks.
- **Restart here (owner, 2026-11-23: "do it in a way it can just use up all the usage and be restarted"):** `~/kaijuflow-notes/reviews/239/round-2/fix-status.md` holds every fix job and its state; do the first row not `merged` or `dropped`, and update it and push kaijuflow-notes after each change. The owner may just type "start".
- **Next steps, in order:** (1) if `COMPLETE` is missing, read the debate and let r2watch finish, or close the round; (2) the fix round: Opus high agents (owner, 2026-11-23: no Fable in the restart), as many jobs as the plan has (up to 5 at once), each in its own files, on `deepen-239`, plants dropped; merge one by one with build, unit, both type-checks, check:brain and `npm run test:integration`; (3) mark PR #252 ready once green; (4) `kf-alert "type /retro"`; the owner types `/mattpocock-skills:retro the #239 build: follow ~/kaijuflow-notes/reviews/239/retro-brief.md` (add round 2's and the fix agents' log paths to that brief first); (5) the review report as an Artifact (`reviews/239/report-design.md`, reviews only, plus the whole-app code comparison main vs final deepen-239); (6) #249, then #250, under the owner's standing go for live tests.
- **Clean-up when done:** worktrees under `.claude/worktrees/` (r2-*, review-target-239, review-fixup-239, the ticket ones), herdr panes in the `agents` and `debate` tabs.

## Deepening spec #239 (grilled 2026-11-23, owner: "yes to all")
- **Tickets** (`python3 -I tools/brain/frontier.py 239`): play path #228 (Walk module, replace once, 30 grabs) → #243 (grabs by ADR 0004 kind), #244 (Walk ends on the next list request) → #246 (play context) → #247 (Source memory) → #248 (delivery, keep-alive); #245 (Unscramble cap and read-error retry) after #228. Tools: #240 (stand-in 503 for a miss), #241 (runs module, one Previous run) → #242 (step lines). Then #249 (warm-list diagnosis, replay) and #250 (closing grouped run against #219's run; not kept → split Walk changes | the rest, then halve).
- **Facts found in the grilling:** #228's walk runs away *before* the play, while a fallback prepares (a failed grab pulls twice); the walk's grab forgets a 404; #219's new fallbacks were Unscramble read-errors (then an upload AltMount rejects), not AltMount; the warm-list path does no new work (the same step got slower: whole process, not proven); old runs are read from `raw.json`, so step lines don't break them. Detail in #239 and the tickets.
- **Written:** GLOSSARY (**Walk** new; Best entry, Head start, Unscramble, Delivery method), ADR 0004 "The walk's grabs", ADR 0005 amended 2026-11-23.

**Alerts:** `~/.local/bin/kf-alert "<what to type next>"` (voice "azelma", repeats until the notification is closed) at every stop-and-ask. Questions: AskUserQuestion plus `~/.local/bin/kf-ask "<question>"`, `kf-ask clear` once answered.

## How KaijuFlow is doing (2026-11-23)
- **Plays reliably.** Every run today played every title (80 of 80 the first try); The Twilight Zone S02E06, the 2026-11-20 fail, is fixed by #190.
- **Faster cold, slower warm (#219, kept).** Cold title to video 4.90 s (easy) and 6.07 s (hard), was 8.98 and 9.10 s: the Head start (#206) checks during the Browse pause, so press-to-video halved. Warm 1.59 s and 0.47 s, was 0.81 and 0.24 s: the list request itself got 0.7–2 s slower on some movies, cause not proven. 80 of 80 played; 4 fallbacks (was 2).
- **Known bugs, confirmed in the code, ticketed under #239:** the Walk's double pull (#228); a ready Source never found again for any dated episode (#247); a press without a Head start builds a different episode pattern (#246). Each ticket starts with a test that fails on it.
- **Code health:** the play path's two ~720-line functions and the tools' four "previous run" rules are #239's subject. Report: `~/kaijuflow-notes/reports/architecture-review-2026-11-23.html`.

## Phase 2 (2026-11-23, done)
- **#219 grouped run: kept** (`~/kaijuflow-notes/brain-runs/2026-11-23T190950Z-grouped-219`, report https://claude.ai/artifact/JrjmPAYSWhP4FCSvjShKCL, result comment on #219). `tuning-183` at 9fb31a2 (main merged in first), image rebuilt, `whenToResolve` set to `on-results` with `testbed.py apply` (the Head start's expected setting). No halving runs. PR #225 merged (a812bfe); #191, #192, #193, #203, #206, #211, #226, #219 closed. Findings, none proven to a cause: warm lists slower (Super Mario warm 2 list 0.99 → 2.96 s); two new fallbacks, both AltMount failing an import ("First segment has no data", missing RAR volume) of a release that played in the other cold round; a check of Night Moves ran on into Upstream Color's list and play (a Head start's work is not stopped when the next title is asked for); #228's walk grabbed 353 unplayed releases (318 in Joker cold 2). The next run's previous run is this one.
- **#218 baseline, first try, not usable** (`~/kaijuflow-notes/brain-runs/2026-11-23T173423Z-baseline-218`): 80 of 80 played, but 1840 NZB grabs from the fallback (on since #190) missed `kf-189`, which was recorded with the fallback off. A stopped attempt of 2026-11-21 (`2026-11-21T050927Z-baseline-218-wifi`, 13 plays) had already missed 863. Owner's decision on #218: "Top up, then re-run".
- **Top-up record** (`2026-11-23T175655Z-kf-189-topup-218-record`): 11 new NZBs (11 of the day's 450 downloads), proof replay with no miss.
- **#218 baseline, re-run: the official baseline** (`~/kaijuflow-notes/brain-runs/2026-11-23T183239Z-baseline-218`, report https://claude.ai/artifact/VETGxZQya2LVNsi5F54ppi): 80 of 80 played, no fails; cold title to video easy 8.98 s, hard 9.10 s; warm 0.81 s and 0.24 s; The Witcher S01E01 played after 1 fallback in both cold rounds (AltMount refused its top pick). Its walk grabbed 81 releases the recording doesn't hold, none played. Owner's decision on #218, "Ignore unplayed misses" (#235, PR #236): such grabs are listed and don't count, so `check` says usable (`CHECK.txt` rewritten; the old one is `CHECK.before-235.txt`).
- **Built along the way, all on main:** #229 (preflight refuses a recording the last run missed; misses named by release; guard; `unreported.py`; the top-up rule in rules.md), #231 (`prwatch.py`: says once when a PR is ready to merge; guard refuses `gh pr checks --json`), #233 (Fresh session: `kf-next` hands off at stopping points). #228 filed.
- **Phase 1** (2026-11-20, `implement-spec #183` in herdr): #217 preflight and #190 Play-time check on main; #193, #211, #203, #192, #226, #206, #191 on `tuning-183`, PR #225 (reviewed, fixed; merged after #219). Owner's decisions then: #206 split into #206 + #226 (in a halving run #226 goes with #206); the 25 s first-Source switch stays (comment on #192).

## The machine
- Machine `brain` (user `brain`) since 2026-11-12; everything only on the old machine is gone.
- Test containers: the brain tools know only `kaijuflow-test` and `altmount-kf-test`; `uu-test`, `nzbdav-test`, `altmount-addon-test` are to be stopped and kept (a live step, owner's go). No live stack here.
- **Tests run on Wi-Fi** (192.168.4.48), owner's decision of 2026-11-20; the preflight checks `HOST_IP` and `altmountUrl`. The ethernet runs (#189, #205 re-run) are never compared with.
- **A timed run needs an idle machine**; the preflight enforces it. Hold `flock ~/.local/share/kf-run/suite.lock` around a run so suites wait.

## The tracker
Two maps: #239 (the deepening spec, `frontier.py 239`) and #183 (`frontier.py`; left on it: #194, owner's, AltMount settings → #195, Speed Check page).

Recording for every run: `--store ~/kaijuflow-test/store --list kf-189 --titles-file tools/brain/fixed-list.json`. Each run's change report goes in its run folder as `change-report.html` and is published as its own page in the #189 report's style (generator `~/kaijuflow-notes/reports/run-report/make_report.py`, `--before` required).

Owner's ideas waiting for a `/grill-with-docs` (not tickets): redo the settings UI, its flow, first-time setup and the name "Ultimate Fallback". Research: `~/kaijuflow-notes/reports/KF UI design.md`, screenshots https://claude.ai/artifact/9uLC6XHL1c8nVW3jVLpr5U. A working beta with an update feature (owner, 2026-11-23: "at what point will i have a working beta with update feature"; added with "yes add it"): not planned yet; what "beta" and "update feature" mean (who installs it, a notice of a new version or a one-click update of the container) is for the grilling, after #250 is kept and PR #252 is on main, and fits with the settings UI and first-time setup above. Use PostersPlus (https://github.com/elfhosted/PostersPlus, "a modern poster overlay") with KaijuFlow (owner, 2026-11-23: "is this forkable?", then "yes add it to ideas"): public, forking allowed, AGPL-3.0, while KaijuFlow is MIT, so copying its code in would bring AGPL's terms; running it as its own service beside KaijuFlow would not. Start with `/research`, then a grilling, after #250.

## Runs and recordings on this machine
- Everything before 2026-11-20 compared three setups and is not compared with: Test 1 (`2026-11-15T115540Z-baseline`, #153), `~/kaijuflow-notes/brain-runs/archive/`, the 2026-11-13 baseline recording.
- Pool: Test 2's 20 drawn titles stay marked used (owner: "dont redo same things").
- Speed Check page (https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD, version 8, Test 1) waits for #195.

## Owner's decisions
- 2026-11-20 (spec #183, all "yes"): the health-check pass list (ADR 0009); no fails first, then fastest cold title to video; fallback on (from #190); one fixed recording replayed every run; comparison code deleted; NzbDAV removed; other test copies stopped and kept; tuning may cut any part of the path.
- 2026-11-20 (evening): tests on Wi-Fi; one grouped run, no noise band, every run idle; merge plan PRs on green without asking.
- 2026-11-23: top up `kf-189` and re-run the baseline; build the retro fixes ("do everything"); `prwatch.py` ("make sure it knows when things are ready to merge"); hand off to a fresh session at stopping points with no typing ("i dont want to have to type or hit enter"); the six deepening candidates plus #228 become one new spec after #219. Grilling of the deepening spec (#239): "yes to all" on every question (Walk rules, Unscramble retry, one Previous run, closing grouped run); seams and tickets "yes"; agents always shown in herdr.
- 2026-11-23 (#239's build): standing go for any live tests ("you have my go for any live tests"), a top-up told in one line; build decisions on #239's comments.
- Standard filter rules (#109), secrets outside both repos (#114, `tools/brain/backup.sh`): see git history of this note.

## Gotchas
- `gh` is 2.46: `gh issue view` needs `--json`, `gh pr checks` has no `--json` (use `prwatch.py`); the guard refuses both and names the call that works.
- A change that makes KaijuFlow ask indexers for more needs a top-up `record` before its run (rules.md, "What a run is"); the preflight refuses a recording the last run missed.
- AltMount's refusal reasons appear only in its log, not in the HTTP answer (500 "NZB processing failed").
- The first title after a reset (The Batman) swings between about 9 and 14 s of cold list on an idle machine; not explained (comment on #205).
- `unscramble-queue.test.ts` can fail once under load and pass on a rerun.
- A project hook (`tools/brain/guard.py`) refuses reads of the test folder's key files and the test copies' configs; `testbed.py read-settings` prints settings with secrets as `***`.

## Where things live
- Run records: `~/kaijuflow-notes/brain-runs/` and its `INDEX.md`; backed up with the recordings to the private repo `ReyesPascal/kaijuflow-notes` (`tools/brain/backup.sh`).
- Test folder (compose, configs, key files; secrets): `~/kaijuflow-test`.
- Runbook: [tools/brain/RUNBOOK.md](../../../tools/brain/RUNBOOK.md). Tools index: [tools/brain/README.md](../../../tools/brain/README.md).
- Reports: `~/kaijuflow-notes/reports/` (architecture review 2026-11-23, run-report generator).

## How to update
At a stopping point the session hands off to a fresh one by itself ([resume.md](../../agents/resume.md), "Fresh session"): keep "Next command" right before it does.
Leave whether to rebuild the image or run `testbed.py apply` to the preflight, which decides both. Every run goes in the note, a stopped one too (`tools/brain/unreported.py` lists the ones it misses).
Update this note after every run or merge. Keep issue lists out of it: the tracker holds them. A gotcha that needs work goes on its ticket; this note keeps only a pointer.
