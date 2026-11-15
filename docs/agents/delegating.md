# Delegating to subagents

- **Three at a time.** Run at most three subagents in parallel. More than that used up the usage limit mid-build on 2026-11-15 and stopped all work for hours.
- **Budget in the brief.** State the time budget and the quality bar ("workable" or "finished") in the first brief. A deadline sent after launch yields half-read sources and a second round.
- **Save as you go.** Tell each subagent to write its output file early and keep adding to it, to a durable folder (`~/kaijuflow-notes/` for off-repo work), never only to a temporary one.

## Parallel builders

When several agents build tickets at once (a spec run with a workflow):

- **One worktree, one branch, one PR per ticket.** Each agent runs with `isolation: "worktree"` and claims its ticket before its first edit.
- **Model and effort per agent** come from the spec's table, passed in each agent's options. With no table, the agent inherits the session's.
- **One file, one agent at a time.** Two tickets that edit the same code file don't run together; the second starts from a `main` that has the first, or rebases onto it.
- **Rebase before merging** onto `origin/main`. `GLOSSARY.md` conflicts are expected when tickets add entries: keep every entry.
- **No Brain checks.** Builders don't touch the test containers or the real indexers (`brainrun record/run/preflight`, `testbed.py`): every Brain check needs the owner's go (`tools/brain/RUNBOOK.md`).
- **Merge on green CI**, then close the ticket with its done comment.
