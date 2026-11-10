# Review standards

Three rules for reviewing a change. Each one comes from a mistake found on 2026-11-10.

## 1. A test double refuses what the real thing refuses

Why: a fake that says yes to everything hides the mistakes the real thing would catch.

Example: the fake world answered a visit to a stopped copy, so a test passed that would have failed against a real, stopped copy. The fake should have refused the connection.

## 2. A reader of another program's output is tested on a captured sample

Why: lines we invent look the way we expect them to look; real output does not.

Example: the NzbDAV import reader was tested on invented lines. It should have been tested on a real captured sample, kept as a scrubbed fixture.

## 3. Two commands that need the same setup share one path for it

Why: two copies of the same setup drift apart, and one command then behaves differently from the other.

Example: record and run started the one-page side differently. They should have called one shared step.
