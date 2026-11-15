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
The first Source in a side's list for a title, the one a round plays. Two top picks are the same Source when their sizes match.
_Avoid_: first result, winner

**Target**:
One of the goals KaijuFlow is measured against, kept in `tools/brain/targets.json` and judged on a finished run only: met, not met, or not measured when the run holds no figure for it. A time target is "inside the noise" when KaijuFlow's own two rounds of that kind differ by more than the target is met or missed by.
_Avoid_: goal, KPI, threshold

**Expected settings**:
The sort and filter rules every test copy must have, kept in `tools/brain/expected-settings.json`. The preflight fails when a copy differs.
_Avoid_: baseline settings, golden config

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
