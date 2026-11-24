# Testing plays as a real viewer watches, judged on fails

Replaces [ADR 0007](0007-speed-tests-play-as-at-home.md). KaijuFlow is tested by **real-use checks**: new titles every time, the live indexers, one cold play per title with fallbacks allowed, and browsing, searching and changing one's mind between plays. A **quick check** plays 5 titles until their video starts. A **full check** plays 20 titles (half popular, half rare or older, about half TV with some next-episode plays) and watches each for a few minutes with a skip into the middle. A check passes on **zero fails** alone. Slow plays (video after 60 s), next-episode plays and typical speed are reported as information, never as the verdict. Decided by the owner on 2026-11-24 in a grilling of the measuring process.

The owner's words: "that doesnt seem to help anythin when it comes to real life usage like this will ne used to pick a title and play it and then the user expects it to play and not take forever they wont be doing tests over and over and playing the same file over and over"; "the top prioirty is zero failed plays because thats the whole point of the health checking systems"; "a fail is a fail, a slow play is not a fail intnernallty but externally to a user it is a given up".

## Why

The replayed Recording, with its proof replays, top-ups, four cold and warm rounds, grouped runs and halving, measured code changes against 20 fixed titles. Real use never replays a title: the indexer is live, every title is new, and the viewer presses play once. Tuning could fit those 20 titles, and warm rounds stood only for a rewatch. Each new draw also needed several record passes (`kf-265` needed three). The health check samples only 3 or 7 pieces of a file, so a play can pass the check and still freeze later. That is why a full check watches each play instead of stopping at the first video bytes.

## Consequences

- When to run: a quick check after any change to playing, health checks or search, before it merges. A full check before work is called done, after an indexer is added, or when the owner asks.
- A wrong title or episode played is a fail: the played file's name must match the title, its year and its episode. This tests Ultimate Text Search, Usenet Ultimate's name search, which KaijuFlow keeps (ADR 0006; replaced by Kaiju Search in #285).
- A check miss (a Source the health check passed that AltMount refused or that froze) is counted apart and becomes a ticket, even when a fallback saved the play. The report shows how many fallbacks happened and whether each ended in video, and says "fallbacks not tested this time" when none happened.
- The full check's rare or older half includes, drawn by kind, a title with a foreign or alternate name, an anime, a title shared with a remake and a daily show. These are never chosen to fail. When one has no Source on any indexer it is nothing to play, not a fail, and another title of the same kind is drawn in its place.
- Every fail becomes a ticket naming the title. Its fix is proven by drilling down on that title alone, played again live, not by a new full check.
- For a fail or a nothing-to-play title, the report lists every Source KaijuFlow looked at and why it said no. No extra tests are run to second-guess it. A title counts as nothing to play only when those reasons hold up.
- Totals are not compared title by title or with a kept or not-kept verdict. Titles differ from check to check, so speed differences are noise, and fails are what stand out.
- Checks run on the owner's dev install. New titles keep every play cold. They are drawn fresh from the wide catalog of films and shows for each check, by kind and never by hand, and never from a fixed pool that could run out.
- Retired, soft-deleted (archived, not removed): the Recordings (`kf-189`, `kf-265`), proof replays and top-ups, the four rounds, grouped runs and halving, the judgement against the previous run, speed tests and tuning tests. Old run folders stay in the archive. The stand-in indexer stays only if the checks need it to protect indexer limits. The cap rule still stops a check at the first "limit reached".
