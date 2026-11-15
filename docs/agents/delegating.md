# Delegating to subagents

- **Three at a time.** Run at most three subagents in parallel. More than that used up the usage limit mid-build on 2026-11-15 and stopped all work for hours.
- **Budget in the brief.** State the time budget and the quality bar ("workable" or "finished") in the first brief. A deadline sent after launch yields half-read sources and a second round.
- **Save as you go.** Tell each subagent to write its output file early and keep adding to it, to a durable folder (`~/kaijuflow-notes/` for off-repo work), never only to a temporary one.

## Building a spec in parallel

The owner runs `/mattpocock-skills:implement-spec <spec>`: implementer agents in their own worktrees, one integration branch, one `/code-review` at the end. KaijuFlow adds these limits:

- **Three at a time**, as above.
- **Model and effort per agent** come from the spec's table. An agent with no entry inherits the session's.
- **No live checks**: nothing that touches the test containers, the indexers or Usenet (`brainrun.py record/run/preflight/smoke`, `testbed.py`, `nntp.py`). They need the owner's go (`tools/brain/RUNBOOK.md`). Tests with fakes are fine, `npm run check:brain` included.
- **Merging:** when an implementer's branch already contains the integration branch's tip, the orchestrator fast-forwards it. A merger agent is only for a real conflict, and it counts toward the three.
- **Keep every `GLOSSARY.md` entry** when merges conflict: tickets add entries side by side.
