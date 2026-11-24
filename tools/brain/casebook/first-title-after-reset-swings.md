---
id: first-title-after-reset-swings
title: The first title after a reset swings between 9 and 14 s on an idle machine.
kind: slow play
step: list
whose: unknown
status: open
match:
  - rules: 1
    sign: "slow play | list ok | *"
confirm:
  - clue: first-visit-after-reset
    answer: yes
fix: none yet
seen:
  - check: 2026-11-21T002421Z-baseline-205-browse-pause
    title: The Batman
    play: cold list 9 to 14 s
    date: 2026-11-21
---

## What the viewer saw

The Batman's cold list takes 9 to 14 s on an idle machine.

## Signs

The first title after a reset of the test copies has the slowest and most varied cold list (comment on #205; a gotcha in the handoff note).

## Cause

Not known.

## How it was proved

Not proved. The Clue it will need: the slow list is the first visit after a reset.

## Ruled out

A busy machine ([busy-machine](busy-machine.md)): it swings on an idle machine too.

## Fix

None yet.

## History

- 2026-11-24: converted from the casebook sweep (draft D3).
