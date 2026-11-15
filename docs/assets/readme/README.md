# README banner

`banner.html` is the source of `banner-light.png` and `banner-dark.png` (the repository's front page shows the one that matches GitHub's theme). Starting line design: Archivo, timing yellow `#FFD400`, the Speed Check page's colours.

To change it, edit `banner.html` and render both themes at 2x with Playwright (for example from `~/.local/share/kf-render`): a 1200 x 380 viewport, `deviceScaleFactor: 2`, a screenshot of `#b` with its class set to `light` and then `dark`.
