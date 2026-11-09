# A bad byte range gets the whole file, not 416

When a player asks for a range KaijuFlow can't satisfy, the proxy answers 200 with the whole file from byte 0 instead of 416. This keeps the existing full-file fallback that players already recover from. The owner chose it on #17 (2026-11-09) even though the #16 spec text says 416.

## Consequences

- The Parity scenario `bad-range-full-file` asserts 200 + whole file for every Backend.
- Spec or ticket text that says "416 for a bad range" is superseded by this ADR.
