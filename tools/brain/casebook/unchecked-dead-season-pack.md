---
id: unchecked-dead-season-pack
title: A dead season pack reached AltMount without a check (an Unchecked Source).
kind: fail
step: health_batch
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "fail | import_wait not ok | *fast-fail segment check failed*"
confirm:
  - clue: played-source-unchecked
    answer: yes
  - clue: altmount-fast-fail-refused
    answer: yes
fix: "#190 (PR #210): no Unchecked Source goes to AltMount; #203 (PR #225): the check samples the wanted episode's file; #191 deleted the list-time check"
seen:
  - check: 2026-11-20T223814Z-baseline-189
    title: The Twilight Zone S02E06
    play: cold 1
    date: 2026-11-20
  - check: 2026-11-20T223814Z-baseline-189
    title: The Twilight Zone S02E06
    play: cold 2
    date: 2026-11-20
  - check: 2026-11-21T002421Z-baseline-205-browse-pause
    title: The Twilight Zone S02E06
    play: cold 1
    date: 2026-11-21
  - check: 2026-11-21T002421Z-baseline-205-browse-pause
    title: The Twilight Zone S02E06
    play: cold 2
    date: 2026-11-21
---

## What the viewer saw

A fail: the failure video.

## Signs

- KaijuFlow's log: `⚠️ Smart mode: no healthy result found after checking` (twice in #189, once per cold round). Per the grilling on #190, the Source at list position 7 then played with no check of its own.
- AltMount's log: `level=WARN msg="Skipping file due to early fast-fail segment check error" component=nzb-processor file=The.Twilight.Zone.(1959).S02.(1080p.BDRip.x265.10bit.FLAC.2.0.-.Frys).[TAoE].part001.rar`, then `error="fast-fail segment check failed: no regular files were successfully processed (all files failed validation)"` (`altmount-kf-test.log:1847` of `2026-11-20T223814Z-baseline-189`). AltMount's probe found 8 of 8 sampled articles missing.

## Cause

The old list-time check (Smart mode) checked positions 1 to 6, found them all blocked, and kept every Source it had not checked. Position 7, a season pack whose articles are gone from Newshosting, became the top pick unchecked. The warm rounds' Source (edge2020) was also unchecked and played by luck. A related flaw: the check sampled the first video of a loose-file season pack, not the wanted episode's file.

## How it was proved

By the logs and the grilling on #190 (2026-11-20); after the fix, #218's runs played the title in every round. The confirming test is the recipe in `confirm`: the played Source has no check line of its own, and AltMount refused it at its fast-fail check. Its Clues are built (#283) and tried on real captures: the recipe proves the cause on #189's cold 1 and rules it out on #219's The Witcher. In a build from before the Play-time check (#190), `played-source-unchecked` reads the old check's `Smart mode: no healthy result found after checking` line.

## Ruled out

Nothing tested and rejected yet.

## Fix

#190 (PR #210): KaijuFlow never hands AltMount an Unchecked Source, and Best walks down the list until one is healthy. #203 (in PR #225): the check samples the wanted episode's file. #191 deleted the list-time check. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft A2).
- 2026-11-24: its confirming recipe runs (#283): Clues played-source-unchecked, altmount-fast-fail-refused.
