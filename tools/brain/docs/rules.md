# Rules

This file is the one home of every standing rule for KaijuFlow's work: how checks run and are judged, the test setup, building, the tracker, secrets and sessions. Every rule is a heading (its name), one sentence, then **Why** (the owner's words with the date, or the incident and its ticket) and **Enforced by** (a tool or test, or "by hand"). History is in git and the tickets; how the code does it is in its docstrings. Other docs give the steps and link a rule here by its name; they do not restate it.

Rules name no indexer: which indexers are switched on, and their daily limits, are the key file's (`python3 -I tools/brain/testbed.py indexer list`). The rules of the replayed Recording, retired by ADR 0010, are archived in [archive/rules-retired.md](../archive/rules-retired.md). Words are defined in [GLOSSARY.md](../../../GLOSSARY.md), "Measuring". Back to the [runbook](../RUNBOOK.md) or the [index](../README.md).

## Machine and power

### Suites take turns

Test suites hold the suite lock (`flock ~/.local/share/kf-run/suite.lock`) so they wait for each other, and no builder works while a full check plays.

- **Why:** #279's and #286's build plans (parallel builders' suites and builds load the machine a check measures on).
- **Enforced by:** `flock` on the lock (`~/.local/share/kf-run/implementer-brief.md` gives it); no builder by hand.

### The test image holds the commit's code

The `kaijuflow:test` image is built from the repository's clean commit and rebuilt only when a build input changed, so a drill-down whose fix is in the image rebuilds first.

