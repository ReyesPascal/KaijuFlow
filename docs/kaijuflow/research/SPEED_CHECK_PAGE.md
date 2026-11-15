# Speed Check page: what "excellent" means and what to change

Research date: 2026-11-14. Read-only audit of version 7 of https://claude.ai/artifact/VUydiLAYH9gbJ63FtXk3qD, its `tables.json`, and the code that builds it. No code or page was changed.

Sources: the platform skills `artifact-design` (page contract and fundamentals) and `dataviz` (`SKILL.md`, `references/choosing-a-form.md`, `marks-and-anatomy.md`, `interaction.md`, `anti-patterns.md`, `palette.md`, `color-formula.md`); WCAG 2.2 (https://www.w3.org/TR/WCAG22/); MDN table accessibility (https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Structuring_content/Table_accessibility).

## 1. What the page is for

- **Reader:** the owner, and nobody else.
- **Job:** decide whether KaijuFlow meets the six targets of spec #58 ("Targets", and user story 16: "a final run that says target by target whether KaijuFlow met it"), and compare runs over time: baseline, tuning runs (#64), final run (#68) (story 17: "compare any two runs later and see how each setting change moved the numbers").
- **What follows:** the page should open with the verdict and the change since the last run. Detail comes after that. `artifact-design` says the same for a page that is scanned: "Put the summary before the detail."

## 2. Audit

### What it does well

- **Theming follows the contract.** Every colour is a token on bare `:root`, with both dark blocks and `color-scheme: dark`, and `body` has an explicit background (`tools/brain/build_page.py:53-67`).
- **Phone width.** The page has the viewport-fit meta together with both `max()` gutters (`build_page.py:68,342`). The wide grids sit in `.scroll` boxes (`:90-91`).
- **Contrast passes WCAG 1.4.3 AA in both themes.** I computed every text token with the `dataviz` validator's `contrast()`. The lowest pair that is actually used is muted text on the `--accent-soft` footer row, at 4.73:1. Dark muted on the dark page is 6.91:1.
- **Table markup.** `scope="row|col|colgroup"` is used throughout (`build_page.py:204,211-212,245`), which MDN recommends.
- **Typography basics.** `tabular-nums` in columns (`:87,96`), a 72ch measure (`:75`), balanced headings.
- **Plain prose.** Each card opens with a one-sentence answer (`story.html:6,23,44`).

### What breaks a rule

| # | Finding | Rule and source | Where it comes from |
|---|---|---|---|
| A1 | **The verdict uses a target the spec replaced.** The page judges "Warm list no slower than 4.7 s". Spec #58 says the target is now the warm list of the NinjaCentral-only baseline: "This replaces 'no slower than today's 4.7 s'". | Spec #58, Targets | `tools/brain/targets.json:5`; `story.html:12` |
| A2 | **The verdict is typed by hand and nothing checks it.** `brainreport.target_results` already computes it (`brainreport.py:783`), but the page does not use that function. | `tools/brain/docs/formats.md:132` ("Numbers written into the story's sentences are not checked") | `story.html:7-17` |
| A3 | **The verdict is not the first thing on the page.** "Who's who" comes before it. That block also carries notes about 2026-11-09 that do not fit the newest run (the "evening run", altHUB's limit), while the 2026-11-13 run used NinjaCentral only. | `artifact-design`: "summary before the detail"; "Make the page complete at rest" | `build_page.py:109-118,424-427` |
| A4 | **No "what changed since the last run".** `meta.json` holds `changes`, and spec #58 says every report opens with it. The comparison with 2026-11-10 is a hand-made table. | Spec #58, "Run records" | `story.html:43-75`; `build_page.py` never reads `meta['changes']` |
| A5 | **No charts at all.** Per-side comparisons, run-to-run change and per-title magnitudes are all tables. | `dataviz/references/choosing-a-form.md`: bar or emphasis for comparing sides, dumbbell for before and after, line for trend, heatmap for a grid, stat tile for a headline | whole page |
| A6 | **Pass and fail rely on red and green.** Round cells "9 of 10" and "10 of 10" differ only by colour. | WCAG 2.2 SC 1.4.1 Use of Color (A); `dataviz/SKILL.md`: status colours "ship with an icon + label, never color alone" | `build_page.py:203` (`ok`/`bad` class) |
| A7 | **Every block is the same card with an accent rail.** Each `.answer` has a 4px left accent border on a rounded card. | `artifact-design`: "accent bar/rail on rounded cards" is listed as AI-generated design; "Use card styling selectively" | `build_page.py:82` |
| A8 | **Tables have no captions, and some header cells are empty.** Captions: 0 in `tables.json`, none in `index.html`. Empty `<th>`: `story.html:80`; `page-archive/2026-11-09-live/section.html:9,30,47`. | MDN (use `<caption>`); WCAG SC 1.3.1 (A) and SC 2.4.6 (AA) | `build_page.py:208-250,283` |
| A9 | **Some tables can push the page wider than the screen.** The 7-column summary is wrapped with an inline style (`story.html:24`). The 6-column 2026-11-09 table has no wrapper (`section.html:8`). | `artifact-design` Responsive: wide tables "each inside its own `overflow-x: auto` container"; WCAG SC 1.4.10 Reflow (AA) | story and archive HTML |
| A10 | **The header words only fit one build.** `HEADER_FOR`, `EYEBROW` and `LEDE` were written for one run. Any other build falls back to "Brain · timed runs". | Not a rule; it limits quality on every future publish | `build_page.py:42-50,421-427`; `RUNBOOK.md:58` |
| A11 | **The words drift from the glossary.** Tables say "Setup" where `GLOSSARY.md` says "Side". "What the words mean" defines old column names ("List shows after", "Video starts after") instead of the current "Start" and "List". It leaves out Target, Round, median and "inside the noise". The definitions note is repeated in every targets card. | `GLOSSARY.md:47-99` ("Measuring"); WCAG SC 3.1.3 Unusual Words (AAA, advisory) | `build_page.py:120-134,211,284`; `story.html:18` |
| A12 | **Smaller issues.** `--ok-soft`, `--bad-soft` and `--warn-soft` are defined but never used (`build_page.py:55,61,65`). Decimals vary ("2.5 s" next to "4.53 s", and "156.0 per title" in `2026-11-09-live/section.html:17,32`). The 2026-11-09 appendix sits below "What the words mean", away from its own section (`build_page.py:428-429`). `CHECK.txt` gives KaijuFlow's cold 2 Inception failure as "failure video", while `report.md` and the story say Backend rejection. | `artifact-design`: "Make repeated elements consistent" | as cited |

## 3. Recommendations, ranked by how much they help the reading

### R1. Put the correct verdict first, and have the builder write it

- **What:** add a verdict band at the top of the page for the newest run.
  - A row of stat tiles: "Targets met: 1 of 6" with the change from the previous run, and KaijuFlow's cold and warm start against what each target compares it with.
  - Below the tiles, the six targets. Each gets a status chip with an icon and a word (✓ Met, ✗ Not met, – Not measured) and the "inside the noise" note.
  - Move "Who's who" below the verdict.
- **Where:**
  - In `build_page.py`, add a `__TARGETS__` placeholder rendered from `brainreport.target_results(run.visits)` and `verdict_text`, and drop the hand-typed table from `story.html:7-17`.
  - Fix `targets.json:5` to #58's definition first. The owner decides whether 2026-11-13 counts as "the redone NinjaCentral-only baseline".
- **Source:** spec #58 (Targets, story 16); `artifact-design` ("summary before the detail"; "Encode state in form as well as in numbers (a pill, a chip...)"); `dataviz/references/marks-and-anatomy.md` (stat tile: label, value, delta "vs a named period"); `dataviz/SKILL.md` ("Status colors are reserved... icon + label").

### R2. Add "Runs at a glance" and "What changed since the last run"

- **What:**
  - Under the verdict, a table with one row per run: date, name, what changed, targets met, KaijuFlow cold and warm start, and plays.
  - In each run section, the `meta.json` `changes` list, plus a table comparing the run with the run before it, computed from both `raw.json` files.
  - Mark the 2026-11-10 and 2026-11-09 runs "not comparable" (different machine and indexers; `2026-11-10-baseline-nc/section.html:54`), and fold them into one closed `<details>` section.
- **Where:** a new `glance_table(runs)` and `compare_table(run, prev)` in `build_page.py`, with placeholders `__CHANGES__` and `__COMPARE_TABLE__` added to `docs/formats.md:126-130`. Archive entries supply one fixed row each.
- **Source:** spec #58 stories 16-17 and "Run records"; `GLOSSARY.md` ("Stopped run... never the previous run of a comparison").

### R3. Chart the comparisons, and keep every table as the twin

Draw them as inline SVG from `build_page.py`, no library (`artifact-design`). Follow `dataviz`: thin marks and hairline grid, text in text tokens, a legend for two or more series, a hover and focus tooltip per mark, and the palette run through `validate_palette.js` in both themes.

Which chart goes where:

1. **Per-side start and list times:** horizontal bars, one per side. KaijuFlow is drawn in the accent colour and the other sides in grey (the emphasis form). The value the target compares against is drawn as a marker line. Source: `choosing-a-form.md` ("One series is the point, rest are context → emphasis").
2. **Run-to-run change:** a dumbbell per measure (previous run to this run). Source: `choosing-a-form.md` ("Before → after per item → dumbbell").
3. **Across baseline, #64 and #68:** small multiples, one line chart per target measure, each with its target line. Times and play counts never share one chart. Source: `anti-patterns.md` ("Dual-axis charts").
4. **Per-title grids** (`detail_table`, `build_page.py:218-250`): shade each cell on a one-hue sequential ramp, keep the numbers, and add a scale legend. Source: `choosing-a-form.md` ("heatmap for a grid"); `palette.md` (sequential blue ramp).

Every chart keeps its table as the twin. Source: `anti-patterns.md` ("Every chart has a table-view twin").

### R4. Let the builder own the header and the shared blocks

- **Header:** derive the eyebrow from the run and archive names and dates. Take the lede from an optional `<p class="lede">` in the newest run's `story.html`, or from a `header.html` in the run folder. Then retire `HEADER_FOR` (`build_page.py:42-50,421`) and the runbook caveat (`RUNBOOK.md:58`).
- **"Who's who":** build it only for the sides present in the runs given (`Run.sides`, `:174`).
- **Old-run notes:** move the 2026-11-09 sentences (`:112,117`) into `page-archive/2026-11-09-live/section.html`.
- **Source:** `artifact-design` ("Structure is information").

### R5. Restyle with fewer cards and stronger hierarchy

- **Cards:** keep a card only for the verdict band. Show other blocks as plain `h3` sections with a hairline divider, and drop `border-left` (`build_page.py:82`).
- **Status chips:** replace the coloured cell text (`:88,98,203`) with chips, so that "9 of 10 ✗" has a mark besides its colour.
- **Hero figure:** "1 of 6" goes in the sans face at 48px or more with proportional figures. Keep `tabular-nums` for columns only.
- **Tokens:** remove the unused `-soft` tokens, or use them as chip fills.
- **Source:** `artifact-design` (card styling; "accent bar/rail"); `marks-and-anatomy.md` (hero figure; "Proportional figures for big numbers"); WCAG SC 1.4.1.

### R6. Make every table readable by screen readers and on a phone

- Give every generated table a `<caption>` (`round_table`, `summary_table`, `detail_table`).
- Name the empty header cells ("Step", "Side").
- Wrap every table in `.scroll` from the builder, not with inline styles (`story.html:24`).
- Align headers with their numeric columns (`:92,96`).
- **Source:** MDN table accessibility ("A caption is placed directly beneath the `<table>` tag"); WCAG SC 1.3.1, 2.4.6, 1.4.10.

### R7. Use the glossary words, and define them once

- Write "Side" instead of "Setup" (`build_page.py:211,284`).
- Rebuild "What the words mean" from `GLOSSARY.md` "Measuring": Side, Round, Top pick, Target, Cold start, Warm start, Recording, plus Start, List, median and "inside the noise" (`brainreport.py:811-816` has the wording).
- Link to the definitions once instead of repeating the note in every card (`story.html:18`).
- Use one number format: two decimals, with units.
- **Source:** `GLOSSARY.md`; `artifact-design` ("Writing the copy... name things by what people recognize"); WCAG SC 3.1.3.

### R8. Close the loop in the process

- **`RUNBOOK.md` "Publish the page":** add a step to look once at phone width and in dark mode before publishing. `artifact-design` says to take that look for "a page that charts real numbers".
- **`tools/brain/test_build_page.py`:**
  - check that every `<table>` has a `<caption>` and sits in `.scroll`;
  - check that no `<th>` is empty;
  - check that the verdict matches `target_results`.
- **Data cleanup:** the `CHECK.txt` and `report.md` disagreement on failure causes (A12) should be resolved in the run tools before the page reuses either.

## Open question for the owner

- Which run is "the redone NinjaCentral-only baseline" that the warm-list target refers to (spec #58)? If it is 2026-11-13, that target is met by definition for that run. For later runs it becomes "no slower than 3.46 s".
