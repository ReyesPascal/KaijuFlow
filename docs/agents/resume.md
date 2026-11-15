# Resuming a session

Run from the repo root, in order. The `/kf` skill brings you here; a session started in the repo follows the same steps.

1. `git status --short --branch`, then `git fetch origin`.
2. Pull only when it is safe: on `main` with a clean tree, `git pull --ff-only`. On any other branch, or with uncommitted changes, leave the branch as it is and note how far `origin/main` is ahead. When the fetch or pull fails (offline, diverged), say so and carry on.
3. Read the handoff note `docs/kaijuflow/audit/NEXT_SESSION.md` (after the pull, so it is the latest).
4. `git log -3 --oneline`.
5. `python3 -I tools/brain/frontier.py`: the tickets that can start now, with their labels. When it fails, say so and show `gh issue list` instead. Pass on any warning it prints.

## Report

A few lines, status first:

- The branch, uncommitted changes, and what the pull brought in.
- Where work left off, from the handoff note.
- The next step: the frontier's tickets in its order, telling `ready-for-agent` (an agent can build it) from `ready-for-human` (needs the owner), plus any frontier warning.

Then start on the task the user gave; without one, stop after the report.
