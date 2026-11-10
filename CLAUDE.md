# KaijuFlow

## Agent skills

### Where things stand

Read first when resuming: handoff note `docs/kaijuflow/audit/NEXT_SESSION.md`. Before any timed run: runbook `tools/brain/RUNBOOK.md`.

### Issue tracker

Issues are tracked in this repo's GitHub Issues (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default labels: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Code map

Component map: `docs/kaijuflow/A3_STATIC_ARCHITECTURE.md` (read the Backend slot row before touching stream preparation). Local test commands: `package.json` scripts; gotchas (commit first, memory caps, byte checks) in `docs/agents/testing.md`.

### Review standards

Three written rules for reviewing tests and shared setup: `docs/agents/review-standards.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
