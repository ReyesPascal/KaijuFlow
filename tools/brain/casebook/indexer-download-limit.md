---
id: indexer-download-limit
title: An indexer at its download limit refused the NZB of a good Source.
kind: fail
step: nzb_fetch
whose: indexer
status: fixed awaiting proof
match:
  - rules: 1
    sign: "fail | nzb_fetch not ok | *limit reached*"
  - rules: 1
    sign: "fallback | nzb_fetch not ok | *limit reached*"
confirm: none (no evidence kept)
fix: "Workaround: ADR 0004 keeps such Sources alive (#51); a Walk skips an indexer that refuses a grab for the rest of that Walk (#243, #255)"
seen:
  - check: 2026-11-09 evening cold run (logs lost)
    title: The Wire
    date: 2026-11-09
  - check: 2026-11-09 evening cold run (logs lost)
    title: Whiplash
    date: 2026-11-09
  - check: 2026-11-09 evening cold run (logs lost)
    title: Severance
    date: 2026-11-09
  - check: 2026-11-09 evening cold run (logs lost)
    title: Severance
    date: 2026-11-09
  - check: 2026-11-09 evening cold run (logs lost)
    title: Better Call Saul
    date: 2026-11-09
  - check: 2026-11-09 evening cold run (logs lost)
    title: Better Call Saul
    date: 2026-11-09
---

## What the viewer saw

The failure video for a pick that was a good Source; it looked like a bad Source.

## Signs

The indexer's answer "Request limit reached" (DrunkenSlug) on the NZB download, in KaijuFlow's log as a failed grab. No AltMount line, since nothing reached it. The exact log lines are lost with the old machine.

## Cause

DrunkenSlug's daily grab limit ran out at 16:18 UTC during the 2026-11-09 evening run, and every DrunkenSlug pick after that failed. The indexer refused; the Source was fine. Under ADR 0004 the Sources stayed alive.

## How it was proved

By reading the run's logs at the time (the old Speed Check page's corrected section "What broke on the other two"). No evidence is kept, so there is no confirming test.

## Ruled out

A bad Source: the Sources played once the limit reset.

## Fix

Not KaijuFlow's to fix; the workaround: ADR 0004 keeps such Sources alive (#51). Today a Walk skips an indexer that refuses a grab for the rest of that Walk and moves on (#243, and #255 for a clicked list entry, both merged), so a press walks on instead of showing the failure video. #65 (move an indexer's Sources down after "limit reached") was closed unbuilt with spec #58. For timed runs the Cap rule stops the pass.

## History

- 2026-11-24: converted from the casebook sweep (draft A4). The six picks were 2nd or 3rd tries in the 2026-11-09 evening cold run.
