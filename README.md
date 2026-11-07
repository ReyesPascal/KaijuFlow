# KaijuFlow

Private, self-hosted Usenet discovery, verification, fallback, and original-quality streaming application, based on the complete Usenet Ultimate v1.4.1 release.

The baseline includes the backend, React UI and media assets, search and indexer integrations, NNTP providers, Smart and Fixed health checks, archive inspection, NzbDAV streaming, automatic fallback, caches, installation scripts, and Docker tooling. Application source and assets remain unchanged from the pinned release. See [UPSTREAM.md](UPSTREAM.md) for provenance and licensing.

## Development

Use an isolated development environment with Node.js 20, as used by the upstream Docker build. Install from the preserved lockfiles:

```sh
npm ci
npm run build
cd ui
npm ci
npm run build
```

Use fabricated credentials and synthetic fixtures for testing. Keep provider credentials, indexer keys, private configuration, logs, and runtime data out of Git. Setup and deployment details remain in the original [INSTALLATION.md](INSTALLATION.md) and [SETUP.md](SETUP.md); the original release README is preserved [verbatim](docs/upstream/README.v1.4.1.md).

## Project records

- [Roadmap and acceptance gates](docs/kaijuflow/ROADMAP.md)
- [Audit findings and development decisions](docs/kaijuflow/AUDIT.md)
- [Next session](docs/kaijuflow/audit/NEXT_SESSION.md)
- [Source manifest](docs/kaijuflow/upstream-v1.4.1-manifest.json) and [validation evidence](docs/kaijuflow/import-verification.json)

Brain and its working containers and streaming configuration are outside this development task. No production deployment is authorized. KaijuNNTP remains a separate, dormant candidate pending an architecture decision.

## License

The original upstream [MIT license](LICENSE), copyright (c) 2026 Usenet Ultimate Contributors, is preserved exactly at the root. The previous ReyesPascal MIT notice is preserved [separately](docs/kaijuflow/LICENSE.ReyesPascal), on `archive/pre-upstream-import`, and in Git history.
