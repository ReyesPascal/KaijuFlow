# KaijuFlow

KaijuFlow is the owner's maintained fork of Usenet Ultimate. It finds Usenet releases for a title, checks they are complete, and hands them to a backend that turns them into a playable video.

## Language

**KaijuFlow**:
The owner's maintained fork of Usenet Ultimate v1.4.1, continued because the original is no longer maintained.
_Avoid_: KF (in docs), UU fork

**Upstream**:
The original Usenet Ultimate project at v1.4.1, which KaijuFlow was forked from and no longer tracks.
_Avoid_: Usenet Ultimate (when you mean KaijuFlow), original

### Finding and playing

**Source**:
One NZB that search found for a title, whether or not it is complete. A Source might be streamed; it is not yet a Stream.
_Avoid_: result, release, NZB (when you mean the search result), "source" for code

**Healthy Source**:
A Source that passed a health check, so its articles are believed to be available.
_Avoid_: verified result, good source

**Stream**:
The playable link a Backend produced for one Source.
_Avoid_: tile, source (when you mean the link)

**Backend**:
A separate service that takes one Source, prepares it, and serves its video file to the player. NzbDAV, AltMount and InfiniDysk are Backends.
_Avoid_: streamer, engine, provider (providers are Usenet servers)

**Parity**:
The bar for supporting a new Backend: any Source that plays through NzbDAV also plays through the new Backend, seeking works, and a Source that fails shows the failure video and is not offered again.
_Avoid_: compatibility, support (unqualified)

### Preparing a Source

**Scrambled RAR set**:
A Source whose RAR parts are named only by numbers that do not match their real volume order.
_Avoid_: obfuscated release (obfuscated names can still be in order), broken RAR, shuffled parts

**Unscramble**:
Renaming the parts of a Scrambled RAR set into a normal RAR volume series in their real volume order, before the Source goes to the Backend.
_Avoid_: reorder, repair, fix names

**Auto-queue**:
KaijuFlow preparing the Healthy Sources of a list on the Backend in the background, right after the list is built and before any play (setting `autoQueueMode`: the top one, all of them, or off). A play of a Source already being prepared joins that prepare.
_Avoid_: pre-warm, preload, prefetch

