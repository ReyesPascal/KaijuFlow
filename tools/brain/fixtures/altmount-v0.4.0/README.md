# AltMount v0.4.0 `stremio:` block

- `stremio-as-found.yaml`: captured from the AltMount direct test copy (`~/kaijuflow-test/altmount-addon/config/config.yaml`) on 2026-11-15, before the like-for-like settings (#142). API keys replaced by `REDACTED`.
- `stremio-like-for-like.yaml`: the same block with the #142 settings and the #154 format "4K words beside 1080p or 720p" (`tools/brain/expected-settings.json`) written in by hand, in the shape AltMount v0.4.0 writes them (`internal/config/manager.go`, `TrashCustomFormatConfig`: `category: ""`, `invert` left out when false). Replace it with a capture once the owner has applied the settings to the copy (#127).
