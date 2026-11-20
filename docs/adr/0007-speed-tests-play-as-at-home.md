# Speed tests give every app one try, on new titles, judged on fails then title to video

A speed test plays an easy list and a hard list of titles no side has played before, new every test. Every app gets one try per title, with no retries for anyone (AltMount direct's fallback stays off, as in #142; KaijuFlow and Usenet Ultimate show the failure video), and is judged first on fails (a play whose top pick does not play on its one try) and then on title to video (one clock from asking for the title until video). Decided by the owner on 2026-11-15 after Test 1; amended twice the same day (below).

**Superseded in part** by spec #183 (2026-11-20, below): runs measure KaijuFlow with AltMount alone, against its own previous run on one fixed recording, and a fallback counts as played. What still holds: fails first, then title to video.

## Why

KaijuFlow exists for health checks: a working video on the first press. Test 1 could not show that. Its ten popular titles have few dead Sources, so AltMount direct's unchecked top pick nearly always played, and its list in under a second beat KaijuFlow's checked list in 3 to 9 s. The targets judged list and start apart, so checking before the list looked like pure cost, and one try per play hid what a viewer actually gets from AltMount's fallback.

- One clock makes checking before the list and checking at play time cost the same.
- No fails comes first: a fast setup that fails a title loses it.
- A hard list of the kinds where Sources die (older, takedown-prone, less popular) shows what checking saves; the easy list shows what it costs. Titles are chosen by kind only, never by which side failed.
- New titles every speed test keep every cache, dead mark and import out of the result.

**Amended 2026-11-15.** This record first said each app plays as shipped, its own retries included (AltMount direct's two). The owner then decided the same day: no retries for anyone, every setup gets one play per title. So speed tests and tuning tests share the one-try rule of #142 and #143, and a fallback counts as a fail.

**Amended again 2026-11-15** (owner's decisions on #167 and #169, after the code review of spec #159). Fails are counted as plays: a cold fail stays a fail and a warm play after learning counts, and every count names both ("2 titles failed · 4 of 40 plays"). The final bar is the owner's of spec #159, replacing #141's: on both lists, KaijuFlow has the fewest fails, any tie counting as fewest, and the fastest median cold title to video among setups with as few fails. The cold title to video target holds KaijuFlow against every setup with as few fails or fewer. The same fails with KaijuFlow no slower is a fourth outcome: "KaijuFlow is as reliable and no slower: tune its speed". The rules are in `tools/brain/docs/rules.md`; the words of the targets and the final bar in `tools/brain/targets.json`.

**Amended 2026-11-20** (spec #183, owner's "yes to all"; #185, #186, #187). KaijuFlow with AltMount is measured alone: Usenet Ultimate and AltMount direct are no side any more, and nothing is compared across setups (no like for like, no targets against another setup, no final bar). Every run replays one fixed recording, an easy and a hard list drawn once from the pool, with a new draw only when the owner asks, instead of new titles every test. The stand-in passes the indexer's answers untouched. A fallback counts as played, its extra seconds in its title to video, not as a fail; until #190 turns Ultimate Fallback on for AltMount, KaijuFlow plays one try per title anyway. Each run is judged against KaijuFlow's previous run on the same recording, per list: fails first, then the median cold title to video; a change is kept only when fails do not rise. The rules are in `tools/brain/docs/rules.md`. The Consequences below describe the runs before #185.

## Consequences

- AltMount direct's fallback stays off in speed tests (one try, the expected setting since #142); a top pick that fails, or plays only after a fallback, is a fail.
- The six targets of `targets.json` are replaced by per-list targets on fails and title to video, and #141's final bar by spec #159's (see the second amendment): fewest fails on both lists, a tie counting as fewest, then the fastest title to video among setups with as few.
- Each speed test needs its own recording of new titles, which spends indexer requests every time; tuning tests replay one.
- Decided in advance, on the hard list against AltMount direct (titles like for like): if KaijuFlow fails fewer plays, tune its speed; if it ties and AltMount direct is faster, try KaijuFlow without its own pre-list check behind AltMount; if AltMount direct fails fewer, KaijuFlow's checking has a bug to find first; if it ties and KaijuFlow is no slower, KaijuFlow is as reliable and no slower: tune its speed.
