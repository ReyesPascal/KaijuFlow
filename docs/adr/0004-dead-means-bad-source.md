# Only a bad Source is marked dead

The dead cache is for Sources that are bad: rejected by the Backend, failed preparation, never ready within the time budget, first byte missing. A Backend that is unreachable or misconfigured (network error, wrong key, Stremio integration off, AltMount's own internal errors) plays the failure video but leaves the Source alive, so it plays once the Backend is fixed. The dead mark is keyed by the Source, not the Backend. Spec #16, made true for NzbDAV in #20 (a network error on submit used to mark the Source dead).

## Consequences

- Backends throw a Source failure (`isSourceFailure`) only for bad Sources; everything else is a plain error.
- The Parity scenario `unreachable-backend-not-dead` runs against every Backend.
