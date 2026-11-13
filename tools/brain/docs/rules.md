# Brain tools: rules and settings

The cap rule, the preflight, the settings table, the replay wait, the indexer allowance and how the targets are judged. Back to the [runbook](../RUNBOOK.md) or the [index](../README.md).

## Cap rule

**Cap rule.** The first "limit reached" from any indexer aborts the run at once: the stand-in's `LIMIT_REACHED.json` (found at the start or after any visit), or a limit line in a side's own logs. The log wordings matched are the ones the sides print (`brainreport.LIMIT_RE`): the indexer's "Request limit reached" text as AltMount and KaijuFlow pass it on, `HTTP 429`, Usenet Ultimate's "Status: 429", KaijuFlow's "Failed to download NZB from X: 429" and the stand-in's `LIMIT_REACHED indexer=`; loose phrases such as "api limit" are not matched. The run is recorded as NULL in INDEX.md with the indexer and time, its report holds no numbers, and a null run is never used as the "previous run" for a diff. The stand-in and the test copies are stopped. A replay run ignores a marker older than its own start (replay never contacts an indexer, so an old marker was left by an earlier command and cannot be news); it is not deleted.

## Settings table and preflight (spec #72, ticket #74)

**Settings command.** `python3 -I tools/brain/testbed.py settings [--limit 100]` prints every test copy's settings as a table and the connection budget (per copy, total, provider limit), read straight from the copies' config files (KaijuFlow and Usenet Ultimate `config.json`, NzbDAV's database, each AltMount's `config.yaml`). Keys, logins and passwords are never printed. It replaces the hand-written table in SETTINGS.md. The run record's `settings.json` comes from the same reader (`testbed.read_settings`), so the table and the "what changed" list agree. The connection budget counts the NewsHosting login only: health-check cap (KaijuFlow, Usenet Ultimate); for NzbDAV and AltMount every provider entry on the same Usenet host as the copy's main provider, backup flag or not. An entry on another host (NzbDAV's backup login) has its own limit: it is shown beside the count (`+ other host max N, own limit`) and not counted.

**Preflight.** `python3 -I tools/brain/brainrun.py preflight [--for run|record] --store <store> --list <list> [--rebuild-image] [--provider-limit 100] [--key-file PATH]` prints one plain sentence per problem and exits 1, or exits 0 with `Setup is right ...`. `--store` and `--list` are only needed for `--for run`. `brainrun.py run` starts with the same check and stops before creating a run folder when it fails. Checks:

1. the `kaijuflow:test` image holds the code of the repository's commit and the tree is clean. The image's `kaijuflow.commit` label names the commit it was built from; the image is current when that is the repository's commit, or when no build input differs between the two (`git diff --quiet <image commit> HEAD -- <build inputs>`). So only a commit that changes the code in the image asks for a rebuild; a commit that touches only docs, tools or tests does not. The build inputs (`brainrun.BUILD_INPUTS`) are what the `Dockerfile` copies into the image, `src/`, `ui/`, `package.json`, `package-lock.json`, `tsconfig.json` and `scripts/docker-entrypoint.sh`, plus the `Dockerfile`, `.dockerignore` and `.gitattributes`, which can change what a build sees; a test holds the list in line with the `Dockerfile`. An image without a label, or from a commit the repository does not have, is not current. `--rebuild-image` builds an image that is not current from the commit itself, an archive of `HEAD` piped into `docker build --label kaijuflow.commit=<commit> -t kaijuflow:test -`, so untracked or ignored files can never get into an image whose label names that commit; it never builds from a dirty tree and leaves a current image alone;
2. record only: the key file (default `<test dir>/indexers.json`) exists, is readable only by the owner, and names exactly the indexers switched on in every test copy (only the names are read, so per-indexer settings added later are fine);
3. every indexer address in every test copy (also switched-off ones, plus Easynews or Prowlarr when on) is `http://host.docker.internal:1340/<slug>` with or without `/api`;
4. the caps add up to at most the provider limit (default 100);
5. the stand-in's port 1340 is free;
6. run only: the recording `<store>/<list>/<slug>/` holds at least one answer for each switched-on indexer, and its state file `<store>/<list>/RECORDING.json` (written by the record command) says `complete`; for a recording that stopped early or is `incomplete` (the proof replay missed requests) the preflight says why and gives the record command to top it up.

Indexers are compared by the slug in the indexer stand-in's address, because each copy names them its own way (for example `IndexerOne` in one copy and `indexerone` in another). Every sentence is plain: the key-file fix reads "make the key file readable only by you (run: chmod 600 <path>)", and "the indexer stand-in" is explained once, in the first address sentence. The tools carry no indexer names. The run record's `commit` is the image label (the code that ran); its `head` is the repository's HEAD, which is a later commit after a docs-only change.

**For the record command (#75).** Call `brainrun.preflight('record', cfg, io)` (or `'run'`); it returns a list of sentences, `[]` meaning go, and `brainrun.preflight_command(mode, cfg, io)` prints them and returns the exit code. `cfg` needs `test_dir`, `store`, `listname`; optional `limit`, `standin_port`, `key_file`, `rebuild_image`. `io` is the runner's IO object (`RealIO`) and needs `git_info`, `image_label`, `build_inputs_changed`, `rebuild_image`, `setup_report`, `key_state`, `port_free`, `recording`; `FakeIO` in the tests shows the shortcut (`io.preflight(mode)`). The image decision alone is `brainrun.image_state(label, head, inputs_changed)`: `current`, `stale`, `unknown` or `missing`. Tests: `test_settings.py`, `test_preflight.py`.

## Recording and the cap rule

**Cap rule for recording.** The first "limit reached" stops the pass at once; the recording is NULL: what was stored stays, the stand-in's `LIMIT_REACHED.json` stays in the store, the record pass gets an INDEX.md row `NULL` and the command exits with 2. A marker left by an earlier command never blocks a later one: a new `record` moves it aside (kept, renamed `LIMIT_REACHED.<its time>.json`) and goes on from what is stored; if the limit still holds, the first answer writes a new marker and the pass stops as before.

**Replay wait.** By default the stand-in waits the recorded indexer time for every replayed answer (#73), so list times look like real life. `run --no-wait` switches that off for a tuning run; the run record notes it as the run-level fact `stand-in replay wait: on|off` (in `meta.json`, not in the settings snapshot), so "What changed since the last run" shows it.

## Indexer allowance (spec #77, ticket #87)

**Limits file.** `limits.json` sits next to the key file (default `~/kaijuflow-test/limits.json`, outside the repo; you fill it in once). Example: `tools/brain/limits.example.json`.

```json
{"indexers": {"ninjacentral": {"search_per_day": 2000, "download_per_day": 450, "reset": "rolling-24h"}}}
```

- `search_per_day`: the daily limit of search (API) requests. `download_per_day`: the daily limit of NZB downloads. Whole numbers.
- `reset`: `"rolling-24h"` (the last 24 hours count; NinjaCentral's reply carries no usage fields and the reset is not confirmed, so this is the safe reading) or a clock time such as `"04:00"`, read in UTC unless the entry also has `"timezone": "Europe/Berlin"`.
- The name is matched to the stand-in's indexer name and the copies' names ignoring case, spaces and dashes.

**`python3 -I tools/brain/brainrun.py usage [--key-file PATH] [--test-dir DIR] [--runs-root DIR]`** prints, per indexer, `Used`, `Limit` and `Left` for searches and for downloads since the indexer's last reset. Used adds up two things: the stand-in's real requests in the record folders (`RECORD` and `ERROR` lines of each `logs/standin.log`; `api` is a search, `nzb` is a download; replayed `HIT` lines cost nothing) and the counts the live copy keeps (`queryHistory` and `grabHistory` in its `config/stats.json`, read-only). The test copies are not counted: they only talk to the stand-in, so their counters never measure real indexer hits. A copy keeps only its latest hundred entries of each, and the command counts this machine only; it says so. Without a limits file it prints one sentence asking you to fill it in. It never contacts an indexer. Code: `allowance.py`; tests: `test_allowance.py`.

**`preflight --for record`** prints the same table, then the request count of the newest complete recording (a record folder whose `meta.json` says `recorded`) of the same list, and warns when that count is more than what is left. It only warns; it never blocks.

## Targets

The targets are read from `tools/brain/targets.json` ([format](formats.md#targets-targetsjson)) and judged on KaijuFlow, by `check` and in `report.md` alike. The result of a target is one of:

- **Met** or **Not met**. A time is met when KaijuFlow's figure is no higher than the other side's figure (or the fixed limit) plus the margin. `plays` is met when KaijuFlow's share of played top picks is higher than the other side's share minus the margin, so with margin 0 an equal share does not meet "more often". `plays per round` is met when every cold and warm round played at least the limit minus the margin, and no more counted top picks failed in it than the margin.
- **Inside the noise**, added to Met or Not met for a time target: KaijuFlow's own two rounds of that kind (both cold rounds for a cold target, both warm rounds for a warm one) differ by more than the target is met or missed by. The same run done again could turn such a result around, so do not read it as settled. With a margin, "missed by" is the distance to the other side's figure plus the margin, not to the figure itself.
- **Not measured**: the run holds no figure for it (the side compared with was not in the run, or no top pick played). The measured values then read "no figure".

The targets do not decide whether a run can serve as a baseline: the exit code of `check` is the same with every target missed.
