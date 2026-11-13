"""The one builder for the KaijuFlow speed-check page (spec #77, tickets #89 and #115).

    python3 -I tools/brain/build_page.py RUN_DIR [RUN_DIR ...] [--out DIR]

RUN_DIR is a run folder from brainrun.py (for example ~/kaijuflow-notes/brain-runs/<run>/). A timed run folder holds
raw.json and meta.json. Its recording folder (only meta.json) may be named too; nothing is read from it.
Nothing is published: the script writes two files into the output folder (default ~/kaijuflow-notes/brain-1338/page/).
RUNBOOK.md, "Publish the page", has the steps from there.

  index.html   small: headline answers, summary tables, column definitions. Safe for an agent to read before republishing.
  tables.json  the per-title tables, one HTML string per table id. The page loads it with fetch() and fills the
               <div data-table="id"> slots.

The page, top to bottom: header, "Who's who", one section per timed run given (newest first), the archived sections
(newest first), "What the words mean", the archived blocks that go below it, the footer.

Where the words come from. Edit them there, never in a built page:

  a timed run   story.html in its run folder, written by hand: the section's heading and findings. The builder puts
                the run's tables in where the story names them (__SUMMARY_TABLE__, __ROUND_TABLE__, __DETAILS__).
                A run without the file gets a numbers-only section.
  a lost run    page-archive/<entry>/ beside this file: the section and its tables as they were published, for runs
                whose folders are gone (2026-11-10, 2026-11-09). Never regenerated from anything.
  the rest      the constants below (header, "Who's who", "What the words mean").

docs/formats.md describes story.html and an archive entry.
"""
import argparse
import html
import json
import os
import re
import statistics

DEFAULT_OUT = os.path.expanduser('~/kaijuflow-notes/brain-1338/page/')
ARCHIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'page-archive')
ARCHIVE_PARTS = ('section.html', 'appendix.html', 'footer.html')
SIDES = [('kaijuflow', 'KaijuFlow with AltMount'), ('uu', 'Usenet Ultimate with NzbDAV'), ('altmount-addon', "AltMount's own addon"),
         ('kaijuflow-1page', 'KaijuFlow, one page per indexer')]
ROUNDS = [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)]

# The header words were written by hand for the page whose only timed run is HEADER_FOR (a run folder's name), with
# the archive below it. Any other build gets the plain words until someone writes new ones here.
HEADER_FOR = '2026-11-13T053200Z-baseline'
EYEBROW = 'Brain · 2026-11-13 baseline run · 2026-11-10 first baseline · 2026-11-09 live runs'
LEDE = ('Newest first: the baseline run of 2026-11-13 on the new machine, four setups on test copies that all got the same recorded indexer answers. '
        'Below it, the first baseline of 2026-11-10 from the old machine, then the four questions from 2026-11-09 about moving from NzbDAV to AltMount, '
        'answered on the live services.')
PLAIN_EYEBROW = 'Brain · timed runs'
PLAIN_LEDE = 'Newest first: the timed runs on the test copies.'

