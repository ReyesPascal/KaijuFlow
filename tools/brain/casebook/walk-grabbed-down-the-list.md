---
id: walk-grabbed-down-the-list
title: After one failed grab the Walk grabbed far down the list, doubling with each failure.
kind: slow play
step: nzb_fetch
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "slow play | first_byte ok | *"
  - rules: 1
    sign: "fallback | nzb_fetch not ok | *"
confirm:
  - clue: walk-grabs-over-cap
    answer: yes
fix: "#228 (Walk module, a failed grab replaced once, 30 grabs per Walk), #243 (grabs sorted by ADR 0004), #255 (a clicked entry's walk-on); PRs #252 and #259"
seen:
  - check: 2026-11-23T173423Z-baseline-218
    title: several titles (1840 grabs in 16 visits)
    date: 2026-11-23
  - check: 2026-11-23T183239Z-baseline-218
    title: several titles (162 grabs of 63 releases)
    date: 2026-11-23
  - check: 2026-11-23T190950Z-grouped-219
    title: Joker
    play: cold 2 (318 of 353 grabs in 4.7 s)
    date: 2026-11-23
---

## What the viewer saw

Nothing direct. Live it would spend most of the day's 450 downloads; in a replay every grab missed. In Joker, cold 2 of #219, video came 30.9 s after the press (with a fallback).

## Signs

KaijuFlow's log: dozens of `❌ Grab failed for #N <release>` lines within the same second, right after `❌ Prepare failed for #1`; the Stand-in's misses for releases never played (#218's re-run: 162 grabs of 63 releases; #219: 353, 318 of them in Joker cold 2 in 4.7 s; #218's first try: 1840).

## Cause

A failed grab was replaced twice (`pullReplacement()` was called but `cs.replaced` never set, so the dead-candidate pass pulled a second replacement), and there was no ceiling, so failures doubled down the list. It ran before the play, while a fallback prepared.

## How it was proved

By a Parity test that went red first (40 Sources whose grabs answer 404) and by #250's count: 182 NZB requests (was 539), no Walk reached its 30-grab stop. The confirming test is the recipe in `confirm`: one Walk made more grabs than its cap allows. Its Clue is not built yet.

## Ruled out

Nothing tested and rejected yet.

## Fix

#228 (Walk module, a failed grab replaced once, 30 grabs per Walk), #243 (grabs sorted by ADR 0004), #255 (a clicked entry's walk-on follows the same rules); PRs #252 and #259. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft B2).
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | nzb_fetch not ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
