---
id: recording-missing-requests
title: The Recording did not hold what KaijuFlow asked for, so the replay answered "not recorded".
kind: fail
step: nzb_fetch
whose: test-only
status: fixed awaiting proof
match:
  - rules: 1
    sign: "fail | nzb_fetch not ok | *"
  - rules: 1
    sign: "nothing to play | indexer_page ok | *"
confirm:
  - clue: standin-miss-for-visit
    answer: yes
fix: "#79, #229, #235 (PR #236) and #240; #273 archives the replayed Recording"
seen:
  - check: 2026-11-10 baseline (logs lost)
    title: warm rounds (40 misses)
    date: 2026-11-10
  - check: 2026-11-21T050927Z-baseline-218-wifi
    title: several titles (863 misses)
    date: 2026-11-21
  - check: 2026-11-23T173423Z-baseline-218
    title: several titles (1840 misses)
    date: 2026-11-23
  - check: 2026-11-23T183239Z-baseline-218
    title: several titles (162 misses, never played)
    date: 2026-11-23
  - check: 2026-11-23T190950Z-grouped-219
    title: several titles (353 misses, never played)
    date: 2026-11-23
  - check: 2026-11-24T044717Z-grouped-250
    title: one title (1 miss)
    date: 2026-11-24
  - check: 2026-11-24T052656Z-kf-265-record-record
    title: "Spider-Man: Across the Spider-Verse"
    play: proof replay (6 misses)
    date: 2026-11-24
  - check: 2026-11-24T053800Z-kf-265-topup-record
    title: one title (1 miss)
    date: 2026-11-24
---

## What the viewer saw

In the run: a fail, "no Sources", or a Walk that ran to the end of the list; warm lists too fast because checks ended at once. A viewer never meets it: it only happens in a replayed test.

## Signs

The Stand-in's log: `MISS ninjacentral api ...` (since #240 it answers 503 "not recorded"); `CHECK.txt`: "Not usable as a baseline: 1840 requests missed the recording in 16 visits", "Missed, never played (listed, not counted against the run; #235)", or "no Sources (a missed request can be the cause)".

## Cause

The Recording was made with other behaviour than the run's: `kf-189` was recorded with the fallback off, so the fallback's grabs (on since #190) were never stored; in 2026-11-10's Recording the warm round's replacement checks were never stored; in a proof replay a fallback grabbed releases the record pass never asked for. Each miss then looks like a refusing indexer or a gone Source.

## How it was proved

By the Stand-in logs and by top-ups that cleared the misses (#218: 11 new NZBs, then no miss that counts). The confirming test is the recipe in `confirm`: the Stand-in logged a miss for this visit's requests. Its Clue is not built yet.

## Ruled out

A refusing indexer or a gone Source: the top-ups found the releases and they played.

## Fix

#79 (a Recording covers a cold and a warm round), #229 (preflight refuses a Recording the last run missed), #235 (PR #236: misses of never-played releases are listed, not counted), #240 (a miss is a refusal, so it writes no dead mark). #273 archives the replayed Recording altogether.

## History

- 2026-11-24: converted from the casebook sweep (draft C1).
