# Only a bad Source is marked dead

The dead cache is for Sources that are bad: rejected by the Backend, failed preparation, never ready within the time budget, first byte missing. A Backend that is unreachable or misconfigured (network error, wrong key, Stremio integration off, AltMount's own internal errors) plays the failure video but leaves the Source alive, so it plays once the Backend is fixed. The dead mark is keyed by the Source, not the Backend. Spec #16, made true for NzbDAV in #20 (a network error on submit used to mark the Source dead).

The same rule holds on the indexer side (#51, 2026-11-09): an indexer that does not hand over the NZB (`429 Too Many Requests`, a 5xx, refused credentials, a network error, a download timeout) says nothing about the Source. Before #51 the grab threw a Source failure for every failed download, so a rate limit killed Healthy Sources for ever (45 such marks in the owner's config, almost all altHUB).

## Consequences

- Backends throw a Source failure (`isSourceFailure`) only for bad Sources; everything else is a plain error.
- The NZB grab (`grabNzb`) throws a Source failure only for bad content: an invalid NZB body, or a link the indexer says is gone (404 and other 4xx, an error payload with code 300). A 429, 5xx, 401/403, an error payload with another code, network error or download timeout is a plain error: failure video, Source kept. (A server that answers 500 for a removed NZB is retried on every play; that is the price of never killing a Source for a server fault.)
- The dead cache drops marks written by earlier builds for an unavailable indexer when it loads (`isIndexerUnavailableMessage`), so the lost Sources come back without a manual clean-up.
- The Parity scenarios `unreachable-backend-not-dead` and `indexer-unavailable-not-dead` run against every Backend.

## First byte (#86, 2026-11-10)

The first-byte check asks the Backend for the first byte of the video. Same rule for every Backend:

- 404 or 410: the file is gone. A bad Source, marked dead as before.
- 400, a refused connection or a dropped connection: says nothing about the Source. Failure video, Source stays alive and is in the next list.
- 5xx or a timeout: today's handling, unchanged (bad Source after the retries). The 2026-11-10 recording gave no evidence either way.

When a first byte fails, KaijuFlow logs one line with the status, the path it asked for and the names of the files the Backend offered. No addresses, no keys.

The case behind it, Oppenheimer: the release name ends in `.mkv`, so AltMount stored it as a folder. The file route answered 400 twice for that folder, KaijuFlow marked a good Source dead, and it plays on NzbDAV. Fixing the folder itself is a separate change in the AltMount adapter (#85). The Parity scenarios `first-byte-400-or-dropped-not-dead` and `first-byte-404-dead` run against every Backend.

## The walk's grabs (deepening spec, 2026-11-23)

The Walk's grab (`walkGrab`, then named `prefetchNzb`) used to treat every failed download alike: the Source was skipped for that play, never marked dead, and grabbed again on every later play, while the full grab (`grabNzb`) already followed this ADR. Found by the architecture review and #228 (a failed grab was also replaced twice, so a walk doubled through 324 Sources in 4.7 s). Owner's decision ("yes to all", grilling of 2026-11-23):

- The walk's grab sorts its answers as `grabNzb` does: a link the indexer says is gone (404, other 4xx) or bad content marks the Source dead; a refusal (429, 5xx, 401/403, a network error, a timeout) says nothing about the Source.
- A 200 with a Newznab error payload is sorted the same way, by its code: 300 (no such item) is a gone link, a Source failure and a dead mark; 1xx (credentials, suspended, privileges), 5xx (request or download limit) and every other code are a refusal, so the indexer is skipped for the rest of the walk and the Source is untouched (review of #239, 2026-11-23).
- An indexer that refuses a grab is skipped for the rest of that walk, so one indexer refusing downloads can't spend the day's allowance.
- A walk stops after 30 grabs, about twice the deepest walk measured (16, The Twilight Zone S02E06), and ends as when the list runs out.
- The test stand-in answers a recording miss with 503 ("not recorded"), a refusal, so a gap in a Recording never writes a dead mark.
