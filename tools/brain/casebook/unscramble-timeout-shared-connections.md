---
id: unscramble-timeout-shared-connections
title: Unscramble ran out of its 15 s because several Sources were prepared at once.
kind: fail
step: unscramble
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "check miss | import_wait not ok | *all files failed validation*"
  - rules: 1
    sign: "fail | import_wait not ok | *all files failed validation*"
confirm:
  - clue: unscramble-timeout
    answer: yes
  - clue: unscrambles-overlap
    answer: yes
  - clue: altmount-missing-volumes
    answer: yes
fix: "#119 (PR #139): Unscrambles run one at a time, each with its own 15 s; #192 and #226 prepare only the played Source; #245 stops an unordered set from going up"
seen:
  - check: archive/2026-11-13T053200Z-baseline
    title: Inception
    play: cold 2
    date: 2026-11-13
  - check: archive/2026-11-13T044542Z-baseline (stopped, no record of its own)
    title: Inception
    play: cold 1
    date: 2026-11-13
  - check: archive/2026-11-13T044542Z-baseline (stopped, no record of its own)
    title: Inception
    play: cold 2
    date: 2026-11-13
---

## What the viewer saw

A fail: the failure video (there was no fallback then).

## Signs

- KaijuFlow's log: `[KF-STEP] {"step":"unscramble",...,"title":"Inception.2010.2160p.UHD.BluRay.Remux.HEVC.DTS-HD.MA.5.1-FGT","result":"timeout","parts":210}` with `"ms":15080`, and at the same moment a second `timeout` (`...-4K4U`, 197 parts, 15061 ms); "Auto-queueing all 3 verified result(s)" before them.
- AltMount's log: `Skipping RAR archive group with missing volume(s)" first_file=f81016b5deb059e74cdf735057726de4.10 parts=210` and `no files were successfully processed (all files failed validation)`.

## Cause

Auto-queue prepared all three verified Sources when play was pressed, so two large Unscrambles (407 parts in all) shared the 12 health-check connections. The top pick's 210-part set needed about 15 s, right at the limit; on a timeout the scrambled original went up and AltMount refused it. Whether it played came down to a second either way. See also [several-sources-prepared](several-sources-prepared.md).

## How it was proved

By the logs and timing in the triage of #119: about 30 to 37 ms per part on 12 connections; alone, a set this size takes about 7 s. After the fix, Test 1 (`2026-11-15T115540Z-baseline`) played Inception in both cold rounds. The confirming test is the recipe in `confirm`: the played release's `unscramble` step ended `timeout`, another Source's Unscramble ran at the same time, and AltMount reported missing volumes. Its Clues are not built yet.

## Ruled out

Nothing tested and rejected yet.

## Fix

#119 (PR #139): Unscrambles run one at a time, each with its own 15 s from its turn. Later #192 and #226 stopped preparing more than the played Source, and #245 stops a set that still can't be put in order from being uploaded ([unscramble-read-error](unscramble-read-error.md)). Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft A3).
- 2026-11-24: a `check miss` sign added (#283): the Source passed its Play-time check before AltMount refused it, so Diagnosis fingerprints the failure as a check miss when the play still ended in video (a fallback that hides a check miss, README "Not signs").
