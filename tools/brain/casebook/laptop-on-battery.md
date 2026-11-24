---
id: laptop-on-battery
title: The laptop ran on battery, so KaijuFlow's own list work ran at a slow CPU's pace.
kind: slow play
step: list
whose: test-only
status: fixed awaiting proof
match:
  - rules: 2
    sign: "slow play | first_byte ok | *"
confirm:
  - clue: machine-on-battery
    answer: yes
fix: "#262 (PR #264): the preflight refuses a run on battery and records a CPU probe"
seen:
  - check: 2026-11-24T040829Z-replay-249-main
    title: the whole replay
    date: 2026-11-24
  - check: 2026-11-24T041343Z-replay-249-base-47ccc06
    title: the whole replay
    date: 2026-11-24
---

## What the viewer saw

Warm lists 0.7 to 2 s slower (Super Mario warm 2: 0.99 s to 2.96 s), and slower cold work.

## Signs

`meta.json` `machine.power: battery` (since #262); the CPU at about 1.07 GHz idle (governor powersave). The list's step lines show `list_sort` about 740 ms and `list_build` about 410 ms on a warm movie list, against about 0.1 s each plugged in; process CPU about equal to wall time, GC about 5%, event-loop delay 0.

## Cause

A warm list is KaijuFlow's own single-thread CPU work (sort and build), so it runs as fast as the CPU does at that moment. It is the test machine's state.

## How it was proved

The code was ruled out by replays (#249: 47ccc06 and main within 4% on the same machine state). Battery was found during those replays, and #250, plugged in (CPU probe 1101 ms), had warm lists of 0.70 s and 0.15 s. The confirming test is the recipe in `confirm`: the run's `meta.json` says battery. Its Clue is not built yet.

## Ruled out

A code change between 47ccc06 and main (#249: within 4% on the same machine state).

## Fix

#262 (PR #264): the preflight refuses a run on battery and records a CPU probe. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft B4). `2026-11-23T190950Z-grouped-219` (and #218) are suspected only: those runs did not record power, so they are not in `seen`.
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | list ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
- 2026-11-24: its slow-play sign is `slow play | first_byte ok | *` (rules 2): any slow play: where its time went is outside the played Source's steps (the list, the machine), so its confirming test tells (review of #279, round 2).
