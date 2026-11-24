---
id: ghost-in-the-shell-no-sources
title: Ghost in the Shell has no Sources in any pass, and it is not known whether one exists.
kind: nothing to play
step: indexer_page
whose: unknown
status: open
match:
  - rules: 1
    sign: "nothing to play | indexer_page ok | *"
confirm:
  - clue: search-year-differs-from-id
    answer: yes
fix: none yet
seen:
  - check: 2026-11-24T052656Z-kf-265-record-record
    title: Ghost in the Shell
    date: 2026-11-24
  - check: 2026-11-24T053800Z-kf-265-topup-record
    title: Ghost in the Shell
    date: 2026-11-24
  - check: 2026-11-24T054751Z-kf-265-topup2-record
    title: Ghost in the Shell
    date: 2026-11-24
---

## What the viewer saw

Nothing to play: 0 Sources in every pass of the `kf-265` record and its two top-ups, so any run on that list fails it.

## Signs

The Stand-in shows KaijuFlow searching `q=Ghost in the Shell 1996` (recorded answer 1016 bytes, which is empty) and once `q=Ghost in the Shell 1995` (a miss). The film is tt0113568 (1995).

## Cause

Not known. Suspected: a wrong year in the search.

## How it was proved

Not proved, and whether a Source exists was not checked, so whether "nothing to play" was right is unknown. The Clue it will need: the year KaijuFlow searched differs from the ID's year.

## Ruled out

Nothing tested and rejected yet.

## Fix

None yet.

## History

- 2026-11-24: converted from the casebook sweep (draft D5).
