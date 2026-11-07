# KaijuFlow

Private, self-hosted Usenet discovery, verification, fallback and original-quality streaming project.

**Status:** Phase A — upstream v1.4.1 static baseline identified; source import and reproducible baseline testing **not yet completed**. This repository currently contains planning material only, not the imported application.

## Source of truth
- Upstream: https://github.com/DSmart33/Usenet-Ultimate
- Exact release tag: `v1.4.1`
- Pinned commit: `499efbdeb631b1b059f8aa70d07c12beaf504876`
- Upstream license: MIT — copyright (c) 2026 Usenet Ultimate Contributors
- Repository's own preexisting MIT LICENSE: copyright (c) 2026 ReyesPascal

Keep both license notices when importing. Do not replace the current `LICENSE` silently. Preserve the upstream MIT license verbatim under `THIRD_PARTY_NOTICES/Usenet-Ultimate-LICENSE` and retain any source-file notices.

## Development restrictions
- Never change, restart, update or replace the existing Usenet Ultimate or NzbDAV containers on Brain without explicit approval.
- No production deployments without explicit approval. Keep stable direct LAN/Wi-Fi playback without Tailscale.
- No credentials, provider passwords, indexer API keys, tokens, or live configuration committed to Git.
- Do not modify Droidusion or Pascal The Popcorn repositories.
- Audit first, then small testable changes with rollback. Prefer source reliability over raw result counts.

See [Phase A baseline and import plan](docs/PHASE_A_BASELINE.md), [development roadmap](docs/ROADMAP.md), and [handoff](HANDOFF.md).

KaijuNNTP is a separately maintained, conditionally activated verification-engine concept: https://github.com/ReyesPascal/KaijuNNTP
