# Resuming a session

Run from the repo root, in order. The `/kf` skill brings you here; a session started in the repo follows the same steps.

1. `git status --short --branch`, then `git fetch origin`.
2. Pull only when it is safe: on `main` with a clean tree, `git pull --ff-only`. On any other branch, or with uncommitted changes, leave the branch as it is and note how far `origin/main` is ahead. When the fetch or pull fails (offline, diverged), say so and carry on.
3. Read the handoff note `docs/kaijuflow/audit/NEXT_SESSION.md` (after the pull, so it is the latest), then `python3 -I tools/brain/unreported.py`: the runs dated after the note's last commit. For each run it lists that the note does not name, read its `CHECK.txt` (or its `report.md` first line).
4. `git log -3 --oneline`.
5. `python3 -I tools/brain/frontier.py`: the tickets that can start now, with their labels. When it fails, say so and show `gh issue list` instead. Pass on any warning it prints.

## Report

A few lines, status first:

- The branch, uncommitted changes, and what the pull brought in.
- Where work left off, from the handoff note, plus any run `unreported.py` listed that the note does not name, with its `check` verdict.
- The next step: the frontier's tickets in its order, telling `ready-for-agent` (an agent can build it) from `ready-for-human` (needs the owner), plus any frontier warning.

- **What to type next**, last, in a code block the owner can copy: the handoff note's "Next command" section, as written. It is there when the next step is a command only the owner can start (a skill hidden from agents, such as `/mattpocock-skills:implement-spec`, or a `! ` command). When the section is empty or missing, say what to type for the first frontier ticket, or leave the line out if nothing waits on the owner.

Then start on the task the user gave; without one, stop after the report.
