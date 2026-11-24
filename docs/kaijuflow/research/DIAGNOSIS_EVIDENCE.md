# What evidence a failed play leaves today (inventory for the diagnosis system)

*Moved here from the notes repo on #280 (spec #279), as written. The evidence folder it asks for (§5: keep the failed Sources' NZBs and all the steps) is built: [formats, "Evidence folder"](../../../tools/brain/docs/formats.md#evidence-folder).*

Written 2026-11-24 from the code on branch `quick-check-270` (working tree, with its uncommitted `quickcheck.py` changes) and from every run folder under `~/kaijuflow-notes/brain-runs/` (13 with a `kaijuflow-test.log`, 15 AltMount logs counting `archive/`). Nothing was edited, run or reset. No quick check folder exists yet, so everything quoted from a log comes from timed runs. Counts are lines in the run folders' logs. A Source played in two cold rounds of one run shows up twice, so a count counts imports or lines, not distinct Sources.

## 0. How the pieces join up, and three gotchas

A play leaves evidence in four places: KaijuFlow's stdout (the `[KF-STEP]` JSON lines plus free text), AltMount's slog lines, the stand-in's request log, and what the brain tools write into `raw.json`. The run folder's `logs/` holds the first three, scrubbed, cut into one chunk per visit, and each chunk starts with a header line such as `--- kaijuflow cold 1 Neon Genesis Evangelion S01E01 2026-11-21T00:30:50.599Z` (for a check, `--- <label> <time>`).

Three facts make matching harder than it looks:

- Times use different clocks. Docker's prefix and KaijuFlow's `t` field are UTC. AltMount's own `time=` field is local time (`time=2026-11-20T18:30:47.152-06:00` on a line whose docker prefix is `2026-11-21T00:30:47.152Z`). The stand-in's `t=` is epoch milliseconds. Join on the docker prefix.
- AltMount's lines that name a cause carry no `queue_id`. Only "Added NZB file to queue", "Successfully processed queue item", "Processing failed" and "Item failed" have one. A cause line ("Skipping RAR archive group with missing volume(s)", "Skipping file due to early fast-fail segment check error") can only be tied to its import by falling between that import's "Added" line and its "Processing failed" line. That is exact while only one import runs at a time, which is the rule since #192, except when the first-Source switch fires at 25 s.
- KaijuFlow's failed `import_wait` line has no `job`. The queue id is added only on success, through the `after` callback in `src/backends/altmount.ts:312`. To join a failed import to AltMount's `queue_id`, match on the release name, which AltMount uses as its file name, sometimes with a 16-hex-digit tag after it (`IMPORT_TAG` in `brainreport.py`), and on the time.

## 1. Per step: what is logged, what is kept, what is missing

Each step below lists KaijuFlow's step line, its free-text lines, AltMount's lines where AltMount takes part, what the brain tools keep, and the gap.

### 1.1 Search (indexer pages)

**Step line.** `indexer_page` (`timeIndexerPage` in `src/utils/stepTiming.ts:405`, called from `src/parsers/usenetSearcher.ts` lines 124/161/267/304/577/625, `src/searchers/prowlarrSearcher.ts` 569/602/667/699 and `src/searchers/nzbhydraSearcher.ts` 561/578). Its fields are `step, source` (the indexer), `ms, ok, t, ref, page`. Across all logs there are 1266 lines, 34 of them `ok:false`. Example: `{"step":"indexer_page","source":"NinjaCentral","ms":295,"ok":true,"t":"2026-11-21T00:30:24.878Z","ref":"tt0052520:2:6","page":1}`. A failed page carries no HTTP status and no body.

**Free text.** `❌ Search error for NinjaCentral:` spreads over several lines, and the answer is on the lines after it:

```
❌ Search error for NinjaCentral:
   Status: 503
   Data: not recorded
```

(34 times, grouped-265.) Searches show up as `🔍 Searching NinjaCentral: <url> [...]`.

**Stand-in.** Each request writes one line: `HIT` (4655), `MISS` (3265), `RECORD` (527), `EMPTY` (112) or `ERROR <slug> <request> -> <status>`, plus `LIMIT_REACHED indexer=<slug> ...`. Each line ends with `from=<ip> t=<epoch ms>`. Examples: `EMPTY ninjacentral api cat=2000&extended=1&offset=82&q=Inception 2010&t=search from=172.18.0.6 t=1794743051067` and `RECORD ninjacentral nzb aHR0cHM6Ly9u -> 200 3487988 bytes from=172.18.0.3 t=1795213264775`.

