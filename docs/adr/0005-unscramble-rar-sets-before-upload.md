# KaijuFlow unscrambles RAR sets before upload

Some Sources are a Scrambled RAR set: the parts are named only by numbers (`<hash>.10` to `<hash>.103`) that don't match the real volume order. NzbDAV reads the RAR headers and plays them. AltMount v0.4.0 reads the name numbers, so it reports missing volumes and rejects a complete Source (Interstellar NOSiViD on 1338: all 46,966 video articles present). We fix this in KaijuFlow instead of waiting for AltMount. Just before the upload, KaijuFlow reads the real RAR5 volume number from the first article of each part and renames the parts in the NZB to `<name>.partNN.rar` in that order. It does this for every Backend, so all Backends get the same NZB. Decided 2026-11-09 (grill on Brain check results).

## Considered Options

- Wait for an AltMount fix: rejected for now. AltMount may never change, and the owner relies on health checks, not fallback, so a rejected Healthy Source matters. A draft report for AltMount is kept in the notes; posting it is the owner's call.
- Unscramble for AltMount only: rejected. One NZB for every Backend keeps Parity simple, and NzbDAV reads headers, so the new names don't affect it.

## Consequences

- Only sets named purely by numbers are checked; properly named sets (`.partNN.rar`, `.rar` + `.rNN`) are never touched.
- Only the chosen Source is checked, at play time, using the health-check providers, within at most 15 s of the prepare budget.
- If Unscramble can't finish (no provider, no provider reachable, a missing first article, not RAR5, a duplicate or missing volume number, timeout), KaijuFlow uploads the original NZB and logs why. It does not mark the Source dead itself. Under ADR 0004 the Backend's rejection decides.
- The health check's own handling of these names is a separate issue (#40).
