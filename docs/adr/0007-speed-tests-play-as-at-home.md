# Speed tests give every app one try, on new titles, judged on fails then title to video

A speed test plays an easy list and a hard list of titles no side has played before, new every test. Every app gets one try per title, with no retries for anyone (AltMount direct's fallback stays off, as in #142; KaijuFlow and Usenet Ultimate show the failure video), and is judged first on fails (a title whose top pick does not play on its one try) and then on title to video (one clock from asking for the title until video). Decided by the owner on 2026-11-15 after Test 1; amended the same day (below).

## Why

KaijuFlow exists for health checks: a working video on the first press. Test 1 could not show that. Its ten popular titles have few dead Sources, so AltMount direct's unchecked top pick nearly always played, and its list in under a second beat KaijuFlow's checked list in 3 to 9 s. The targets judged list and start apart, so checking before the list looked like pure cost, and one try per play hid what a viewer actually gets from AltMount's fallback.

- One clock makes checking before the list and checking at play time cost the same.
- No fails comes first: a fast setup that fails a title loses it.
- A hard list of the kinds where Sources die (older, takedown-prone, less popular) shows what checking saves; the easy list shows what it costs. Titles are chosen by kind only, never by which side failed.
- New titles every speed test keep every cache, dead mark and import out of the result.

**Amended 2026-11-15.** This record first said each app plays as shipped, its own retries included (AltMount direct's two). The owner then decided the same day: no retries for anyone, every setup gets one play per title. So speed tests and tuning tests share the one-try rule of #142 and #143, and a fallback counts as a fail.

## Consequences

- AltMount direct's fallback stays off in speed tests (one try, the expected setting since #142); a top pick that fails, or plays only after a fallback, is a fail.
- The six targets of `targets.json` and #141's final bar are replaced by per-list targets on fails and title to video.
- Each speed test needs its own recording of new titles, which spends indexer requests every time; tuning tests replay one.
- Decided in advance: if KaijuFlow fails fewer hard titles, tune its speed; if it ties and AltMount direct is faster, try KaijuFlow without its own pre-list check behind AltMount; if AltMount direct fails fewer, KaijuFlow's checking has a bug to find first.