**Kept.** A run's `raw.json` keeps `indexer_page` lines by `ref` (`attribute_steps`), plus `indexer_s`, `misses` and `limit`. A quick check keeps none of them (`KEPT_STEPS` in `quickcheck.py:26` is `list_filter, play_check, played, play_failed`), only `limit`.

**Gap.** Nothing structured records what the indexer answered for a failed page: the status, the newznab error code, the body. In a check the stand-in runs in record mode on a store that is deleted after the check (`formats.md`, "Check folder"), so the answer itself is gone. An `ERROR` line keeps only the status. **Fetch afterwards:** for a timed run, the Recording's store (`<store>/<list>/<slug>/<sha256>.body` and `.meta.json`). For a check, nothing can fetch it unless the check keeps its answers, and asking the indexer again costs allowance.

### 1.2 List and filters

**Step lines** (`src/addon/index.ts:194, 328, 351, 352, 360`; `src/addon/streamBuilder.ts:106`):

- `list_filter` has `results` and `kept`.
- `list_sort` has only the time.
- `fallback_group` has `candidates` and `groups`.
- `list_build` has `streams`.
- `head_start` has only the time.
- `list` has `cache` (hit or miss), `streams`, `cpu_ms`, `gc_ms`, `gc_n`, `loop_max_ms`, `loop_p99_ms`, `elu` and `heap_mb`.

There are 138 of each since #249. Example: `{"step":"list_filter","ms":..,"ok":true,"ref":"…","results":N,"kept":N}`.

**Free text** (counts across logs):

- `🚫 Filtered N dead NZB(s) from results (N remaining)` (159).
- `🚫 Filters dropped N/N candidate(s) — No disc images: N` (157), which counts per filter.
- `🚫 Filtered out N blocked/error NZB(s)` (94, the old list-time check).
- `✂️ <release>` lines, one per dropped release.

**Kept.** A check keeps `list_filter`, and `judge` turns it into "the search found 12 releases and the filters kept none" (`quickcheck._search_text`). Runs keep all the list lines by `ref`.

