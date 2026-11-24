# The Casebook

One file per known cause of a play going wrong (spec #279, #281): what the viewer saw, the signs, the cause, how it was proved, what was ruled out, the fix and its history. Diagnosis reads it to put the leads for a new failure in order; **only a passing confirming test names a cause**, every time. A look-alike failure for an entry whose confirming test does not run yet is *suspected*, never *found*.

- `<id>.md`: one entry (the format below).
- `index.json`: what programs need from every entry, **generated** from the files, never edited by hand.
- `../casebook.py`: `python3 -I tools/brain/casebook.py index` rewrites the index; `python3 -I tools/brain/casebook.py check` lists every problem (exit 1 when there is one). `npm run check:brain` runs the check (`test_casebook.py`): it fails when an entry breaks the format, when the index and the files disagree, or when an entry claims proved without a confirming test that runs.

After changing, adding or removing an entry, run the index command and commit the index with it. `python3 -I tools/brain/diagnosis.py record <check folder>` adds a diagnosed check's proved occurrences and ruled-out leads to the entries and writes the index itself. A new entry comes from a solved Case log: `python3 -I tools/brain/diagnosis.py case entry <case> <entry id>` writes it (its match, recipe and ruled-out list) and the index ([formats, Case log](../docs/formats.md#case-log)).

## The format

An entry starts with front matter between two `---` lines, then the seven sections.

```
---
id: unscramble-read-error
title: Unscramble could not read a Scrambled RAR set, so the scrambled original went up and AltMount refused it.
kind: fallback
step: unscramble
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "fallback | import_wait not ok | *all files failed validation*"
confirm:
  - clue: unscramble-read-error
    answer: yes
fix: "#245 (PR #252): a read-error is retried once, then the Source is not uploaded"
seen:
  - check: 2026-11-23T190950Z-grouped-219
    title: Joker
    play: cold 2
    date: 2026-11-23
---

## What the viewer saw
## Signs
## Cause
## How it was proved
## Ruled out
## Fix
## History
```

The fields, all ten, in this order:

| Field | What it holds |
|---|---|
| `id` | The file name without `.md`: lower-case words joined by `-`. |
| `title` | One plain sentence naming the cause. |
| `kind` | What the check saw: `fail`, `fallback`, `check miss`, `slow play`, `wrong title`, `nothing to play`. |
| `step` | The step where the play first went wrong (the cause's step, which can come before the step where it failed): a step-line name ([formats](../docs/formats.md#step-lines-kf-step)), `search` (spec #279) or the old list-time check's `health_batch`. |
| `whose` | Who can fix it: `KaijuFlow`, `AltMount`, `indexer`, `Usenet`, `test-only` (it only happens in a test: a replayed Recording, the test machine's state), or `unknown` (only while the entry is `open`). A cause that isn't KaijuFlow's gets a workaround, no ticket. |
| `status` | `open`, `fix in progress`, `fixed awaiting proof` (the fix is merged, no Drill-down has played it yet), `proved fixed`, `reopened`. `proved fixed` and `reopened` claim proof: they need a `confirm` recipe whose every Clue is in the Clue library (`tools/brain/clues.py`). |
| `match` | The signs Diagnosis looks a failure up by, each with `rules` (the masking rules' version it is written against) and `sign`, a fingerprint pattern `<kind> \| <step> ok\|not ok \| <reason>`: the kind, the last step line and whether it was ok, and the `play_failed` reason with its variable parts masked. `*` stands for anything (a whole part, or inside the reason). A match only orders the leads. |
| `confirm` | The confirming test: a recipe of Clues, each a `clue` name with the `answer` (`yes` or `no`) that proves the cause on this failure's own evidence. Until a Clue is built the recipe names the Clue it will need. An old cause whose evidence is gone says `none (no evidence kept)`. |
| `fix` | The ticket and PR, the workaround for a cause that isn't KaijuFlow's, or `none yet`. |
| `seen` | Every occurrence: `check` (the run or check folder, or what is left of it), `title`, `play` (which press, or the evidence folder Diagnosis proved it in; optional), `date` (`YYYY-MM-DD`), `rules` (the masking rules' version Diagnosis matched it with; optional, absent on the converted ones). The index counts them and gives the first and last date. Diagnosis adds an occurrence only when the entry's confirming test passed on that failure (`diagnosis.py record`, [formats](../docs/formats.md#diagnosis)). |

Values are plain text, or a JSON string in double quotes when they hold a `#`, a `: `, or start with a sign YAML reads otherwise (`"`, `[`, `-`, `*` and the like); the check names the line that needs quotes. The front matter is a small subset of YAML: `field: value`, and lists under `field:` whose items are a value (`  - value`) or `key: value` pairs (`  - key: value`, then `    key: value`).

The sections, all seven, in this order, none empty, nothing before the first: **What the viewer saw**, **Signs** (log lines and step lines, quoted), **Cause**, **How it was proved** (and what the confirming test checks), **Ruled out** (hypotheses tested and rejected, with the test; "Nothing tested and rejected yet." when none), **Fix** (and what proof waits on), **History** (one dated line per change: converted, merged, split, reopened). An entry converted from the casebook sweep (`~/kaijuflow-notes/diagnosis/casebook-draft.md`, 2026-11-24) names its draft label in History, `(draft A1)`.

## Not signs

Lines that look like a cause and are not; the sweep's notes for Diagnosis (draft E1 to E5).

- **AltMount's reason is in its own log first.** Its HTTP answer is a 500 (`INTERNAL_SERVER_ERROR`); KaijuFlow copies the message into `❌ Failed: AltMount could not process the Source: {...}`, but the detail (which file, which volume) is only in AltMount's log, on the lines `Processing failed` and `Item failed` with the queue id (E1).
- **"First segment has no data" is not a sign.** AltMount prints this WARN for dozens of files at the start of every run (for example `MWin1vsbfNbX4YaMqVvQmrzikUi8qcM9.7z.003`, par2 files) for sets that play. #219's findings named it as a sign; the real cause was [unscramble-read-error](unscramble-read-error.md) (E2).
- **"Skipping RAR archive group with missing volume(s)" with `first_file=<hash>.10`** means AltMount got a number-named set out of order. KaijuFlow's `unscramble` step for the same title tells which: `read-error` ([unscramble-read-error](unscramble-read-error.md)), `timeout` ([unscramble-timeout-shared-connections](unscramble-timeout-shared-connections.md)), or a RAR4 set ([scrambled-rar4-set](scrambled-rar4-set.md)) (E3).
- **"Retrying inconclusive fast-fail STATs ... context deadline exceeded"** shows in most runs of AltMount's log with no failed play beside it (E4).
- **A fallback hides a check miss.** [unscramble-read-error](unscramble-read-error.md) and [no-extension-file-passed](no-extension-file-passed.md) are both Sources the check passed and AltMount refused; a run's count shows them only as fallbacks, or, for the second, not at all (E5).