CSS = """/* Layout: answers first in one reading column, the full result grids below in their own scroll boxes. */
:root {
  --bg: #f4f6f8; --surface: #ffffff; --fg: #1c2733; --muted: #5d6b7a; --line: #d6dde5;
  --accent: #0e7490; --accent-soft: #e0f2f7; --ok: #15803d; --ok-soft: #e6f4ea; --bad: #b42318; --bad-soft: #fbeae7; --warn: #a16207; --warn-soft: #fdf3d8;
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0f161d; --surface: #161f28; --fg: #e4ebf2; --muted: #93a1b0; --line: #2a3542;
  --accent: #38bdd8; --accent-soft: #113845; --ok: #4ade80; --ok-soft: #12301f; --bad: #f87171; --bad-soft: #3a1a18; --warn: #facc15; --warn-soft: #3a2f10;
  color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #0f161d; --surface: #161f28; --fg: #e4ebf2; --muted: #93a1b0; --line: #2a3542;
  --accent: #38bdd8; --accent-soft: #113845; --ok: #4ade80; --ok-soft: #12301f; --bad: #f87171; --bad-soft: #3a1a18; --warn: #facc15; --warn-soft: #3a2f10;
  color-scheme: dark }
body { background: var(--bg); color: var(--fg); font-family: var(--sans); font-size: 16px; line-height: 1.55;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 28px 56px; }
main { max-width: 1120px; margin: 0 auto; display: grid; gap: 40px; }
header { display: grid; gap: 10px; max-width: 72ch; }
.eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
h1 { font-size: clamp(26px, 4vw, 34px); font-weight: 600; line-height: 1.15; margin: 0; text-wrap: balance; }
h2 { font-size: 21px; font-weight: 600; margin: 0; text-wrap: balance; }
h3 { font-size: 17px; font-weight: 600; margin: 0; }
p { margin: 0; max-width: 72ch; }
.lede { color: var(--muted); }
section { display: grid; gap: 14px; }
.who { display: grid; gap: 10px; max-width: 80ch; margin: 0; }
.who div { display: grid; grid-template-columns: minmax(12ch, 24ch) 1fr; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--line); }
.who dt { font-weight: 600; }
.who dd { margin: 0; color: var(--muted); }
.answer { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: 6px; padding: 16px 18px; display: grid; gap: 12px; }
.answer .big { font-size: 18px; font-weight: 600; }
table.mini { border-collapse: collapse; font-size: 15px; max-width: 80ch; }
table.mini th, table.mini td { padding: 7px 14px 7px 0; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
table.mini thead th { color: var(--muted); font-weight: 500; font-size: 12.5px; }
table.mini td.num { font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
table.mini td.ok { color: var(--ok); font-weight: 500; } table.mini td.bad { color: var(--bad); font-weight: 500; }
.note { color: var(--muted); font-size: 14.5px; }
.scroll { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
table.grid { border-collapse: collapse; width: 100%; min-width: 760px; font-size: 13.5px; }
table.grid th, table.grid td { padding: 7px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
table.grid thead th { font-weight: 500; color: var(--muted); font-size: 12px; letter-spacing: .02em; }
table.grid thead th.side { color: var(--fg); font-weight: 600; font-size: 13px; border-bottom: 2px solid var(--accent); text-align: center; white-space: nowrap; }
table.grid tbody th { font-weight: 500; white-space: nowrap; }
table.grid td.num { font-family: var(--mono); font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
table.grid tfoot th, table.grid tfoot td { font-weight: 600; border-top: 2px solid var(--line); border-bottom: 0; background: var(--accent-soft); }
td.ok { color: var(--ok); } td.bad { color: var(--bad); font-weight: 500; } td.warn { color: var(--warn); }
.why { display: block; font-family: var(--sans); font-size: 11.5px; color: var(--muted); white-space: normal; max-width: 22ch; text-align: left; font-weight: 400; }
details { display: grid; gap: 12px; }
summary { cursor: pointer; font-weight: 600; font-size: 17px; }
summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
ul { margin: 0; padding-left: 20px; display: grid; gap: 8px; max-width: 80ch; }
code { font-family: var(--mono); font-size: 12.5px; background: var(--surface); border: 1px solid var(--line); border-radius: 4px; padding: 1px 5px; }
footer { color: var(--muted); font-size: 13px; max-width: 90ch; display: grid; gap: 4px; }
@media (max-width: 640px) { .who div { grid-template-columns: 1fr; gap: 2px; } }
"""

WHO = """<section>
  <h2>Who's who</h2>
  <dl class="who">
    <div><dt>AltMount's own addon</dt><dd>AltMount searches and plays by itself. No KaijuFlow involved. For the evening run it got the same three indexers as KaijuFlow (it had one in the afternoon).</dd></div>
    <div><dt>KaijuFlow with AltMount</dt><dd>KaijuFlow searches and checks the Sources, AltMount plays them. This is the planned setup.</dd></div>
    <div><dt>Usenet Ultimate with NzbDAV</dt><dd>What the TVs use today. It is in the tables as the yardstick: the new setup has to be at least this good.</dd></div>
    <div><dt>KaijuFlow, one page per indexer</dt><dd>KaijuFlow with AltMount again, but asking each indexer for one page of results only. In the 2026-11-13 run only.</dd></div>
  </dl>
  <p class="note">altHUB, the third indexer, had hit its daily limit before the evening run and answered "request limit reached" to every side, so the evening numbers come from NinjaCentral and DrunkenSlug on all three sides. It resets around 11:30 UTC on 2026-11-10.</p>
</section>"""

