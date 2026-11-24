# KaijuFlow's health check passes what AltMount streams

Replaces [ADR 0008](0008-kaijuflow-plays-plain-video-only.md) (plain video only). AltMount is KaijuFlow's one Backend, and KaijuFlow's health check passes a Source only when AltMount is shown to stream it: plain video, stored RAR5 (in volume order, hash-named, or put in order by Unscramble) and stored 7z. It blocks the rest: compressed archives, encrypted archives (with or without a password), nested archives, ZIP, a Scrambled RAR4 set, an NZB with no file it can name, a disc image, and an archive whose header it cannot read. Decided by the owner on 2026-11-20 (spec #183).

The owner's words: "I just want altmount to be the fast backend and want KF to do the healthcheck, even if its RARS, find a way to make them work together as fast as possible forget speed testing against the rest"; then "i want it to be as fast and lean as possible". Asked whether cases not yet shown to play (an old-style RAR4 set, an encrypted archive with its password, ZIP) pass or are blocked: blocked, probed on the live AltMount copy only if a run shows titles failing for lack of a playable Source.

## Why

ADR 0008 blocked every archive because the health check said a Source was complete, not that the Backend could stream what was inside it. That cost most Sources: in Test 2's cancelled record about 19 of 117 health checks were plain video. The fix is to check for what the one Backend can stream, not to give up archives.

What AltMount v0.4.0 was seen to do (Test 1, `2026-11-15T115540Z-baseline` logs, and ADR 0008):

- played plain video, stored multi-volume RAR5 sets (named and hash-named), Unscrambled RAR5 sets, and stored 7z sets ("Successfully processed 7zip archive files");
- refused a compressed 7z ("Only uncompressed files are supported"), a Scrambled RAR4 set ("all files failed validation"), a number-named RAR5 set out of order, and a bare disc image.

Nothing else was seen, so nothing else passes.

## Consequences

- More Sources than plain video only, fewer than "complete": a title whose Sources are all compressed or encrypted fails.
- Archive inspection always runs on an archive, whatever the `archiveInspection` setting says; a header that cannot be read blocks the Source (a flaky provider costs Sources: the accepted price of "proven only").
- Usenet Ultimate and AltMount direct are no longer compared with (spec #183), so this rule is KaijuFlow's alone with nothing to keep equal.
- If AltMount changes what it streams, this list changes with it, from a run that shows it (since ADR 0010: a check or a drill-down that shows it).
