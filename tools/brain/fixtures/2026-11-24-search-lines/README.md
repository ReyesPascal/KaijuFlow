Captured for Kaiju Search's dev lines (#285, spec #279: `test_evidence.py`): the `search` step lines KaijuFlow really writes, so the evidence step is tested on KaijuFlow's own output (review rule 2), not on invented lines.

How: on 2026-11-24, at commit f8f3dc3 of `kaiju-search-285`, KaijuFlow's `kaijuSearch` ran with the dev switch on (`devDiagnostics`) for The Witcher S01E01 (`tt5180504:1:1`, inside `withStepRef`, as the list path runs it), against one fake NinjaCentral (caps `q`, `imdbid`) that answered every query with `../2026-11-23-failed-play/search-answer.xml`, the real stored answer of the failed play's search. Both ways (by IMDb, by name) got that answer, so both lines list its two real releases, each sure.

- `kaijuflow-search.log`: the two `[KF-STEP]` lines it printed, as printed. Nothing is changed; they carry no docker timestamp (the test puts the failed play's time in front of them when it adds them to that play's KaijuFlow log).
