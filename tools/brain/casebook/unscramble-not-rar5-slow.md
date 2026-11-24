---
id: unscramble-not-rar5-slow
title: Finding out a set needs no Unscramble cost a second of reading articles.
kind: slow play
step: unscramble
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "slow play | first_byte ok | *"
confirm:
  - clue: unscramble-not-rar5-slow
    answer: yes
fix: "#193 (in PR #225): a set with no RAR or number names is decided from the names alone"
seen:
  - check: 2026-11-09 runs (logs lost)
    title: 7 imports
    date: 2026-11-09
  - check: 2026-11-10 baseline (logs lost)
    title: 5 of 10 top picks
    date: 2026-11-10
  - check: 2026-11-23T183239Z-baseline-218
    title: most cold plays
    date: 2026-11-23
---

## What the viewer saw

0.6 to 1.6 s extra on many cold plays.

## Signs

`{"step":"unscramble",...,"result":"not-rar5"}` with `ms` 600 to 1600 on 7z sets and other non-RAR5 sets.

## Cause

Unscramble read first articles of a set that its file names already showed was not a RAR set.

## How it was proved

By the step lines; after the fix, a 7z set shows `not-scrambled` with `ms` near 0. The confirming test is the recipe in `confirm`: an `unscramble` step ended `not-rar5` after more than half a second. Its Clue is not built yet.

## Ruled out

Nothing tested and rejected yet.

## Fix

#193 (in PR #225): a set with no RAR or number names is decided from the names alone. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft B6). Seen in most runs up to `2026-11-23T183239Z-baseline-218`.
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | unscramble ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
