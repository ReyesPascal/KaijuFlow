# Retired formats of the replayed Recording (ADR 0010, #273)

The sections of `tools/brain/docs/formats.md` about run folders, the Speed Check page of timed runs, the pool, and recordings, archived as they stood when ADR 0010 retired them; they hold for a command run with `--revive` ([README.md](README.md)). The live formats are in [docs/formats.md](../docs/formats.md).

## Run folder

**Run records.** Every run gets its own folder `<runs-root>/<UTC date-time>-<name>/` (default runs root `~/kaijuflow-notes/brain-runs`; use a temporary one for any trial) with `settings.json` (every side's settings, secrets replaced by `***`, exactly the settings reader's output), `meta.json` (settings, run-level facts, container addresses, KaijuFlow `commit` (the one the test image was built from) and the repository's `head`, titles, indexers, status, what changed), `raw.json` (every visit with its timings, step lines and imports), `logs/` (stand-in log and the test containers' logs, scrubbed of keys) and `report.md`. One row per run is appended to `<runs-root>/INDEX.md` (date, name, result, what changed, headline numbers, folder link). Nothing is overwritten: a rerun, even in the same second, gets a new folder, and INDEX.md is only ever appended to. The report opens with one sentence and the run's facts (its name, commit, start and, since #262, its machine), then "What changed since the last run" (a diff of settings, run-level facts (stand-in replay wait on or off, the one-page side), KaijuFlow commit, titles, indexers and sides against the [previous run](rules-retired.md#judged-against-the-previous-run-186) (`runs.previous`), whose folder its first line names; a run recorded in the older shape, which kept those facts inside its settings, is read as facts too, so it shows no false difference, then one line per title and side whose top pick changed, always ending with the time of day of both runs, the machine of both runs (power and CPU probe, when both have it, #262), and with how many null runs lie between them and when; the same list goes into the INDEX.md row), then the shared-steps table (search time split into "Indexers", the recorded wait, and "Side's own work"), the extras table, top pick plays counted on the first try with fallbacks shown apart (#143), failures split into indexer limit / Backend rejection / failure video / other / not recorded, per-title detail (with each visit's top pick and its size) and, when there are misses, a "Not recorded" section with the top-up command; every column is defined under its table.

