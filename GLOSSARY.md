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
One NZB that search found for a title on one indexer, whether or not it is complete. A Source might be streamed; it is not yet a Stream.
_Avoid_: result, release (when you mean one indexer's copy), NZB (when you mean the search result), "source" for code

**Release**:
One upload of a title, found as one Source on each indexer that has it. The list shows a Release once, and the Play-time check checks it once; when one indexer's NZB cannot be fetched, the Release's Source on another indexer is used.
_Avoid_: duplicate, copy

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
How a Play route gets the video to the player: `proxy` (through KaijuFlow's buffer, the default), `pipe` (through a small buffer) or `direct` (the player is sent to the Backend). The setting is `playDeliveryMethod`, read afresh on every request, a repeat request of the same play included; there is no other streaming choice, KaijuFlow always plays through the Backend.
_Avoid_: streaming method, streaming mode

**Parity**:
The bar a Backend's path through KaijuFlow must meet, tested by the shared Parity scenarios against the fake AltMount: a good Source plays, seeking works, and a Source that fails shows the failure video and is not offered again. (It began as "plays like NzbDAV" when NzbDAV was the reference Backend.)
_Avoid_: compatibility, support (unqualified)

### Preparing a Source

**Scrambled RAR set**:
A Source whose RAR parts are named only by numbers that do not match their real volume order.
_Avoid_: obfuscated release (obfuscated names can still be in order), broken RAR, shuffled parts

**Unscramble**:
Renaming the parts of a Scrambled RAR set into a normal RAR volume series in their real volume order, before the Source goes to the Backend. When its reads fail for connection trouble it is tried once more, and a set it still can't unscramble that way is not sent to the Backend (ADR 0005).
_Avoid_: reorder, repair, fix names

**Auto-queue** (deleted, #226):
KaijuFlow preparing the Healthy Sources of a list on the Backend in the background, right after the list was built and before any play (setting `autoQueueMode`: the top one, all of them, or off). Deleted in #226 with its setting and UI control; an old config's `autoQueueMode` is dropped at startup. Head start replaces it (owner, 2026-11-20).
_Avoid_: pre-warm, preload, prefetch

**Head start**:
The Play-time check of the Best entry's Sources and the prepare of the first Healthy one, begun in the background as soon as any player asks for a title's stream list, so a press of Best finds the check done and the video ready. In Stremio the list is asked for when a film's page opens or an episode is picked. Only the newest list request has a Head start: a new one stops what is unfinished for the one before, unless a press of Best is waiting on it (a press makes it a play). Once that play's video arrives, the next list request stops the rest of its walk too. On by default (#206): Ultimate Fallback's "On Search" (`whenToResolve` on-results); "On Click" turns it off, and Best then starts on the press.
_Avoid_: prefetch, pre-warm, auto-queue

**Play-time check**:
The health check run when a Source is clicked rather than before the stream list is sent: the list goes out at once, unchecked, and the Sources about to be played are checked then. KaijuFlow's only health check: it replaced checking the list before it is shown (the list-time Smart and Fixed checks, deleted in #191), and no setting turns it off.
_Avoid_: lazy check, on-demand check, deferred check, list-time check (deleted)

**Best entry**:
The entry on top of KaijuFlow's stream list ("KaijuFlow ▶ Best") that plays the first Healthy Source of the list, found by a Play-time check a few Sources at a time from the top down until one is healthy or the list runs out, rather than one chosen Source. The search down the list is its **Walk**. The Walk tries the sure Sources first, then the maybes, each group in list order (Search Flow, #282); the list a viewer sees keeps its own sort.
_Avoid_: auto entry, smart pick, top pick (the top pick is the first Source of a list)

**Walk**:
One play's progress down a list: grabbing and checking Sources a few at a time from the top until one is healthy, the list runs out, or the walk stops. A failed grab is replaced once. Why it failed decides what follows (ADR 0004): an indexer that refuses a grab (a limit, an outage, refused credentials) is skipped for the rest of the walk, while a Source the indexer says is gone is a bad Source and the walk moves on. A walk stops after 30 grabs and ends as if the list had run out, so a list of gone Sources can't be walked to its end. A walk ends when any player asks for another title's list: its unfinished grabs and checks stop, unless a press is still waiting on it for its video, and a video already playing goes on. A Head start begins a walk; a press of Best joins it, and walks on its own only when there is none (On Click, or the Head start was stopped), so the 30 grabs are one walk's whether it began before or at the press. A clicked list entry that fails walks on down the list as a walk too (#255): one Source at a time from the entry, with the same grabs, the same skip of a refusing indexer and its own 30 grabs, kept across the self-redirects of its play. A player is always waiting on it for its video, so another title's list does not stop it. A Source that needs no grab (one the Backend already holds, or remembered ready) is never held back by a walk's limits.
_Avoid_: pool loop, fallback walk, search (search finds the list; the walk checks it)

**Play context**:
What a play of a list is for: the title's type, season, episode, aired date and episodes in season, and Best's session for it. Made once when the list is built and kept with the list, so a Head start, a press of Best and a played list entry all look for the same episode; a daily show's episode is found by its aired date whichever of them plays it (#246). It says what is wanted, not how the caches remember it.
_Avoid_: play params, episode info, session data

**Source memory**:
What KaijuFlow remembers of Sources across plays and restarts: the ready ones (the Backend made their video, so a later play reuses it) and the dead ones (bad Sources, ADR 0004, kept out of lists and walks). A play remembers what it learned and recalls a Source as its play context asks for it; the memory alone decides how a Source is keyed, so a Source remembered by one play is found by another for the same episode, a dated one included (#247). A dead mark is the Source's for every episode when its link is gone or the check blocked it, otherwise its episode's, unless a season pack fails whole before any episode of it played. A dead mark on a Release covers its Source on every indexer, except a link one indexer says is gone, which is that Source's alone (#300).
_Avoid_: NZB database, healthy cache, stream cache (the prepares under way)

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

**Short run** (retired by ADR 0010):
A timed run that is not the full plan: without KaijuFlow's own pass, one round instead of two, or fewer titles than the list, for a quick check while tuning. It says what it played, and it is never a baseline or a previous run.
_Avoid_: partial run, quick run

**Pass** (retired by ADR 0010):
The sides that are played together, title by title in turn, through every round, with a reset of their test copies before each cold round. A timed run has a pass of KaijuFlow and, with the one-page side, a pass of that side after it. A record command's pass is one cold and one warm round, followed by its proof replay.
_Avoid_: batch, phase (cold or warm is the phase)

**Browse pause**:
The fixed wait in a run between a title's list arriving and its play, standing for a viewer reading the page before pressing play, so work begun when the list is asked for shows in the start. Not part of title to video. The rule is in `tools/brain/docs/rules.md` ("Browse pause").
_Avoid_: think time, settle (the settle is the pause after a play)

**CPU probe**:
A short fixed piece of single-thread work (about 1 s on Brain plugged in) that a run's preflight times before the run starts, the same work every run, so a run whose CPU was slower says so. It judges nothing; the run keeps it in `meta.json` and the report holds it against the previous run's. Format in `tools/brain/docs/formats.md`.
_Avoid_: benchmark (it measures the machine, not KaijuFlow)

**Round** (retired by ADR 0010):
Every title played once, cold or warm, on every side of a pass. A timed run plays four rounds: cold, warm, cold, warm. A side's figures for a round are made of its own plays in it; the time a round takes covers every side of the pass.
_Avoid_: iteration, lap

**Top pick**:
The first Source in a side's list for a title. Two top picks are the same Source when their sizes match. A round plays the first entry of a side's list: the top pick, or on KaijuFlow's list (since #190) the Best entry above it, which plays the first Healthy Source. Video that arrives only after an import failed (the played entry's own, or with Best a checked Source that AltMount refused) is a **fallback**: counted as played, with its extra seconds in its title to video. A Source Best skips because its check failed costs no import, so it is no fallback.
_Avoid_: first result, winner

**Fail**:
A play that gives no video: the viewer presses the round's entry (the top pick, or Best) and gets an error, the failure video or a refusal. A video of the wrong title or episode is a fail too, and in a full check so is video that freezes or breaks on a skip while it is watched. Video after a fallback is played, not a fail, and so is slow video (a slow play). Speed never makes up for a fail; fails come first, then fast. Fails are counted as plays, and a count names the titles too ("2 titles failed · 4 of 40 plays"); the rule is in `tools/brain/docs/rules.md` ("Real-use checks" for a check: it passes on zero fails).
_Avoid_: miss (a miss is a request the Recording cannot answer), error

**Nothing to play**:
A title for which no indexer KaijuFlow asks has a Source the Backend can stream, shown to the viewer as such. It is not a fail, but it counts only once it is shown that no Source would have played; a Source that would have played but was marked dead or never reached makes it a fail. The rule is in `tools/brain/docs/rules.md` ("Real-use checks").
_Avoid_: no results (search may have found Sources that are all dead), fail (when nothing could play)

**Real-use check**:
A check that plays the way a viewer watches: new titles each time, the live indexers, one cold play per title (fallbacks allowed), watched for a while after the video starts, with browsing, searching and changing one's mind between plays. It is the main measure of KaijuFlow; it is judged on its totals, never title by title.
_Avoid_: speed test, tuning test (both replay a Recording), soak test

**Quick check**:
A real-use check of 5 new titles, cold, ended as soon as each video starts: a fast look at how a change does. Run with `brainrun.py check --quick`; its rules are in `tools/brain/docs/rules.md` ("Real-use checks").
_Avoid_: smoke test, short run (a short run replays a Recording)

**Full check**:
A real-use check of 20 new titles (half popular, half rare or older, about half TV episodes with some next-episode plays), each watched for a few minutes with a skip into the middle, with a viewer's browsing between plays: the one that shows KaijuFlow really works.
_Avoid_: long run, soak test

**Drill-down**:
Playing one failed title again, live, after a fix, to prove the fix: a single title, not a new check. It plays the title as a Quick check plays one, keeps its evidence folder however it went, runs the suspected cause's confirming test on it, and marks the Casebook entry *proved fixed* (it played with no failure) or *reopened* (a failure appeared). The command a fix ticket names: `brainrun.py drill --title <imdb id> [--episode S01E02]`.
_Avoid_: rerun, tuning test

**Check miss**:
A Source the health check passed that the Backend then refused, or whose video froze: the check was wrong even when a fallback saved the play. It is counted apart, and each one becomes a ticket. The rule is in `tools/brain/docs/rules.md` ("Real-use checks").
_Avoid_: fail (when a fallback played), false positive

**Slow play**:
A play whose video arrives, but more than 60 s after the press, when a viewer would have given up. It is not a fail; it is counted and named apart, as the plays to speed up. The rule is in `tools/brain/docs/rules.md` ("Real-use checks").
_Avoid_: fail (video arrived), timeout

**Next-episode play**:
A play of a TV episode whose Source KaijuFlow already prepared for an earlier episode, as a viewer watching on gets. It is reported apart from fresh plays, since it starts partly warm.
_Avoid_: warm start (a warm start is the same Source and episode again), binge play

**Previous run** (retired by ADR 0010):
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

**Speed test** (retired by ADR 0010):
A timed run on an easy list and a hard list drawn from the pool, titles KaijuFlow has not played before. The first speed test that works is the baseline.
_Avoid_: baseline, benchmark

**Tuning test** (retired by ADR 0010):
A timed run that plays a title list again, so a change to KaijuFlow or its AltMount can be judged against the run before it on the same titles.
_Avoid_: speed test (when the titles are reused), rerun

**Grouped run** (retired by ADR 0010):
A tuning test that carries several changes at once and is judged as one against the previous run. When it is not kept, its changes are split in halves, each half run on its own, until the change that made it not kept shows.
_Avoid_: batch run, combined test

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

**Recording** (retired by ADR 0010):
The indexer answers stored once so that every run can replay them and no run asks the real indexer. It counts only after its proof replay missed nothing.
_Avoid_: cache, snapshot

**Stand-in**:
The small stand-in indexer on port 1340 that every test copy talks to. In a real-use check it passes every request to the live indexer and keeps the answers in the check's own store, so the cap rule and the allowance count the check (its replay of a Recording is retired by ADR 0010).
_Avoid_: mock, proxy

**Cap rule**:
The first "limit reached" from any indexer stops the check at once with no verdict. The work waits for the indexer's reset.
_Avoid_: rate-limit handling

**Stopped run**:
A timed run that was stopped by Ctrl-C, or by SIGTERM as `timeout` sends it, before its last play. Its record keeps the plays that finished and says where it stopped; it is not a baseline, and it is never the previous run of a comparison. A record command is stopped the same way.
_Avoid_: aborted run, cancelled run, null run (null is the cap rule's result)

**Archived run**:
A run from before the like-for-like rules, kept in the `archive/` folder of the runs root as a record. It is never the baseline, never compared with, and never on the Speed Check page.
_Avoid_: old run, deleted run (nothing is deleted)

### Diagnosis (spec #279)

**Diagnosis**:
The one system that finds, proves and learns why a play in a check went wrong, run by itself after every check with a failure: it gathers the evidence folder, fingerprints the failure, looks it up in the Casebook, proves or rules out every lead with Clues, works an unknown failure through a Case log until it is solved, and proves the fix with a Drill-down. A cause is named only when its confirming test passes on this failure's own evidence; a look-alike with no confirming test is "suspected", never "found". Its recording is dev only, behind the dev switch (`devDiagnostics`, on in the test copies only).
_Avoid_: debugging (by hand), triage, root-cause tool

**Casebook**:
The known causes of failed plays, one readable file per cause in a fixed format (what the viewer saw, signs, cause, how it was proved, ruled out, fix, history), with an index generated from the files that the programs read. A match in it only orders the leads; it never names a cause by itself. A proved KaijuFlow cause files its own fix ticket; one that is not KaijuFlow's gets a workaround. A failure that proves a cause already proved fixed is a *comeback*, and reopens its entry (`tools/brain/docs/formats.md`, "Fixing").
_Avoid_: known-error database, FAQ, list of bugs

**Clue**:
One small reusable yes/no test that answers a single question from the evidence or from a live read-only look at Usenet or AltMount (are all the articles there? what reason did AltMount give? did Unscramble rename the volumes?). A cause's confirming test is a recipe of Clues; a new Clue is built only for a truly new question, and none is ever deleted.
_Avoid_: probe, check (a check plays titles), test (unqualified)

**Case log**:
The record of a failure with no proved cause yet: every observation, hypothesis (with the result that would refute it), Clue run and result, so a later attempt starts from what was tried and never runs a Clue twice. The diagnosing agent, started by the check, works it; every claim it writes must quote evidence that holds it. A concluded cause is *probable* until the failure is repeated at will (a Drill-down or a replay), then *proved*; it is written up as a Casebook entry.
_Avoid_: ticket (a ticket is for a fix), notes, incident

**Kaiju Search**:
KaijuFlow's whole search: every indexer asked by ID (the IDs each indexer's capabilities list: IMDb, TMDB, TVDB, TVmaze; IMDb when they are unknown, none when they list no ID) and by name (the title's other names too) at once, the answers merged and each Source listed once with the ways that found it, then sorted by Search Flow. There is nothing to set: no search method. It ships in the release; it learns in dev.
_Avoid_: Ultimate text search, search method, text search (one way of asking only)

**Search Flow**:
What Kaiju Search does with each result: the loose rule (the inherited name match) decides what stays, and nothing the strict rule passes is dropped (#282); the strict rule (the right title, with only seen tags between the name and the year or episode) only sorts, never removes, into **sure** (passes strict) and **maybe** (loose only); **extra proof** makes a maybe sure (#286): the ID search returned it too, the video file name inside its NZB fits (read when the Play-time check fetches it), its own runtime fits the title's or its size is a sure Source's, or it fits another TMDB/TVDB name of the title. No proof makes sure a name that says another year, season or episode. Best tries sure Sources first. A maybe that played the right title offers its **odd word** (the one word that kept the strict rule from passing it) as a new allowed word, with that release as proof.
_Avoid_: Name rule, name filter, strict filter
