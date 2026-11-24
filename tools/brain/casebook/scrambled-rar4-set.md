---
id: scrambled-rar4-set
title: A Scrambled RAR4 set went up out of order, because Unscramble reads RAR5 only.
kind: fail
step: unscramble
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "fail | import_wait not ok | *all files failed validation*"
confirm: none (no evidence kept)
fix: "ADR 0009, #184 (PR #197): a Scrambled RAR4 set is blocked by the health check"
seen:
  - check: Test 2's cancelled record (logs deleted, ADR 0008)
    title: Coherence
    date: 2026-11-15
---

## What the viewer saw

A fail.

## Signs

KaijuFlow: Unscramble answers that the set is not RAR5 and the original goes up. AltMount's log: `all files failed validation`.

## Cause

Unscramble reads only RAR5 volume numbers, so a scrambled RAR4 set goes up out of order and AltMount refuses it, as in [scrambled-rar-name-order](scrambled-rar-name-order.md).

## How it was proved

By the logs of Test 2's cancelled record (ADR 0008). No evidence is kept, so there is no confirming test.

## Ruled out

Nothing tested and rejected yet.

## Fix

ADR 0009, #184 (PR #197): a Scrambled RAR4 set is blocked by the health check. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft A10). Coherence was on the hard list.
