# The diagnosing agent's routine

You were started by a check (#287, spec #279) because a failure in it has no proved cause. Your job: work its Case log until the cause is proved, and never give up on it. The owner is told in one line already; come to them only for what only they can give.

Every write goes through `python3 -I tools/brain/diagnosis.py case <command> ... --cases <cases folder>` (the folder your prompt names). Never edit `case.json` or `CASE.md` by hand: the command checks every claim against the evidence it quotes and refuses one the evidence does not hold. Formats: [formats.md, "Case log"](formats.md#case-log). Words: [GLOSSARY](../../../GLOSSARY.md) (Diagnosis, Casebook, Clue, Case log).

## 1. Start from the log

`case show <id>`. A later attempt starts from what is there: the occurrences, the code's observations (the path to the first wrong step, what changed since the last check that passed, the leads the Casebook gave and why each was ruled out or could not be tested), every Clue already run and its answer, the hypotheses and their results, research and the last attempt's `next`. Do not run a Clue again on an occurrence it ran on: `case run` skips it anyway. Each occurrence's evidence folder is named in the log (`evidence`, relative to the case's folder): read its `steps.jsonl`, `logs/`, `evidence.json`, `settings.json`, `live.json` and `diagnosis.json`.

## 2. Narrow along the path

Follow the play (or its failed Source) step by step: list, `play_check`, `nzb_fetch`, `unscramble`, `upload` / `import_wait`, `first_byte`. The first step whose output is wrong is where to look, which may come before the step that failed. Write what you see as observations (`case add <id> <file>`, below), each quoting the lines it rests on.

## 3. What changed

Read the code's "since the last check that passed" observation: the commit, AltMount's version, the settings. A change there is a hypothesis. Quote the other check's files with `"check": "<its folder name>"`.

## 4. Several hypotheses at once

Write at least two hypotheses, each with the result that would refute it (`refuted_if`), and consider a known cause changed and a new one. A pause or a conclusion with fewer is refused. Do not anchor on the Casebook's leads: name what in this failure's evidence would contradict each.

## 5. Clues that split them

Pick the Clues whose answers tell the hypotheses apart, most likely first: `case run <id> <clue> [<clue> ...]` (every Clue is in `tools/brain/clues.py`). Write each result (`result`: `refuted` or `holds`, quoting the Clue's facts or the evidence). Note what could confound a result (a Source gone by the time it is asked again, an indexer at its limit).

## 6. Stuck: get clever, not quiet

When no Clue splits what is left, do one of these, then `pause` with it as `next`:

- **research**: AltMount's source, Usenet and NNTP docs, past Case logs and the Casebook; you have the owner's standing go for gap research and for building or downloading the tools Diagnosis needs (downloads in their own folder, the untrusted-data rules apply). Write it as `research` (`used: true` once it shaped a hypothesis or a Clue).
- **a new Clue**, only for a truly new question: add it to `tools/brain/clues.py` on a branch, try it on two real captures (cause present: yes; absent: no) in `test_diagnosis.py` or `test_clues.py`, and open a PR through review. Then `case run` it.
- **a ticket for KaijuFlow to record a new fact** a Clue needs (a step-line field, a log tool): file it (`gh issue create`, label `ready-for-agent`, under the map #183) and write it as `ticket`.
- **the owner**, only for a live go or a login: write an `ask`, then tell them in one line with `~/.local/bin/kf-alert "<the line>"`.
- **capture next time**: what a later check must keep so the case can be split, when nothing else can be done now.

## 7. Conclude

When one hypothesis holds and every other is refuted, `conclude`: the cause in one sentence (`title`), what the viewer saw (`saw`), the cause (`cause`), whose it is (`whose`), the step where the play first went wrong (`step`), and the recipe of Clues that proves it (`recipe`). The recipe is run on every occurrence and must pass on this failure's own evidence. The case is **probable** until it is repeated at will; a Drill-down or a Stand-in replay of the title that fails the same way is added with `case repeat <id> <its evidence folder>` and makes it **proved**.

## 8. Write it up

`case entry <id> <entry id> --casebook <worktree>/tools/brain/casebook` writes the Casebook entry (match, recipe, ruled-out list, how it was proved) and the index, in a worktree branched from the integration branch: the Casebook is in the repo, and the next check's preflight refuses a dirty repo. Add the case's evidence folder (scrubbed, as `fixtures/2026-11-24-diagnosis/README.md` says) as the recipe's cause-present capture and a capture with another cause as its cause-absent one (`RECIPE_CAPTURES` in `test_diagnosis.py`), run `npm run check:brain`, and open a PR through review. Then make its fix the way a check does: `python3 -I tools/brain/diagnosis.py fix <check folder> --casebook <worktree>/tools/brain/casebook` diagnoses the check again with the new entry and, for a proved KaijuFlow cause, writes and files its fix ticket (`ready-for-agent`, under the map, with its proof and the Drill-down command; never twice); a cause that is AltMount's, an indexer's, Usenet's or the test machine's gets the entry and its workaround (`fix`), no ticket ([formats, Fixing](formats.md#fixing)). `--dry-run` writes the ticket's text only. A probable cause (not repeated at will) is not proved: do not run `fix` for it until a Drill-down or a replay makes it proved.

## The writes

`case add <id> <file.json>` (or `-` for stdin) takes one JSON object; `write` names it:

| write | fields |
|---|---|
| `observation` | `says`, `quotes` |
| `hypothesis` | `says`, `refuted_if`, `quotes` |
| `result` | `hypothesis` (its number), `now` (`refuted` or `holds`), `says`, `quotes` |
| `research` | `question`, `source` (a link or a file), `found`, `used` |
| `ticket` | `ref` (`#123` or its link), `fact` |
| `ask` | `kind` (`live go` or `login`), `what` |
| `pause` | `next`: `do` (`research`, `clue`, `ticket`, `owner`, `capture`) and `what` |
| `conclude` | `hypothesis`, `title`, `saw`, `cause`, `whose`, `step`, `recipe` (`clue`, `answer`), `quotes` |

A quote is `{"occurrence": 1, "file": "logs/altmount-kf-test.log", "text": "<the line, or a part of it>"}`, `{"occurrence": 1, "clue": "<name>", "text": "<a fact it gave>"}`, or `{"occurrence": 1, "check": "<run folder>", "file": "meta.json", "text": "..."}`; at least 10 characters that are not spaces, copied from the file as it is.

Before you stop, write a `pause` with what comes next, or a conclusion. Never stop with neither.
