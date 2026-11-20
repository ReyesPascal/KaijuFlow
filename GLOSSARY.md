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
A separate service that takes one Source, prepares it, and serves its video file to the player. AltMount is KaijuFlow's only Backend (NzbDAV was removed in #188; InfiniDysk stays unbuilt).
_Avoid_: streamer, engine, provider (providers are Usenet servers)

**Parity**:
The bar a Backend's path through KaijuFlow must meet, tested by the shared Parity scenarios against the fake AltMount: a good Source plays, seeking works, and a Source that fails shows the failure video and is not offered again. (It began as "plays like NzbDAV" when NzbDAV was the reference Backend.)
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
One setup that is played in a timed run: KaijuFlow, or KaijuFlow with one page per indexer (`--one-page`), both on KaijuFlow's test copy and its AltMount (#185). The runs before #185 also had Usenet Ultimate and AltMount direct as sides; the brain tools name them only to read those runs (#187).
_Avoid_: variant, candidate, contestant

**AltMount direct**:
History (before #185): the side where the player got its Streams from AltMount itself, with no KaijuFlow or Usenet Ultimate in front of it. No longer a side (#187); its test copy stays stopped.
_Avoid_: AltMount's own addon, addon, AltMount alone

**Short run**:
A timed run that is not the full plan: without KaijuFlow's own pass (`--sides kaijuflow-1page`), one round instead of two, or fewer titles than the list. Made with `--sides`, `--rounds`, `--quick` or a title subset, for a quick check while tuning. Its report, `meta.json`, INDEX.md row and `check` say what it played, and it is never a baseline.
_Avoid_: partial run, quick run (`--quick` is one way to make one)

**Pass**:
The sides that are played together, title by title in turn, through every round, with a reset of their test copies before each cold round. A timed run has a pass of KaijuFlow and, with the one-page side, a pass of that side after it. A record command's pass is one cold and one warm round, followed by its proof replay.
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

**Previous run**:
The run a run of KaijuFlow is judged against: the newest earlier finished run on the same Recording, not archived, not short and not marked never compared with. Per list, fails first, then the cold title to video, each better, same or worse; the change is **kept** when the fails are not higher and the cold title to video is not slower, otherwise **not kept**. Each list also shows its fallback time (its fallbacks' extra seconds added up) against the previous run's, which never changes the verdict. The rule is in `tools/brain/docs/rules.md` ("Judged against the previous run").
_Avoid_: baseline (the baseline is one run; the previous run moves on with every run), last run (it may be on another recording)

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
A timed run on an easy list and a hard list of titles KaijuFlow has not played before, new for every speed test. Until #187 it said how KaijuFlow compared with the other setups; a run is now judged against the previous run on its Recording. The first speed test that works is the baseline.
_Avoid_: baseline, benchmark

**Tuning test**:
A timed run that plays a title list again, so a change to KaijuFlow or its AltMount can be judged against the run before it on the same titles.
_Avoid_: speed test (when the titles are reused), rerun

**Target**:
One of the goals the Speed Check page holds KaijuFlow to, most of them against the other setups of the runs before #185, kept in `tools/brain/targets.json` and judged by `pagetargets.py` (page code until #195): met, not met, or not measured when the run holds no figure for it. A time target is "inside the noise" when KaijuFlow's own two rounds of that kind differ by more than the target is met or missed by. `check` and the report no longer judge targets (#187); see Previous run.
_Avoid_: goal, KPI, threshold

**Final bar**:
The owner's goal for a speed test beyond its three targets, held against the other setups and shown apart from the targets (spec #159, #169). Only the Speed Check page still shows it, until #195 (`tools/brain/docs/rules.md`, "Deleted with the comparison of setups"); its words are in `tools/brain/targets.json`.
_Avoid_: final target, end goal

**Expected settings**:
The sort and filter rules every test copy must have, kept in `tools/brain/expected-settings.json`. The preflight fails when a copy differs.
_Avoid_: baseline settings, golden config

**Like for like**:
History (#142 to #187): the one rule set every side of a timed run played by when KaijuFlow was measured beside other setups (the stand-in's filtered list of Sources, 4K first, one try per play), and the per-title comparison of KaijuFlow's top pick with each other setup's. Deleted in #187 (the stand-in passes answers untouched since #185); only the Speed Check page code still applies it to its targets, until #195. `tools/brain/docs/rules.md`, "Deleted with the comparison of setups".
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
A timed run that was stopped by Ctrl-C, or by SIGTERM as `timeout` sends it, before its last play. Its record keeps the plays that finished and says where it stopped; it is not a baseline, and it is never the previous run of a comparison. A record command is stopped the same way.
_Avoid_: aborted run, cancelled run, null run (null is the cap rule's result)

**Archived run**:
A run from before the like-for-like rules, kept in the `archive/` folder of the runs root as a record. It is never the baseline, never compared with, and never on the Speed Check page.
_Avoid_: old run, deleted run (nothing is deleted)
