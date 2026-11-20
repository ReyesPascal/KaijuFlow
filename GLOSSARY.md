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

**Unchecked Source**:
A Source no health check has looked at yet. It is neither healthy nor dead, and KaijuFlow never hands one to the Backend: a Source is checked before it is played.
_Avoid_: kept result, passed (when it was never checked)

**Stream**:
The playable link a Backend produced for one Source.
_Avoid_: tile, source (when you mean the link)

**Backend**:
A separate service that takes one Source, prepares it, and serves its video file to the player. AltMount is KaijuFlow's only Backend.
_Avoid_: streamer, engine, provider (providers are Usenet servers)

**Play route**:
KaijuFlow's address a Stream's play link points at (`/play/stream/...`, and `/play/v` for the video bytes): it hands the Source to the Backend and delivers the video. Named after the play since #200; before that it carried NzbDAV's name.
_Avoid_: nzbdav route, stream proxy (unqualified)

**Delivery method**:
How a Play route gets the video to the player: `proxy` (through KaijuFlow's buffer, the default), `pipe` (through a small buffer) or `direct` (the player is sent to the Backend). The setting is `playDeliveryMethod`; there is no other streaming choice, KaijuFlow always plays through the Backend.
_Avoid_: streaming method, streaming mode

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
KaijuFlow preparing the Healthy Sources of a list on the Backend in the background, right after the list is built and before any play (the top one, all of them, or off). A play of a Source already being prepared joins that prepare.
_Avoid_: pre-warm, preload, prefetch
To be replaced by Head start (owner, 2026-11-20).

**Head start**:
The Play-time check of the Best entry's Sources and the prepare of the first Healthy one, begun in the background as soon as any player asks for a title's stream list, so a press of Best finds the check done and the video ready. In Stremio the list is asked for when a film's page opens or an episode is picked. Only the newest list request has a Head start: a new one stops what is unfinished for the one before.
_Avoid_: prefetch, pre-warm, auto-queue (once built)

**Play-time check**:
The health check run when a Source is clicked rather than before the stream list is sent: the list goes out at once, unchecked, and the Sources about to be played are checked then. Replaces checking a whole list before it is shown.
_Avoid_: lazy check, on-demand check, deferred check

**Best entry**:
The entry on top of KaijuFlow's stream list ("KaijuFlow ▶ Best") that plays the first Healthy Source of the list, found by a Play-time check a few Sources at a time from the top down until one is healthy or the list runs out, rather than one chosen Source.
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
One setup that is played in a timed run: KaijuFlow with its AltMount, or the same with one page asked of each indexer. Earlier runs also had Usenet Ultimate and AltMount direct as sides.
_Avoid_: variant, candidate, contestant

**AltMount direct**:
The setup where the player gets its Streams from AltMount itself, with no KaijuFlow or Usenet Ultimate in front of it. A side of earlier runs only; KaijuFlow's runs no longer play it.
_Avoid_: AltMount's own addon, addon, AltMount alone

**Short run**:
A timed run that is not the full plan: without KaijuFlow's own pass, one round instead of two, or fewer titles than the list, for a quick check while tuning. It says what it played, and it is never a baseline or a previous run.
_Avoid_: partial run, quick run

**Pass**:
The sides that are played together, title by title in turn, through every round, with a reset of their test copies before each cold round. A timed run has a pass of KaijuFlow and, with the one-page side, a pass of that side after it. A record command's pass is one cold and one warm round, followed by its proof replay.
_Avoid_: batch, phase (cold or warm is the phase)

**Browse pause**:
The fixed wait in a run between a title's list arriving and its play, standing for a viewer reading the page before pressing play, so work begun when the list is asked for shows in the start. Not part of title to video.
_Avoid_: think time, settle (the settle is the pause after a play)

**Round**:
Every title played once, cold or warm, on every side of a pass. A timed run plays four rounds: cold, warm, cold, warm. A side's figures for a round are made of its own plays in it; the time a round takes covers every side of the pass.
_Avoid_: iteration, lap

**Top pick**:
The first Source in a side's list for a title, the one a round plays. Two top picks are the same Source when their sizes match. Video that arrives only after the top pick's own import failed is a **fallback**: counted as played, with its extra seconds in its title to video.
_Avoid_: first result, winner

**Fail**:
A play whose top pick gives no video: the viewer presses it and gets an error, the failure video or a refusal. Video after a fallback is played, not a fail. Speed never makes up for a fail; fails come first, then fast. Fails are counted as plays, and a count names the titles too ("2 titles failed · 4 of 40 plays"); the rule is in `tools/brain/docs/rules.md`.
_Avoid_: miss (a miss is a request the Recording cannot answer), error

**Previous run**:
The run a run of KaijuFlow is judged against: the newest earlier finished run on the same Recording, not archived, not short and not marked never compared with. Per list, fails first, then the cold title to video, each better, same or worse; the change is **kept** when the fails are not higher and the cold title to video is not slower, otherwise **not kept**. Each list also shows its warm title to video, its fallbacks and their extra seconds against the previous run's, which never change the verdict. A run that was stopped or is short is not judged. The rule is in `tools/brain/docs/rules.md` ("Judged against the previous run").
_Avoid_: baseline (the baseline is one run; the previous run moves on with every run), last run (it may be on another recording)

**Title to video**:
Seconds from asking for a title until its video arrives: the list and the start, on one clock for every side, so checking before the list and checking at play time cost the same. The Browse pause between them is not counted. A fail has no title-to-video time.
_Avoid_: total time, end-to-end time

**Easy list**:
A title list of popular, well-kept titles whose top Sources nearly always play; it shows what checking costs where little is dead.
_Avoid_: baseline list, normal titles

**Hard list**:
A title list of the kinds where dead Sources are common (older releases, titles prone to takedowns, less popular titles), chosen by kind only and played as each app plays it, with no check beforehand; never chosen by which side failed. It shows what checking saves.
_Avoid_: stress list, fail list

**Speed test**:
A timed run on an easy list and a hard list drawn from the pool, titles KaijuFlow has not played before. The first speed test that works is the baseline.
_Avoid_: baseline, benchmark

**Tuning test**:
A timed run that plays a title list again, so a change to KaijuFlow or its AltMount can be judged against the run before it on the same titles.
_Avoid_: speed test (when the titles are reused), rerun

**Target**:
A goal the Speed Check page holds KaijuFlow to, most of them against another setup: met, not met, or not measured when the run holds no figure for it; a time target is "inside the noise" when KaijuFlow's own two rounds of that kind differ by more than the target is met or missed by. A run itself is judged against the previous run, not on targets.
_Avoid_: goal, KPI, threshold

**Final bar**:
The owner's goal for a speed test beyond its targets, held against the other setups and shown apart from the targets.
_Avoid_: final target, end goal

**Expected settings**:
The settings every test copy must have, its sort and filter rules among them. The preflight fails when a copy differs.
_Avoid_: baseline settings, golden config

**Like for like**:
One rule set for every side of a comparison of setups (the same list of Sources, 4K first, one try per play), and KaijuFlow's top pick compared per title with each other setup's. KaijuFlow's runs alone need neither.
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
