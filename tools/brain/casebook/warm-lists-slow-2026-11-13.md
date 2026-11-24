---
id: warm-lists-slow-2026-11-13
title: Warm lists were as slow as cold ones on 2026-11-13, on KaijuFlow and Usenet Ultimate.
kind: slow play
step: health_batch
whose: unknown
status: open
match:
  - rules: 2
    sign: "slow play | first_byte ok | *"
confirm:
  - clue: health-batch-inside-list
    answer: yes
fix: none yet
seen:
  - check: archive/2026-11-13T053200Z-baseline
    title: Interstellar
    play: warm 12 to 13 s
    date: 2026-11-13
  - check: archive/2026-11-13T053200Z-baseline
    title: Dune
    play: warm 11 to 17 s
    date: 2026-11-13
  - check: archive/2026-11-13T053200Z-baseline
    title: Game of Thrones S02E03
    play: warm 9 to 22 s
    date: 2026-11-13
---

## What the viewer saw

Warm lists as slow as cold ones: Interstellar 12 to 13 s warm, Dune 11 to 17 s, Game of Thrones S02E03 9 to 22 s, on KaijuFlow and Usenet Ultimate (archived baseline).

## Signs

Slow warm lists on both sides of the same run.

## Cause

Not known: "The cause was not looked into." The list-time check, which ran on warm lists then, is a lead ([health-check-before-list](health-check-before-list.md)); it has since been deleted.

## How it was proved

Not proved. The Clue it will need: a `health_batch` step ran inside the warm list's time.

## Ruled out

Nothing tested and rejected yet.

## Fix

None yet. The list-time check that ran on warm lists then has since been deleted (#191).

## History

- 2026-11-24: converted from the casebook sweep (draft D4).
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | list ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
- 2026-11-24: its slow-play sign is `slow play | first_byte ok | *` (rules 2): any slow play: where its time went is outside the played Source's steps (the list, the machine), so its confirming test tells (review of #279, round 2).
