# KaijuFlow handoff — Phase A

Last update: 2026-11-07. Current phase: **A (in progress; planning and initial static audit)**.

## Completed and verified
- Connected GitHub user `ReyesPascal` has admin permissions; `KaijuFlow` and `KaijuNNTP` are both private and each was already initialized with a ReyesPascal MIT `LICENSE` only.
- Initial commits: KaijuFlow `1cd3932a9ae6d0a5a2fe53d8834637bc1f822cd0`; KaijuNNTP `16a308411569602a9ffea055e824296f6607f033`.
- Canonical upstream `DSmart33/Usenet-Ultimate` release tag `v1.4.1` resolves to `499efbdeb631b1b059f8aa70d07c12beaf504876`; verified MIT upstream notice differs from current KaijuFlow license.
- Remote static inspection completed of critical health-check, NNTP, fallback, cache, archive, config, UI and Docker modules; source behavior and import plan recorded in `docs/PHASE_A_BASELINE.md`.
- Roadmap and checklists documented: `docs/ROADMAP.md`, `docs/CHECKPOINTS.md`.

## Unfinished
- Source code is **NOT imported**. No source/build changes or runtime benchmark have been made. Phase A full-tree, dependency, reproducible build, test and risk audit is incomplete.
- Preserve both MIT notices; before source import, use separate `import/upstream-v1.4.1` branch and verify source tag SHA.
- KaijuNNTP implementation remains intentionally inactive pending Phase E.
- No direct Brain inspection or container change was performed; deployment rollback is simply to retain the existing unchanged working containers.

## Important finding
`src/health/nntpConnection.ts` at upstream tag sets TLS `rejectUnauthorized: false`. Record for Phase B security review, not an undocumented baseline edit.

## Exact next action
Confirm this checkpoint's GitHub documents exist and both repos remain private. In an isolated dev environment, capture and scan the complete v1.4.1 tree for secrets/licenses, then open an import-only development branch and commit the unchanged source with original upstream MIT license under `THIRD_PARTY_NOTICES/Usenet-Ultimate-LICENSE`; retain current root LICENSE. Do not touch Brain. Only after import, run baseline backend/UI builds and regression tests using synthetic fixtures.

## Verification / rollback
- Check `main` documentation and `LICENSE`; review `docs/CHECKPOINTS.md`.
- Check `git rev-parse v1.4.1^{commit}` against `499efbdeb631b1b059f8aa70d07c12beaf504876` in an isolated upstream clone.
- Return the *future* development import branch to the recorded pre-import commit if an import fails. Never force-push or change Brain containers as a rollback mechanism.
