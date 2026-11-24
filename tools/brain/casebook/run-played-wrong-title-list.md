---
id: run-played-wrong-title-list
title: A run was started without its title list, so it played titles its Recording does not hold.
kind: nothing to play
step: indexer_page
whose: test-only
status: open
match:
  - rules: 1
    sign: "nothing to play | indexer_page ok | *"
confirm:
  - clue: titles-not-in-recording
    answer: yes
fix: none yet
seen:
  - check: 2026-11-24T060037Z-grouped-265
    title: all 10 titles (40 of 40 plays)
    date: 2026-11-24
---

## What the viewer saw

In the run: 40 of 40 plays failed with "no Sources". A viewer never meets it: it only happens in a replayed test.

## Signs

`CHECK.txt`: "Top picks played, KaijuFlow: cold 0 of 20, warm 0 of 20", every failure "no Sources", and misses for searches of titles not on the Recording (`q=Inception 2010`, `q=Interstellar 2014`).

## Cause

The run was started without `--titles-file`, so it played the built-in ten titles against `kf-265`, which holds none of them.

## How it was proved

The session's own mistake (comment on #265). The confirming test is the recipe in `confirm`: the run's titles are not in its Recording. Its Clue is not built yet.

## Ruled out

Nothing tested and rejected yet.

## Fix

The run is marked never compared with; #267 makes the preflight pass over it. Nothing stops the same mistake.

## History

- 2026-11-24: converted from the casebook sweep (draft C2).
