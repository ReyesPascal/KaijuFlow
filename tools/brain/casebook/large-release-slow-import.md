---
id: large-release-slow-import
title: A large release took AltMount a long time to import while its news connections died.
kind: slow play
step: import_wait
whose: unknown
status: open
match:
  - rules: 2
    sign: "slow play | first_byte ok | *most time in import_wait*"
confirm:
  - clue: import-wait-long
    answer: yes
  - clue: altmount-connection-died
    answer: yes
fix: none yet
seen:
  - check: archive/2026-11-13T053200Z-baseline
    title: Game of Thrones S02E03
    play: cold 1
    date: 2026-11-13
  - check: archive/2026-11-13T053200Z-baseline
    title: Game of Thrones S02E03
    play: cold 2
    date: 2026-11-13
---

## What the viewer saw

A slow play: 44 s and 57 s from press to video (title to video about 57 and 70 s).

## Signs

Most of the wait in AltMount's import (21 to 41 s). AltMount's log at the time: `msg="Failed to normalize segment sizes with yEnc headers" ... error="failed to fetch last segment yEnc part size: failed to get body: nntp: all providers exhausted: newshosting: nntp: connection died" ... nzb_path=/tmp/.altmount-queue/Game.of.Thrones.S02E03.2160p…`.

## Cause

Suspected: a 26.5 GB 4K top pick, and connections to Newshosting dying during the import. Which of the two cost the time was not looked into, so whose cause it is (the size of KaijuFlow's pick, AltMount, or Usenet) is not known.

## How it was proved

Not proved: suspected from the log line and the size. The confirming test it will need is the recipe in `confirm`: the import wait was long, and AltMount's log shows news connections dying during it. Its Clues are not built yet.

## Ruled out

Nothing tested and rejected yet.

## Fix

None yet.

## History

- 2026-11-24: converted from the casebook sweep (draft B8). The one-page side took 24 s and 42 s on the same title.
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | import_wait ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
- 2026-11-24: its slow-play sign is `slow play | first_byte ok | *most time in import_wait*` (rules 2): the step of the played Source that took the most time, `import_wait`, as rules 2's fingerprint gives it (review of #279, round 2).
