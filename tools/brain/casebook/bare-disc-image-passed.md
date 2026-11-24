---
id: bare-disc-image-passed
title: A bare disc image passed the health check, and AltMount does not play disc images.
kind: check miss
step: health_batch
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "check miss | import_wait not ok | *no files with allowed extensions found*"
  - rules: 1
    sign: "fail | import_wait not ok | *no files with allowed extensions found*"
confirm:
  - clue: check-passed-source
    answer: yes
  - clue: nzb-largest-file-disc-image
    answer: yes
  - clue: altmount-no-allowed-extension
    answer: yes
fix: "#120 (PR #139): a bare .iso or .img as the largest file is blocked as \"Disc image\" without sampling"
seen:
  - check: archive/2026-11-13T053200Z-baseline
    title: The Matrix
    play: cold 1
    date: 2026-11-13
  - check: archive/2026-11-13T053200Z-baseline
    title: The Matrix
    play: cold 2
    date: 2026-11-13
---

## What the viewer saw

A fail (the failure video); the next pick played in the warm round.

## Signs

- KaijuFlow's log: `No recognized file types — checking largest file: …MAMA.iso`, then "Auto-queueing (verified 1/2)" for it.
- AltMount's log: `error="no files with allowed extensions found (allowed: [.mkv .mp4 .avi .ts .m2ts .vob .m4v .mov .wmv .mpg .mpeg ...])"`, and before it `msg="UDF: file ICB read failed, dropping file from listing" path=BDMV/BACKUP/CLIPINF/00008.clpi`.

## Cause

The NZB (`The.Matrix.1999.4K.Remastered.Multi.Complete.UHD.BluRay-MAMA`, on the one-page side) held one 71 GB `.iso` plus `.nfo`, `.url` and par2 files. With no video or archive name found, the check sampled the largest file whatever it was, and passed it. AltMount does not play disc images.

## How it was proved

By the logs in #120's triage and by unit tests. Not proved live after the fix: the test copies drop disc images by title (#109), so runs no longer meet one. The confirming test is the recipe in `confirm`: the check passed the Source, the NZB's largest file is a disc image, and AltMount found no file with an allowed extension. Its Clues are not built yet.

## Ruled out

Nothing tested and rejected yet.

## Fix

#120 (PR #139): a bare `.iso` or `.img` as the largest file is blocked as "Disc image" without sampling. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft A7).
