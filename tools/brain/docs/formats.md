# Brain tools: formats

What the files and lines look like: run folder, top picks, targets, expected settings, recording state, misses, the page's `findings.html`, step lines. Back to the [runbook](../RUNBOOK.md) or the [index](../README.md).

## Run folder

**Run records.** Every run gets its own folder `<runs-root>/<UTC date-time>-<name>/` (default runs root `~/kaijuflow-notes/brain-runs`; use a temporary one for any trial) with `settings.json` (every side's settings, secrets replaced by `***`, exactly the settings reader's output), `meta.json` (settings, run-level facts, container addresses, KaijuFlow `commit` (the one the test image was built from) and the repository's `head`, titles, indexers, status, what changed), `raw.json` (every visit with its timings, step lines and imports), `logs/` (stand-in log and the test containers' logs, scrubbed of keys) and `report.md`. One row per run is appended to `<runs-root>/INDEX.md` (date, name, result, what changed, headline numbers, folder link). Nothing is overwritten: a rerun, even in the same second, gets a new folder, and INDEX.md is only ever appended to. The report opens with one sentence, then the targets table (see [Targets](#targets-targetsjson)), then "What changed since the last run" (a diff of settings, run-level facts (stand-in replay wait on or off, the one-page side), KaijuFlow commit, titles, indexers and sides against the newest earlier finished run; a run recorded in the older shape, which kept those facts inside its settings, is read as facts too, so it shows no false difference, then one line per title and side whose top pick changed, always ending with the time of day of both runs, and with how many null runs lie between them and when; the same list goes into the INDEX.md row), then the shared-steps table (search time split into "Indexers", the recorded wait, and "Side's own work"), the extras table, failures split into indexer limit / Backend rejection / failure video / other / not recorded, per-title detail (with each visit's top pick and its size) and, when there are misses, a "Not recorded" section with the top-up command; every column is defined under its table.

**Top picks (#109).** The top pick of a visit is the first Source in the side's list, the one that was played; `raw.json` holds it as the visit's `tries[0]` (`title`: the first 140 characters of the text the side showed for it, `listed_size`: the size that text states after the disk sign, read from the whole text so a long release name cannot cut it off (a run made before it has only `title`, and the size is read from that), `size`: bytes of the served file, `plays`) and, for KaijuFlow, `played_source` (the release name from its own log). `brainreport.top_pick(visit)` reads it. The per-title table shows it in two columns:

- **Top pick**: the release name where KaijuFlow's log gives it, otherwise the side's list text (Usenet Ultimate and AltMount's own addon give no other name). "-" when the side listed no Source.
- **Size**: the served file's size in GB of 1000 x 1000 x 1000 bytes. A top pick that did not play serves the failure video, whose size says nothing about the Source, so its row shows the size its list text states after the disk sign, marked `listed` (`95.01 GB listed`): the indexer's figure for the post, which KaijuFlow counts in GB of 1024 x 1024 x 1024 bytes.

"What changed since the last run" lists a title whose top pick differs from the previous run's, one line per title and side, with the rounds it differs in and the old and the new pick of the first of them:

```
Top pick changed: KaijuFlow, Inception (Cold 1, Warm 1, Cold 2, Warm 2): Inception.2010.2160p.UHD.BluRay.Remux.HEVC.DTS-HD.MA.5.1-FGT, 85.4 GB -> Inception.2010.2160p.WEB-DL.DDP5.1.HEVC-NEW, 22.3 GB
```

The previous run's top picks are read from its folder's `raw.json`, so a run made before this column existed is compared too. Whether two picks are the same Source is decided by the size of the served file when both played, otherwise by the size both lists state, and by the name only when neither size can be compared. The name is not used first, because a side's list text also holds the Source's age and its health-check mark, which change from one run to the next. Only rounds both runs hold are compared, and a title or a side that only one run has is not a changed top pick (it is listed as added or removed). When the previous run's folder holds no top picks, nothing is compared and no line is written.

**Archived runs (#144).** Runs from before the like-for-like rules (#142) are moved, by hand, into `<runs-root>/archive/` and kept there as a record; their INDEX.md rows say `archived (not like for like)` and link into `archive/`. The tools look for runs only directly in the runs root (`brainreport.run_folders`), so an archived run is never the "previous run" of a diff, a short run's baseline or a null run counted between two runs; `check` says `Not usable as a baseline: archived (not like for like)` and exits 1, and `build_page.py` refuses the folder. Recordings are not archived: the next runs replay them.

**A stopped run (#110).** Ctrl-C or SIGTERM (what `timeout` sends) during a run stops the pass and then runs the normal ending, so the folder is whole; a second Ctrl-C while it finishes is ignored until the record is written. `meta.json` and `raw.json` have status `stopped`, and `meta.json` has `stopped`: `time` (when it was stopped), `signal` (`SIGINT` for Ctrl-C, or `SIGTERM`), `stage` (`the pass of the main sides`, `the pass of the one-page side`, or null before the first pass), `plays_done`, `plays_planned` (as the play lines count them) and `during` (`side`, `phase`, `round`, `title` of the play that was cut off, or null when it stopped between two plays). A record command keeps `stopped` in the same shape (its `stage` is `the record pass` or `the proof replay`, its plays are counted per stage as its play lines count them, and `round` is null: a record's rounds have no number). `raw.json` holds every play that finished; the cut-off play is not in it. `report.md` opens with one sentence saying the run was stopped, by what, when and how far it got, then has the usual sections made from the finished plays alone (a round that was cut short shows fewer titles in "Top pick plays"; a round that never began has no row), except the targets: a run that is not finished gets no target verdict (see [Targets](#targets-targetsjson)). The INDEX.md row has result `stopped` and that same sentence as its headline, with no numbers. A stopped run is never the "previous run" of a diff, and `check` says it is not usable as a baseline.

**Wall-clock time (#112).** A run says how long it took and on what. Every figure is in seconds, by the runner's own clock.

- `meta.json` has `timing`:

  | Field | Meaning |
  |---|---|
  | `seconds` | the whole run, from `started` to `finished` |
  | `settle_s` | the pause asked for after every play (`--settle`) |
  | `passes` | one entry per pass, `main sides` and then `one-page side`: `name`, `sides`, `start`, `end`, `seconds`. A pass holds its resets and its rounds |
  | `rounds` | one entry per round of each pass: `pass`, `phase`, `round`, `start`, `end`, `seconds`, `plays` and `pause_s` (the pauses of the round added up, as the clock saw them). A round goes from its first play to the end of the pause after its last play |
  | `resets` | one entry per reset: `pass`, `phase` and `round` of the cold round it came before, `start`, `end`, `seconds`. The first reset of the one-page side is the switch to one page, which resets too |
  | `parts` | where the whole run went: `measured_s`, `pauses_s`, `failed_s`, `resets_s`, `other_s` |

- The five `parts` add up to `seconds`. `measured_s` is the list time plus the start time of every top pick that played; `pauses_s` the pauses of all rounds; `failed_s` the whole visit (`t_start` to `t_end`) of every top pick that did not play; `resets_s` all resets; `other_s` is what is left: the seek checks after a top pick played, reading the logs after each play, starting and stopping the stand-in and the test copies.
- `raw.json`: every visit has `t_start` and `t_end`, so its own wall-clock time is the difference.
- `report.md` ends with the section "Where the time went": one sentence with the whole run and each pass, a table of the five parts and the whole run (seconds to one decimal, so the parts as printed are within a second of the total), and a table with one row per round and the reset before it. In "Per title", the Result of a top pick that did not play ends with how long its whole visit took, for example `failure video (the whole visit took 37.4 s)`.
- A run that ended early (stopped, null, failed) has `timing` too. A stretch that was cut short keeps the time it had taken; a run stopped during a reset shows that reset in a row with no round. Only the report of a stopped run has the section; a null or failed run has no tables at all.
- A run made before #112 has no `timing`, and its report has no such section.

Usenet Ultimate's Import column is NzbDAV's own job time (#82): after each Usenet Ultimate visit the runner reads the test NzbDAV's history answer (port 3001, read-only) and takes `download_time` of the job that is new since before the visit. It is whole seconds (NzbDAV reports no fractions), against AltMount's log figure to the millisecond; the report's column definition says so. A visit that adds no job (item already imported) reads "-". The Usenet Ultimate test copy's own log is kept as `logs/uu-test.log` (scrubbed).

## Targets (`targets.json`)

The targets KaijuFlow is measured against are in `tools/brain/targets.json`, one entry per target under `targets`. Change a target there and nowhere else.

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

"Counted" leaves out a top pick that failed only because a request was not recorded, as everywhere in the report. How a target is judged is in [rules.md](rules.md#targets).

**Where the result shows.** `check --run <folder>` prints one line per target after its other lines, and `report.md` has the same as a table (Target, This run, Result) right under its opening lines, followed by how many targets are met:

```
Target: Warm list no slower than 4.7 s. Measured: KaijuFlow 3.46 s. Met.
Target: Cold start no slower than Usenet Ultimate. Measured: KaijuFlow 6.73 s, Usenet Ultimate 5.51 s. Not met (1.22 s slower), inside the noise: KaijuFlow's two cold rounds differ by 1.86 s (8.59 and 6.73 s), more than the 1.22 s the target is missed by.
```

Only a finished run (status `ok`) is judged: for a stopped, null or failed run, the check prints one line instead (`Targets: not judged: the run was stopped before its last play, and the targets are judged on a finished run alone.`) and the report's Targets section is that one sentence. The check and the report go through the same gate (`brainreport.targets_not_judged`). If `targets.json` cannot be used, one sentence says why (`Targets: not judged (targets.json, entry 2: the margin is not a number from 0 up).`) and the rest of the check and the report is unchanged.

## Expected settings (`expected-settings.json`)

The settings every test copy is expected to have are in `tools/brain/expected-settings.json`; the preflight compares each copy with it ([rules.md](rules.md#expected-settings-109)). Change the standard there and in the test copies together.

```json
{"about": "...",
 "expected": [
  {"copies": ["kaijuflow", "uu"],
   "settings": {"movieFilters": {"sortOrder": ["regexScore", "quality"], "maxFileSize": 32212254720},
                "tvFilters": {"sortOrder": ["regexScore", "quality"], "maxFileSize": 10737418240}}}
 ]}
```

(The example is cut short; the file holds both sections in full.)

| Field | Meaning |
|---|---|
| `about` | what the file is, in plain words; not read by the tools |
| `expected` | the entries; each one names copies and the settings they must have |
| `copies` | the test copies the entry is for: `kaijuflow`, `uu`, `nzbdav`, `altmount-addon`, `altmount-kf` |
| `settings` | setting name and expected value. The name is the setting's name in the run's `settings.json`: a top-level name (`movieFilters`) or a dotted one (`healthChecks.sampleCount`) |

- A value that is an object (a section) is compared as a whole: every value in it must match, and a value the copy has there and the file does not is a difference too. A list of plain values (an order) is one setting.
- The value is compared as the run's `settings.json` holds it. KaijuFlow and Usenet Ultimate keep numbers and true/false. The AltMount copies keep every value as text, and NzbDAV most of them, so those are written as text (`"2"`, `"true"`).
- The file is in the repository: no host, address, login or key. An entry whose setting has a secret name (the settings reader's own test, `brainreport.is_secret_name`) is refused.
- A file that cannot be used fails the preflight with one sentence that says why.

Today the file holds the standard sort and filter rules of KaijuFlow and Usenet Ultimate and nothing else; any other setting the settings reader reads can be added the same way.

## Recording state and misses

**The recording's state and error answers.** At its end the record command writes `<store>/<list>/RECORDING.json`: `state` (`complete`: the proof replay had no miss; `incomplete`: it had, with each missed request and the side that asked in `misses`; or `stopped` with `why` and `when`: an indexer limit, a failure, or the command was stopped by Ctrl-C or SIGTERM) and `errors`, the number of answers in this pass that were errors and were not stored. The command ends with one sentence, for example "12 answers were errors and were not stored: run record again to top them up." The preflight of a run passes only a `complete` recording.

**Nothing is measured.** A record pass gets its own folder `<runs-root>/<date>-<name>-record/` with `logs/standin.log` and `meta.json` (status `recorded`, `null`, `stopped` or `failed`, new and already-stored answer counts; a stopped pass also has `stopped`, in the shape a stopped run keeps it in (see "A stopped run" above)), but no report, no tables, no INDEX.md row unless it is NULL, stopped or failed, and it is never the "previous run" of a diff. Its timings (the first side to ask waits for the real indexer) reach nobody's numbers.

**Misses and indexer time, matched to the side and the visit.** Every stand-in request line says which address asked and when its answer was sent (`from=<ip> t=<epoch ms>`). The runner reads each test container's address on the test network with `docker inspect` (read-only, test containers only) after every reset, because a container gets its address when it starts, and keeps them in the run's `meta.json` (`addresses`). A line belongs to the side whose container sent it, and within that side to the visit that was current for that side when the line was sent (from that side's visit start until its next visit starts: the same rule the step lines use), so a late background request cannot land on another side's visit. A line from an unknown address falls back to the time window of the visit in progress; the report says how many lines were matched that way. From a visit's lines the report takes:


- the misses: every one is counted per side and title in the "Not recorded" table. A failed top pick is the failure cause "Not recorded", and left out of the plays-out-of-ten figure, only when the miss can be the cause: the list came back empty and that side had a search miss for that visit, or that side had an NZB miss while the top pick played (after the list arrived, until the visit ended). Otherwise the pick keeps its real cause (indexer limit, Backend rejection, failure video, other) and stays in the figure.
- the indexer time: the time that side spent waiting on replayed indexer answers while the list was loading, that is the union of the intervals `[t - wait_ms, t]` of its search answers between the visit's start and the list's arrival (parallel indexers and parallel pages are not added up; NZB files and play-time requests are left out). "Side's own work" is the list time minus that. With the wait off, both read as before (0 and the list time).

## The page: `findings.html`

`build_page.py` builds the Speed Check page, one `index.html`, in the owner's "Starting line" design (#132; drawn by `startline.py`) from run folders; the runbook's "Publish the page" has the steps. The page is about the newest timed run given, which must be finished (status `ok`); the newest finished run before it, when one is given, is what it is compared with, and every timed run given gets a row in "Every run so far". Every number comes from the runs' `raw.json` through `brainreport` (the medians the targets are judged on), every verdict from `brainreport.target_results`, and "What changed" from the newest run's `meta.json` `changes`. The headings that state a finding (for example "KaijuFlow starts slower than Usenet Ultimate") are worked out from the same numbers.

**`report.html`, the one-page report (#133).** The same build writes it beside `index.html`, from the same page model, so its numbers and verdicts are the page's. It is a fixed Letter sheet (816 x 1056 px, `@page` Letter with no margin, white paper, no dark theme) in the same design: the header, the verdict with KaijuFlow's four headline numbers, the cold start ruler with its limits, the targets (result, target, KaijuFlow, limit, margin; a target inside the noise says so with both rounds), what changed (the run's own changes and, against an earlier run, KaijuFlow before and after as a table), the warm list ruler, the findings and the next step from `findings.html`, and a footer that says what Start, List and "inside the noise" mean and "Page 1 of 1". Long findings can push it past one sheet; the render check (816 px) then flags CUT OFF.

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

## Step lines (`[KF-STEP]`)

KaijuFlow writes one line per timed step to stdout (`src/utils/stepTiming.ts`): `[KF-STEP] ` followed by a one-line JSON object. `docker logs -t` prefixes are fine: parse from the first `[KF-STEP] ` (`json.loads(line.split("[KF-STEP] ", 1)[1])`). Lines carry names, titles and numbers only, never URLs or keys.

| Field | Meaning |
|---|---|
| `step` | `indexer_page`, `health_batch`, `nzb_fetch`, `unscramble`, `upload`, `import_wait`, `first_byte` |
| `source` | Source or indexer name (none for `health_batch`) |
| `ms` | whole milliseconds the step took |
| `ok` | false when the step threw (the line is still written) |
| `t` | end time, ISO UTC |
| `ref` | Stremio id (`tt0133093`, `tt1234567:1:2`), on the search-side steps `indexer_page` and `health_batch` only |
| `title` | release title of the Source, on the prepare-side steps (`nzb_fetch`, `unscramble`, `upload`, `import_wait`, `first_byte`) |
| `job` | Backend job id on `upload`, `import_wait`, `first_byte` |
| extras | `page` (`indexer_page`, 1 = first page); `count`, `checked`, `indexers` (`health_batch`); `result`, `parts`, `wait_ms` (`unscramble`; `wait_ms` is the part of `ms` spent waiting for its turn, #119); `includes_upload` (`import_wait` on AltMount: one request uploads and waits, so there is no `upload` line) |

`brainrun.py` ties lines to a title like this: search-side lines by `ref`, for that side's visit until the next visit that used the same KaijuFlow container starts (a late `health_batch` is kept); prepare-side lines to the Source that was played (its release title appears in the played Stream's text; otherwise the work that began after the visit began), so background work of the previous title cannot land in the next one. This runs once at the end of the run (`finalize_steps`).
