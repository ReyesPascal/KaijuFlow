---
id: grab-429-dead-mark
title: An indexer's 429 on the NZB grab marked a good Source dead for ever.
kind: fail
step: nzb_fetch
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "fail | nzb_fetch not ok | *429*"
confirm: none (no evidence kept)
fix: "#51 (PR #52), ADR 0004: a 429, 5xx, 401/403, network error or timeout leaves the Source alive; old marks dropped on load; the Walk's own grab since #243"
seen:
  - check: "#46 re-check on port 1338 (logs lost)"
    title: Game of Thrones S02E03
    date: 2026-11-09
---

## What the viewer saw

The failure video, and afterwards the Source missing from every list.

## Signs

KaijuFlow's log: `Failed to download NZB from <indexer>: 429 …` (also `NZB download failed: <network error>` or a download timeout), then a dead mark with `expiresAt: 0`. The test config held 45 such marks, almost all altHUB.

## Cause

The grab (`grabNzb`) treated every failed download as a Source failure, so a rate limit (two sides and their health checks hitting altHUB at once) killed Healthy Sources. Behaviour inherited from Usenet Ultimate.

## How it was proved

Seen live on 2026-11-09, and covered by the unit test and the Parity scenario `indexer-unavailable-not-dead`. No evidence of the live case is kept, so there is no confirming test.

## Ruled out

Nothing tested and rejected yet.

## Fix

#51 (PR #52), ADR 0004: a 429, 5xx, 401/403, network error or timeout is a plain error, the Source stays alive, and old marks are dropped on load. The Walk's own grab got the same rules in #243 (2026-11-23). Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft A5). Also found: the 45 dead marks in the test config.
