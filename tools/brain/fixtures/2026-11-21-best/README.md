Captured on tuning-183 (spec #183, review fix-up of PR #225) for the brain tools' reading of a Best press (`test_brainreport.py` `BestPressFixtureTest`, `HeadStartRefusalFixtureTest`).

How: `npm run test:integration` runs the Play-time check's Parity suite (`tests/integration/parity-play-time-check.mjs`): real KaijuFlow, its stream list asked for through the addon with a fake indexer, then Best pressed through the real play routes, against the fake news server and the fake AltMount. Two scenarios of `tests/integration/parity/play-time-scenarios.mjs` collect every line KaijuFlow logs from the list request on, each after its time as `docker logs --timestamps` writes it, and hand them out in their result (`capture`, in `integration-results-parity-play-time-check.json`). Each file is one scenario's lines, joined and passed through `brainreport.scrub_text`; nothing else is changed.

- `kaijuflow-best-dead-first.txt` (`best-press-log-lines-the-brain-tools-read`): a list request starts the Head start (#206); Best checks three Sources: the first is dead, the second plays, the third is healthy and never prepared (#192); then the press writes `Best plays`.
- `kaijuflow-head-start-refused-first.txt` (`head-start-refusal-log-lines-the-brain-tools-read`): the Head start's first healthy Source is refused by AltMount before the press, so it prepares the next one; the press plays it with no new import.

The fake AltMount writes no log of its own, so these files hold KaijuFlow's lines only; AltMount's import reader is tested on its own capture (`fixtures/2026-11-10/`).