WORDS = """<section>
  <h2>What the words mean</h2>
  <dl class="who">
    <div><dt>Source</dt><dd>One release of a title found on an indexer. A Stream is a Source that is ready to play.</dd></div>
    <div><dt>Backend</dt><dd>The program that turns a Source into a playable video: NzbDAV today, AltMount next.</dd></div>
    <div><dt>List shows after</dt><dd>Seconds from asking for a title until the list of Sources arrives in Stremio.</dd></div>
    <div><dt>Top pick plays</dt><dd>The first Source in the list played without an error.</dd></div>
    <div><dt>Broken</dt><dd>A Source that is in the list but will not play: an error, or the failure video.</dd></div>
    <div><dt>Video starts after</dt><dd>Seconds from pressing play until the first bytes of video arrive.</dd></div>
    <div><dt>Jump</dt><dd>Seeking: reading 64 KiB at the middle of the file and at 90% of it.</dd></div>
    <div><dt>Cold / warm</dt><dd>Cold: the Backend has never seen the file and must import it first, and KaijuFlow has not health-checked the title yet. Warm: both have been done, and the sides answer from what they already have.</dd></div>
    <div><dt>Unscramble</dt><dd>KaijuFlow's step that puts a Scrambled RAR set (parts with random names) back in order before the upload, so AltMount accepts it. It runs on every cold import and is skipped quickly when the set is fine.</dd></div>
    <div><dt>Dead mark</dt><dd>KaijuFlow and Usenet Ultimate remember a Source that failed and leave it out of the next list.</dd></div>
  </dl>
</section>"""


# ---------- small helpers ----------
def esc(s):
    return html.escape(str(s))


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def s(v, digits=2):
    return '–' if v is None else f'{v:.{digits}f}'


def of(p):
    return f'{p[0]} of {p[1]}'


# ---------- one timed run (raw.json visits) ----------
def played(v):
    return bool(v['tries'] and v['tries'][0]['plays'])


class Run:
    """The numbers of one timed run folder."""

    def __init__(self, folder):
        self.folder = folder.rstrip('/') + '/'
        self.folder_name = os.path.basename(self.folder.rstrip('/'))
        self.meta = json.load(open(self.folder + 'meta.json'))
        self.name = self.meta.get('name') or self.folder_name
        self.visits = json.load(open(self.folder + 'raw.json'))['visits']
        self.titles = []
        for v in self.visits:
            if v['title'] not in self.titles:
                self.titles.append(v['title'])
        seen = {v['side'] for v in self.visits}
        self.sides = [(n, label) for n, label in SIDES if n in seen] + [(n, n) for n in sorted(seen) if n not in dict(SIDES)]
        self.id = self.name

    def group(self, side, phase=None, rnd=None):
        return [v for v in self.visits if v['side'] == side and (phase is None or v['phase'] == phase) and (rnd is None or v['round'] == rnd)]

    def plays(self, side, phase=None, rnd=None):
        g = [v for v in self.group(side, phase, rnd) if not v.get('not_recorded')]
        return sum(1 for v in g if played(v)), len(g)

    def start(self, side, phase=None, rnd=None):
        return med([v['start_s'] for v in self.group(side, phase, rnd) if played(v)])

    def listtime(self, side, phase=None, rnd=None):
        return med([v['list_s'] for v in self.group(side, phase, rnd)])

    def failed_titles(self, side):
        return sorted({v['title'] for v in self.group(side) if not played(v) and not v.get('not_recorded')}, key=self.titles.index)

    def date(self):
        return (self.meta.get('finished') or self.meta.get('started') or '')[:10]


