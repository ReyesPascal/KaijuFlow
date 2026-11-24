---
id: health-check-before-list
title: The health check ran before the list was sent, so cold lists were slow.
kind: slow play
step: health_batch
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "slow play | first_byte ok | *"
confirm:
  - clue: health-batch-inside-list
    answer: yes
fix: "#190 (PR #210), #191 (the list-time checks deleted), #206 (Head start: check and prepare during the Browse pause), in PR #225"
seen:
  - check: 2026-11-10 baseline (logs lost)
    title: every cold list
    date: 2026-11-10
  - check: archive/2026-11-13T053200Z-baseline
    title: every cold list
    date: 2026-11-13
  - check: 2026-11-20T223814Z-baseline-189
    title: every cold list
    date: 2026-11-20
  - check: 2026-11-23T183239Z-baseline-218
    title: every cold list
    date: 2026-11-23
---

## What the viewer saw

Slow cold lists: about 6 of the 7 to 10 s of a cold title to video.

## Signs

In the reports: "Cold list (10.1 s): indexer 1.8 s, health checks about 6 s" (2026-11-10), "6.5 s health checks" (2026-11-13), "Cold list about 6.4 s, of which indexers 1.3 s and KaijuFlow's own work 5.2 s" (#189). The run folders of the time hold `health_batch` step lines inside the list's time.

## Cause

The list-time Smart and Fixed checks checked Sources before any list went out.

## How it was proved

By #219: with the Play-time check and the Head start, cold title to video fell from 8.98 s / 9.10 s to 4.90 s / 6.07 s, and to 3.72 s / 3.10 s in #250. The confirming test is the recipe in `confirm`: a `health_batch` step ran inside the cold list's time. Its Clue is not built yet.

## Ruled out

The indexers: they took 1.3 to 1.8 s of the cold list.

## Fix

#190 (PR #210), #191 (delete the list-time checks), #206 (Head start: check and prepare during the Browse pause), in PR #225. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft B1). Seen in every cold list of every run up to `2026-11-23T183239Z-baseline-218`; `seen` lists the runs the sweep quoted.
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | list ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
