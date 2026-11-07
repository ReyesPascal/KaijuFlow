# KaijuFlow

Private, self-hosted Usenet discovery, verification, fallback and original-quality streaming project.

**Mission: preserve and extend the ENTIRE Usenet Ultimate v1.4.1 application**, including all backend, frontend, streaming, search, indexers, NNTP providers, health modes, archive inspection, NzbDAV integration, automatic fallback, caches, media assets, Docker/build tooling and documentation. Smart mode is one protected feature, **not** the scope of the project.

**Status:** Phase A — exact upstream release and full 192-file manifest verified; **full source code/assets not yet imported**. The repository contains planning and audit material, not yet the working application.

## Canonical source of truth
- Upstream: https://github.com/DSmart33/Usenet-Ultimate
- Exact release: `v1.4.1`
- Pinned commit: `499efbdeb631b1b059f8aa70d07c12beaf504876`
- Source tree: **192 files, 12,132,917 bytes**, including non-UTF8 binaries (MP4 videos, PDF changelogs, PNG and ICO assets).
- Original upstream license: MIT — copyright (c) 2026 Usenet Ultimate Contributors
- Current KaijuFlow repository license: MIT — copyright (c) 2026 ReyesPascal

**Do not import only selected modules.** The import must preserve all 192 upstream file blobs, original bytes/modes and attribution, with documented remapping of `README.md` and `LICENSE` to retain the existing KaijuFlow versions. Preserve the upstream MIT license verbatim under `THIRD_PARTY_NOTICES/Usenet-Ultimate-LICENSE` and retain any source-file notices.

## Phase A documents
- [Whole-application capture requirements](docs/WHOLE_APP_CAPTURE.md)
- [Complete upstream file manifest with Git blob SHAs](docs/upstream-v1.4.1-manifest.json)
- [Preliminary baseline/architecture audit and import planning](docs/PHASE_A_BASELINE.md)
- [Roadmap, Phases A–F](docs/ROADMAP.md)
- [Checkpoint register](docs/CHECKPOINTS.md)
- [Current work state / resumable handoff](HANDOFF.md)

## Operational restrictions
- Never change, restart, update or replace the working Usenet Ultimate or NzbDAV containers on Brain without explicit approval.
- No production deployment without approval; preserve stable direct LAN/Wi-Fi playback without Tailscale.
- Never commit credentials, provider passwords, indexer keys, tokens, private configuration or runtime media data.
- Keep KaijuFlow separate from Droidusion and Pascal The Popcorn source.
- Keep the entire current functional application intact as a baseline before targeted improvements; prioritize verified playable reliability over result count.

[KaijuNNTP](https://github.com/ReyesPascal/KaijuNNTP) is a separate, **dormant** candidate for a future verifier service. It does not replace or justify deleting the verification implementation inside the full KaijuFlow application.
