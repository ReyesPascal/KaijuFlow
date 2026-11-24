---
id: unscramble-read-cause-unknown
title: Why Unscramble's first-article reads fail is not known.
kind: fallback
step: unscramble
whose: unknown
status: open
match:
  - rules: 1
    sign: "fallback | import_wait not ok | *all files failed validation*"
confirm:
  - clue: unscramble-read-error
    answer: yes
  - clue: provider-read-failed
    answer: yes
fix: none yet
seen:
  - check: 2026-11-21T050927Z-baseline-218-wifi
    title: The Witcher S01E01
    date: 2026-11-21
  - check: 2026-11-23T183239Z-baseline-218
    title: The Witcher S01E01
    date: 2026-11-23
  - check: 2026-11-23T190950Z-grouped-219
    title: The Witcher S01E01
    date: 2026-11-23
---

## What the viewer saw

The fallbacks of [unscramble-read-error](unscramble-read-error.md): this entry is the open part of that cause.

## Signs

KaijuFlow's `unscramble` step ends `read-error`. The log line gives no NNTP error. Seen in #218's stopped try, #218's re-run and #219, none in #250.

## Cause

Not known. Suspected: connection trouble on Newshosting while the same Walk's checks read.

## How it was proved

Not proved. The chain after the read-error is proved ([unscramble-read-error](unscramble-read-error.md)); the read-error itself is not. The confirming test it will need: the `unscramble` step ended `read-error`, and the news server's answer to the failed read was an error. That second Clue needs a fact KaijuFlow does not record yet (the NNTP error of the failed read).

## Ruled out

KaijuFlow going over its own connection cap (#245's first test).

## Fix

None yet. [unscramble-read-error](unscramble-read-error.md)'s fix (#245) keeps such a Source from being uploaded, but not the read from failing.

## History

- 2026-11-24: converted from the casebook sweep (draft D1).