**Play-time check**:
The health check run when a Source is clicked rather than before the stream list is sent: the list goes out at once, unchecked, and the Sources about to be played are checked then (spec #183). Replaces checking a whole list before it is shown.
_Avoid_: lazy check, on-demand check, deferred check

**Best entry**:
The entry on top of KaijuFlow's stream list ("KaijuFlow ▶ Best") that plays the first Healthy Source among the top few, found by a Play-time check, rather than one chosen Source.
_Avoid_: auto entry, smart pick, top pick (the top pick is the first Source of a list)

**Disc image**:
A Source whose content is a disc image file (`.iso`, `.img`) that the Backends cannot play; the health check blocks it.
_Avoid_: ISO release, Blu-ray rip

### Measuring

**Cold start**:
The first play of a Source on a Backend, when the Backend has never held it and must import it before the video can start.
_Avoid_: first play (unqualified), fresh start

**Warm start**:
A later play of a Source the Backend already holds, so the video starts from what the Backend has.
_Avoid_: cached play, repeat play

**Side**:
One setup that is played in a timed run: KaijuFlow, Usenet Ultimate, AltMount direct, or KaijuFlow with one page per indexer. Each side has its own test copy.
_Avoid_: variant, candidate, contestant

**AltMount direct**:
The side where the player gets its Streams from AltMount itself, with no KaijuFlow or Usenet Ultimate in front of it.
_Avoid_: AltMount's own addon, addon, AltMount alone

**Short run**:
A timed run that is not the full plan: fewer than the three main sides, one round instead of two, or fewer titles than the list. Made with `--sides`, `--rounds`, `--quick` or a title subset, for a quick check while tuning. Its report, `meta.json`, INDEX.md row and `check` say what it played, and it is never a baseline.
_Avoid_: partial run, quick run (`--quick` is one way to make one)

**Pass**:
The sides that are played together, title by title in turn, through every round, with a reset of their test copies before each cold round. A timed run has a pass of the three main sides and, with the one-page side, a pass of that side after it. A record command's pass is one cold and one warm round, followed by its proof replay.
_Avoid_: batch, phase (cold or warm is the phase)

**Round**:
Every title played once, cold or warm, on every side of a pass. A timed run plays four rounds: cold, warm, cold, warm. A side's figures for a round are made of its own plays in it; the time a round takes covers every side of the pass.
_Avoid_: iteration, lap

**Top pick**:
The first Source in a side's list for a title, the one a round plays. Two top picks are the same Source when their sizes match. Video that arrives after the top pick's own import failed is a **fallback**: counted as played since #185, shown as "played after N fallbacks" with its extra seconds, which stay in its title to video (until #185 it counted as not played, #143).
_Avoid_: first result, winner

**Fail**:
A play whose top pick gives no video: the viewer presses it and gets an error, the failure video or a refusal. Video after a fallback is played, not a fail (#185). Speed never makes up for a fail; fails come first, then fast. Fails are counted as plays, and a count names the titles too ("2 titles failed · 4 of 40 plays"); the rule is in `tools/brain/docs/rules.md`.
_Avoid_: miss (a miss is a request the Recording cannot answer), error

**Title to video**:
Seconds from asking for a title until its video arrives: the list and the start, on one clock for every side, so checking before the list and checking at play time cost the same. A fail has no title-to-video time.
_Avoid_: total time, end-to-end time

**Easy list**:
A title list of popular, well-kept titles whose top Sources nearly always play; it shows what checking costs where little is dead.
_Avoid_: baseline list, normal titles

**Hard list**:
A title list of the kinds where dead Sources are common (older releases, titles prone to takedowns, less popular titles), chosen by kind only and played as each app plays it, with no check beforehand; never chosen by which side failed. It shows what checking saves.
_Avoid_: stress list, fail list

**Speed test**:
A timed run on an easy list and a hard list of titles no side has played before, new for every speed test, played like for like. It says how KaijuFlow compares with the other setups. The first speed test that works is the baseline.
_Avoid_: baseline, benchmark

**Tuning test**:
A timed run that plays a title list again, so a change to one setup can be compared with the tuning test before it on the same titles.
_Avoid_: speed test (when the titles are reused), rerun

**Target**:
One of the goals KaijuFlow is measured against, kept in `tools/brain/targets.json` and judged on a finished run only: met, not met, or not measured when the run holds no figure for it. A time target is "inside the noise" when KaijuFlow's own two rounds of that kind differ by more than the target is met or missed by.
_Avoid_: goal, KPI, threshold

**Final bar**:
The owner's goal for a speed test beyond its three targets, shown apart from them and never counted with them or towards "usable" (spec #159, #169). The rule lives in `tools/brain/docs/rules.md` ("A speed test's targets, outcome and final bar"); its words are in `tools/brain/targets.json`.
_Avoid_: final target, end goal

**Expected settings**:
The sort and filter rules every test copy must have, kept in `tools/brain/expected-settings.json`. The preflight fails when a copy differs.
_Avoid_: baseline settings, golden config

**Like for like**:
The one rule set every side of a timed run plays by (#142): the same list of Sources from the stand-in (no post over 30 GB for a film or 10 GB for an episode, no disc images, the first 100 results, no later pages), 4K first, the same indexer and Backend connections, and one try per play with no fallback for every side, in every timed run (ADR 0007). A comparison between sides counts only when the run was like for like. Per title, the report and `check` compare KaijuFlow's top pick with each setup's (#143): a different resolution, or a served file over the cap or a disc image, makes that title not like for like, and it is left out of the targets against that setup.
_Avoid_: fair run, same settings

**Recording**:
The indexer answers stored once so that every run can replay them and no run asks the real indexer. It counts only after its proof replay missed nothing.
_Avoid_: cache, snapshot

**Stand-in**:
The small stand-in indexer on port 1340 that every test copy talks to. It records real answers once and replays them afterwards.
_Avoid_: mock, proxy

**Cap rule**:
The first "limit reached" from any indexer stops the pass at once, and its result is null: no numbers are reported. The work waits for the indexer's reset.
_Avoid_: rate-limit handling

**Stopped run**:
A timed run that was stopped by Ctrl-C, or by SIGTERM as `timeout` sends it, before its last play. Its record keeps the plays that finished and says where it stopped; it is not a baseline, its targets are not judged, and it is never the previous run of a comparison. A record command is stopped the same way.
_Avoid_: aborted run, cancelled run, null run (null is the cap rule's result)

**Archived run**:
A run from before the like-for-like rules, kept in the `archive/` folder of the runs root as a record. It is never the baseline, never compared with, and never on the Speed Check page.
_Avoid_: old run, deleted run (nothing is deleted)
