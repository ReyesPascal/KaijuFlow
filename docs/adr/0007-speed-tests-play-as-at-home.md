# Speed tests play each app as at home, on new titles, judged on fails then title to video

A speed test plays an easy list and a hard list of titles no side has played before, new every test. Each app plays as it would at home, its own retries included, and is judged first on fails (a title that ends with no video) and then on title to video (one clock from asking for the title until video, retries included). Decided by the owner on 2026-11-15 after Test 1.

## Why

KaijuFlow exists for health checks: a working video on the first press. Test 1 could not show that. Its ten popular titles have few dead Sources, so AltMount direct's unchecked top pick nearly always played, and its list in under a second beat KaijuFlow's checked list in 3 to 9 s. The targets judged list and start apart, so checking before the list looked like pure cost, and one try per play hid what a viewer actually gets from AltMount's fallback.

- One clock makes checking before the list, checking at play time and retrying cost the same.
- No fails comes first: a fast setup that fails a title loses it.
- A hard list of the kinds where Sources die (older, takedown-prone, less popular) shows what checking saves; the easy list shows what it costs. Titles are chosen by kind only, never by which side failed.
- New titles every speed test keep every cache, dead mark and import out of the result.

The rejected alternative was one try per play for every side (#142, #143): it judges the choice of top pick, not what the viewer gets. Tuning tests keep it, because they compare one change on the same titles.

## Consequences

- AltMount direct's fallback is back on in speed tests; every retry is timed and shown, never hidden.
- The six targets of `targets.json` and #141's final bar are replaced by per-list targets on fails and title to video.
- Each speed test needs its own recording of new titles, which spends indexer requests every time; tuning tests replay one.
- Decided in advance: if KaijuFlow fails fewer hard titles, tune its speed; if it ties and AltMount direct is faster, try KaijuFlow without its own pre-list check behind AltMount; if AltMount direct fails fewer, KaijuFlow's checking has a bug to find first.
