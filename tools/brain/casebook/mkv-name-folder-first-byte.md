---
id: mkv-name-folder-first-byte
title: A release name ending in .mkv made AltMount store a folder, and the first byte was refused.
kind: fail
step: first_byte
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "fail | first_byte not ok | *400*"
confirm: none (no evidence kept)
fix: "#85 (PR #105): such a Source is uploaded under a name without the extension; #86 (PR #100), ADR 0004: a 400 at the first byte no longer marks a Source dead"
seen:
  - check: 2026-11-10T073655Z-baseline-nc (lost with the old machine)
    title: Oppenheimer
    play: cold 1
    date: 2026-11-10
  - check: 2026-11-10T073655Z-baseline-nc (lost with the old machine)
    title: Oppenheimer
    play: cold 2
    date: 2026-11-10
---

## What the viewer saw

A fail (the failure video), and the good Source was marked dead.

## Signs

KaijuFlow got HTTP 400 twice at the first byte. AltMount's answer to the folder path: 400 `Cannot stream directory.` The offered path is `/complete/kaijuflow/<release>.mkv`, while the file is `/complete/kaijuflow/<release>.mkv/<release>.mkv` (#84's capture). Since #86 KaijuFlow logs one line with the status, the asked path and the names of the files offered.

## Cause

AltMount files a release whose name ends in a video extension as a folder with that name holding the file. KaijuFlow asked for the folder, and the 400 was treated as a bad Source.

## How it was proved

By capturing AltMount's real answer on a test AltMount (#84, PR #98); Test 1 then played Oppenheimer (FLUX, 2160p) in every round. The run's own logs are lost (numbers on #63), so there is no confirming test.

## Ruled out

A bad Source: the same Source played once it was uploaded under another name.

## Fix

#85 (PR #105): such a Source is uploaded under a name without the extension. #86 (PR #100), ADR 0004 "First byte": a 400 or a dropped connection at the first byte no longer marks the Source dead; only 404 or 410 does. Proof waits on a Drill-down.

## History

- 2026-11-24: converted from the casebook sweep (draft A6).
