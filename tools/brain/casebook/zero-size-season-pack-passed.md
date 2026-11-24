---
id: zero-size-season-pack-passed
title: A season pack whose NZB sums to zero size passed the health check, and AltMount refused it.
kind: check miss
step: health_batch
whose: KaijuFlow
status: open
match:
  - rules: 1
    sign: "check miss | import_wait not ok | *total size is zero*"
  - rules: 1
    sign: "fail | import_wait not ok | *total size is zero*"
confirm: none (no evidence kept)
fix: none yet
seen:
  - check: 2026-11-09 evening cold run (logs lost)
    title: The Wire S01E01
    play: cold
    date: 2026-11-09
---

## What the viewer saw

A fail on the first press, cold.

## Signs

AltMount: `invalid NZB: total size is zero`. KaijuFlow's health check had passed it. The logs are lost.

## Cause

The health check samples articles; it does not check what AltMount checks on accept (every file's first article readable, sizes readable, a total above zero).

## How it was proved

Only as far as AltMount's own message goes (spec #58 and the old Speed Check page). No replay or test; no evidence is kept, so there is no confirming test.

## Ruled out

Nothing tested and rejected yet.

## Fix

None yet. #66 planned "the Backend's acceptance check" in the health check but was closed unbuilt with spec #58 on 2026-11-15.

## History

- 2026-11-24: converted from the casebook sweep (draft A11). It was The Wire S01E01's top pick (the S01 season pack) and KaijuFlow's only cold miss of 10 that run.
