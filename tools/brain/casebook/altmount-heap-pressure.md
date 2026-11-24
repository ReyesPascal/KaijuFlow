---
id: altmount-heap-pressure
title: AltMount warns its live heap is pressing on its Go memory limit; no play has been tied to it.
kind: slow play
step: import_wait
whose: unknown
status: open
match:
  - rules: 1
    sign: "slow play | first_byte ok | *"
confirm:
  - clue: altmount-heap-warning
    answer: yes
  - clue: import-wait-long
    answer: yes
fix: none yet
seen:
  - check: 2026-11-20T223814Z-baseline-189
    title: no play tied to it
    date: 2026-11-20
  - check: 2026-11-23T183239Z-baseline-218
    title: no play tied to it
    date: 2026-11-23
---

## What the viewer saw

Nothing known: no play has been tied to it. A slow import is the harm it could do, so it is filed as a slow play.

## Signs

AltMount's log: "Live heap is pressing on the Go memory limit" (`live_mb=682 limit_mb=678`), in #189 and #218.

## Cause

Not known whether it does any harm.

## How it was proved

Not proved. The Clues it will need: AltMount warned about its heap during this play, and the import wait was long.

## Ruled out

Nothing tested and rejected yet.

## Fix

None yet.

## History

- 2026-11-24: converted from the casebook sweep (draft D7).
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | import_wait ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
