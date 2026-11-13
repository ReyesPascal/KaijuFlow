# Brain tools: formats

What the files and lines look like: run folder, recording state, misses, step lines. Back to the [runbook](../RUNBOOK.md) or the [index](../README.md).

## Run folder

**Run records.** Every run gets its own folder `<runs-root>/<UTC date-time>-<name>/` (default runs root `~/kaijuflow-notes/brain-runs`; use a temporary one for any trial) with `settings.json` (every side's settings, secrets replaced by `***`, exactly the settings reader's output), `meta.json` (settings, run-level facts, container addresses, KaijuFlow commit, titles, indexers, status, what changed), `raw.json` (every visit with its timings, step lines and imports), `logs/` (stand-in log and the test containers' logs, scrubbed of keys) and `report.md`. One row per run is appended to `<runs-root>/INDEX.md` (date, name, result, what changed, headline numbers, folder link). Nothing is overwritten: a rerun, even in the same second, gets a new folder, and INDEX.md is only ever appended to. The report opens with one sentence, then "What changed since the last run" (a diff of settings, run-level facts (stand-in replay wait on or off, the one-page side), KaijuFlow commit, titles, indexers and sides against the newest earlier finished run; a run recorded in the older shape, which kept those facts inside its settings, is read as facts too, so it shows no false difference, always ending with the time of day of both runs, and with how many null runs lie between them and when; the same list goes into the INDEX.md row), then the shared-steps table (search time split into "Indexers", the recorded wait, and "Side's own work"), the extras table, failures split into indexer limit / Backend rejection / failure video / other / not recorded, per-title detail and, when there are misses, a "Not recorded" section with the top-up command; every column is defined under its table.

Usenet Ultimate's Import column is NzbDAV's own job time (#82): after each Usenet Ultimate visit the runner reads the test NzbDAV's history answer (port 3001, read-only) and takes `download_time` of the job that is new since before the visit. It is whole seconds (NzbDAV reports no fractions), against AltMount's log figure to the millisecond; the report's column definition says so. A visit that adds no job (item already imported) reads "-". The Usenet Ultimate test copy's own log is kept as `logs/uu-test.log` (scrubbed).

## Recording state and misses

**The recording's state and error answers.** At its end the record command writes `<store>/<list>/RECORDING.json`: `state` (`complete`: the proof replay had no miss; `incomplete`: it had, with each missed request and the side that asked in `misses`; or `stopped` with `why` and `when`) and `errors`, the number of answers in this pass that were errors and were not stored. The command ends with one sentence, for example "12 answers were errors and were not stored: run record again to top them up." The preflight of a run passes only a `complete` recording.

**Nothing is measured.** A record pass gets its own folder `<runs-root>/<date>-<name>-record/` with `logs/standin.log` and `meta.json` (status `recorded`, `null` or `failed`, new and already-stored answer counts), but no report, no tables, no INDEX.md row unless it is NULL or failed, and it is never the "previous run" of a diff. Its timings (the first side to ask waits for the real indexer) reach nobody's numbers.

**Misses and indexer time, matched to the side and the visit.** Every stand-in request line says which address asked and when its answer was sent (`from=<ip> t=<epoch ms>`). The runner reads each test container's address on the test network with `docker inspect` (read-only, test containers only) after every reset, because a container gets its address when it starts, and keeps them in the run's `meta.json` (`addresses`). A line belongs to the side whose container sent it, and within that side to the visit that was current for that side when the line was sent (from that side's visit start until its next visit starts: the same rule the step lines use), so a late background request cannot land on another side's visit. A line from an unknown address falls back to the time window of the visit in progress; the report says how many lines were matched that way. From a visit's lines the report takes:


- the misses: every one is counted per side and title in the "Not recorded" table. A failed top pick is the failure cause "Not recorded", and left out of the plays-out-of-ten figure, only when the miss can be the cause: the list came back empty and that side had a search miss for that visit, or that side had an NZB miss while the top pick played (after the list arrived, until the visit ended). Otherwise the pick keeps its real cause (indexer limit, Backend rejection, failure video, other) and stays in the figure.
- the indexer time: the time that side spent waiting on replayed indexer answers while the list was loading, that is the union of the intervals `[t - wait_ms, t]` of its search answers between the visit's start and the list's arrival (parallel indexers and parallel pages are not added up; NZB files and play-time requests are left out). "Side's own work" is the list time minus that. With the wait off, both read as before (0 and the list time).

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
| extras | `page` (`indexer_page`, 1 = first page); `count`, `checked`, `indexers` (`health_batch`); `result`, `parts` (`unscramble`); `includes_upload` (`import_wait` on AltMount: one request uploads and waits, so there is no `upload` line) |

`brainrun.py` ties lines to a title like this: search-side lines by `ref`, for that side's visit until the next visit that used the same KaijuFlow container starts (a late `health_batch` is kept); prepare-side lines to the Source that was played (its release title appears in the played Stream's text; otherwise the work that began after the visit began), so background work of the previous title cannot land in the next one. This runs once at the end of the run (`finalize_steps`).