**Top picks (#109).** The top pick of a visit is the first Source in the side's list, the one that was played; `raw.json` holds it as the visit's `tries[0]` (`title`: the first 140 characters of the text the side showed for it, `listed_size`: the size that text states after the disk sign, read from the whole text so a long release name cannot cut it off (a run made before it has only `title`, and the size is read from that), `size`: bytes of the served file, `plays`) and, for KaijuFlow, `played_source` (the release name from its `played` and `play_failed` step lines, #242; `cause` beside it holds why a failed play's top pick failed, from the same lines). `brainreport.top_pick(visit)` reads it. The per-title table shows it in two columns:

- **Top pick**: the release name where KaijuFlow's log gives it, otherwise the side's list text (an earlier run's Usenet Ultimate and AltMount direct gave no other name). "-" when the side listed no Source.
- **Size**: the served file's size in GB of 1000 x 1000 x 1000 bytes. A top pick that did not play serves the failure video, whose size says nothing about the Source, so its row shows the size its list text states after the disk sign, marked `listed` (`95.01 GB listed`): the indexer's figure for the post, which KaijuFlow counts in GB of 1024 x 1024 x 1024 bytes.

"What changed since the last run" lists a title whose top pick differs from the previous run's, one line per title and side, with the rounds it differs in and the old and the new pick of the first of them:

```
Top pick changed: KaijuFlow, Inception (Cold 1, Warm 1, Cold 2, Warm 2): Inception.2010.2160p.UHD.BluRay.Remux.HEVC.DTS-HD.MA.5.1-FGT, 85.4 GB -> Inception.2010.2160p.WEB-DL.DDP5.1.HEVC-NEW, 22.3 GB
```

The previous run's top picks are read from its folder's `raw.json`, so a run made before this column existed is compared too. Whether two picks are the same Source is decided by the size of the served file when both played, otherwise by the size both lists state, and by the name only when neither size can be compared. The name is not used first, because a side's list text also holds the Source's age and its health-check mark, which change from one run to the next. Only rounds both runs hold are compared, and a title or a side that only one run has is not a changed top pick (it is listed as added or removed). When the previous run's folder holds no top picks, nothing is compared and no line is written.

**Archived runs (#144).** Runs from before the like-for-like rules (#142) are moved, by hand, into `<runs-root>/archive/` and kept there as a record; their INDEX.md rows say `archived (not like for like)` and link into `archive/`. The tools look for runs only directly in the runs root (`brainreport.run_folders`), so an archived run is never the "previous run" of a diff, a short run's baseline or a null run counted between two runs; `check` says `Not usable as a baseline: archived (not like for like)` and exits 1, and `build_page.py` refuses the folder. Recordings are not archived: the next runs replay them.

**The recording a run replayed (#186).** `meta.json` has `recording`, the list name (`--list`) of the recording the run replayed; `check` judges the run against the previous run on the same recording ([rules](rules-retired.md#judged-against-the-previous-run-186)). A run from before #186 has none and is never that previous run.

**A run never compared with (#153).** Two `meta.json` fields, added by hand: `"never_compared": true` keeps the run out of every comparison ([rules](rules-retired.md#never-compared-with-153)), and `"label"` (for example `"Test 1"`) is the name the page and the one-page report call it by instead of `name`.

**A run on a tagged title list (#167).** A speed test's title list is tagged ([#165](#the-pool-pooljson-and-the-tagged-title-list)): each entry is `[type, id, label, list]`, `list` being `"easy"` or `"hard"`. `record` and `run` take it with `--titles-file` like any title list and keep each title's list: `meta.json` has `lists` (`{"<label>": "easy"}`, beside `titles`; a record folder's `meta.json` too), and every visit in `raw.json` has `list`. A tagged list is a speed test's whole list, so a run on it is not a short run. The report adds, for such a run:

- its opening sentence and its INDEX.md headline: each side's fails per list, then its median cold title to video per list (#159: list and start times stay as detail, in the tables);
- in "Per title", the columns **List** and **Title to video** (that visit's list time plus its start time; "-" for a fail);
- after the extras table, "Fails and title to video per list": one row per side, list and phase, with the fails of the phase and of each round (`1 title failed · 1 of 20 plays: 1 of 10 in Cold 1, 0 of 10 in Cold 2`) and the median title to video over the top picks that played in both rounds of the phase.

`check` adds one line per side and list, naming each fail: `Fails, KaijuFlow: easy 0 titles failed · 0 of 40 plays; hard 2 titles failed · 2 of 40 plays (Cold 1 <title>; Cold 2 <title>, played after 1 fallback).` Every fail count names both the titles with a failed play and the failed plays ([rules](rules-retired.md#fails-and-title-to-video-in-a-speed-test-167)). A run without tags (Test 1, the tuning tests) has none of this: its `meta.json`, `raw.json`, report and check are as before. The figures come from one place, for `check`, the report and the page to share: `brainreport.fail_figure(visits, side, phase, rnd, lst)` (`{'titles', 'fails', 'counted'}`: titles with a failed play, failed plays, plays counted) and `brainreport.fails_words(figure)` (its words), `brainreport.side_fails(visits, side, phase, rnd, lst)` (how many failed plays), `brainreport.fail_visits(visits, side, lst)` (which), `brainreport.side_time(visits, side, phase, 'video', lst)` (the median title to video), `brainreport.title_to_video(visit)`, `brainreport.run_lists(visits)` and `runs.load(folder)` (`tools/brain/runs.py`, the one reader of a run folder, #241).

**A stopped run (#110).** Ctrl-C or SIGTERM (what `timeout` sends) during a run stops the pass and then runs the normal ending, so the folder is whole; a second Ctrl-C while it finishes is ignored until the record is written. `meta.json` and `raw.json` have status `stopped`, and `meta.json` has `stopped`: `time` (when it was stopped), `signal` (`SIGINT` for Ctrl-C, or `SIGTERM`), `stage` (`the pass of the main sides`, `the pass of the one-page side`, or null before the first pass), `plays_done`, `plays_planned` (as the play lines count them) and `during` (`side`, `phase`, `round`, `title` of the play that was cut off, or null when it stopped between two plays). A record command keeps `stopped` in the same shape (its `stage` is `the record pass` or `the proof replay`, its plays are counted per stage as its play lines count them, and `round` is null: a record's rounds have no number). `raw.json` holds every play that finished; the cut-off play is not in it. `report.md` opens with one sentence saying the run was stopped, by what, when and how far it got, then has the usual sections made from the finished plays alone (a round that was cut short shows fewer titles in "Top pick plays"; a round that never began has no row). The INDEX.md row has result `stopped` and that same sentence as its headline, with no numbers. A stopped run is never the "previous run" of a diff, and `check` says it is not usable as a baseline.

**Wall-clock time (#112).** A run says how long it took and on what. Every figure is in seconds, by the runner's own clock.

- `meta.json` has `timing`:

  | Field | Meaning |
  |---|---|
  | `seconds` | the whole run, from `started` to `finished` |
  | `settle_s` | the pause asked for after every play (`--settle`) |
  | `passes` | one entry per pass, `main sides` (KaijuFlow) and then `one-page side`: `name`, `sides`, `start`, `end`, `seconds`. A pass holds its resets and its rounds |
  | `rounds` | one entry per round of each pass: `pass`, `phase`, `round`, `start`, `end`, `seconds`, `plays` and `pause_s` (the pauses of the round added up, as the clock saw them). A round goes from its first play to the end of the pause after its last play |
  | `resets` | one entry per reset: `pass`, `phase` and `round` of the cold round it came before, `start`, `end`, `seconds`. The first reset of the one-page side is the switch to one page, which resets too |
  | `parts` | where the whole run went: `measured_s`, `pauses_s`, `browse_s`, `failed_s`, `resets_s`, `other_s` |

- `meta.json` also has `start_load`, the machine's 1-minute load average as the run started, to the hundredth: the reading the run's preflight judged (none in a run from before #217; the limit is in [rules](rules-retired.md#settings-table-and-preflight-spec-72-ticket-74), check 7).
- `meta.json` also has `machine` (#262), what the run's preflight read of the machine as the run started: `power` (`ac`, plugged in or no `Mains` supply, or `battery`; the preflight refuses a run on battery, so a run keeps `ac`), `governor` and `energy_preference` (the first CPU's `scaling_governor` and `energy_performance_preference`, each only when readable) and `cpu_probe_ms`, the CPU probe's time in milliseconds: the same fixed work every run, so a higher number is a slower CPU ([rules](rules-retired.md#settings-table-and-preflight-spec-72-ticket-74), check 7). For example `{"power": "ac", "governor": "powersave", "energy_preference": "performance", "cpu_probe_ms": 1012}`. A run from before #262 has none. The report's opening facts say it (`Machine: plugged in, CPU probe 1012 ms (governor powersave, energy preference performance).`), and "What changed since the last run" holds it against the previous run's in one line, listed whenever both runs have it: `Machine: previous run plugged in, CPU probe 1000 ms (...); this run plugged in, CPU probe 1240 ms (...): the probe 24% slower` (`faster`, or `the same` when it rounds to 0%). When either run has none, the line is left out, so a run from before shows no false difference.
- `meta.json` also has `browse_pause_s`, the run's [Browse pause](rules-retired.md#browse-pause-205) in seconds (none in a run from before #205), and the run-level fact `browse pause` (`5 s`). Every visit in `raw.json` has `browse_pause_s`, the seconds it waited between its list and its play (0 when its list had nothing to play).
- The six `parts` add up to `seconds`. `measured_s` is the list time plus the start time of every top pick that played; `pauses_s` the pauses of all rounds; `browse_s` the Browse pauses of every visit; `failed_s` the whole visit (`t_start` to `t_end`) of every top pick that did not play, less its Browse pause; `resets_s` all resets; `other_s` is what is left: the seek checks after a top pick played, reading the logs after each play, starting and stopping the stand-in and the test copies.
- `raw.json`: every visit has `t_start` and `t_end`, so its own wall-clock time is the difference.
- `report.md` ends with the section "Where the time went": one sentence with the whole run and each pass, a table of the six parts and the whole run (seconds to one decimal, so the parts as printed are within a second of the total), and a table with one row per round and the reset before it. In "Per title", the Result of a top pick that did not play ends with how long its visit took less its Browse pause, the time "Failed plays" adds up, for example `failure video (the visit took 37.4 s, less its 5 s Browse pause)` (`the whole visit took 37.4 s` in a run from before #205).
- A run that ended early (stopped, null, failed) has `timing` too. A stretch that was cut short keeps the time it had taken; a run stopped during a reset shows that reset in a row with no round. Only the report of a stopped run has the section; a null or failed run has no tables at all.
- A run made before #112 has no `timing`, and its report has no such section.

## Targets (`targets.json`): the Speed Check page's

`tools/brain/targets.json` holds the targets the Speed Check page shows, one entry per target under `targets`, judged by `pagetargets.py` (page code). `check` and `report.md` no longer judge them (#187): a run is judged against the previous run ([rules](rules-retired.md#judged-against-the-previous-run-186)). The file and `pagetargets.py` go with the page code (#195).

```json
{"target": "Cold start within 1 s of AltMount direct", "measure": "cold start", "against": "altmount-addon", "margin": 1}
```

| Field | Meaning |
|---|---|
| `target` | the target in plain words, as it is printed |
| `measure` | what is measured on KaijuFlow, see the next table |
| `against` | the side KaijuFlow is compared with: `uu`, `altmount-addon` or `kaijuflow-1page` |
| `limit` | a fixed limit instead of a side (seconds, or plays for `plays per round`); an entry has `against` or `limit`, never both |
| `margin` | how far KaijuFlow may fall short and still meet the target, in the measure's unit; 0 for none |

| `measure` | Figure | Takes |
|---|---|---|
| `cold start`, `warm start` | median seconds from pressing play to the first byte, over the top picks that played in both cold (or both warm) rounds together | `against` or `limit` |
| `cold list`, `warm list` | median seconds until the Stream list arrived, over every title of both rounds together | `against` or `limit` |
| `plays` | top picks that played out of those counted, all four rounds together (margin: a share between 0 and 1) | `against` |
| `plays per round` | top picks that played out of those counted, for each round on its own (margin: plays) | `limit` |

"Counted" leaves out a top pick that failed only because a request was not recorded, as everywhere in the report. How a target is judged is in [rules.md](rules-retired.md#deleted-with-the-comparison-of-setups-187).

**A speed test** (a run on a tagged title list, #167) is judged on the three targets under `speed_test` instead (spec #159, ADR 0007), each on the easy list and on the hard list on its own; the six entries under `targets` judge an untagged run (Test 1 and before), as they always did. `speed_test` also holds the owner's final bar, in the owner's words:

```json
"speed_test": {
 "targets": [
  {"target": "KaijuFlow fails no more plays than any other setup, and none on the easy list", "measure": "fails"},
  {"target": "KaijuFlow's median cold title to video is no slower than any setup with as few fails or fewer", "measure": "cold title to video"},
  {"target": "Warm title to video under about 1 s", "measure": "warm title to video", "limit": 1}
 ],
 "final_bar": "On both lists, KaijuFlow has the fewest fails (a tie counts as fewest), and the fastest title to video among setups with as few fails."
}
```

| `measure` | Figure, per list | Takes |
|---|---|---|
| `fails` | failed plays (a play whose top pick did not play on its one try), all four rounds together, of KaijuFlow and of each other setup | nothing |
| `cold title to video` | median seconds from asking for the title until video, over the top picks that played in both cold rounds | nothing |
| `warm title to video` | the same over both warm rounds | `limit` (seconds) |

The final bar is shown beside the targets and never counted with them.

The page reads the judgement from `pagetargets.speed_test_judgement` (targets per list, outcome, final bar) and `pagetargets.target_results` (an untagged run); a verdict's `value` and `limit` are the two figures compared, `held_against` the setup the limit is from (none for a fixed limit) and `left_out` the titles left out of both as not like for like.

## The pool (`pool.json`) and the tagged title list

Every speed test plays titles no speed test has played before (ADR 0007). They come from the pool, `tools/brain/pool.json` (#165): titles are not secret, so it is in the repository. `pool.py draw` takes a speed test's titles from it and marks them used; a used title is never drawn again.

```json
{"about": "...",
 "titles": [
  {"type": "movie", "id": "tt0071360", "label": "The Conversation", "list": "hard", "reason": "1974 film, older release"},
  {"type": "series", "id": "tt4574334:4:1", "label": "Stranger Things S04E01", "list": "easy", "reason": "very popular streaming show, 2022 season", "used_by": "Test 2"}
 ]}
```

| Field | Meaning |
|---|---|
| `about` | what the file is, in plain words; not read by the tools |
| `type` | `movie` (a film) or `series` (an episode), as in a title list |
| `id` | the IMDb ID; an episode's is the show's ID, its season and its episode: `tt4574334:4:1` |
| `label` | the name the tables show: a film's TMDB title, or the show's TMDB name and `S04E01` |
| `list` | `easy` or `hard` ([GLOSSARY.md](../../../GLOSSARY.md), "Easy list" and "Hard list") |
| `reason` | one line saying why the title is on its list, by kind only (`1974 film, older release`, `anime series, takedown-prone`) |
| `used_by` | the speed test that drew it (`Test 2`); absent while the title is unused |

**Filling it.** An agent adds titles by kind only, without asking the owner: easy, popular well-kept titles whose top Sources nearly always play; hard, the kinds where dead Sources are common (older releases, takedown-prone shows, less popular titles). A title is never chosen by which side failed and never checked before it is played (no indexer search, no article check), and a title whose Sources all turn out dead stays. Each ID (and an episode's season and episode) is checked against TMDB with `python3 -I tools/brain/pool.py check-ids`, which reads the metadata key from KaijuFlow's test copy (`<TEST_DIR>/config/config.json`, `searchConfig.tmdbApiKey`) itself and never prints it. It prints one line per title with what TMDB has (`OK`, `NOT FOUND` or `LABEL DIFFERS`, with TMDB's name, year and id, and an episode's name and air date) and exits 1 when any title is not as the pool says. Keep the pool at three speed tests' worth or more: 18 films and 12 episodes on each list.

**What the pool refuses.** `draw` and `check-ids` refuse, with one sentence and nothing changed, a pool that holds one of Test 1's ten titles (`common.TITLES`), a title twice, a list other than `easy` or `hard`, an ID that does not fit its type, or a title without a reason. `draw` also refuses when a list has fewer unused titles than a speed test needs, naming what is missing (`The pool is too small for Test 5: the hard list has 2 unused episodes of the 4 a speed test needs.`); nothing is marked then.

**The draw.** `python3 -I tools/brain/pool.py draw --test "Test 2" --out <titles.json>` takes the first 6 unused films and the first 4 unused episodes of each list, in the pool's order, marks the 20 titles `used_by` that speed test in the pool, then writes the speed test's tagged title list to `--out` (`--pool` names another pool file, for a trial on a copy). The pool is written first, so a list that cannot be written wastes the 20 titles (one sentence says so; draw again under another name) and never lets a later draw take them again. Commit the pool after a draw, so the next speed test cannot draw the same titles.

**The tagged title list.** The run's title list (a JSON list of `[type, id, label]`, as `--titles-file` takes it) with a fourth field, the list the title is on:

```json
[
  ["movie", "tt1630029", "Avatar: The Way of Water", "easy"],
  ["series", "tt0098936:1:2", "Twin Peaks S01E02", "hard"]
]
```

The field is called the list, not the kind: kind already means film or series here. (A real-use check's drawn list has a fifth field and calls its fourth the kind of draw, such as `popular-film`: see "The title draw and the ledger".) A draw writes the easy films, the easy episodes, the hard films, then the hard episodes.

## Recording state and misses

**The recording's state and error answers.** At its end the record command writes `<store>/<list>/RECORDING.json`: `state` (`complete`: the proof replay had no miss; `incomplete`: it had, with each missed request and the side that asked in `misses` (a missed NZB download reads `<slug> nzb <first 12 characters of its stored key> <release title>`, the title taken from the stored search answers, so each NZB has its own name, #229); or `stopped` with `why` and `when`: an indexer limit, a failure, or the command was stopped by Ctrl-C or SIGTERM) and `errors`, the number of answers in this pass that were errors and were not stored. A finished record prints `Folder: <record folder>`, then one line of sentences, for example "12 answers were errors and were not stored: run record again to top them up." Its last sentence counts the top picks of the record pass that played on the first try, per side and round, in the words `check` uses for a run (`brainreport.top_picks_played`, shared by both): `Top picks played, KaijuFlow: cold 9 of 10, warm 10 of 10.` Every play of the record pass counts, the proof's do not; the counts are kept in the folder's `meta.json` as `plays` (`{side: {round: [played, plays]}}`). The preflight of a run passes only a `complete` recording.

**Nothing is measured.** A record pass gets its own folder `<runs-root>/<date>-<name>-record/` with `logs/standin.log` and `meta.json` (status `recorded`, `null`, `stopped` or `failed`, new and already-stored answer counts; a stopped pass also has `stopped`, in the shape a stopped run keeps it in (see "A stopped run" above)), but no report, no tables, no INDEX.md row unless it is NULL, stopped or failed, and it is never the "previous run" of a diff. Its timings (the first side to ask waits for the real indexer) reach nobody's numbers.

**Misses and indexer time, matched to the side and the visit.** Every stand-in request line says which address asked and when its answer was sent (`from=<ip> t=<epoch ms>`). The runner reads each test container's address on the test network with `docker inspect` (read-only, test containers only) after every reset, because a container gets its address when it starts, and keeps them in the run's `meta.json` (`addresses`). A line belongs to the side whose container sent it, and within that side to the visit that was current for that side when the line was sent (from that side's visit start until its next visit starts: the same rule the step lines use), so a late background request cannot land on another side's visit. A line from an unknown address falls back to the time window of the visit in progress; the report says how many lines were matched that way. From a visit's lines the report takes:


- the misses: every one is counted per side and title in the "Not recorded" table. A failed top pick is the failure cause "Not recorded", and left out of the plays-out-of-ten figure, only when the miss can be the cause: the list came back empty and that side had a search miss for that visit, or that side had an NZB miss while the top pick played (after the list arrived, until the visit ended). Otherwise the pick keeps its real cause (indexer limit, Backend rejection, failure video, other) and stays in the figure.
- the indexer time: the time that side spent waiting on replayed indexer answers while the list was loading, that is the union of the intervals `[t - wait_ms, t]` of its search answers between the visit's start and the list's arrival (parallel indexers and parallel pages are not added up; NZB files and play-time requests are left out). "Side's own work" is the list time minus that. With the wait off, both read as before (0 and the list time).

## The page: `findings.html`

`build_page.py` builds the Speed Check page, one `index.html`, in the owner's "Starting line" design (#132; drawn by `startline.py`) from run folders; the runbook's "Publish the page" has the steps. The page is about the newest timed run given, which must be finished (status `ok`); its [previous run](rules-retired.md#judged-against-the-previous-run-186) (`runs.previous`, the run `check` and `report.md` name, #241) is what it is compared with, and every timed run given gets a row in "Every run so far". Every number comes from the runs' `raw.json` through `brainreport` (the medians `check` and the page's targets share), every verdict from `pagetargets.target_results` (a speed test's from `pagetargets.speed_test_judgement`), and "What changed" from the newest run's `meta.json` `changes`. The headings that state a finding (for example "KaijuFlow starts slower than Usenet Ultimate") are worked out from the same numbers.

**`report.html`, the one-page report (#133).** The same build writes it beside `index.html`, from the same page model, so its numbers and verdicts are the page's. It is a fixed Letter sheet (816 x 1056 px, `@page` Letter with no margin, white paper, no dark theme) in the same design: the header, the verdict with KaijuFlow's four headline numbers, the cold start ruler with its limits, the targets (result, target, KaijuFlow, limit, margin; a target inside the noise says so with both rounds), what changed (the run's own changes and, against an earlier run, KaijuFlow before and after as a table), the warm list ruler, the findings and the next step from `findings.html`, and a footer that says what Start, List and "inside the noise" mean and "Page 1 of 1". Long findings can push it past one sheet; the render check (816 px) then flags CUT OFF.

**A speed test on the page and the report (#171).** A run on a tagged title list is judged per list, fails first, then title to video, and the page and report show it that way, from `pagetargets.speed_test_judgement`: the verdict counts its three targets on each list (the final bar is never one of them); the lead under it is the outcome line of the hard list; the headline numbers are KaijuFlow's failed plays on each list (with its titles failed), then its median cold title to video on each list; the first rulers are cold title to video on each list, every setup sorted fewest failed plays first, then fastest, each lane with its fails on a line under its bar; the targets are grouped under "Easy list" and "Hard list" (the report puts one row per target with both lists beside it), each with what was measured on every setup (page only); the final bar is a box of its own under the targets, with why on each list. Start and list stay as detail on four rulers with no target, beside each setup's fails over both lists. "Title by title" is one section per list: KaijuFlow's cold title to video per title, and a table of every setup where a note names each round, of all four, whose top pick failed ("Failed: Cold 1 after a fallback"); the report has the same fails per setup and list in one table, each cell its fails in words and one title with its rounds ("every round" when it failed in all four), then "+N more", so the sheet stays one page; the report's rulers carry no fails, the table under them does. A speed test is compared with its previous run, which replayed the same recording and so the same tagged list (#241; the page's own "speed test with a speed test" rule is gone); a run without tags renders as before.

**`findings.html`, the words nobody can compute.** An optional file in the newest run's folder, written by hand: the findings, then the next step. Each finding is an `<h3>` heading that states it, then its paragraphs; the next step, if there is one, is an `<h2>` heading and its paragraphs, after the last finding:

```html
<h3>Game of Thrones is the slow title.</h3>
<p>Its top pick is a 26.5 GB 4K release.</p>
<h3>Inception is hit-and-miss on KaijuFlow.</h3>
<p>It played in the first cold round and was rejected in the second.</p>
<h2>Next: tuning run 1</h2>
<p>Health-check connections raised from 12 to 20 on KaijuFlow.</p>
```

The build stops with one sentence when the file does not start with an `<h3>`. Without the file the page has no findings and no next step. Numbers written into its sentences are not checked against the run.

**`story.html` and the page archive (before #132).** The earlier page took a run's section from `story.html` in its folder and kept the runs whose folders are gone in `tools/brain/page-archive/` (2026-11-10 and 2026-11-09, as published in version 7 on 2026-11-13). The Starting line page reads neither; both stay as the record of what was published. Their runs are archived (#144): never compared with.

