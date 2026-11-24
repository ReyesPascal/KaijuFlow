---
id: several-sources-prepared
title: Auto-queue prepared several Sources at once, so prepares competed for connections and import slots.
kind: slow play
step: import_wait
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 2
    sign: "slow play | first_byte ok | *most time in import_wait*"
confirm:
  - clue: several-sources-prepared
    answer: yes
fix: "#192 (prepare only the played Source; the 25 s first-Source switch kept), #226 (Auto-queue deleted), in PR #225"
seen:
  - check: 2026-11-15T115540Z-baseline
    title: every cold play (about 35 imports for 20 cold plays)
    date: 2026-11-15
  - check: 2026-11-23T183239Z-baseline-218
    title: every cold play
    date: 2026-11-23
---

## What the viewer saw

Slower cold starts, and the Unscramble timeouts of [unscramble-timeout-shared-connections](unscramble-timeout-shared-connections.md).

## Signs

"Auto-queueing all 3 verified result(s)" in KaijuFlow's log; about 35 AltMount imports for 20 cold plays in Test 1.

## Cause

Auto-queue (default `all`) prepared every verified Source of the list on AltMount, not only the played one, so prepares competed for connections and AltMount's import slots.

## How it was proved

Proved for the Unscramble contention ([unscramble-timeout-shared-connections](unscramble-timeout-shared-connections.md)); the speed cost is folded into #219's result, not measured alone. The confirming test is the recipe in `confirm`: more than one Source was prepared for one press. Its Clue is not built yet.

## Ruled out

Nothing tested and rejected yet.

## Fix

#192 (prepare only the played Source; the 25 s first-Source switch kept), #226 (delete Auto-queue), in PR #225. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft B5). Seen in every run up to `2026-11-23T183239Z-baseline-218`; `seen` lists the runs the sweep quoted.
- 2026-11-24: its slow-play sign names the last step line, `first_byte ok` (was `slow play | import_wait ok | *`, which no fingerprint gives: a slow play's video came, so its last step line is `first_byte`; where the time went is the confirming test's to tell; review of #279).
- 2026-11-24: its slow-play sign is `slow play | first_byte ok | *most time in import_wait*` (rules 2): the step of the played Source that took the most time, `import_wait`, as rules 2's fingerprint gives it (review of #279, round 2).
