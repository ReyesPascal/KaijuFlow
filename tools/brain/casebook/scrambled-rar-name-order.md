---
id: scrambled-rar-name-order
title: A Scrambled RAR set was sent to AltMount in name order, which is not its volume order.
kind: fail
step: import_wait
whose: AltMount
status: fixed awaiting proof
match:
  - rules: 1
    sign: "fail | import_wait not ok | *all files failed validation*"
confirm: none (no evidence kept)
fix: "Workaround: ADR 0005, spec #42 (#43 to #46, PRs #47 to #49): Unscramble puts the parts in order before upload"
seen:
  - check: Brain check on port 1338 (logs lost)
    title: Interstellar
    date: 2026-11-09
---

## What the viewer saw

A fail: AltMount refused a complete Source that NzbDAV played.

## Signs

AltMount reported missing volumes for parts named `<hash>.10` to `<hash>.103` (the same `Skipping RAR archive group with missing volume(s)` and `all files failed validation` lines as [unscramble-read-error](unscramble-read-error.md), now that the logs say it). All 46,966 video articles were present.

## Cause

AltMount v0.4.0 orders RAR parts by the numbers in their names, which in a Scrambled RAR set do not match the real volume order.

## How it was proved

On port 1338 by renaming the parts in their real order by hand (AltMount then streamed the same bytes as NzbDAV), then by the re-check #46: `Unscrambled RAR set: 94 parts (3091 ms)`, bytes identical at the start, 50% and 90%. The logs are lost, so there is no confirming test.

## Ruled out

Missing articles: a STAT of every article found all 46,966 video articles present.

## Fix

Not KaijuFlow's to fix (AltMount's ordering); the workaround: ADR 0005, spec #42 (#43 to #46, PRs #47 to #49): Unscramble before upload. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft A8). The release was Interstellar (NOSiViD).
