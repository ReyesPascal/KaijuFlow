# KaijuFlow unscrambles RAR sets before upload

Some Sources are a Scrambled RAR set: the parts are named only by numbers (`<hash>.10` to `<hash>.103`) that don't match the real volume order. NzbDAV reads the RAR headers and plays them. AltMount v0.4.0 reads the name numbers, so it reports missing volumes and rejects a complete Source (Interstellar NOSiViD on 1338: all 46,966 video articles present). We fix this in KaijuFlow instead of waiting for AltMount. Just before the upload, KaijuFlow reads the real RAR5 volume number from the first article of each part and renames the parts in the NZB to `<name>.partNN.rar` in that order. It does this for every Backend, so all Backends get the same NZB. Decided 2026-11-09 (grill on Brain check results).

## Considered Options

- Wait for an AltMount fix: rejected for now. AltMount may never change, and the owner relies on health checks, not fallback, so a rejected Healthy Source matters. A draft report for AltMount is kept in the notes; posting it is the owner's call.
- Unscramble for AltMount only: rejected. One NZB for every Backend keeps Parity simple, and NzbDAV reads headers, so the new names don't affect it.

## Consequences

- Only sets named purely by numbers are checked; properly named sets (`.partNN.rar`, `.rar` + `.rNN`) are never touched.
- Only the chosen Source is checked, at play time, using the health-check providers, within at most 15 s of the prepare budget. The 15 s were confirmed after the Brain re-check (#46, 2026-11-09): 94 parts took 3.1 s on 8 connections, about 33 ms per part, so the limit leaves room for sets with more, smaller parts and only bites when a news server is slow.
- If Unscramble can't finish (no provider, no provider reachable, a missing first article, not RAR5, a duplicate or missing volume number, timeout), KaijuFlow uploads the original NZB and logs why. It does not mark the Source dead itself. Under ADR 0004 the Backend's rejection decides.
- The health check's own handling of these names is a separate issue (#40).

## One at a time (#119, 2026-11-15)

Auto-queue prepares several Sources at once (all Healthy Sources of the list by default), not only the one that is played, so several Unscrambles can run together. They share the health-check connection cap, so each runs slower: in the 2026-11-13 baseline the 210-part and 197-part sets of Inception's two top picks read 407 parts together on 12 connections and both ran out of their 15 s, and AltMount rejected the original NZB. So Unscrambles run one at a time, process-wide, first come first served, each with its own 15 s from the start of its turn. Auto-queue sends the top pick first, so it gets the connections first.

- The prepare budget still covers the wait: if it runs out before the turn comes, the original NZB goes up (reason `timeout`) and nothing is read.
- An NZB with no number-named set doesn't wait.
- No priority for a play over auto-queued Unscrambles (owner's decision, 2026-11-15): a play of the top pick joins its prepare that is already running. Accepted cost: a Source picked by hand lower in the list waits behind the ones queued before it.
- The `unscramble` step line gives `wait_ms`, the part of `ms` spent waiting for the turn.

**Amended 2026-11-20** (#226): Owner's words: "i want it to be as fast and lean as possible" (spec #183), and on the Head start that replaces Auto-queue, "I want the process to start when someone clicks the catalog link to the media before pressing play" (#206); then "can 206 be split up with agents to make it faster", "yes", which made deleting Auto-queue its own ticket (#226). So Auto-queue is deleted, and the several prepares at once described above no longer come from it: KaijuFlow prepares only the Source being played, the next only when it fails (#192). One at a time, first come first served, stays for prepares that still overlap (two players at once, a fallback beside a running prepare).
