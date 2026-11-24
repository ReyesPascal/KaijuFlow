# NNTP health checks: what KaijuFlow's check proves, what AltMount's checks prove, and the gap between them

Research date: 2026-11-24. Read-only: no code changed, no timed run, no test container touched. Written for the planned **diagnosis system**, which must say why a **Check miss** happened (a Source KaijuFlow's health check passed that AltMount then refused, or whose video froze; [GLOSSARY](../../../GLOSSARY.md)) and prove it with a test. Usenet failure modes in general are in `USENET_STREAM_FAILURES.md` (another agent); this note stays on health checks.

**Words used throughout.**

- An **article** (also **segment**) is one Usenet post holding a slice of a file, about 700 KB of video. A film is tens of thousands of them. Each has a **message-id**, its unique name.
- An **NZB** is the list of a release's files and, for each file, the message-ids of its articles in order.
- A **provider** (here Newshosting) is the company whose news servers store the articles. **NNTP** is the protocol spoken to them.
- **STAT** asks a news server "do you have the article with this message-id?" and gets a yes (code 223) or no (430) without receiving it. **BODY** downloads the article's content. **HEAD** downloads only its headers; **ARTICLE** both.
- **yEnc** is the encoding that turns binary data into text for posting; each article carries a checksum (CRC) of its own bytes.
- A **RAR set** or **7z set** is a file cut into numbered **volumes** (`.part01.rar`, `.7z.001`, ...). **Stored** means not compressed, so the video can be read straight out of it. **par2** files hold repair data, used to rebuild missing pieces after a full download.
- **Obfuscated** names are random-looking file names (`7a870da9cbcc480a075cde6a2bd4dbd5.10`) that hide what a file is.

Code is cited as `file:line`. KaijuFlow at the working tree of branch `quick-check-270` (HEAD 41a82c1). AltMount at tag **v0.4.0**, commit `276157560ecd510de127c69b5368aaa0e0ce4277` (the version ADR 0009 says the test copy runs; the repository now lives at `kipsilabs/altmount`, `javi11/altmount` redirects there). I did not confirm the test copy's image tag from its logs. Upstream main was 22 commits past v0.4.0 on 2026-11-24 (`748d137`); none of it was read. Statements marked **(inference)** are mine, not read from code or logs.

## The short answer

- **KaijuFlow's check asks about three articles.** It STATs 3 articles of the one file it thinks will be played (first, middle, last), or the first article of 3 volumes of an archive set. For an archive it also downloads (BODY) the first article of the first volume to read the archive header. It passes when all 3 STATs say yes and, for an archive, the header shows stored RAR5 or 7z with a video inside.
- **AltMount's import check asks about 5 to 64 articles of the whole release**, chosen as the first 3, the last 2 and a random middle (1% of all articles, at least 5, at most 64), then downloads the first article of most files. While streaming it downloads every article it plays and checks each one's CRC.
- **In the runs since the Play-time check began (21 to 24 Nov), no Check miss came from missing articles.** There were 8 Check misses out of 270 imports after a passed check (about 3%): 7 were hash-named RAR sets whose Unscramble step failed after the check (AltMount then read the number names as a set with missing volumes), and 1 was a file AltMount named differently from KaijuFlow and then refused for having no video extension. The first cause stopped after the ADR 0005 amendment of 2026-11-23 (0 in run `grouped-250`).
- **The gaps that have not yet shown up are real by design**: 3 STATs catch a file with 1% of its articles missing about 3 times in 100; AltMount's 64 catch it about 47 times in 100 **(inference, arithmetic below)**. STAT never proves an article's content is intact. A season pack checked on one episode can be judged dead as a whole by AltMount. No quick check can see a freeze, because it stops at the first video byte.
- **Published practice agrees STAT proves only existence.** RFC 3977 defines STAT as ARTICLE without the article. SABnzbd's and NZBGet's health numbers come from actually downloading bodies; SABnzbd's only check before downloading STATs *every* article and is off by default.

## 1. KaijuFlow's check, exactly

### Where it lives and when it runs

- The **Play-time check** is `checkSource` in `src/play/playTimeCheck.ts:52-64`. It is KaijuFlow's only health check (GLOSSARY, "Play-time check"): no setting turns it off.
- It is called two ways: by the Best entry's **Walk** for each grabbed Source (`src/play/ultimateFallback.ts:379`, sharing one connection pool per walk), and for a list entry the viewer clicks, through `requireHealthySource` (`src/play/playTimeCheck.ts:72-82`, called from `src/play/streamHandler.ts:282`).
- It runs `performHealthCheck` in `src/health/healthCheckPipeline.ts:46-395` with archive inspection always on and the sample count from `ultimateFallback.sampleCount`, default 3 (`src/play/playTimeCheck.ts:59`; read and limited to 3 or 7 in `src/config/accessors.ts:381-382`). The test copy has `sampleCount` 3 (`settings.json` of run `2026-11-24T044717Z-grouped-250`).
- **Not checked at all**: a Source AltMount already holds (a "library hit", `src/play/ultimateFallback.ts:337-343`) and a Source KaijuFlow remembers as ready (Source memory; GLOSSARY, "Walk": "A Source that needs no grab ... is never held back"). A ready Source is remembered for 3 days by default (`src/play/sourceMemory.ts:117-119`, `healthyNzbDbTTL` 259200 s).

### Which file and which articles

1. **The NZB** is downloaded (or taken from KaijuFlow's NZB cache) and parsed; each file's articles are sorted by their number (`src/health/nzbParser.ts:29-116`, sort at `:110`). The cache keeps the NZB text 10 minutes, at most 50 entries, so the later grab reuses the same NZB (`src/health/nzbContentCache.ts:9-10`; the grab logs "Using cached NZB from health check", `src/backends/nzbGrab.ts:43`).
2. **File names come from the NZB's subject lines**: the first quoted text, else a bracketed name with a known extension, else the cleaned subject (`src/health/fileClassifier.ts:16-39`). KaijuFlow never reads names from inside the articles.
3. **Video or archive**: a file is video when its name ends in one of `.mkv .mp4 .avi .m4v .ts .m2ts .wmv .webm .mov .mpg .mpeg` and does not contain "sample" (`src/health/fileClassifier.ts:42-58`). It is an archive when its name ends in `.rar .zip .7z .tar .gz .bz2`, `.rNN`, `.7z.NNN`, `.zip.NNN`, `.partN.rar`, any `.NN`/`.NNN`, or is a 16+ character letters-and-digits name with or without a number extension (obfuscated names) (`src/health/fileClassifier.ts:92-144`). `.par2 .nfo .sfv .txt .srt .idx .sub` are neither (`:96-99`), so **par2 files are never looked at**.
4. **Which file is checked**:
   - If any video file exists, the one whose name matches the episode selector AltMount will be sent (`src/health/healthCheckPipeline.ts:31-35`, `:111-116`), else the first video file in NZB order. A pack of several videos checked on the wanted episode gives a verdict "for that episode only" (`episodeOnly`, `:114`).
   - Else, for archives, the first volume found by name (`.7z.001`, `.part01.rar`, `.zip.001`, `.001`, a lone `.rar`, `.7z` or `.zip`; `src/health/archiveGrouper.ts:122-141`), and when no name matches (a hash-named set such as `<hash>.10`), simply the first archive file in NZB order (`src/health/healthCheckPipeline.ts:118`).
   - Else the Source is blocked: "Disc image" when the largest file ends `.iso`/`.img` (`:120-136`, `src/archive/utils.ts:79-84`), otherwise "No video or archive file named" (`:137-143`).
5. **Which articles are STATed** (with the default 3):
   - A video, or an archive that is a single file: the file's first, middle (index ⌊n/2⌋) and last article (`src/health/healthCheckPipeline.ts:294-311`). With `sampleCount` 7: 0%, 20%, 40%, 50%, 60%, 80% and the last.
   - A multi-volume archive set: the **first article of 3 evenly spaced volumes** of the largest set (for a 74-volume set, volumes 1, 25 and 50), topped up from the largest volume if fewer than 3 were found (`src/health/archiveGrouper.ts:74-115`, used at `src/health/healthCheckPipeline.ts:283-289`). No other article of any volume is asked about.

### Which NNTP commands, against which providers, with which time limits

- **STAT**, all 3 sent at once on one connection (pipelined), answers matched by order (`src/health/articleChecker.ts:120-123`). 223 counts as present, 430 as missing, **any other reply also as missing** (`:60-75`). If the server closes the connection, every unanswered article counts as missing (`:98-108`). One limit of **30 s** for the whole batch (`:21`, `:35-41`).
- **BODY**, only for an archive: up to 3 articles from the start of the checked volume, stopping once 64 KB are in, so in practice 1 article (`src/health/healthCheckPipeline.ts:161`, `src/archive/nntpSegmentDownloader.ts:17-46`), each with a **30 s** limit (`src/archive/nntpSegmentDownloader.ts:108-113`, command at `:214`). The yEnc decoder **does not check the CRC** (`src/archive/nntpSegmentDownloader.ts:54-92`). For a 7z set whose header has no file list, KaijuFlow also reads the end of the whole set to get it (`src/health/healthCheckPipeline.ts:195-233`).
- **HEAD and ARTICLE are never used.**
- **Providers**: the enabled health-check providers (`src/play/playTimeCheck.ts:23-25`). All "pool" providers are asked in parallel with the same articles, then "backup" providers for what none had; an article counts as present if **any** provider has it (`src/health/articleChecker.ts:162-243`). If no provider could be asked at all, the check throws and the result is `error` (`:233-236`). The archive header is read from the first provider that answers, pool ones first (`src/health/healthCheckPipeline.ts:153-250`).
- **Connections**: one cap for the whole process, default 8 (`src/health/nntpConnection.ts:22`), 12 on the test copy (`healthChecks.maxTotalConnections`). Opening and logging in has a **10 s** limit (`src/health/nntpConnection.ts:213-218`).
- The check as a whole has **no overall time limit** in these files.
- **In the test bed both sides use one and the same Newshosting server**: KaijuFlow's one health-check provider and AltMount's one provider have the same host (compared in `settings.json` of `grouped-250` without printing it; the host is `<REDACTED>`).

### What counts as pass or fail

| Result (`status`) | When | Source marked dead? |
|---|---|---|
| `verified` | a video file, all sampled STATs said yes (`src/health/healthCheckPipeline.ts:324-337`) | no |
| `verified_stored` | an archive the pass rule allows, all sampled STATs yes (`:338-348`) | no |
| `blocked` | a sampled article missing (`:351-366`); no files; no segments; disc image; no video or archive named; or the pass rule refused the archive | yes (`src/play/playTimeCheck.ts:80`, `src/play/walk.ts:168`); for a pack checked on one episode, dead for that episode only |
| `error` | the NZB could not be fetched, no provider answered, the VPN check failed, anything thrown (`src/health/healthCheckPipeline.ts:377-394`) | no (ADR 0004) |

`isHealthy` passes `verified`, `verified_stored` and `verified_archive` (`src/play/playTimeCheck.ts:39-41`); nothing in the pipeline produces `verified_archive` any more.

**The pass rule for archives** (ADR 0009, `src/health/altmountPassRule.ts:19-32`), decided from the header before any STAT: blocked when the header could not be read, encrypted (with or without a password), nested archive, ZIP, RAR4, unknown format or no file list, compressed, or no video file inside. So RAR5 and 7z pass only when stored and holding a video.

**What KaijuFlow does about** ...

- **RAR sets**: reads one volume's header, STATs the first article of 3 volumes. It never checks that the NZB lists every volume, nor in what order the names put them.
- **par2**: ignores them entirely.
- **Obfuscated names**: treats them as archives and reads the header to learn what is inside. A **Scrambled RAR set** (number-named volumes out of order) passes the check as stored RAR5; it is put in order later, at prepare time, by Unscramble, which BODY-reads the first article of *every* volume (`src/backends/sourceNzb.ts:39-96`, `src/archive/unscramble.ts:1-20`, 15 s limit at `src/backends/sourceNzb.ts:19`). If Unscramble ends with a read error twice, nothing is uploaded; any other failure uploads the original NZB (ADR 0005, amended 2026-11-23; `src/backends/sourceNzb.ts:53-70`).
- **Disc images**: blocked by name, before any article is asked about.

### What it caches

- The NZB text, 10 minutes (above).
- **No check verdict is cached.** A healthy result is not remembered; a Source is remembered as **ready** only after AltMount made its video and the first byte served (`src/play/ultimateFallback.ts:423-425`), and then skips the check for up to 3 days.
- A **dead mark** is written for `blocked` (above) and kept 1 day by default (`src/play/sourceMemory.ts:121-123`, `deadNzbDbTTL` 86400 s).

### The `[KF-STEP]` lines

A step line is one line of JSON after the tag `[KF-STEP]` (`src/utils/stepTiming.ts:12`, `:39-44`).

- **`play_check`**, the check's only line: `{step, source (indexer), title (release), ok, status, ms, t, ref}` (`src/play/playTimeCheck.ts:62`). It is not written when the check's pool was stopped (its Walk ended, or an Unscramble retry stopped the checks).
- Lines around it for the same Source: `nzb_fetch` (`src/backends/sourceNzb.ts:46-49`); `unscramble` with `result` (`unscrambled`, `not-scrambled`, `read-error`, `missing-article`, `not-rar5`, `duplicate-volume`, `volume-gap`, `timeout`, `stopped`, `no-provider`), `parts`, `wait_ms`, `retry` (`src/backends/sourceNzb.ts:86`, `:92`; reasons at `src/archive/unscramble.ts:31-41`); `import_wait` (`src/backends/altmount.ts:273`); `first_byte`; `played` and `play_failed` with `reason` (`src/utils/stepTiming.ts:79-85`).
- **What the step lines do not carry**: why a check said no (only in console lines such as `❌ #3 not healthy (Missing 1 of 3 segments)`, `src/play/ultimateFallback.ts:384`, and `[label] → Blocked: ...`); which file was checked (console `Checking video: <name>`); which articles were sampled; which provider answered (console `Result: 3/3 found (Newshosting (3/3))`). A diagnosis tool has to read those console lines today.

## 2. AltMount's checks, exactly (v0.4.0)

### At import

KaijuFlow uploads with category `kaijuflow` (`src/backends/altmount.ts:64`, `:264`), so AltMount does **not** treat the upload as a Stremio import: the Stremio-only settings below do not apply (`internal/importer/processor.go:557`).

1. **Gap placeholders.** Articles the NZB itself skips (number gaps) become placeholders, known holes counted without a STAT (`internal/importer/processor.go:1031`).
2. **The release probe (STAT).** `preParseFastFail` (`internal/importer/processor.go:451`):
   - Takes the articles of **every file except par2** (par2 kept but never STATed, `:459-463`), all files' articles in one list.
   - Picks `max(1% of all articles, 5)`: the first 3 and last 2 of that list, plus random ones from the middle (`internal/usenet/validation.go:340-390`, the minimum of 5 at `:350`), then keeps at most **64**: the 5 edge picks and 59 random middle ones (`internal/importer/validation/fast_fail.go:337-353`). The percentage is `import.segment_sample_percentage`, default 1 (`internal/config/manager.go:2299`), and **cannot be set below 1**: the config is refused outside 1-100 (`internal/config/manager.go:1249`). The test copy has 1.
   - STATs the first 8, all of them; if at least 8 are missing and they make at least half the answers, the release is **dead** (`internal/importer/validation/fast_fail_verdict.go:22`, `:104-118`; `fast_fail.go:222-242`). Otherwise it STATs the rest, stopping at the first miss (`fast_fail_verdict.go:124-133`). Only a 430 counts as missing (`fast_fail.go:38`).
   - Time limits: 2 s for the first attempt, one 15 s budget for all attempts (`fast_fail_verdict.go:84-85`, `fast_fail.go:28`); out of time means **inconclusive**, not missing (`fast_fail_verdict.go:87-93`). Each provider is told the release's post date so a provider with too short a retention is not asked (`processor.go:485`).
   - **Dead**: every file is marked broken (`processor.go:518-528`). **Nothing missing**: the import goes on with no more STATs (`:529-546`). **Some missing**: a second sweep STATs a per-file sample (first, last and 1% of the middle of each file, `fast_fail.go:299-326`) to learn which files are broken (`processor.go:590-601`).
   - **RAR and split-volume parts share a set key: one broken part condemns the whole set** (`processor.go:469-476`). A standalone video file with little damage (within `acceptable_missing_segments_percentage`, test copy 2) may import "degraded" and be zero-filled when played (`processor.go:668-683`); sampled damage inside an archive set never does (`:646-660`).
   - When every importable file is broken: `no regular files were successfully processed (all files failed validation)` (`internal/importer/multifile/processor.go:25`, returned at `processor.go:798-799`), wrapped as **`fast-fail segment check failed: ...`** (`processor.go:1073`). Out of time: **`fast-fail segment check inconclusive: ...`** (`processor.go:1071`). Per broken file it logs `Skipping file due to early fast-fail segment check error` (`processor.go:697`).
   - Repair: with par2 repair on, a damaged archive set is parked for a repair instead (`processor.go:87-139`, `:781-796`). The test copy has `par2_repair.enabled` false, so this never happens there.
3. **First articles (BODY).** While the probe runs, AltMount downloads the first article of each file (`internal/importer/processor.go:1045`, `internal/importer/parser/parser.go:1045`; 30 s per try, `parser.go:1202`) to read the yEnc header and the real file name and type. It **skips** this for a file with at least 3 articles whose name has a plain video extension and does not look obfuscated, and for 7z continuation volumes and par2 recovery volumes (`parser.go:716-745`, used at `:900-909`). If a first article is gone, it asks the next few for the header (`:924-930`). An empty one logs **`First segment has no data`** (`parser.go:1031-1034`), a warning only: run `grouped-250` logged it 2005 times and had no failed import.
4. **Names and extensions.** AltMount decides real file names itself, using SABnzbd's obfuscation rules (`internal/importer/parser/fileinfo/fileinfo.go:243-300`). A single file whose name lacks an allowed extension fails with **`file '<name>' does not match allowed extensions (allowed: [...])`** (`internal/importer/singlefile/processor.go:34-38`); several files with none allowed log `No files with allowed extensions found` (`internal/importer/multifile/processor.go:48`). The allowed list is `import.allowed_file_extensions`; on the test copy it lacks **`.webm`**, which KaijuFlow counts as video.
5. **RAR sets.** A set whose volume *names* leave a gap is skipped before any read, logging **`Skipping RAR archive group with missing volume(s)`** (`internal/importer/archive/rar/aggregator.go:161-165`; the name test `internal/importer/archive/rar/utils.go:155-190`); when every set was skipped: **`no files were successfully processed (all files failed validation)`** (`aggregator.go:203`; text at `internal/importer/archive/common.go:34`). After reading the headers, each file inside is checked for size and offsets only, with no network (`aggregator.go:380-389`, `internal/importer/validation/segments.go:14-76`); if none survives, the same message (`aggregator.go:422`). 7z sets have the same message (`internal/importer/archive/sevenzip/aggregator.go:357`). Compressed 7z: "Only uncompressed files are supported" (seen in Test 1, ADR 0009).

### While streaming

- AltMount downloads (BODY) each article as the player reads it. A missing article (430) is re-checked once, because "a 430 is not proof the article is gone: backends desync" (`internal/usenet/usenet_reader.go:209-227`, its issue #749). A yEnc **CRC mismatch** is treated as corrupt data (`usenet_reader.go:250-267`). Either becomes a `DataCorruptionError` naming the segment and file position (`usenet_reader.go:188-206`) and the read fails.
- Instead of failing, a confirmed-missing article may be **zero-filled** (played as blank data) when AltMount's hole rule allows it (`usenet_reader.go:43-63`, `:1093-1104`): only `.mp4 .m4v .mov .mkv .webm` files (`internal/holes/holes.go:109-112`), at most 4 missing in a row, 64 in all, 2% of the file (`holes.go:28-35`). A video inside a RAR set is not a zero-fillable file **(inference from `processor.go:646-660` and the extension list; the hook's wiring in the virtual filesystem was not traced)**, so a hole there fails the read.
- One read has a time limit, `streaming.read_timeout_seconds`, 120 s on the test copy (`internal/config/manager.go:585-594`). `streaming.failure_masking` is off on the test copy.
- AltMount's separate **health checker** after import (5% sample, `internal/health/checker.go:254`; default at `manager.go:2325`) is switched off on the test copy (`health.enabled` false), so it never runs there.

### Settings that change these checks

| Setting | Test copy | Effect |
|---|---|---|
| `import.segment_sample_percentage` | 1 | share of articles the release probe picks (5 to 64) and the per-file sweep samples; 1-100 |
| `health.acceptable_missing_segments_percentage` | 2 | damage a standalone video may have and still import, zero-filled |
| `import.allowed_file_extensions` | 25 types, no `.webm` | names that may import |
| `par2_repair.enabled`, `par2_repair.repair_on_import` | false, false | park a damaged set for repair instead of failing |
| `stremio.fast_fail_header_only`, `stremio.skip_repair` | true, unset | Stremio imports only; not KaijuFlow's (`manager.go:471-474`, `:527-532`) |
| `import.verify_content`, `health.verify_content` | false, false | content checks after import, off |
| `streaming.read_timeout_seconds` | 120 | longest wait for one read while playing |
| `health.enabled`, `health.segment_sample_percentage` | false, 5 | post-import health checker, off |
| `providers[0].max_article_age_days` | 0 | provider retention, used to skip asking for older posts |

## 3. The gap: how a Source passes KaijuFlow's check and still fails in AltMount

**What the runs show.** I paired every `import_wait` that failed with the `play_check` lines of the same release in the same run, for every run folder in `~/kaijuflow-notes/brain-runs/`, and read AltMount's log at the same moment. No run has `play_failed` lines yet (they came with #242). Runs since the Play-time check (`baseline-218-wifi` onward): 503 checks passed, 262 imports succeeded, **8 imports failed after a passed check**.

| # | Run | Release | Unscramble | AltMount's error | AltMount's log |
|---|---|---|---|---|---|
| 1 | `2026-11-21T050927Z-baseline-218-wifi` | The.Witcher.S01E01...HHWEB | `read-error`, 74 parts | KaijuFlow gave up: "AltMount did not finish preparing within 3s" | — |
| 2, 4 | `2026-11-23T183239Z-baseline-218` | The.Witcher.S01E01...HHWEB | `read-error`, 74 | no files were successfully processed (all files failed validation) | Skipping RAR archive group with missing volume(s), parts=74 |
| 3 | same run, 18:36:04 | The.Witcher.S01E01...SiC-AsRequested | `not-scrambled` | file '...SiC-AsRequested' does not match allowed extensions | Processing file ... type=single_file; File does not match allowed extensions |
| 5, 8 | `2026-11-23T190950Z-grouped-219` | The.Witcher.S01E01...HHWEB | `read-error`, 74 | all files failed validation | missing volume(s), parts=74 |
| 6 | same run | Upstream.Color...PmP | `read-error`, 122 | all files failed validation | missing volume(s), parts=122 |
| 7 | same run | Joker.2019...DON | `read-error`, 65 | all files failed validation | missing volume(s), parts=65 |

Before the Play-time check, The Twilight Zone S02 pack by Frys/TAoE was refused 4 times (`2026-11-20T223814Z-baseline-189`, `2026-11-21T002421Z-baseline-205-browse-pause`): AltMount's probe found 8 of its first 8 articles missing ("judged the release dead from its first wave"; "fast-fail segment check failed"). It was never checked then (no `play_check` line), so it was an Unchecked Source, not a Check miss. Every Play-time check since has blocked it (`blocked`, 4 times in `baseline-218`, `grouped-250`), because the BODY of its header article answers 430.

Below, each way a Source can pass and still fail, with how often the runs show it.

### Gap A. A step after the check changes what AltMount gets (Unscramble)

- **What happens.** The check passes a Scrambled RAR set as stored RAR5. AltMount reads volume numbers from the names alone; the NZBs of cases 1, 2, 4-8 name their volumes `<hash>.10` to `<hash>.83` (74 parts), `.10` to `.131` (122) and `.10` to `.74` (65) (read from the stored NZBs in `~/kaijuflow-notes/recordings/kf-189/ninjacentral/`), so AltMount sees volumes 1 to 9 missing and skips the set. Only Unscramble's renaming makes them streamable, and Unscramble reads every volume's first article, which the check never asked about.
- **How often.** 7 of the 8 Check misses, all with Unscramble `read-error`. ADR 0005's amendment says the read errors were "connection trouble while the same walk's checks used Newshosting". Since that amendment (a read error is retried once with the checks stopped and never uploaded), run `grouped-250` unscrambled the same three sets every time (74, 122 and 65 parts, plus a fourth of 66) and had no failed import.
- **Still open.** A first article that is really missing (`missing-article`), `timeout`, `duplicate-volume` and `volume-gap` still upload the original NZB (ADR 0005, amended 2026-11-23), which AltMount will refuse the same way. None of these appear in the runs.

### Gap B. AltMount names the file differently

- **What happens.** KaijuFlow takes the name from the subject's quotes. For case 3 the NZB has 8 par2 files named after the release and one video named `3YuT.mkv`; KaijuFlow checked `3YuT.mkv` (console `Checking video: 3YuT.mkv`, `verified`). AltMount processed it as a single file named `The.Witcher.S01E01.2160p.NF.WEB-DL.DDPA5.1.HDR.DV.HEVC-SiC-AsRequested`, with no extension, and refused it. **(inference)** AltMount judged the short random name obfuscated and named the file after the release, dropping `.mkv`.
- **Related, not yet seen.** A Source whose only video is `.webm` passes KaijuFlow (`src/health/fileClassifier.ts:42`) and fails AltMount's extension list. The episode file KaijuFlow samples is matched on subject names (`src/health/healthCheckPipeline.ts:31-35`), while AltMount picks the episode on its own names, so in an obfuscated pack the two could pick different files **(inference)**.
- **How often.** 1 of 8.

### Gap C. Different articles checked: the sample is small

- **What happens.** KaijuFlow asks about 3 fixed articles of one file. AltMount asks about up to 64 spread over the whole release, the middle ones at random. **(inference, my arithmetic)** If a share *p* of a file's articles is missing at random, all 3 of KaijuFlow's are present with chance (1−*p*)³, all 64 of AltMount's with chance (1−*p*)⁶⁴:

  | Missing share | KaijuFlow passes | AltMount's probe passes |
  |---|---|---|
  | 0.5% | 98.5% | 72% |
  | 1% | 97% | 53% |
  | 2% | 94% | 27% |
  | 5% | 86% | 4% |

  Missing articles usually come in runs, not at random (a takedown removes whole posts, a failed upload loses its end), which helps both checks; damage confined to the middle helps neither **(inference)**.
- **Archive sets are the worst case.** KaijuFlow asks only the first article of 3 volumes. AltMount condemns the whole set when any volume has a sampled miss (`processor.go:469-476`, `:646-660`), and cannot zero-fill inside a set while playing.
- **Season packs.** KaijuFlow checks only the wanted episode. AltMount's probe samples the whole pack; if its first 8 picks are mostly gone, it marks **every** file broken, the healthy wanted episode too (`fast_fail_verdict.go:110-118`, `processor.go:518-528`). A pack where most episodes expired but the wanted one survives passes KaijuFlow and fails AltMount.
- **How often.** 0 of the 8. No `fast-fail segment check failed` followed a passed check in any run.

### Gap D. STAT says present but the body is damaged

- **What happens.** STAT proves only that the server has an article by that name. A body that is truncated, has a bad CRC or holds other data passes STAT. KaijuFlow downloads a body only for an archive's header and does not check its CRC (`src/archive/nntpSegmentDownloader.ts:54-92`). For a clean-named video neither side downloads any body before playing: AltMount skips the first-article fetch (`parser.go:716-745`). The first body is fetched by KaijuFlow's first-byte request (`Range: bytes=0-0`, `src/backends/altmount.ts:196`, `:235`); a damaged article later in the file shows only while watching, as a failed read.
- **How often.** Not seen: no Check miss names corruption, and no run watched video past the first byte.

### Gap E. Different provider or server

- **What happens.** KaijuFlow counts an article present if any of its health-check providers has it, backups included (`src/health/articleChecker.ts:162-243`). AltMount streams from its own provider list. A provider KaijuFlow has and AltMount lacks passes Sources AltMount cannot fetch. The same company can also answer differently from different front-end servers for a short time (the desync AltMount re-checks for, `usenet_reader.go:209-227`).
- **How often.** It cannot happen in the test bed today: both sides use the one Newshosting server (Section 1). It could happen in the owner's own setup if the two configs differ.

### Gap F. Retention edges and time between check and import

- **What happens.** A post can be removed (takedown) or expire between the check and AltMount's probe. That window is seconds (grab, Unscramble, upload). It is much longer for Sources that skip the check: a library hit or a remembered-ready Source plays up to 3 days later with no check (Section 1). KaijuFlow ignores post dates; AltMount passes the post date to the provider (`processor.go:485`), which matters only when `max_article_age_days` is set (0 on the test copy).
- **How often.** Not seen. **(inference)** Takedowns come in waves and hit popular films most, so a Source remembered ready is the likeliest to go stale.

### Gap G. Missing volumes in the NZB itself

- **What happens.** KaijuFlow never checks that the NZB lists every volume of a set. AltMount skips a set whose names leave a gap (`aggregator.go:161-165`), even when every listed article exists. The 3 sampled volumes all exist, so the check passes.
- **How often.** Seen only through Gap A (number names read as gaps). No real missing volume in the runs.

### Gap H. AltMount's own probe runs out of time

- **What happens.** AltMount's 15 s STAT budget ends with an **inconclusive** result, which fails the import (`processor.go:1071`) even though nothing is known missing. This is not a wrong check; a diagnosis must tell it apart, and by ADR 0004 it says nothing about the Source.
- **How often.** AltMount logged "Retrying inconclusive fast-fail STATs ... context deadline exceeded" 17 times, and "proceeding with unverified stragglers" 9 times; no import failed as inconclusive.

### Freezes are invisible to the quick check

The quick check stops reading at the first video bytes (`tools/brain/docs/rules.md`, "Real-use checks", step 4). A Source whose video freezes later counts as played. Only the full check (#271) watches video, so Gaps C, D and F can show up as freezes only there.

## 4. Confirming tests: proving which gap caused a Check miss

Each test is meant to give a yes or no from one Check miss's evidence (the shape in `FAILURE_DIAGNOSIS.md` §6.5). The tools are read-only: `tools/brain/nntp.py` (a logged-in connection to AltMount's provider; `Conn.cmd` sends one command), `tools/brain/statcheck.py <nzb>` (STATs every article of an NZB), `tools/brain/rarorder.py <nzb>` (BODY-reads each number-named part's first article and prints its real RAR volume number).

**The NZB must be saved first.** A quick check deletes its indexer answers when it ends (`tools/brain/docs/rules.md`, step 3); KaijuFlow's NZB cache lives 10 minutes in memory. AltMount keeps a failed NZB: its log line `Moved failed NZB to failed directory new_path=/config/.nzbs/failed/kaijuflow/<name>.nzb` names it. That folder is inside AltMount's test config, so whether the project's guard allows reading it must be checked first. A record or run keeps NZBs in `~/kaijuflow-notes/recordings/<list>/<indexer>/*.body`.

| Gap | Yes when |
|---|---|
| A. Unscramble | the `unscramble` step line before the failed import has a `result` other than `unscrambled` and `not-scrambled`; AltMount's log has `Skipping RAR archive group with missing volume(s)` with the same `parts`; and `rarorder.py` on the saved NZB shows every volume 0 to N−1 once. That last part proves the set itself was complete and only the names failed. |
| B. Naming | KaijuFlow's console `Checking video: <name>` names a file with a video extension, and AltMount's `File does not match allowed extensions filename=<other>` (or `No files with allowed extensions found`) names one without, or whose extension is missing from `import.allowed_file_extensions` in the run's `settings.json`. |
| C. Sample too small | `statcheck.py` on the saved NZB finds missing articles in a non-par2 file; KaijuFlow's own 3 picks, computed from the same NZB by the rule in Section 1, are all present in that output; and AltMount's error is `fast-fail segment check failed`. For a season pack, add: the wanted episode's file has no missing article, and AltMount logged `judged the release dead from its first wave`. |
| D. Damaged body | AltMount's log names a `DataCorruptionError` or CRC mismatch for a segment; STAT of that message-id says 223; BODY of it, decoded, does not match the CRC in its `=yend` line, or its size differs from the NZB's `bytes`. **No tool does the CRC part yet**: `rarorder.py`'s `ydecode` (`tools/brain/rarorder.py:15-28`) decodes but does not check. |
| E. Provider | KaijuFlow's console `Result: 3/3 found (<provider> (n/n), ...)` names a provider whose host is not among AltMount's `providers[*].host` in `settings.json`, compared by a program without printing the hosts; and STAT of the sampled articles through `nntp.py` (AltMount's provider) answers 430. |
| F. Time between | STAT now of KaijuFlow's 3 picks: one answers 430 although `play_check` said `verified` at its `t`. The test must run soon after the miss, since a later 430 proves only that the article is gone now. For a Source that skipped the check, no `play_check` line exists for that play. |
| G. Volume missing from the NZB | the volume numbers in the saved NZB's names (or from `rarorder.py` for number names) leave a gap; AltMount logged `missing volume(s)`; `unscramble` was `not-scrambled` or `unscrambled`. |
| H. AltMount timed out | AltMount's error is `fast-fail segment check inconclusive`, or its log has `Retrying inconclusive fast-fail STATs` for that queue item; and `statcheck.py` finds every non-par2 article present. Not a check miss in substance: the Source is good. |
| Not a health gap | `play_failed` reason `AltMount did not finish preparing within Ns`, or a first-byte failure: the time budget or delivery, not the check. Case 1 above is this, after an Unscramble read error. |

## 5. What the specs and published practice say about checking by sampling

**RFC 3977 (NNTP), §6.2.4 STAT**: "The STAT command behaves identically to the ARTICLE command except that, if the article exists, it is NOT presented to the client and the response code is 223 instead of 220." The only answers for a message-id are 223 "Article exists" and 430 "No article with that message-id". So a 223 says the server will serve an article by that name; it says nothing about the bytes. §3.5 allows pipelining (several commands sent before the answers) but warns that "certain server implementations throw away all text received from the client following certain commands", so answers can be mismatched; KaijuFlow pipelines its STATs and counts any odd answer as missing (`src/health/articleChecker.ts:70-75`), which errs on the side of blocking. The article's CRC is defined by the yEnc format (its `=yend` line carries `pcrc32`), not by NNTP **(from the yEnc 1.3 format; not checked against a source here)**.

**SABnzbd** (`sabnzbd/sabnzbd`, commit `4d9d995`, 2026-11-23):

- Its only check before downloading, **pre-check**, is off by default (`sabnzbd/cfg.py:489`). When on, it STATs **every** article, falling back to HEAD when a server lacks STAT (`sabnzbd/newswrapper.py:235-239`). It needs the available non-par2 bytes, par2 counted toward them, to reach `req_completion_rate`, default 100.2% (`cfg.py:597`; formula at `sabnzbd/nzb/object.py:1295-1320`), with up to 5 bad articles forgiven (`sabnzbd/constants.py:94`, `object.py:1317`).
- While downloading, with `fail_hopeless_jobs` and `fast_fail` on by default (`cfg.py:493-494`), it aborts a job when at least 80% of the first articles of 10 or more files are missing (`object.py:1323-1334`), and afterwards when the missing share is more than par2 can rebuild (`object.py:928-941`).
- It checks every downloaded article's CRC (`sabnzbd/decoder.py:242-244`).

**NZBGet** (`nzbgetcom/nzbget`, commit `3064f1c`, 2026-11-23):

- It has no check before downloading. Its "health" is the share of non-par2 bytes actually downloaded so far (`daemon/queue/DownloadInfo.cpp:293-309`), compared with a "critical health" computed from how much par2 there is, assumed 85% when unknown (`DownloadInfo.cpp:334-364`). `HealthCheck=park` (default, `nzbget.conf:1526`) parks the job when health falls below it.
- Articles are fetched with BODY (`daemon/nntp/ArticleDownloader.cpp:347`). A CRC error counts like a missing article and moves to the next server (`ArticleDownloader.cpp:64-74`, `:539`).

**What this implies for KaijuFlow's check (inference).**

1. Both download clients measure health by downloading bodies, with CRCs, and lean on par2 to cover what is missing. SABnzbd's only check before downloading asks about every article, not a sample. Neither treats a handful of STATs as proof of anything.
2. Read that way, a pass from KaijuFlow's check proves four things. Three named articles of one file existed on the health-check provider at that moment. The NZB names a file KaijuFlow takes for video. For an archive, one header article downloaded and showed stored RAR5 or 7z with a video inside. And the Source is not one of the kinds ADR 0009 blocks.
3. It does not prove that every article exists, that any article's content is intact, that AltMount will name and accept the files the same way, or that a set's volumes are all listed. Sections 3 and 4 list how each shows up.
4. AltMount, the last word on the import, itself samples only 1% (at most 64 articles) and documents why that is enough "with near certainty" for damage near its 2% hole cap (`internal/importer/validation/fast_fail.go:331-336`). It still learns about corrupt bodies only while streaming. So even a check that copied AltMount's sample exactly would prove "AltMount's import will pass" at best, not "the video will play to the end".
5. With one shared provider, as in the test bed, a check that used AltMount's own rule would, by construction, rarely disagree with AltMount's probe; the remaining misses would be Gaps A, B, D, F and G. The price is up to 64 STATs instead of 3; pipelined on one connection, that is still about one round trip to the server, at most a few hundred ms. None of this was measured here.
