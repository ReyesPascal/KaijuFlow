# KaijuFlow handoff — Phase A

Last update: 2026-11-07. Current phase: **A (in progress; full-app scope established, complete manifest created, initial static audit)**.

## Scope — corrected

**The project is a full application capture/fork of Usenet Ultimate v1.4.1.** Smart mode is one regression-protected subsystem, not the focus. Never start Phase B changes until **every original file** (including binary media, changelogs, scripts, backend, UI and installation assets) has been imported and verified. See `docs/WHOLE_APP_CAPTURE.md`.

## Completed and verified
- Connected GitHub user `ReyesPascal` has admin permissions; `KaijuFlow` and `KaijuNNTP` are both private and each was already initialized with a ReyesPascal MIT `LICENSE` only.
- Initial commits: KaijuFlow `1cd3932a9ae6d0a5a2fe53d8834637bc1f822cd0`; KaijuNNTP `16a308411569602a9ffea055e824296f6607f033`.
- Canonical upstream `DSmart33/Usenet-Ultimate` release tag `v1.4.1` resolves to `499efbdeb631b1b059f8aa70d07c12beaf504876`; verified MIT upstream notice differs from current KaijuFlow license.
- Pinned source tree enumerated using GitHub Git-tree API: **192 files, 12,132,917 bytes** (untruncated). File path, SHA, mode and size of every original blob committed in `docs/upstream-v1.4.1-manifest.json`. Scope recorded in `docs/WHOLE_APP_CAPTURE.md`. Initial source inspection covered health-check, NNTP, fallback, cache, archive, config, UI and Docker modules; this is not a complete application audit.
- Roadmap and checklists documented: `docs/ROADMAP.md`, `docs/CHECKPOINTS.md`.

## Unfinished
- Source code and binary assets are **NOT imported**. Do not mistake the complete inventory/manifest for a code import. No runtime benchmark has been made; the full application audit, reproducible build and tests remain outstanding.
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
