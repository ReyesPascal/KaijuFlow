# KaijuFlow

## Agent skills

### Where things stand

Resuming a session: `docs/agents/resume.md` (status, handoff note `~/kaijuflow-notes/NEXT_SESSION.md`, frontier). Before any real-use check: runbook `tools/brain/RUNBOOK.md`.

### Issue tracker

Issues are tracked in this repo's GitHub Issues (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default labels: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Code map

Component map: `docs/kaijuflow/A3_STATIC_ARCHITECTURE.md` (read the Backend slot row before touching stream preparation). Local test commands: `package.json` scripts; gotchas (commit first, memory caps, byte checks) in `docs/agents/testing.md`.

### Rules

Every standing rule is in `tools/brain/docs/rules.md`. A new standing decision of the owner's goes there with `/srule`, never in the handoff note, a memory or a ticket.

### Review standards

Four written rules for reviewing tests, shared setup and call sites, and the review a fix-up gets before it merges: `docs/agents/review-standards.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