def round_rows(run):
    out = []
    for n, label in run.sides:
        cells = ''
        for ph, rd in ROUNDS:
            p = run.plays(n, ph, rd)
            cells += f'<td class="num">{s(run.start(n, ph, rd))} s</td><td class="num">{s(run.listtime(n, ph, rd))} s</td><td class="{"ok" if p[0] == p[1] else "bad"}">{of(p)}</td>'
        out.append(f'<tr><th scope="row">{esc(label)}</th>{cells}</tr>')
    return ''.join(out)


def round_table(run):
    return f'''<div class="scroll"><table class="grid">
      <thead>
        <tr><th rowspan="2" scope="col">Setup</th>{''.join(f'<th colspan="3" scope="colgroup" class="side">{ph.capitalize()} {rd}</th>' for ph, rd in ROUNDS)}</tr>
        <tr>{'<th scope="col">Start</th><th scope="col">List</th><th scope="col">Top pick plays</th>' * 4}</tr>
      </thead>
      <tbody>{round_rows(run)}</tbody>
    </table></div>'''


def detail_table(run, field):
    """Per-title grid, one column per side and round. field is 'start_s' or 'list_s'. Goes into tables.json."""
    rows = []
    for t in run.titles:
        cells = ''
        for n, _ in run.sides:
            for ph, rd in ROUNDS:
                v = next((v for v in run.visits if v['side'] == n and v['title'] == t and v['phase'] == ph and v['round'] == rd), None)
                if v is None:
                    cells += '<td class="warn">no visit</td>'
                elif field == 'start_s':
                    if v.get('not_recorded'):
                        cells += '<td class="warn">not recorded</td>'
                    elif not played(v):
                        cells += '<td class="bad">fails</td>'
                    else:
                        cells += f'<td class="num">{s(v["start_s"])}</td>'
                else:
                    cells += f'<td class="num">{s(v["list_s"])}</td>'
        rows.append(f'<tr><th scope="row">{esc(t)}</th>{cells}</tr>')
    foot = ''
    for n, _ in run.sides:
        for ph, rd in ROUNDS:
            foot += f'<td class="num">{s(run.start(n, ph, rd) if field == "start_s" else run.listtime(n, ph, rd))}</td>'
    heads = ''.join(f'<th scope="col">{ph.capitalize()} {rd}</th>' for _ in run.sides for ph, rd in ROUNDS)
    return f'''<div class="scroll"><table class="grid">
<thead>
<tr><th rowspan="2" scope="col">Title</th>{''.join(f'<th colspan="{len(ROUNDS)}" scope="colgroup" class="side">{esc(l)}</th>' for _, l in run.sides)}</tr>
<tr>{heads}</tr>
</thead>
<tbody>{''.join(rows)}</tbody>
<tfoot><tr><th scope="row">Median</th>{foot}</tr></tfoot>
</table></div>'''


def slot(table_id):
    return f'<div data-table="{esc(table_id)}" class="slot">Loading the table...</div>'


def run_details(run):
    """The two per-title detail blocks of a run: slots in the page, the tables themselves go to tables.json."""
    start_id, list_id = f'{run.id}-start', f'{run.id}-list'
    html_ = f'''  <details>
    <summary>All numbers: start time per title (s)</summary>
    {slot(start_id)}
    <p class="note">"fails" = the top pick did not play. Each setup plays its own top pick, so the setups are not always starting the same file.</p>
  </details>
  <details>
    <summary>All numbers: list time per title (s)</summary>
    {slot(list_id)}
  </details>'''
    tables = {start_id: detail_table(run, 'start_s'), list_id: detail_table(run, 'list_s')}
    return html_, tables


# ---------- the section of a timed run: its story.html if it has one, else numbers only ----------
STORY_FILE = 'story.html'


