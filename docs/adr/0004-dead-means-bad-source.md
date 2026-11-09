# Only a bad Source is marked dead

The dead cache is for Sources that are bad: rejected by the Backend, failed preparation, never ready within the time budget, first byte missing. A Backend that is unreachable or misconfigured (network error, wrong key, Stremio integration off, AltMount's own internal errors) plays the failure video but leaves the Source alive, so it plays once the Backend is fixed. The dead mark is keyed by the Source, not the Backend. Spec #16, made true for NzbDAV in #20 (a network error on submit used to mark the Source dead).

The same rule holds on the indexer side (#51, 2026-11-09): an indexer that does not hand over the NZB (`429 Too Many Requests`, a 5xx, refused credentials, a network error, a download timeout) says nothing about the Source. Before #51 the grab threw a Source failure for every failed download, so a rate limit killed Healthy Sources for ever (45 such marks in the owner's config, almost all altHUB).

## Consequences

- Backends throw a Source failure (`isSourceFailure`) only for bad Sources; everything else is a plain error.
- The NZB grab (`grabNzb`) throws a Source failure only for bad content: an invalid NZB body, an indexer error payload, or a link the indexer says is gone (404 and other 4xx). A 429, 5xx, 401/403, network error or download timeout is a plain error: failure video, Source kept. (A server that answers 500 for a removed NZB is retried on every play; that is the price of never killing a Source for a server fault.)
- The dead cache drops marks written by earlier builds for an unavailable indexer when it loads (`isIndexerUnavailableMessage`), so the lost Sources come back without a manual clean-up.
- The Parity scenarios `unreachable-backend-not-dead` and `indexer-unavailable-not-dead` run against every Backend.
