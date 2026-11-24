---
id: compressed-7z-passed
title: A compressed 7z passed the health check as playable, and AltMount streams only stored 7z.
kind: check miss
step: health_batch
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "check miss | import_wait not ok | *Only uncompressed files are supported*"
  - rules: 1
    sign: "fail | import_wait not ok | *Only uncompressed files are supported*"
confirm: none (no evidence kept)
fix: "ADR 0008 (plain video only), replaced by ADR 0009 and built in #184 (PR #197): compressed archives are blocked"
seen:
  - check: Test 2's cancelled record (logs deleted, ADR 0008)
    title: "Avengers: Endgame"
    play: round 1
    date: 2026-11-15
  - check: Test 2's cancelled record (logs deleted, ADR 0008)
    title: "Avengers: Endgame"
    play: round 2
    date: 2026-11-15
---

## What the viewer saw

A fail in both rounds.

## Signs

KaijuFlow's health check: `Verified: compressed archive`, every sampled segment found. AltMount's log: `no valid files found in 7zip archive after filtering. Only uncompressed files are supported`.

## Cause

The check said the Source was complete, not that the Backend could stream what is inside it. AltMount streams only stored (uncompressed) 7z.

## How it was proved

By the logs of Test 2's first record (cancelled; read before they were deleted, ADR 0008), and by unit tests and the fake AltMount, which now refuses a compressed 7z with the real text. No evidence is kept, so there is no confirming test.

## Ruled out

Missing articles: every sampled segment was found.

## Fix

ADR 0008 (plain video only), replaced by ADR 0009 and built in #184 (PR #197): compressed archives are blocked. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft A9).
