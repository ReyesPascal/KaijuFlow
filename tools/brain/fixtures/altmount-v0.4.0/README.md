# AltMount v0.4.0 `stremio:` block

- `stremio-as-found.yaml`: captured from the AltMount direct test copy (`~/kaijuflow-test/altmount-addon/config/config.yaml`) on 2026-11-15, before the like-for-like settings (#142). API keys replaced by `REDACTED`.
- `stremio-like-for-like.yaml`: a capture, taken from the same copy on 2026-11-15 (#151) after `testbed.py apply altmount-addon` had written the #142 settings and the #154 format "4K words beside 1080p or 720p" (`tools/brain/expected-settings.json`) into it. API keys replaced by `REDACTED`. Its scoring formats are in the shape `testbed.py apply` writes them (strings quoted, no `category`); AltMount v0.4.0 loads that shape (Test 1, #127, ran on it) and has not re-saved the file since. It replaces the hand-written block of #142.
