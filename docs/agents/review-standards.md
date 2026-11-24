# Review standards

Four rules for reviewing a change. Each one comes from a real mistake (rules 1 to 3 on 2026-11-10, rule 4 on 2026-11-15).

**A fix-up is reviewed too.** Before a review's fix-up branch merges into the integration branch, run `/mattpocock-skills:code-review` and `/codex-review` on the fix-up's own diff (base: the integration tip it branched from), and fix what survives on the same branch. One review per fix-up. Why: #239's round 1 fix-up merged unreviewed, and a later review of its diff alone found three real bugs in it.

## 1. A test double refuses what the real thing refuses

Why: a fake that says yes to everything hides the mistakes the real thing would catch.

Example: the fake world answered a visit to a stopped copy, so a test passed that would have failed against a real, stopped copy. The fake should have refused the connection.

## 2. A reader of another program's output is tested on a captured sample

Why: lines we invent look the way we expect them to look; real output does not.

Example: the NzbDAV import reader (deleted since, #187) was tested on invented lines. It should have been tested on a real captured sample, kept as a scrubbed fixture, as AltMount's import reader is (`tools/brain/fixtures/2026-11-10/`).

## 3. Two commands that need the same setup share one path for it

Why: two copies of the same setup drift apart, and one command then behaves differently from the other.

Example: record and run started the one-page side differently. They should have called one shared step.

## 4. A test reaches the code that uses the change

Why: a test that pins only a new helper still passes when the caller never uses it.

Example: #131's test checked `healthCheckWorkerCount` but not that the coordinator passes its value to the health-check workers (both deleted since, #191). The test should have gone through the coordinator, or through the batch call it makes.