**Gap.** Step lines never say which Sources the Source memory dropped as dead, or why each filter dropped what it did. That is only in free text, and only per filter. For "nothing to play" against "a Source that would have played was marked dead" (the GLOSSARY's *Nothing to play*), a diagnosis needs the dead marks behind the drop. **Fetch afterwards:** the test copy's `config/dead-nzbs.json`, which holds each dead mark's reason. The project hook refuses reads of the test folder's configs, so this needs a sanctioned reader. The tools have none today.

### 1.3 Play-time check (health check)

**Step line.** `play_check` (`src/play/playTimeCheck.ts:62`). Its fields are `source, title, ok, status, ms, t, ref`. There are 808 lines: 342 `verified_stored`, 304 `blocked`, 161 `verified` and 1 `error`. No line is written when the check's pool was stopped. Example: `{"step":"play_check","source":"NinjaCentral","ms":1048,"ok":true,"t":"2026-11-23T19:12:17.377Z","ref":"tt5180504:1:1","title":"The.Witcher.S01E01.The.Ends.Beginning.2160p.NF.WEB-DL.DDP5.1.Atmos.DV.HEVC-HHWEB","status":"verified_stored"}`. **The line has no `message`.** It does not say why a Source was blocked.

**Free text.** The reason appears twice. The first copy is the pipeline's line, prefixed with the first 25 characters of the release in brackets (`src/health/healthCheckPipeline.ts:129,137,256,356`):

- `→ Blocked: Archive header unreadable` (221)
- `→ Blocked: Encrypted archive (password in NZB)` (131)
- `→ Blocked: N/N missing` (43)
- `→ Blocked: RAR4 archive` (24)
- `→ Blocked: No video files in archive` (22)
- `→ Blocked: Nested archive` (1)
- `→ Blocked: no video or archive file named (largest: …)` (1)
- `→ Blocked: disc image (…)` (code only)

The second copy is the Walk's line with the full release (`src/play/ultimateFallback.ts:384`), for example `👑 Ultimate-Fallback [<session>:series:tt0052520:2:6] ❌ #3 not healthy (Archive header unreadable) — The Twilight Zone (1959) Season 2 Complete …`. Its counts are Archive header unreadable 160, Encrypted archive (password in NZB) 91, `Missing N of N segments` 19, No video files in archive 16, RAR4 archive 16, and `Check failed: All providers failed to connect` 1.

The NNTP answer shows only on the archive-inspection warning: `⚠️ Archive inspection failed (Newshosting): Article not found: 430 No Such Article` (204 lines) or `⚠️ Archive inspection failed (Newshosting): getaddrinfo EAI_AGAIN news.newshosting.com` (1). Sampling prints `Checking 3 segments across 1 provider(s)` and then `Result: 0/3 found ()`. A provider outage prints `Pool check failed: Error: getaddrinfo EAI_AGAIN news.newshosting.com` (`src/health/articleChecker.ts:198`) and `❌ Health check error for <url> All providers failed to connect` (`healthCheckPipeline.ts:388`).

A trap: **"Archive header unreadable" means two different things.** `whyAltMountCannotStream` (`src/health/altmountPassRule.ts:20,27`) returns it both when inspection failed outright (`info` null, for example a 430 on the first segment) and when the header was read but its format was unknown or it listed no files. The two can only be told apart by whether an `Archive inspection failed (…)` warning came just before.

**Kept.** Both a run and a check keep `play_check`. A check makes `checked: [{release, ok, status}]` out of it.

**Gap.** The step line has no reason for a block, no `episodeOnly`, no `containerType`, and does not say which segments were sampled (message-ids), what each NNTP answer was (430, timeout, connection reset), or which provider answered. **Fetch afterwards:** `tools/brain/nntp.py` can `STAT` or `ARTICLE` any message-id from the NZB, read-only, with AltMount's provider. That needs the NZB: for a run it is in the Recording's store, for a check it is gone. `checkSource`'s result object already holds `message` and `containerType`, so adding them to the line is cheap.

### 1.4 NZB grab

**Step line.** `nzb_fetch` (`src/backends/sourceNzb.ts:46`). Its fields are `source, title, ms, ok, t, ref`. There are 636 lines, all `ok:true`: a grab that throws writes `ok:false`, but none in these logs did. The line carries no byte count and no HTTP status. Walk grabs (`walkGrab`, `src/backends/nzbGrab.ts:132`) write no step line at all. The prepare's later `nzb_fetch` then finds the NZB in the cache, which is why it takes 2 ms in chain A (§3), so in a Walk the real grab's time and outcome are in free text only.

**Free text.** `📥 Downloading NZB from indexer: <url>...` is followed by `✅ NZB downloaded (4483659 bytes)` or `💾 Using cached NZB from health check (N bytes)`. A failure prints `👑 Ultimate-Fallback [...] ❌ Grab failed for #N <release>: <message>` (`ultimateFallback.ts:450`), where the message is one of these (`src/backends/nzbGrab.ts:48–112`):

- `Failed to download NZB from <indexer>: <status> (indexer unavailable, Source kept)` for a 429 or 5xx. Real example: `Failed to download NZB from NinjaCentral: 503 Service Unavailable (indexer unavailable, Source kept)`, grouped-250.
- `… (indexer refused us, check its API key; Source kept)` for a 401 or 403.
- A bare `Failed to download NZB from <indexer>: 404 …` for a gone link, which is a Source failure.
- `Indexer says the NZB is gone (code 300): …`
- `Indexer <x> refused the grab: … (code N; indexer unavailable, Source kept)`
- `Invalid NZB content received (N bytes)`
- `NZB download timed out after Ns for <x>`
- `NZB download stopped for <x>`

After the first refusal comes `⏭️ NinjaCentral refused a grab: skipped for the rest of the Walk, its Sources kept (ADR 0004)`. The 3125 `Grab failed for` lines in the 11-21 to 11-23 runs carry **no message**, because those builds did not print one. They line up with 3265 stand-in `MISS ninjacentral nzb …` lines, NZBs the Recording did not hold.

**Kept.** A run keeps `nzb_fetch` for the played Source. A check keeps nothing of the grab.

**Gap.** There is no step line for a grab failure, and its reason (refusal against gone link) lives only in free text, although ADR 0004 hangs the walk's choice on exactly that difference. **Fetch afterwards:** the stand-in log (`MISS`/`RECORD`/`ERROR … -> status`) gives each grab's status by time and `from=` address. The Recording's store holds the NZB body (run only).

### 1.5 Unscramble

**Step line.** `unscramble` (`sourceNzb.ts:86`, and `:92` for a throw). Its fields are `source, title, ms, ok, t, ref, wait_ms, result, parts` and, on the second try, `retry: true`. There are 595 lines: `not-scrambled` 343, `not-rar5` 160, `unscrambled` 81, `read-error` 9, `timeout` 2. The other values the code can write (`src/archive/unscramble.ts:31`) are `no-provider`, `missing-article`, `duplicate-volume`, `volume-gap`, `stopped`, and `failed` on a throw. Example: `{"step":"unscramble","source":"NinjaCentral","ms":8769,"ok":true,"t":"2026-11-23T19:12:26.150Z","ref":"tt5180504:1:1","title":"The.Witcher.S01E01…HEVC-HHWEB","wait_ms":0,"result":"read-error","parts":74}`. Note that `ok` stays `true` for every result except a throw.

**Free text** (`sourceNzb.ts:58,66,87–93`):

- `🧩 Unscrambled RAR set: N parts renamed in volume order (N ms)`.
- `🧩 Unscramble skipped (<reason>, N parts, N ms): uploading the original NZB` (not-rar5 119, read-error 7 in old builds).
- `🧩 Unscramble read-error: retrying once, the Walk's other checks stopped` (current builds).
- `⏸️ Checks stopped for an Unscramble retry: #2, #3`.
- `🧩 Unscramble failed (<message>): uploading the original NZB`.
- The error thrown after a second read-error: `Unscramble could not read the Scrambled RAR set (read-error, retried once): not uploaded`.

**Kept.** Runs keep it for the played Source. Checks do not keep it.

**Gap.** The line does not say which part failed, its message-id, or what the NNTP error was. `readVolume` (`unscramble.ts:302–330`) swallows the error text and keeps only `missing-article` or `read-error`. **Fetch afterwards:** `tools/brain/rarorder.py <file.nzb>` reads the first article of every part and prints each part's real volume number. Combined with `nntp.py`, it can tell a missing article apart from a connection error and find a gap in the volumes. It needs the NZB.

### 1.6 Upload to AltMount and import

**Step line.** `import_wait` (`altmount.ts:273`) with `includes_upload: true`, because one request uploads and waits. The `upload` step is declared in `STEP_NAMES` but never written. Its fields are `source, title, ms, ok, t, ref, includes_upload` and `job` on success only. There are 538 lines, 16 `ok:false`. Example: `{"step":"import_wait","source":"NinjaCentral","ms":9458,"ok":false,"t":"2026-11-21T00:30:47.154Z","title":"The.Twilight.Zone.(1959).S02.(1080p.BDRip.x265.10bit.FLAC.2.0.-.Frys).[TAoE]","includes_upload":true}`. The line has no HTTP status, no reason and no job.

**Free text.** `📤 Sending Source to AltMount (waits up to 300s)`, then either `✅ AltMount prepared the Source (<status>)` or the thrown message, which `prepare` prints in the Walk as `[prepare #N] ❌ Failed: <message>` and `❌ Prepare failed for #N <release>` (`ultimateFallback.ts:433–434`), and the clicked-entry path as `❌ Stream failed [i/n] <release>: <message>` and `❌ All N candidate(s) exhausted, serving failure video` (`streamHandler.ts:861,908,941`). The messages (`altmount.ts:284–309`) are:

- `AltMount is not reachable (…)`: not the Source's fault.
- `AltMount did not finish preparing within Ns` (408; 1 seen).
- `AltMount rejected the Source (400|422): <body>`
- `AltMount could not process the Source: <body>` (500 that is not on the AltMount-side list `BACKEND_SIDE_500`; 11 seen).
- `AltMount returned status N: <body>`
- `AltMount returned no ready file for this Source`

A real one: `❌ Stream failed [1/1] The.Twilight.Zone.(1959).S02.(1080p.BDRip.x265.10bit.FLAC.2.0.-.Frys).[TAoE]: AltMount could not process the Source: {"error":{"code":"INTERNAL_SERVER_ERROR","details":"","message":"fast-fail segment check failed: no regular files were successfully processed (all files failed validation)"},"success":false}`.

**AltMount's own lines** are in §2.

**Kept.** `raw.json` `imports` holds `{name, queue_id, start, end, seconds, ok}` per AltMount import in the visit's window (`brainreport.altmount_imports`, `brainreport.py:146`). **It drops AltMount's `error=` text and every cause warning.** A run also keeps `cause`, the first `play_failed` reason (§1.8). A check keeps `play_failed` lines and turns them into `check_misses: [{release, reason}]`.

**Gap.** The reason AltMount actually acted on (the missing volume and its `first_file`, which files failed fast-fail) never reaches KaijuFlow: its HTTP body carries only the queue item's top-level error (§2). It is in AltMount's log alone, joined by time. **Fetch afterwards:** the run folder's `logs/altmount-kf-test.log`, and `rarorder.py` on the NZB to confirm a missing volume.

### 1.7 First byte

**Step line.** `first_byte` (`altmount.ts:319`). Its fields are `source, title, job, ms, ok, t, ref`. There are 665 lines, all `ok:true`.

**Free text.** On failure, `⚠️ First byte failed: <what>; asked for <path>; Backend offered: <names>` (`src/backends/firstByte.ts:36`). The thrown messages are `First byte failed (<what>); the Source is kept: <path>`, `Video file not servable (<status>): <path>` and `Video file not servable (probe failed after N attempts): <path>` (`altmount.ts:207,221`). None appears in these logs.

**Kept.** Runs keep it. `brainreport.visit_cause` falls back to "first byte failed after N s". Checks keep only `play.first_byte_s`.

**Gap.** The step line does not carry the HTTP status of the probe or the offered names. There is no real example yet to test a sign on.

### 1.8 Played on, or failed

**Step lines.** `played` (`streamHandler.ts:182`, through `logPlayedOnce`, once per press per 15 s) and `play_failed` (`streamHandler.ts:862,909`; `ultimateFallback.ts:435`). Their fields are `step, source, title, ms:0, ok, t` and, for `play_failed`, `reason`. There are 98 `played` lines. **They carry no `ref`**, because they are written in the HTTP route outside `withStepRef`, so they belong to a visit by time only. Example: `{"step":"played","source":"NinjaCentral","ms":0,"ok":true,"t":"…","title":"…"}`.

There is **no `play_failed` line in any run log**. The only run since #242 with a prepare in it, grouped-250, had no failed import. The `cause` values in older `raw.json` files were read from free text before #242. The shape, from the code: `{"step":"play_failed","source":"NinjaCentral","title":"<release>","ms":0,"ok":false,"reason":"<stepReason(err)>"}`.

`stepReason` (`stepTiming.ts:395`) keeps the first line, replaces URLs with `<url>`, cuts everything after `: /`, and **cuts at 200 characters**. AltMount's 229-character answer is cut mid-message, so the reason ends `…"message":"fast-fail segment check failed: no regular files were successfully processed (all files failed v`. The `: /` cut also drops the path from "Video file not servable (404): /…".

**Playing on.** A quick check stops at the first video, so it records nothing after that. A run records `seeks`. In a full check, freezes and broken skips will need their own evidence, and none exists today: no step covers them, and KaijuFlow logs no stall.

**Gap.** `played` cannot be tied to a title by `ref`. `play_failed` is not proven in a real log, and its 200-character cap cuts the most useful part of AltMount's message.

## 2. AltMount: what it logs on a refused or failed import

**The lifecycle lines** carry `queue_id`. A failed import goes:

```
level=INFO msg="Added NZB file to queue" component=importer-service file="/tmp/.altmount-queue/<name>.nzb" queue_id=N
level=WARN msg="Processing failed" component=importer-service queue_id=N file=/tmp/.altmount-queue/<name>.nzb error="<reason>"
level=ERROR msg="Item failed" component=importer-service queue_id=N file=/tmp/.altmount-queue/<name>.nzb
```

A successful import ends with `msg="Successfully processed queue item"` instead. Across all 15 AltMount logs there were 551 imports: 519 ok and 32 failed.

**The `error=` reasons on "Processing failed"** (32 in all; "addon" is the AltMount-direct side of older runs, "kf" is KaijuFlow's AltMount):

| Count | Side | `error=` | Releases | The cause line just before it |
|---|---|---|---|---|
| 16 | addon | `NZB validation failed: invalid NZB: total size is zero` | Chernobyl S01E02 onlyfaffs ×12, Vialle ×4 | `Excluding unreachable files from import` (12 lines), `Skipping file due to early fast-fail segment check error` |
| 9 | kf | `no files were successfully processed (all files failed validation)` | Witcher S01E01 HHWEB ×5, Upstream Color PmP, Joker DON, Inception FGT, Inception 4K4U | always `Skipping RAR archive group with missing volume(s)` (9 of 9) and `No files with allowed extensions found` |
| 4 | kf | `fast-fail segment check failed: no regular files were successfully processed (all files failed validation)` | Twilight Zone S02 Frys pack ×4 | `Skipping file due to early fast-fail segment check error` (5 per import, one per `.partNNN.rar`), sometimes `Retrying inconclusive fast-fail STATs` |
| 2 | kf | `no files with allowed extensions found (allowed: [.mkv .mp4 …])` | The Matrix 4K Remastered MAMA (archive run, a disc image) | `UDF: file ICB read failed, dropping file from listing` |
| 1 | kf | `file '<name>' does not match allowed extensions (allowed: […])` | Witcher S01E01 SiC-AsRequested | `File does not match allowed extensions filename=<name>` |

**The cause lines quoted as logged:**

- `level=WARN msg="Skipping RAR archive group with missing volume(s)" first_file=7a870da9cbcc480a075cde6a2bd4dbd5.10 parts=74` (9). This is the "missing RAR volume". The `first_file` is a scrambled part name, and it follows an `unscramble` `read-error` on the same release (§3, chain A).
- `level=WARN msg="Skipping file due to early fast-fail segment check error" component=nzb-processor file=The.Twilight.Zone.(1959).S02.(…).[TAoE].part001.rar` (32). It names the file but not the segment or the NNTP answer.
- `level=WARN msg="Retrying inconclusive fast-fail STATs" attempt=2 remaining=2 delay=100ms error="context deadline exceeded"` (23). This is AltMount's own NNTP STAT timing out.
- `level=WARN msg="Excluding unreachable files from import"` (12), `msg="Failed to normalize segment sizes with yEnc headers"` (11), `msg="UDF: file ICB read failed, dropping file from listing"` (2), and `msg="File does not match allowed extensions"` (1).

**Noise, not signs.** `msg="First segment has no data" component=nzb-parser file="[003/186] - \"….7z.003\" yEnc 157286400 (1/220)"` is the most common line in every AltMount log (33,777 lines), but it shows up inside 514 of the 519 *successful* imports and 27 of the 32 failed ones. It does not mark a failure and must never be a sign. The same goes for `No files with allowed extensions found` (96 lines but only 11 failures: it is written per archive group before the RAR analysis), for `subscriber channel full, skipping update` (126) and for the `Live heap is pressing on the Go memory limit…` warning (9).

**What its HTTP answer says.** KaijuFlow received, every time in these logs, `500 {"error":{"code":"INTERNAL_SERVER_ERROR","details":"","message":"<the error= text>"},"success":false}`. Six of those answers held "no files were successfully processed (all files failed validation)", four the fast-fail text and one the "does not match allowed extensions" text. The research doc (`docs/kaijuflow/research/ALTMOUNT_INTEGRATION.md:49`) says the pinned source can also answer a bare 500 "NZB processing failed". In these runs the body always carried the item's own `error=` text, but **never the cause line under it**. So the answer says "no files were successfully processed", while only the log says "missing volume(s), first_file=…10, parts=74". Read the gotcha that way: the answer stops at the top-level error, and the cause lives only in AltMount's log.

## 3. Two full chains, as they appear today

**Chain A: a check miss (Witcher S01E01 HHWEB, grouped-219 at 19:12, and four more runs).**

1. `play_check` comes back `verified_stored` (the check passed).
2. `nzb_fetch` is ok in 2 ms.
3. `unscramble` takes 8769 ms and gives `read-error` with `parts:74`, so the original NZB was uploaded (an old build, before the #245 retry).
4. AltMount writes `No files with allowed extensions found file_count=1`, then `Analyzing RAR archive content parts=74`, then `Skipping RAR archive group with missing volume(s) first_file=7a870da9cbcc480a075cde6a2bd4dbd5.10 parts=74`, then `Processing failed … error="no files were successfully processed (all files failed validation)"`, then `Item failed queue_id=10`.
5. KaijuFlow writes `import_wait` `ok:false`, then `❌ Prepare failed for #1 …HHWEB`.

The diagnosis is a scrambled RAR set that Unscramble could not read and AltMount could not open. Today a check's `raw.json` would hold only steps 1 and 5 plus `reason` (cut at 200 characters). Steps 3 and 4 survive only in `logs/`.

**Chain B: a whole pack that is not on the server (Twilight Zone S02 Frys, baseline-189 and baseline-205, two rounds each).**

1. `nzb_fetch` is ok, 4,483,659 bytes.
2. `unscramble` gives `not-scrambled`.
3. AltMount writes 5× `Skipping file due to early fast-fail segment check error file=….partNNN.rar`, then `Processing failed error="fast-fail segment check failed: …"`.
4. KaijuFlow prints the 500 body and then `All 1 candidate(s) exhausted, serving failure video`.

These runs are from before the Play-time check: the Source was a clicked entry that the old list-time check never sampled. The NNTP answer AltMount got (430 or a timeout) is not logged anywhere.

## 4. What the brain tools keep and what they throw away

**A timed run** (`brainrun.collect_visit`, `brainrun.py:1158`, re-attributed by `finalize_steps`):

- A visit keeps `tries` (HTTP facts, with the list text cut to 140 characters) and `steps`, chosen by `attribute_steps`:
  - the `ref` steps and list lines for the title;
  - every `play_check` in the window;
  - prepare-side lines (`nzb_fetch`, `unscramble`, `import_wait`, `first_byte`) only when their `title` matches `played_source`, the *first* Source tried.
- Reading the code, when Best falls back, the prepare lines of the Source that finally played are dropped, and so is any second Source prepared by the 25 s first-Source switch.
- It also keeps `imports` (with no reason), `played_source`, `cause` (the first `play_failed` reason only) and `limit`. In a run with misses, it keeps `misses`, `indexer_s` and `not_recorded`.
- `classify_failure` (`brainreport.py:610`) sorts a failure into only `indexer_limit`, `not_recorded`, `backend_rejection`, `failure_video` or `other`.

**A quick check** (`brainrun.collect_check_visit`, `brainrun.py:1438`; `quickcheck.visit_steps` and `judge`):

- A visit keeps only `list_filter`, `play_check`, `played` and `play_failed`, plus `imports` (no reason) and `limit`.
- It throws away `indexer_page`, `list` and its process trace, `nzb_fetch`, `unscramble`, `import_wait` and `first_byte`.
- The outcome keeps `checked: [{release, ok, status}]` and `check_misses: [{release, reason}]`.
- The stand-in's answers, the NZBs among them, are deleted after the check. Nothing can be re-read offline then, short of a fresh grab.

**Both keep the raw logs.** `logs/` holds KaijuFlow's and AltMount's lines per visit, scrubbed, and for a run the stand-in log too. So nothing above is lost for good *within the folder*, but none of it is in structured form. Every sign that needs AltMount's cause line, the health check's message or the NNTP answer has to be read from `logs/` again.

## 5. Gaps at a glance, and what could fetch each one afterwards

| Step | What a diagnosis needs and cannot see today | Could fetch it afterwards |
|---|---|---|
| Search | the indexer's status and body for a failed page; `indexer_page` has only `ok:false` | Recording store (run); stand-in `ERROR … -> status` line; nothing for a check (store deleted) |
| List/filters | which Sources were dropped as dead, and the dead mark's reason | the test copy's `dead-nzbs.json` (needs a reader the hook allows) |
| Play-time check | the block reason on the step line; which segments were sampled; the NNTP answer per segment and provider; whether "Archive header unreadable" came from a 430 | `nntp.py` STAT/ARTICLE on the NZB's message-ids; the free-text `not healthy (…)` and `Archive inspection failed (…)` lines in `logs/` |
| NZB grab | a step line for a failed grab, with HTTP status, bytes and refusal-or-gone | the stand-in log (status by `from=`/`t=`); the free-text `Grab failed for … : <message>` |
| Unscramble | which part failed, its message-id and the NNTP error behind `read-error` | `rarorder.py` on the NZB (real volume per part); `nntp.py` |
| Import | AltMount's cause line (missing volume and `first_file`, fast-fail files) and the `error=` text, kept with the import; a `job` on a failed `import_wait` | `logs/altmount-kf-test.log` joined by time window; `rarorder.py` to confirm the gap |
| First byte | the probe's status and what AltMount offered, on the step line | the free-text `First byte failed: …` line (none seen yet) |
| Played/failed | a `ref` on `played`; the full AltMount message in `play_failed` (cut at 200 characters) | nothing: it has to be written |
| Playing on | freezes and broken skips | nothing today (a full check needs its own measurement) |

All of these fetches need the NZB. A run's Recording has it, a check throws it away. Keeping each failed Source's NZB in the check's evidence folder (it holds no keys; its links point back at the stand-in) is the single change that makes `nntp.py` and `rarorder.py` usable after any check.

## 6. A first proposal for signs

A sign should be a stable string or field that names the kind of failure, with no release name, time, id, count or size. Each sign below gives where it is read and a real example, with the run-specific parts removed. "From KaijuFlow" means a step line where one exists, else a free-text line. "From AltMount" means a line inside the import's time window.

**Search and grab**

1. `search-unavailable`: an `indexer_page` with `ok:false`, together with `Search error for <indexer>:` and `Status: 503` on the next line. If `Data: not recorded` follows, it is the stand-in's gap (sign `not-recorded`), not the indexer's.
2. `indexer-limit`: `brainreport.LIMIT_RE` matches, or the stand-in writes `LIMIT_REACHED indexer=`. The tools already handle this one.
3. `grab-refused`: `Failed to download NZB from <indexer>: (429|5xx) … (indexer unavailable, Source kept)` or `(indexer refused us, check its API key; Source kept)`, followed by `refused a grab: skipped for the rest of the Walk`.
4. `grab-gone`: `Failed to download NZB from <indexer>: (404|410)` with no `Source kept`, or `Indexer says the NZB is gone (code 300)`.
5. `grab-not-recorded`: a stand-in `MISS <slug> nzb` at the grab's time, against a 503 grab failure (runs only).

**Play-time check.** Read the `play_check` line's `status` together with the message in `not healthy (<message>)`:

6. `check-blocked:encrypted`: `Encrypted archive (password in NZB)` or `(no password)`.
7. `check-blocked:rar4`: `RAR4 archive`.
8. `check-blocked:nested`: `Nested archive`.
9. `check-blocked:no-video-in-archive`: `No video files in archive`.
10. `check-blocked:header-430`: `Archive header unreadable`, with `Archive inspection failed (<provider>): Article not found: 430 No Such Article` just before it for the same release tag.
11. `check-blocked:header-unknown`: `Archive header unreadable` with no inspection warning before it.
12. `check-blocked:segments-missing`: `Missing <n> of <m> segments`, or `→ Blocked: <n>/<m> missing`.
13. `check-error:provider-down`: `Check failed: All providers failed to connect`, together with `getaddrinfo EAI_AGAIN` or `Pool check failed`.
14. `check-blocked:disc-image`: `→ Blocked: disc image (` or the message `Disc image`.

**Unscramble.** Read the `unscramble` line's `result`:

15. `unscramble-read-error`: `read-error`, optionally with `retry:true`, then either `Unscramble could not read the Scrambled RAR set (read-error, retried once): not uploaded` (current builds) or an upload that fails (old builds).
16. `unscramble-not-rar5`, `unscramble-missing-article`, `unscramble-volume-gap`, `unscramble-duplicate-volume`, `unscramble-timeout`: the matching `result` values. Each is a sign of its own, and none means failure by itself: `not-rar5` happened 160 times, mostly on plays that worked.

**Import (AltMount).** From AltMount, the `error=` text on "Processing failed", refined by the cause line in the same window:

17. `import-missing-rar-volume`: `Skipping RAR archive group with missing volume(s)` and `error="no files were successfully processed (all files failed validation)"`. Paired with sign 15 on the same Source, this is chain A: a **check miss** from a Scrambled RAR set.
18. `import-fast-fail`: `error="fast-fail segment check failed: …"` with `Skipping file due to early fast-fail segment check error`. Articles were missing that the check did not sample. When the same Source's `play_check` passed, it is a **check miss**.
19. `import-no-allowed-extension`: `error="no files with allowed extensions found` or `error="file '…' does not match allowed extensions`. The Source holds no file AltMount will serve (a disc image, or a file with no extension). It is a check miss whenever the check passed it.
20. `import-zero-size`: `error="NZB validation failed: invalid NZB: total size is zero"` with `Excluding unreachable files from import`.
21. `import-timeout`: `AltMount did not finish preparing within` (408).
22. `backend-unreachable`: `AltMount is not reachable (`, or a 500 that matches `BACKEND_SIDE_500`. The Backend is at fault, not the Source.
23. `import-stat-timeouts` (a modifier, not a cause): `Retrying inconclusive fast-fail STATs … error="context deadline exceeded"` inside the window means AltMount's provider was slow during the import.

**First byte and the play**

24. `first-byte-gone`: `First byte failed:` with a 404 or 410, or `Video file not servable (404|410)`.
25. `first-byte-kept`: `First byte failed (…); the Source is kept`.
26. `wrong-title`: `quickcheck.judge`'s `the wrong title played: … (` followed by its `why` text with the release removed.
27. `walk-ran-out` and `walk-ceiling`: `❌ Exhausted all N candidates`, `Walk stopped: N grabs, the most one Walk makes`, or the error `Ultimate-Fallback found no Source to play`.

**Never a sign:** `First segment has no data`, `No files with allowed extensions found` on its own, `subscriber channel full`, the Go heap warning, and any `ok:true` `unscramble` line on its own.

To make these signs readable without parsing free text, the cheapest code changes would be these:

- Add `message` (and `containerType`) to `play_check`.
- Add the HTTP `status` and the reason to failed `nzb_fetch`, `import_wait` and `first_byte` lines, and `job` to a failed `import_wait`.
- Raise `stepReason`'s 200-character cap, or keep only AltMount's `message`.
- Give `played` a `ref`.
- Have `altmount_imports` keep `error` and the cause lines in each import's window.
- Have a check keep the failed Sources' NZBs, and keep all its steps, not just `KEPT_STEPS`.
