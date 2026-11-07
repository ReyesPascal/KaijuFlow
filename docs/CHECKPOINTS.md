# Checkpoint register — KaijuFlow

Updated: 2026-11-07. Each checkpoint must have evidence, a GitHub commit SHA, reproducible validation, and reversal instructions. Statuses: `verified`, `in-progress`, `pending`, `blocked`.

| ID | State | Evidence | Next acceptance gate |
| --- | --- | --- | --- |
| A1-repos-upstream | verified | Both private repos exist, only initial LICENSE commits; upstream `v1.4.1` points to `499efbdeb631b1b059f8aa70d07c12beaf504876`; tagged packages versioned 1.4.1; both MIT notices identified | Verify new planning docs are present |
| A2-source-import | pending | Import procedure in `docs/PHASE_A_BASELINE.md` | Isolated exact-source import committed on development branch, upstream license retained |
| A3-static-audit | in-progress | `docs/PHASE_A_BASELINE.md` records initial code inspection and known TLS validation issue | Inventory full tree, mappings, tests, dependencies and sensitive paths |
| A4-baseline-tests | pending | Regression contract in `docs/PHASE_A_BASELINE.md` | Isolated build and regression run with validated metrics and rollback |
| B1/B2, C1/C2, D1/D2, E1, F1/F2/F3 | pending | `docs/ROADMAP.md` | Open only after corresponding phase gate |

## Current source and rollback anchors
- Main repo initial pre-import commit: `1cd3932a9ae6d0a5a2fe53d8834637bc1f822cd0`. Its `LICENSE` is the existing ReyesPascal MIT notice.
- KaijuNNTP initial commit: `16a308411569602a9ffea055e824296f6607f033`.
- Upstream source commit: `499efbdeb631b1b059f8aa70d07c12beaf504876`.
- Documentation checkpoint already pushed through `docs/ROADMAP.md` commit `44e8e465ced031c247f3c6bf218dd581e1f8e387`; later documentation commits do not supersede the preserved initial anchor.
- Brain deployment: **not accessed or changed**. Git rollback: revert documentation commits or reset a separate development branch to the initial anchor. Do not reset shared `main` without coordination.

## Handoff rule
Update `HANDOFF.md` and this register after each milestone. Never mark source import, tests or deployment as completed based solely on planning.
