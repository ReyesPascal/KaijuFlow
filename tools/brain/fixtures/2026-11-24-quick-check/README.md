The real quick check `2026-11-24T122253Z-quick-check` (`~/kaijuflow-notes/brain-runs/`), the first with NinjaCentral and DrunkenSlug both switched on, for the judge and the indexer table (#304, spec #298 stories 23 to 25; `test_quickcheck.py`, `RealCheckTest`).

- `kaijuflow-steps.log`: every `[KF-STEP]` line of its `logs/kaijuflow-test.log`, as written (dev switch on: the `search` lines list each indexer's Sources by name). They hold no key.
- `standin.log`: its `logs/standin.log`, unchanged (`RECORD` lines name the indexer, the query and the NZB's short id; no key).
- `check.json`: `indexers`, `titles` and `started` from its `meta.json`, and each visit of its `raw.json` without its `steps` and `imports` (the test takes the steps from `kaijuflow-steps.log` through `quickcheck.visit_steps`, as the check does).
- `meta.json` and `raw.json`: its own files, unchanged, as the check wrote them (written before #304, so no `found` and no indexer table), for the Speed Check page (`checkpage.py`, #273; `test_checkpage.py`), whose expected numbers are its `report.md`'s.

Both indexers answered every page in it; the tests make one down by editing these lines (its pages `ok` false, its `search` and check lines gone).
