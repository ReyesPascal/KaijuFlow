---
id: no-extension-file-passed
title: A file with no extension passed the health check, and AltMount accepts only listed extensions.
kind: check miss
step: play_check
whose: KaijuFlow
status: open
match:
  - rules: 1
    sign: "check miss | import_wait not ok | *does not match allowed extensions*"
  - rules: 1
    sign: "fallback | import_wait not ok | *does not match allowed extensions*"
confirm:
  - clue: check-passed-source
    answer: yes
  - clue: nzb-file-without-extension
    answer: yes
  - clue: altmount-extension-refused
    answer: yes
fix: none yet
seen:
  - check: 2026-11-23T183239Z-baseline-218
    title: The Witcher S01E01
    play: cold 1 (a backup prepare, AltMount queue item 27)
    date: 2026-11-23
---

## What the viewer saw

Nothing that time: it was a backup prepare beside a play that had already started. Had it been the played Source, a fallback or a fail.

## Signs

- KaijuFlow's log: `{"step":"play_check",...,"title":"The.Witcher.S01E01.2160p.NF.WEB-DL.DDPA5.1.HDR.DV.HEVC-SiC-AsRequested","status":"verified"}`, then `📦 #5 Backup match (MKV)` and `❌ Failed: AltMount could not process the Source: ... "message":"file 'The.Witcher.S01E01.2160p.NF.WEB-DL.DDPA5.1.HDR.DV.H…`.
- AltMount's log: `level=WARN msg="File does not match allowed extensions" filename=The.Witcher.S01E01.2160p.NF.WEB-DL.DDPA5.1.HDR.DV.HEVC-SiC-AsRequested`, then `Processing failed ... error="file '...' does not match allowed extensions (allowed: [.mkv ...])"`.

## Cause

The NZB's one file is named like the release, with no extension. The check passed it as video; AltMount accepts only listed extensions. ADR 0009 says an NZB with no file the check can name is blocked, so the check's naming rule seems to accept this name.

## How it was proved

The refusal is proved by both logs. Why the check passed it is suspected only, from the `verified` status (the check's code was not read). The confirming test is the recipe in `confirm`: the check passed the Source, its NZB's file has no extension, and AltMount refused the extension. Its Clues are not built yet.

## Ruled out

Nothing tested and rejected yet.

## Fix

None yet; no ticket names it. The backup prepare that reached it was removed by #192, so it can only hurt now if such a Source is played.

## History

- 2026-11-24: converted from the casebook sweep (draft A12); it was new in that sweep. It is not counted in that run's fallbacks.
