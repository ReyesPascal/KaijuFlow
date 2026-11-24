---
id: first-title-after-reset-swings
title: The first title after a reset swings between 9 and 14 s on an idle machine.
kind: slow play
step: list
whose: unknown
status: open
match:
  - rules: 2
    sign: "slow play | first_byte ok | *"
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
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | list ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
- 2026-11-24: its slow-play sign is `slow play | first_byte ok | *` (rules 2): any slow play: where its time went is outside the played Source's steps (the list, the machine), so its confirming test tells (review of #279, round 2).
