# Checkpoint register — KaijuFlow

Updated: 2026-11-07. Each checkpoint must have evidence, a GitHub commit SHA, reproducible validation, and reversal instructions. Statuses: `verified`, `in-progress`, `pending`, `blocked`.

| ID | State | Evidence | Next acceptance gate |
| --- | --- | --- | --- |
| A1-repos-upstream | verified | Both private repos exist; upstream tag `v1.4.1` points to `499efbdeb631b1b059f8aa70d07c12beaf504876`; both MIT notices verified; complete **192 file / 12,132,917 byte manifest** recorded under `docs/upstream-v1.4.1-manifest.json` | Full app binary-safe import required for A2 |
| A2-source-import | pending | **Whole application** import contract in `docs/WHOLE_APP_CAPTURE.md`, all 192 SHA/mode entries in release manifest; direct API binary read unavailable | Complete Git clone/archive transfer in isolated development checkout, import every file including 14 binary assets, SHA-verify, license retention and secret scan, commit on separate development branch |
| A3-static-audit | in-progress | `docs/PHASE_A_BASELINE.md` records initial code inspection and known TLS validation issue; full file inventory created, **not** a full functional audit | Audit every application subsystem including indexer search, UI, NzbDAV, fallback, archive and playback; test against unchanged release |
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