def summary_table(run):
    lines = []
    for n, label in run.sides:
        c, w = run.plays(n, 'cold'), run.plays(n, 'warm')
        lines.append(f'<tr><th scope="row">{esc(label)}</th><td class="num">{s(run.start(n, "cold"))} s</td><td class="num">{s(run.start(n, "warm"))} s</td>'
                     f'<td class="num">{s(run.listtime(n, "cold"))} s</td><td class="num">{s(run.listtime(n, "warm"))} s</td><td>{of(c)}</td><td>{of(w)}</td></tr>')
    return f'''<table class="mini">
      <thead><tr><th scope="col">Setup</th><th scope="col">Start, cold</th><th scope="col">Start, warm</th><th scope="col">List, cold</th><th scope="col">List, warm</th><th scope="col">Top pick plays, cold</th><th scope="col">Top pick plays, warm</th></tr></thead>
      <tbody>{''.join(lines)}</tbody>
    </table>'''


def story_of(run):
    """The run's written findings (story.html in its folder) or None. docs/formats.md says what the file holds."""
    path = run.folder + STORY_FILE
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return fh.read()


def numbers_only(run):
    """The section body for a run nobody has written about yet."""
    V = run
    indexers = ', '.join(V.meta.get('indexers') or []) or 'indexers not named'
    fails = []
    for n, label in V.sides:
        bad = V.failed_titles(n)
        if bad:
            fails.append(f'<li><strong>{esc(label)}:</strong> the top pick did not play for {esc(", ".join(bad))}.</li>')
    fail_block = ('<ul>' + ''.join(fails) + '</ul>') if fails else '<p>Every top pick played on every side.</p>'
    err = V.meta.get('error')
    status = f'<p class="note">The run stopped with an error: {esc(err)}</p>' if err else ''
    return f'''  <h2>Run {esc(V.name)}, {esc(V.date())} ({esc(indexers)})</h2>
  <p>{len(V.titles)} titles, {len(V.sides)} setups, rounds {esc(', '.join(f'{p} {r}' for p, r in ROUNDS))}. Numbers only; no written story for this run yet.</p>
  <div class="answer">
    <h3>Summary</h3>
    __SUMMARY_TABLE__
    <p class="note">Start = seconds from pressing play on the top pick until the first bytes of video arrive. List = seconds from asking for a title until the list of Sources arrives. Every time is the median over the titles. Cold = the Backend is empty and has to import the file. Warm = the same titles again right after.</p>
  </div>
  <div class="answer">
    <h3>The numbers, round by round</h3>
    __ROUND_TABLE__
  </div>
  <div class="answer">
    <h3>Top picks that did not play</h3>
    {fail_block}
    {status}
  </div>
__DETAILS__'''


def run_section(run):
    """One run's section and its per-title tables. The tables the builder makes go in where the body names them."""
    details, tables = run_details(run)
    story = story_of(run)
    body = numbers_only(run) if story is None else story.strip('\n')
    for name, made in (('__SUMMARY_TABLE__', summary_table(run)), ('__ROUND_TABLE__', round_table(run)), ('__DETAILS__', details)):
        body = body.replace(name, made)
    mark = f'{run.id} {run.date()}'
    return f'<!-- {mark} start -->\n<section>\n{body}\n</section>\n<!-- {mark} end -->\n', tables


# ---------- the page ----------
HEAD = '''<title>KaijuFlow Speed Check</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
''' + CSS.rstrip('\n') + '''
.slot { min-height: 2em; color: var(--muted); }
</style>
'''

SCRIPT = '''<script>
// The per-title tables sit in tables.json beside this page; fill each slot from it.
(function () {
  var slots = document.querySelectorAll('[data-table]');
  function fill(tables) { slots.forEach(function (el) { el.innerHTML = tables[el.getAttribute('data-table')] || 'This table is missing from tables.json.'; el.classList.remove('slot'); }); }
  function fail() { slots.forEach(function (el) { el.textContent = 'The tables could not be loaded (tables.json must sit next to this page).'; }); }
  fetch('tables.json').then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.json(); }).then(fill).catch(fail);
})();
</script>
'''


def find_runs(folders):
    """The timed runs among the given folders (those with raw.json), newest first. A recording folder (meta mode
    'record') may be named beside its run; nothing on the page is read from it."""
    runs = []
    for f in folders:
        if os.path.exists(os.path.join(f, 'raw.json')):
            runs.append(Run(f))
            continue
        with open(os.path.join(f, 'meta.json')) as fh:
            if json.load(fh).get('mode') != 'record':
                raise SystemExit(f'{f}: neither a timed run (raw.json) nor a recording (meta.json with mode "record")')
    if not runs:
        raise SystemExit('Give at least one timed run folder (one that holds raw.json).')
    runs.sort(key=lambda r: r.folder_name, reverse=True)
    return runs


