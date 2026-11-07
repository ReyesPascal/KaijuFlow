# Whole-application capture contract — KaijuFlow Phase A

**Scope: the complete Usenet Ultimate v1.4.1 application, not a Smart-mode project.**

Date: 2026-11-07. Status: **manifest verified; source bytes NOT imported into KaijuFlow yet**.

## Pinned release and inventory

- Canonical upstream: `DSmart33/Usenet-Ultimate`
- Tag: `v1.4.1`
- Exact commit: `499efbdeb631b1b059f8aa70d07c12beaf504876`
- GitHub Git tree inspection: 220 tree entries including **192 file blobs totaling 12,132,917 bytes**, not truncated.
- Machine-readable source inventory: [upstream-v1.4.1-manifest.json](upstream-v1.4.1-manifest.json) lists **every source path, Git blob SHA, byte size, and file mode** (including binary assets). A release is not captured until **all 192** are present and match hashes.

### Full application subsystem inventory

| Area | Included content and preservation obligation |
| --- | --- |
| Backend and application APIs | All `src/` TypeScript modules (106 files total under src), server entrypoints, request handling, metadata/episode resolution and playback URLs |
| Search and indexers | Every provider and indexer adapter, Prowlarr / NZBHydra / Newznab paths, source ranking/deduplication and search configuration |
| Health-check engine | Smart **and** Fixed modes, article sampling, NNTP multi-provider checks, archive detection and eligibility, caching, status/visibility behavior |
| NzbDAV and direct streaming | WebDAV video discovery, redirect/stream endpoints, original-quality range/seek behavior, startup and failure paths |
| Fallback and error handling | Ultimate Fallback, candidate state machine, failure recovery, retry budget, dead-NZB cache and ready cache |
| UI and browser assets | Entire `ui/` tree (62 files), React overlays, hooks, CSS, PWA icons, favicons, **all five MP4 UI/system videos** |
| Build/deployment (development artifacts only) | `Dockerfile`, `docker-compose.yml`, `.dockerignore`, TypeScript config, Node backend/UI `package.json` and lockfiles, PWA build |
| Installation and utilities | `auto-installers/`, `scripts/`, `release.sh`, `INSTALLATION.md`, `SETUP.md`, upstream README, all PDF changelogs |
| Attribution | Upstream original MIT license and source comments; keep existing KaijuFlow MIT license separately and preserve upstream notice verbatim |

Directory distribution in original release: `src/` 106 files; `ui/` 62; `auto-installers/` 5; `changelogs/` 3; `scripts/` 3; and 13 root-level files. The original release has 14 binary files (five MP4, three PDF, five PNG, one ICO). Non-UTF8 binaries **must** be imported via Git, not reconstructed from text.

## Non-negotiable fidelity gates

1. **No selective rewrite:** all original release files must be present before app development starts. No cherry-picking just Smart mode or NNTP submodules.
2. **Byte-for-byte match:** every import path checked against upstream blob SHA and mode. Only required collisions are transparently remapped: original `README.md` → `docs/upstream/README.v1.4.1.md`; original `LICENSE` → `THIRD_PARTY_NOTICES/Usenet-Ultimate-LICENSE`. Existing KaijuFlow root README/LICENSE and preexisting project docs remain. Track mappings in the import verification report.
3. **Build integrity:** unmodified source must support both backend and UI build under documented, compatible toolchain; preserve package lockfiles and assets.
4. **Application-wide behavioral parity:** compare every listed subsystem against release behavior; record gaps explicitly. Smart mode is merely one regression test among many.
5. **Security and privacy:** no real `.env`, provider credentials, indexer secrets, NzbDAV tokens, private playback metadata, or production configs enter the Git repository. Independently scan import before pushing.
6. **Isolation:** work only in a new `import/upstream-v1.4.1` development branch and isolated dev checkout. Do not stop/update/change working Brain containers.
7. **Rollback:** record pre-import `main` SHA, import commit, tree manifest, and reversible commit history. Do not force-push shared branches. No deployment authorization is implied.

## Complete import procedure

The pinned source is public, but the connected GitHub text-file API cannot currently read its non-UTF8 binary artifacts. **Do not label a text-only import as complete.** Use a regular Git clone/fetch from a development machine with network access to GitHub and push the validated branch to the private KaijuFlow repo.

A non-deploying, checksum-verifying import helper is committed at [scripts/import-upstream-v1.4.1.sh](../scripts/import-upstream-v1.4.1.sh). It operates only in a clean isolated KaijuFlow checkout, fetches the exact public tag, imports and hash-verifies **all 192 files**, preserves the existing root README/LICENSE and saves a validation report. It **does not** commit, push, deploy, or scan credentials for you; a trusted secret scan and isolated tests are required before any Git push.

The underlying commands, from a new **isolated** KaijuFlow clone (never inside the live Brain container folders):

```bash
git status --short
bash scripts/import-upstream-v1.4.1.sh
# The helper performs the fetch, import, and all-blob SHA checks below.
# For manual inspection only, the underlying Git fetch is:
git fetch --no-tags upstream-ultimate refs/tags/v1.4.1:refs/tags/upstream-ultimate-v1.4.1
git rev-parse 'refs/tags/upstream-ultimate-v1.4.1^{commit}'
# Must equal: 499efbdeb631b1b059f8aa70d07c12beaf504876
git switch -c import/upstream-v1.4.1
# Extract the entire exact upstream tree to a temporary directory.
# Copy all files, retaining executable bits, with README and LICENSE remapped
# as documented above; verify all 192 file blob hashes against the manifest.
# Run security/credential scans before staging or committing.
# Run isolated backend/UI build, then commit and push this development branch.
```

Record detailed audit/testing evidence under this docs directory, update `HANDOFF.md` and the checkpoint register, and only then proceed to Phase B. KaijuNNTP does not replace or remove in-app NNTP features.