- **Why:** a docs-only commit should not force a rebuild (#113); an image from a dirty tree cannot name the code that ran.
- **Enforced by:** `brainrun.preflight` check 1 (`image_state`, `BUILD_INPUTS`, held in line with the `Dockerfile` by `test_preflight.py`); `--rebuild-image` and `--fix` rebuild.

### Connection caps

KaijuFlow's health-check cap plus its AltMount's 25 connections stay at or under the provider's limit of 100.

- **Why:** the Newshosting plan (owner, 2026-11-09, `testbed.PROVIDER_LIMIT`); 25 is the 2026-11-13 baseline's setting.
- **Enforced by:** `brainrun.preflight` check 4 (the sum); AltMount's 25 by hand (`expected-settings.json` names no AltMount setting).

## Indexers and allowance

### Indexers change only through the indexer command

An indexer is added, switched on or off, or removed in the test setup only with `testbed.py indexer add|on|off|remove` (agents may run it, the test copies stopped), the default key file is the only one used (never `--key-file`), and the test copy of AltMount has no indexers switched on.

- **Why:** adding the second indexer took four hand edits agents were blocked from (owner, 2026-11-24, when the second indexer was switched on; spec #298); KaijuFlow searches and AltMount only streams (#302).
- **Enforced by:** `testbed.py indexer` (`test_testbed_indexer.py`); `brainrun.preflight` check 2 (key file mode and switches; `--fix` switches KaijuFlow to match); `--key-file` by hand.

### Every indexer request goes through the stand-in, untouched

Every indexer address in KaijuFlow's test copy is the stand-in's, and the stand-in, on the check's own empty store, passes each answer on as the indexer sent it, so KaijuFlow's own filters choose.

- **Why:** no test may reach a real indexer around the cap rule and the allowance, and a check plays as at home (#185, ADR 0010).
- **Enforced by:** `brainrun.preflight` checks 3 and 6 (`testbed.standin_slug`, port 1340 free); `indexer_standin.py` (`test_indexer_standin.py`).

### The allowance

The preflight refuses a check unless every switched-on indexer has the check's searches left today (12 per title, plus one for its preflight search) and together they have its downloads (30 per title), counted against the daily limits in the key file.

- **Why:** every title is searched on every indexer, while the Walk's 30 grabs are shared, taken from whichever indexer has the Source (owner's pick on #286, 2026-11-24, when an indexer with 100 downloads a day joined one with 450).
- **Enforced by:** `brainrun.preflight` check 11 (`allowance.left`, `quickcheck.NEED_PER_TITLE`; `test_allowance.py`, `test_preflight.py`); `brainrun.py usage` shows Used, Limit and Left.

## The preflight

### Every refusal names its fix

The preflight says each problem in one plain sentence that names the command or step that fixes it, and `--fix` runs only the safe fixes (the image rebuilt, the expected settings written, the key file made private, an indexer switched to match the key file), never power, the machine's addresses, DNS, the allowance or an indexer's key.

- **Why:** "a refusal is one step from fixed", and a check should start without rounds of refusals, while power, addresses, DNS and the allowance stay the owner's (spec #298 stories 10–12, #303).
- **Enforced by:** `brainrun.Problem`, `brainrun.checked` (`FIX_ROUNDS`; `test_preflight_fix.py`).

### Every switched-on indexer answers before titles are drawn

A check starts only when every switched-on indexer answers one one-result search, sent by the test tools only and counted as one search.

- **Why:** a wrong key, an expired account or a down indexer is caught before titles are drawn, without slowing real use (spec #298 stories 15–16, #303); a search, since indexers answer a caps request without a key (owner, 2026-11-27, the review of #298).
- **Enforced by:** `brainrun.preflight` check 12 (`ping_search`, `preflight-searches.log`; `test_search_ping.py`).

## Test copies and settings

### A test copy changes only through the tools

A test copy is never edited by hand: its expected settings go in with `testbed.py apply <copy>` or the preflight's `--fix`, its indexers with `testbed.py indexer`, the standard changes in the file and the copy together, and the preflight decides whether to rebuild or apply.

- **Why:** the tools back the config up and print each change, never a secret (#109, #302, #303).
- **Enforced by:** `testbed.py apply` (`test_apply_settings.py`), `testbed.py indexer`, `brainrun.checked` (`--fix`).

### One reset per check

A check resets the two test copies once, after drawing its titles and before its first play.

- **Why:** each title is new, so each play is cold (#268).
- **Enforced by:** `brainrun.quick_check_all`, `brainrun.drill_all` (`test_quickcheck.py`, `test_drill.py`).

## Checks and verdicts

### When to check, and who says go

A quick check runs after any change to playing, health checks or search before it merges, and a full check (once #271 builds it) before work is called done, after an indexer is added or when the owner asks; quick checks and drill-downs have a standing go, a full check needs the owner's go each time or a standing go that names it (`--standing-go`), and any other live step needs the owner's go.

- **Why:** ADR 0010 (owner, 2026-11-24); the owner's "yes" to the standing go (#268); a check spends real indexer requests.
- **Enforced by:** by hand (`--full` is refused until #271).

### New titles every time

Every check draws new titles from TMDB by kind, never by hand and never from a fixed pool, skips every title in the ledger and writes them to it before they are played.

- **Why:** "they wont be doing tests over and over and playing the same file over and over" (owner, 2026-11-24, ADR 0010).
- **Enforced by:** `draw.py titles` (`test_draw.py`).

### How a title is played

A quick check plays 5 titles (2 popular films, 1 rare or older film, 1 popular episode, 1 rare or older episode), each by asking for its list, waiting the fixed 5 s Browse pause, pressing Best once and waiting at most 300 s for video, and title to video leaves the pause out.

- **Why:** ADR 0010: "one cold play per title"; the pause stands for a viewer reading the page (owner, 2026-11-20, #205: "yes to all").
- **Enforced by:** `quickcheck.QUICK_KINDS`, `PLAY_TIMEOUT_S`; `brainrun.BROWSE_PAUSE_S`, `check_visit_answer` (`test_quickcheck.py`).

### What is a fail

A title fails when no video came while some Source passed, was tried or was left unchecked, when no list or no Best entry came, when the video is the wrong title or episode or its release is not named, and a new allowed word joins the match only once a release a check played shows it, through review, in both copies of the rule and the shared table.

- **Why:** "a fail is a fail" (owner, 2026-11-24); a wrong title tests KaijuFlow's name search, Kaiju Search (ADR 0010, #285).
- **Enforced by:** `quickcheck.judge`, `right_title`, `FILM_TAGS`, `SHOW_TAGS`, `odd_word` (`test_quickcheck.py`, the shared table `tests/fixtures/release-names/table.tsv`); allowed words by review.

### What is reported but is not a fail

A slow play (right video after 60 s), a check miss, a fallback and nothing to play (every Source checked said no, or every switched-on indexer down) are reported and never fail a title, a title one indexer missed is judged on the list the others gave, and no extra test second-guesses a Source's reason.

- **Why:** "a slow play is not a fail intnernallty but externally to a user it is a given up" (owner, 2026-11-24); "really no Source" is shown, not assumed (#268 story 13); one indexer's outage is not blamed on a title that had Sources (spec #298, #304).
- **Enforced by:** `quickcheck.judge`, `_empty_list`, `SLOW_PLAY_S` (`test_quickcheck.py`).

### The verdict and the report

A check passes on zero fails, one stopped by the cap rule, by hand or by a failure has no verdict, and its `report.md` gives verdict and fails first, then totals and the indexer table, with no per-title table and no comparison with an earlier check.

- **Why:** "the top prioirty is zero failed plays because thats the whole point of the health checking systems" (owner, 2026-11-24); titles differ from check to check, so speed differences are noise (ADR 0010).
- **Enforced by:** `quickcheck.verdict`, `render_report`; `brainrun.quick_check_command` (exit codes; `test_quickcheck.py`).

### After a check

After a check, its ticket texts are filed (one per fail and per check miss), `diagnosis.py record <folder>` runs in a worktree and its Casebook changes are committed, `tools/brain/backup.sh` backs it up and the handoff note names it, while fix tickets Diagnosis files during a build wait for the owner.

- **Why:** "Every fail becomes a ticket naming the title" (ADR 0010); the check itself leaves the repo clean; #279's "Building it" keeps fix tickets for the owner under #183.
- **Enforced by:** `quickcheck.ticket_texts`; Diagnosis files a proved KaijuFlow cause's ticket itself (`fixing.py`, `--tickets-dry-run`); `unreported.py` lists checks the note misses; the rest by hand.

### A fix is proved by a drill-down

A fix is proved by `brainrun.py drill` on that one title, live, once the fix is merged, which marks each suspected cause proved fixed (no failure at all), reopened (any failure) or not marked.

- **Why:** "Its fix is proven by drilling down on that title alone, played again live, not by a new full check" (ADR 0010); a fix that moves the problem does not count.
- **Enforced by:** `brainrun.drill_all`, `drill.py`, `diagnosis.py` (`test_drill.py`).

### Diagnosis keeps its records only through its tools

`casebook/index.json` is never edited by hand, an entry claims proved only with a confirming recipe whose Clues all exist, and the diagnosing agent works a Case log only through `diagnosis.py case` commands.

- **Why:** a claim of proof must rest on a test that runs (#281, #287).
- **Enforced by:** `casebook.py check` (`test_casebook.py` checks the repo's Casebook); `caselog.py` (`test_caselog.py`).

### Live Clues only read

Live Clues read Usenet over one read-only connection (STAT, BODY checked in memory) and save nothing but their answers.

- **Why:** #279's standing go covers "any live read-only Clues" (#284).
- **Enforced by:** `nntp.Usenet`, `clues.py`.

### What AltMount streams changes only on evidence

The health check's pass list changes only when a check or a drill-down shows AltMount streaming or refusing a kind, and an unproven kind (RAR4 set, encrypted archive with password, ZIP) is probed on the AltMount test copy only when titles fail for lack of a playable Source.

- **Why:** "proven only" (owner, 2026-11-20, ADR 0009).
- **Enforced by:** no tool; by hand.

### Retired commands stay retired

A command of the replayed Recording, archived by #273, runs only when the owner asks for it, with `--revive`, and old run folders stay in the archive.

- **Why:** "ARCHIVE THE OLD STUFF AND STOP IT FROM COMING BACK UNLESS WE TELL IT TO" (owner, 2026-11-24, spec #298); ADR 0010 retired the path.
- **Enforced by:** `retired.gate` (exit 5); `test_live_docs.py` fails when a live doc describes a retired command again.

## Building and reviewing

### The test commands

Briefs and merge checks run `npm run check` (CI's command) and then `npm run test:integration`, one suite at a time while working and the full run before DONE.

- **Why:** plain `tsc` skips the test files; CI runs `npm run check`.
- **Enforced by:** CI (`npm run check` in `.github/workflows/ci.yml`).

### The test runners' conditions

Integration and A4 runs test committed code with `src/` left alone while they go, each scenario under 4G and parallel suites each in their own 6G scope.

- **Why:** the runners test `dist/` built from committed code, and parallel agents' suites need their own memory cap ([testing.md](../../../docs/agents/testing.md)).
- **Enforced by:** `tests/integration/run-ci.sh` (STALE-DIST, SOURCE HASHES CHANGED), `in-namespace.sh` (4G); the 6G scope by hand.

### Bytes are compared with assertBytes

Tests compare bytes with `assertBytes` (`tests/integration/parity/bytes.mjs`), never `deepEqual`.

- **Why:** `deepEqual`'s mismatch diff over bytes can take tens of GB.
- **Enforced by:** `tests/unit/byte-compare-guard.test.ts`.

### A test reaches the caller

A test goes through the code that uses the change, not just the new helper.

- **Why:** #131's test passed while the coordinator never used the value (2026-11-15; review-standards.md).
- **Enforced by:** by hand (review).

### Words and ADRs

Output uses the GLOSSARY's terms, and a contradiction of an ADR is said out loud, never made silently.

- **Why:** [domain.md](../../../docs/agents/domain.md), the domain-docs skill's rule.
- **Enforced by:** no tool; by hand.

## The tracker and git

### Ticket first, order in the tracker

Work gets a ticket before it starts, as a sub-issue of the map (#183) with its order as native blocked-by links, never a list in the body, and a claimed ticket is assigned as the session's first write.

- **Why:** an order agreed only in chat is lost, and `frontier.py` reads only the tracker.
- **Enforced by:** `frontier.py` (warns on a "Blocked by" body; `test_frontier.py`).

### One home per rule

A rule is written only in this file, as one sentence, why and enforced by, and every other doc (the runbook, the handoff note, GLOSSARY.md, the ADRs) links it by name.

- **Why:** the 2026-11-24 audit found most rules in three to five places, and one gone stale made an agent ask the owner for a step ADR 0010 had retired (spec #298 stories 42–45).
- **Enforced by:** the rules check (`rulescheck.py`, `test_rules_check.py`: every rule names its enforcer, a tool or test as code or "by hand"; no rule or runbook line names an indexer or a retired command); `/srule` writes a new rule here (#310).

### Check before claiming

Before a behaviour change goes into a ticket or to the owner, it is checked in the code that uses the value, not just the line that sets it.

- **Why:** written in [issue-tracker.md](../../../docs/agents/issue-tracker.md) without its incident.
- **Enforced by:** no tool; by hand.

### Every pushed PR is watched, and plan PRs merge on green

Right after a push `prwatch.py <n>` runs in the background, and on GREEN a PR the plan names is merged at once (`gh pr merge <n> --merge`) and the owner told in one line, on RED fixed or reported.

- **Why:** "make sure it knows when things are ready to merge i had to ask" (owner, 2026-11-23); "dont even wait for me to say go to merge just do it if green and part of plan" (owner, 2026-11-20).
- **Enforced by:** `prwatch.py` (`test_prwatch.py`).

### Merging into an integration branch

A build merges each ticket's branch into its integration branch (one draft PR to main closing all its tickets) in a merge worktree with `git merge --no-ff`, runs `npm run check:brain` under the suite lock, pushes after every merge and comments "merged into `<branch>` at <sha>" on the ticket.

- **Why:** saving as it goes lets a stopped session resume from the branch, the ticket comments and the note (#279).
- **Enforced by:** no tool; by hand.

### Close when done

A ticket is closed in the session its work is done, with a done comment, and a parent whose last sub-issue closes is closed in the same session with a summary.

- **Why:** written in issue-tracker.md without its incident; an open ticket whose work is done stays on the frontier (`frontier.py`).
- **Enforced by:** by hand (a PR's closing keywords).

### The gh calls that work here

On gh 2.46 `gh issue view` takes `--json` (never `--comments`), PR checks are read with `prwatch.py`, a PR body is edited with `gh api -X PATCH`, and sub-issues and blockers are set with `gh api`.

- **Why:** those calls fail here, and a session called one although the doc warned against it (#161, the 2026-11-15 retro).
- **Enforced by:** `guard._gh` (`test_guard.py`).

## Secrets and the guard

### The guard

Nothing shows the test folder's key files or a test copy's config, settings are read with `testbed.py read-settings` (secrets as `***`), AltMount's failed NZBs are the one exception (#280), and the guard is a guardrail, not a sandbox.

- **Why:** the key files hold the indexer keys and the provider login.
- **Enforced by:** `tools/brain/guard.py`, run by `.claude/settings.json` on Bash, Read and Grep (`failed_nzb`; `test_guard.py`).

### Secrets stay out of both repos

Keys and logins live only in `~/kaijuflow-test` and the owner's password manager, never in the KaijuFlow or notes repo, `expected-settings.json` or a tool's output.

- **Why:** the check folders are pushed to GitHub (#114).
- **Enforced by:** `backup.sh` (refuses to push a key value); `brainrun.load_expected_settings` (refuses a secret name); `indexer_standin.py` (stores no key); `testbed.read_settings`, `brainrun.read_pinned`.

### Downloads are untrusted

Downloads and extracted archives go in their own folder and are read as untrusted data.

- **Why:** #279's standing go covers tools and research only on those terms.
- **Enforced by:** no tool; by hand.

## Sessions and handoffs

### Resuming a session

A session starts with the steps of [resume.md](../../../docs/agents/resume.md) and ends its first report with what to type next.

- **Why:** [resume.md](../../../docs/agents/resume.md): the written records carry the work from one session to the next.
- **Enforced by:** by hand (the `/kf` skill brings the session there).

### The handoff note holds state only

`~/kaijuflow-notes/NEXT_SESSION.md` is the one state note, replaced not appended, holding only the current state (no rules, no issue lists), and pushed straight to the notes repo's `main` after every check and merge, stopped checks too.

- **Why:** #117; a note pushed after every merge lets a stopped session resume (#279); rules kept in the note went stale beside this file (spec #298 story 45).
- **Enforced by:** `unreported.py` (checks the note misses); `kf-next` refuses a note not pushed.

### Fresh sessions at stopping points

At a stopping point the session updates "Next command", pushes the note and runs `kf-next "<task>"`, never mid-check, mid-merge, with a question or alert open or in a parallel build whose plan does not say so, and when the next step needs the owner it stops and `kf-alert`s instead.

- **Why:** "i want it to give me logical places it clears and starts a new session automatically"; "i dont want to have to type or hit enter" (owner, 2026-11-23).
- **Enforced by:** `~/.local/bin/kf-next` (refuses uncommitted changes or an unpushed note).

### Alerts and questions

Every stop-and-ask raises `~/.local/bin/kf-alert "<what to type next>"`, and a question goes through AskUserQuestion plus `kf-ask "<question>"`, cleared with `kf-ask clear` once answered.

- **Why:** the owner may be away from the screen (#183: a blocked pane is answered, otherwise `kf-alert`).
- **Enforced by:** no tool; by hand.