def load_archive(folder):
    """The archived runs, newest first. Each is a dict: 'name', the text of every part ('' if the entry has no such
    file) and 'tables'."""
    entries = []
    for name in sorted(os.listdir(folder), reverse=True):
        path = os.path.join(folder, name)
        if not os.path.isdir(path):
            continue
        entry = {'name': name, 'tables': {}}
        for part in ARCHIVE_PARTS:
            entry[part] = ''
            if os.path.exists(os.path.join(path, part)):
                with open(os.path.join(path, part)) as fh:
                    entry[part] = fh.read()
        if os.path.exists(os.path.join(path, 'tables.json')):
            with open(os.path.join(path, 'tables.json')) as fh:
                entry['tables'] = json.load(fh)
        entries.append(entry)
    return entries


def add_tables(tables, new, owner):
    for tid, table_html in new.items():
        if tid in tables:
            raise SystemExit(f'Two tables are called "{tid}" (the second one comes from {owner}). Every run on the page needs its own name.')
        tables[tid] = table_html


def build(folders, archive=ARCHIVE):
    """Returns (index_html, tables): the page as a string and the per-title tables as a dict. archive is the folder
    of archived runs (None: none)."""
    runs = find_runs(folders)
    entries = load_archive(archive) if archive else []
    tables = {}
    sections = []
    for run in runs:
        text, t = run_section(run)
        sections.append(text)
        add_tables(tables, t, run.folder)
    for entry in entries:
        add_tables(tables, entry['tables'], f'the archive entry {entry["name"]}')
    written = [r.folder_name for r in runs] == [HEADER_FOR] and bool(entries)
    plain_lede = PLAIN_LEDE + (' Below them, the earlier runs whose records are gone, as they were published.' if entries else '')
    footer = ''.join(e['footer.html'] for e in entries)
    parts = [HEAD, '<main>\n<header>\n',
             f'  <div class="eyebrow">{EYEBROW if written else PLAIN_EYEBROW}</div>\n',
             '  <h1>KaijuFlow Speed Check</h1>\n',
             f'  <p class="lede">{LEDE if written else plain_lede}</p>\n</header>\n\n', WHO, '\n\n',
             '\n'.join(sections + [e['section.html'] for e in entries if e['section.html']]), '\n', WORDS, '\n\n',
             ''.join(e['appendix.html'] + '\n' for e in entries if e['appendix.html']),
             f'<footer>\n{footer}</footer>\n' if footer else '', '</main>\n', SCRIPT]
    index = ''.join(parts)
    empty = [tid for tid in re.findall(r'data-table="([^"]+)"', index) if tid not in tables]
    if empty:
        raise SystemExit(f'The page has a place for the table "{empty[0]}", but no such table was built or archived.')
    return index, tables


def write(folders, out=DEFAULT_OUT, archive=ARCHIVE):
    index, tables = build(folders, archive)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'index.html'), 'w') as fh:
        fh.write(index)
    with open(os.path.join(out, 'tables.json'), 'w') as fh:
        json.dump(tables, fh, ensure_ascii=False, indent=1)
    return index, tables


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the speed-check page (index.html + tables.json) from run folders. Does not publish.')
    ap.add_argument('runs', nargs='+', help='run folders, e.g. ~/kaijuflow-notes/brain-runs/<run>/')
    ap.add_argument('--out', default=DEFAULT_OUT, help='output folder (default %(default)s)')
    a = ap.parse_args(argv)
    index, tables = write(a.runs, a.out)
    print(f'wrote {a.out}index.html ({len(index)} bytes) and tables.json ({len(tables)} tables)' if a.out.endswith('/') else
          f'wrote {a.out}/index.html ({len(index)} bytes) and tables.json ({len(tables)} tables)')


if __name__ == '__main__':
    main()
