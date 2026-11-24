---
id: busy-machine
title: A busy machine (agents building beside the run) slowed the cold lists.
kind: slow play
step: list
whose: test-only
status: fixed awaiting proof
match:
  - rules: 2
    sign: "slow play | first_byte ok | *"
confirm:
  - clue: machine-busy-at-start
    answer: yes
fix: "#217 (PR #224): the preflight refuses a busy machine (load 1.0 or more)"
seen:
  - check: 2026-11-21T002421Z-baseline-205-browse-pause
    title: the whole run (37 of 40 lists slower)
    date: 2026-11-21
---

## What the viewer saw

Slower cold lists: 37 of 40 slower, KaijuFlow's own work 5.3 s to 6.6 s, Everything Everywhere All at Once's cold list 22.3 to 25.1 s.

## Signs

A whole run slower with no code change; work that never leaves the machine also slow (reading three stored NZBs took about 2.5 times as long). Today: the preflight's 1-minute load and the CPU probe in `meta.json`.

## Cause

Five implementer agents built beside the run (`npm ci`, an integration script) outside the suite lock. It is the test machine's state, not KaijuFlow's or a viewer's.

## How it was proved

By replays on #205: four cold titles took 36.7 s idle; three cold lists took 25.3 to 27.5 s idle, 33.0 s with 4 busy loops and 43.4 s with 8. Which process took the CPU was not proved. The confirming test is the recipe in `confirm`: the machine was busy when the run started. Its Clue is not built yet.

## Ruled out

A code change: the replays on the same commit were fast on an idle machine.

## Fix

#217 (PR #224): the preflight refuses a busy machine (load 1.0 or more). Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft B3).
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | list ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
- 2026-11-24: its slow-play sign is `slow play | first_byte ok | *` (rules 2): any slow play: where its time went is outside the played Source's steps (the list, the machine), so its confirming test tells (review of #279, round 2).
