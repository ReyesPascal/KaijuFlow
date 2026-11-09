# KaijuFlow grabs the NZB and uploads it to the Backend

KaijuFlow downloads the chosen Source's NZB itself (`grabNzb`: proxy exit-IP check, content validation, grab tracking) and uploads the file to the Backend. The Backend never fetches the NZB from the indexer, even when it could (AltMount's `nzb_url`), so indexer traffic keeps going through KaijuFlow's proxy and counts against KaijuFlow's grab limits. Decided 2026-11-09 during #19.

## Consequences

- Every Backend's prepare takes NZB bytes, not an indexer link.
- The AltMount Parity test asserts KaijuFlow sent a multipart `file` and no `nzb_url`.
