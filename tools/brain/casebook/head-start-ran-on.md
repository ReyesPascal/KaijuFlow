---
id: head-start-ran-on
title: A Head start's work ran on into the next title and shared its connections.
kind: slow play
step: head_start
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "slow play | play_check ok | *"
  - rules: 1
    sign: "fallback | import_wait not ok | *"
confirm:
  - clue: other-title-steps-in-visit
    answer: yes
fix: "#244 (PR #252): a Walk ends when another title's list is asked for, before its search starts"
seen:
  - check: 2026-11-23T190950Z-grouped-219
    title: Upstream Color
    play: cold 1
    date: 2026-11-23
---

## What the viewer saw

The next title's play shared connections with the last title's checks; in #219 that next play (Upstream Color, cold 1) fell back.

## Signs

A `play_check` step for one title's release (Night Moves, 19:13:02 to 19:13:14, 11.9 s) inside the next title's visit.

## Cause

A Head start was stopped only after the next list was built, and a claimed Walk was never stopped, so its leftover checks ran on.

## How it was proved

The overlap is proved by the times; that it caused Upstream Color's read-error ([unscramble-read-error](unscramble-read-error.md)) is suspected only. The confirming test is the recipe in `confirm`: a step of another title's release ran inside this visit. Its Clue is not built yet.

## Ruled out

Nothing tested and rejected yet.

## Fix

#244 (PR #252): a Walk ends when another title's list is asked for, before its search starts. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft B7).
