---
id: unscramble-read-error
title: Unscramble could not read a Scrambled RAR set, so the scrambled original went up and AltMount refused it.
kind: fallback
step: unscramble
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "check miss | import_wait not ok | *all files failed validation*"
  - rules: 1
    sign: "fallback | import_wait not ok | *all files failed validation*"
  - rules: 1
    sign: "fail | import_wait not ok | *all files failed validation*"
confirm:
  - clue: unscramble-read-error
    answer: yes
  - clue: original-uploaded-after-unscramble
    answer: yes
  - clue: altmount-missing-volumes
    answer: yes
fix: "#245 (PR #252, 6efbc7c; ADR 0005 amended 2026-11-23): a read-error is retried once with the Walk's other checks stopped, then the Source is not uploaded"
seen:
  - check: 2026-11-21T050927Z-baseline-218-wifi
    title: The Witcher S01E01
    play: cold 1
    date: 2026-11-21
  - check: 2026-11-23T183239Z-baseline-218
    title: The Witcher S01E01
    play: cold 1
    date: 2026-11-23
  - check: 2026-11-23T183239Z-baseline-218
    title: The Witcher S01E01
    play: cold 2
    date: 2026-11-23
  - check: 2026-11-23T190950Z-grouped-219
    title: The Witcher S01E01
    play: cold 1
    date: 2026-11-23
  - check: 2026-11-23T190950Z-grouped-219
    title: The Witcher S01E01
    play: cold 2
    date: 2026-11-23
  - check: 2026-11-23T190950Z-grouped-219
    title: Upstream Color
    play: cold 1
    date: 2026-11-23
  - check: 2026-11-23T190950Z-grouped-219
    title: Joker
    play: cold 2
    date: 2026-11-23
---

## What the viewer saw

A fallback: video from the next Source, 2 to 8 s late. In Joker, cold 2 of #219, the video came 30.9 s after the press.

## Signs

- KaijuFlow's log: `[KF-STEP] {"step":"unscramble",...,"result":"read-error","parts":74}`, then `🧩 Unscramble skipped (read-error, 74 parts, 8769 ms): uploading the original NZB`, then `❌ Failed: AltMount could not process the Source: {"error":{"code":"INTERNAL_SERVER_ERROR",...,"message":"no files were successfully processed (all files failed validation)"}}`, then an `import_wait` step with `"ok":false`.
- AltMount's log for the same Source: `level=WARN msg="Skipping RAR archive group with missing volume(s)" first_file=7a870da9cbcc480a075cde6a2bd4dbd5.10 parts=74`, `level=WARN msg="Processing failed" ... error="no files were successfully processed (all files failed validation)"`, `level=ERROR msg="Item failed"`.
- `Skipping RAR archive group with missing volume(s)` with `first_file=<hash>.10` means AltMount got a number-named set out of order. KaijuFlow's `unscramble` step for the same release tells the causes apart: `read-error` (this entry), `timeout` ([unscramble-timeout-shared-connections](unscramble-timeout-shared-connections.md)), not RAR5 ([scrambled-rar4-set](scrambled-rar4-set.md)).
- The read-error line does not say which read failed or why; no NNTP error is logged beside it.

## Cause

The Source is a Scrambled RAR set. Unscramble could not read the first articles it needs (connection trouble on the news server, Newshosting, while the same Walk's checks were reading), so KaijuFlow uploaded the NZB with its parts still out of order. AltMount v0.4.0 reads the parts in name order, finds volumes missing and refuses every such set. The same sets unscramble fine in other runs (The Witcher HHWEB set: `unscrambled` in #189, #205, #218's first try and #250; `read-error` in #218's stopped try, #218's re-run and #219), so the Sources are good and the read trouble comes and goes. Why the reads fail is its own open entry: [unscramble-read-cause-unknown](unscramble-read-cause-unknown.md).

## How it was proved

The chain (read-error, original uploaded, AltMount refusal) is proved by the logs of every case, step by step. The confirming test is the recipe in `confirm`: the `unscramble` step for the played release ended `read-error`, the original NZB was uploaded after it, and AltMount's log for that Source says volumes were missing. Its Clues are built (#283) and tried on real captures: the recipe proves the cause on #219's The Witcher (cold 1) and rules it out on #189's The Twilight Zone (a look-alike: the same `all files failed validation`, refused at the fast-fail check).

## Ruled out

- KaijuFlow going over its own connection cap: #245's first test showed Unscramble and the checks already shared one cap.
- AltMount's `First segment has no data` WARN, which #219's findings first blamed: AltMount prints it for dozens of files at the start of every run, for sets that play (README, "Not signs"). The grilling of #239 corrected the cause to the read-error.

## Fix

#245 (merged with PR #252, 6efbc7c; ADR 0005 amended 2026-11-23): a read-error is retried once with the Walk's other checks stopped; if it fails again the Source is not uploaded and the Walk moves to the next Healthy Source, without a dead mark. #250's run had 40 Unscramble steps and no read-error, so the retry has not been seen working live yet. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft A1). Read-errors also show in the archived 2026-11-13 baseline (Inception's second pick, 197 parts; Dune, 190 parts); what those plays did next was not traced, so they are not in `seen`.
- 2026-11-24: a `check miss` sign added (#283): the Source passed its Play-time check before AltMount refused it, so Diagnosis fingerprints the failure as a check miss when the play still ended in video (a fallback that hides a check miss, README "Not signs").
- 2026-11-24: its confirming recipe runs (#283): Clues unscramble-read-error, original-uploaded-after-unscramble, altmount-missing-volumes.
