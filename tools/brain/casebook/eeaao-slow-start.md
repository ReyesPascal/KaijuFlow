---
id: eeaao-slow-start
title: Everything Everywhere All at Once starts slowly, with no fallback, and nobody knows why.
kind: slow play
step: play_check
whose: unknown
status: open
match:
  - rules: 1
    sign: "slow play | first_byte ok | *"
confirm:
  - clue: play-check-slow-blocked
    answer: yes
  - clue: import-wait-long
    answer: yes
fix: none yet
seen:
  - check: 2026-11-23T183239Z-baseline-218
    title: Everything Everywhere All at Once
    play: 13.4 s and 16.3 s
    date: 2026-11-23
  - check: 2026-11-23T190950Z-grouped-219
    title: Everything Everywhere All at Once
    play: 23.4 s
    date: 2026-11-23
  - check: 2026-11-24T041343Z-replay-249-base-47ccc06
    title: Everything Everywhere All at Once
    play: 17.1 s
    date: 2026-11-24
  - check: 2026-11-24T044717Z-grouped-250
    title: Everything Everywhere All at Once
    play: 13.5 s
    date: 2026-11-24
---

## What the viewer saw

13 to 23 s from press to video, in four runs, with no fallback.

## Signs

The step lines show play checks of 7 to 13.7 s that end `blocked`, and an `import_wait` of 3 to 14.3 s.

## Cause

Not known. Nobody has looked into it.

## How it was proved

Not proved. The Clues it will need: the Play-time check spent long on Sources it then blocked, and the import wait was long.

## Ruled out

Nothing tested and rejected yet.

## Fix

None yet.

## History

- 2026-11-24: converted from the casebook sweep (draft D2).
