Recorded NNTP answers for the live read-only Clues (#284, spec #279: `test_clues.py`), asked of the provider on 2026-11-24 through `nntp.Recorder` around `nntp.Usenet` (one connection each, STAT and BODY only, nothing downloaded into a library, no Recording written). The answers are real; so are both NZBs, which come from the Recording `kf-189` (`~/kaijuflow-notes/recordings/kf-189/ninjacentral/`).

Scrubbed for a public repository: every message-id in the NZBs and in `answers.json` is replaced by the first 24 hex characters of its SHA-256 plus `@kf-fixture` (the same id in both, so a replay matches them up), and every `poster` is `(scrubbed)`. Nothing else in the NZBs is changed. No article body is kept: `Usenet.body` checks a body in memory (`yenc.check`) and keeps only that check, which is what `answers.json` holds.

| File | What it is |
|---|---|
| `sic-asrequested.nzb` | The.Witcher.S01E01.2160p.NF.WEB-DL.DDPA5.1.HDR.DV.HEVC-SiC-AsRequested: the Source #218's capture had AltMount refuse for its extension (`../2026-11-24-diagnosis/218-witcher-two-refusals/`). Every one of its 1872 video articles answered 223, and the first, middle and last came back whole. The cause absent for both live Clues. |
| `aaf-tz-s02e06-dead.nzb` | The.Twilight.Zone.1960.S02E06.720p.BluRay.x264-aAF, from 2010: its articles are gone. The sweep's first 10 answered 430, and 430 again when asked a second time; each 430 took the provider about 0.5 s, pipelined or not, which is why the sweep stops after 10 (`clues.ENOUGH_MISSES`). The cause present for `articles-missing`; `segment-crc-bad` cannot tell (nothing to read). |
| `answers.json` | `{"stat": {id: [code, ...]}, "body": {id: [check, ...]}}`, each list in the order the Clues asked: 1872 STATs and 3 body checks for SiC, 20 STATs and 3 BODY answers (430) for aAF. |
| `nfo-article.yenc` | The one article of `The Twilight Zone S02 720p AMZN WEB-DL DD 2 0 H 264-playWEB.nfo` (2538 bytes of text), as BODY gave it, dot-unstuffed, lines ending CRLF: the real body `yenc.check` is tried on. |

**Derived, not captured:** no damaged article was found on the provider (no run's AltMount log names a CRC error either, NNTP_HEALTH_CHECKS gap D), so the cause-present case of `segment-crc-bad` is SiC's middle article answered by the `.nfo` article's real body cut short before its `=yend` line (a transfer that ended early), as `yenc.check` reads it. The test says so where it builds it.

The 189 and 218 captures in `../2026-11-24-diagnosis/` got a `live.json` from the same session: the live Clues run by `diagnosis.live_clues` on a copy of each with its failed Source's NZB from the same Recording (the Frys pack: its first 10 articles 430 twice; SiC: as above). For 189 this was four days after its play, not right after a check.
