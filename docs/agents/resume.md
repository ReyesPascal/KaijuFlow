# Resuming a session

Run from the repo root, in order. The `/kf` skill brings you here; a session started in the repo follows the same steps.

1. `git status --short --branch`, then `git fetch origin`; also `git -C ~/kaijuflow-notes pull --ff-only`, where the handoff note lives.
2. Pull only when it is safe: on `main` with a clean tree, `git pull --ff-only`. On any other branch, or with uncommitted changes, leave the branch as it is and note how far `origin/main` is ahead. When the fetch or pull fails (offline, diverged), say so and carry on.
3. Read the handoff note `~/kaijuflow-notes/NEXT_SESSION.md` (after the pull, so it is the latest), then `python3 -I tools/brain/unreported.py`: the runs dated after the note's last commit. For each run it lists that the note does not name, read its `CHECK.txt` (or its `report.md` first line).
4. `git log -3 --oneline`.
5. `python3 -I tools/brain/frontier.py`: the tickets that can start now, with their labels. When it fails, say so and show `gh issue list` instead. Pass on any warning it prints.

## Report

A few lines, status first:

- The branch, uncommitted changes, and what the pull brought in.
- Where work left off, from the handoff note, plus any run `unreported.py` listed that the note does not name, with its `check` verdict.
- The next step: the frontier's tickets in its order, telling `ready-for-agent` (an agent can build it) from `ready-for-human` (needs the owner), plus any frontier warning.

- **What to type next**, last, in a code block the owner can copy: the handoff note's "Next command" section, as written. It is there when the next step is a command only the owner can start (a skill hidden from agents, such as `/mattpocock-skills:implement-spec`, or a `! ` command). When the section is empty or missing, say what to type for the first frontier ticket, or leave the line out if nothing waits on the owner.

Then start on the task the user gave; without one, stop after the report.

## Fresh session

At a **stopping point** this session hands the work to a fresh one, so the owner never types `/clear`, `/kf` or Enter (owner, 2026-11-23: "i want it to give me logical places it clears and starts a new session automatically"; "i dont want to have to type or hit enter"). The written records (handoff note, ticket comments, run folders) carry everything the next step needs, and a fresh session reloads in about 30–40k tokens, where a long one re-sends its whole history every turn.

**Stopping points:**
- a timed run is checked, backed up, reported, and its result is on its ticket (#218, #219, each halving run);
- a PR merges and its ticket closes, outside a parallel build;
- a `/retro`'s fixes are merged.

**Never at:** the middle of a run or a record; a question to the owner or a `kf-alert` still open; a parallel build (`implement-spec`), whose watcher and merges live in that session; between grilling, `/to-spec` and `/to-tickets`.

**The step:** update the handoff note's "Next command", commit it and push `~/kaijuflow-notes` (straight to its `main`: no branch, PR or CI), then run `~/.local/bin/kf-next "<task>"`, where `<task>` is the words after `/kf` in "Next command" (for example `phase 2 of #183`). The task starts on its own only when a plan already gives the go for it (#183's phase 2 standing go). When the next step needs the owner instead, do not hand off: stop and `kf-alert` them. `kf-next` refuses uncommitted changes in the repo or a note not pushed to kaijuflow-notes' `origin/main`; it opens the new session in a pane beside this one, checks its turn started, and closes this pane 20 s later. On a refusal or a failed start, this pane stays: say why in one line and stop.
