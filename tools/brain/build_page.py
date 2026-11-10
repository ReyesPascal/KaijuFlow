"""The one builder for the KaijuFlow speed-check page (spec #77, ticket #89).

    python3 -I tools/brain/build_page.py RUN_DIR [RUN_DIR ...] [--out DIR] [--notes DIR] [--no-1109]

RUN_DIR is a run folder from brainrun.py (for example /home/ryan/kaijuflow-notes/brain-runs/<run>/). A timed run
folder holds raw.json and meta.json; a recording folder holds only meta.json (its times go into the page text).
Newest run first. Nothing is published: the script writes two files into the output folder (default
/home/ryan/kaijuflow-notes/brain-1338/page/):

  index.html   small: headline answers, summary tables, column definitions. Safe for an agent to read before republishing.
  tables.json  the per-title tables, one HTML string per table id. The page loads it with fetch() and fills the
               <div data-table="id"> slots.

The 2026-11-09 text (the afternoon and evening runs on the live services) was corrected by hand. It lives in this
file as the constants below and is never regenerated from anything: edit the text here, never in a built page.
Its per-title tables are built from the old result files in --notes (search.json, parity-run3.json, cold-search.json,
warm-search.json, parity-fresh.json); --no-1109 leaves the 2026-11-09 part out.
"""
import argparse
import html
import json
import os
import statistics

DEFAULT_OUT = '/home/ryan/kaijuflow-notes/brain-1338/page/'
DEFAULT_NOTES = '/home/ryan/kaijuflow-notes/brain-1338/'
SIDES = [('kaijuflow', 'KaijuFlow with AltMount'), ('uu', 'Usenet Ultimate with NzbDAV'), ('altmount-addon', "AltMount's own addon")]
ROUNDS = [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)]
SIDES_1109 = [('altmount-addon', "AltMount's own addon"), ('kaijuflow-altmount', 'KaijuFlow with AltMount'), ('uu-nzbdav', 'Usenet Ultimate with NzbDAV (today)')]

EYEBROW = 'Brain · 2026-11-10 baseline run · 2026-11-09 afternoon and evening runs'
LEDE = ('Newest first: the baseline run of 2026-11-10, three setups on test copies that all got the same recorded indexer answers. '
        'Below it, the four questions from 2026-11-09 about moving from NzbDAV to AltMount, answered on the live services.')
GENERIC_LEDE = 'Newest first: the timed runs on the test copies, then the questions from 2026-11-09 answered on the live services.'

# ---------- hand-corrected 2026-11-09 text (kept word for word) ----------
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
  </dl>
  <p class="note">altHUB, the third indexer, had hit its daily limit before the evening run and answered "request limit reached" to every side, so the evening numbers come from NinjaCentral and DrunkenSlug on all three sides. It resets around 11:30 UTC on 2026-11-10.</p>
</section>"""

ANSWERS_1109 = """<section>
  <h2>Earlier answers, 2026-11-09 (live services)</h2>
  <p class="note">Four questions about moving from NzbDAV to AltMount. Afternoon: 10 titles the Backends had seen before. Evening: 10 fresh titles nobody had played, each played twice, first cold and then warm. All five runs finished without errors.</p>

  <div class="answer">
    <h3>1. Which search should KaijuFlow use, its own or AltMount's?</h3>
    <div class="big">Its own. With the same indexers on both, AltMount's addon still lists faster but keeps failing the same picks; KaijuFlow learns from a bad pick and played 10 of 10 the second time.</div>
    <table class="mini">
      <thead><tr><th scope="col"></th><th scope="col">List shows after, cold</th><th scope="col">List shows after, warm</th><th scope="col">Top pick played, cold</th><th scope="col">Top pick played, warm</th><th scope="col">Broken picks, cold (of 29 / 30 / 30 tried)</th></tr></thead>
      <tbody>
        <tr><th scope="row">AltMount's own addon</th><td class="num">1.19 s</td><td class="num">0.71 s</td><td class="bad">8 of 10</td><td class="bad">8 of 10</td><td class="num">7</td></tr>
        <tr><th scope="row">KaijuFlow with AltMount</th><td class="num">9.24 s</td><td class="num">4.67 s</td><td class="ok">9 of 10</td><td class="ok">10 of 10</td><td class="num">7</td></tr>
        <tr><th scope="row">Usenet Ultimate today</th><td class="num">8.94 s</td><td class="num">4.42 s</td><td class="ok">8 of 10</td><td class="ok">10 of 10</td><td class="num">8</td></tr>
      </tbody>
    </table>
    <p>Evening run, fresh titles. The addon lists in about a second because it shows indexer results without checking them; when you press play it finds the missing pieces and gives up. Its top pick failed on Whiplash and Band of Brothers S01E02 the first time and on Whiplash and Band of Brothers S01E02 again the second time: it does not remember a bad Source. KaijuFlow and Usenet Ultimate spend their 9 seconds (cold) or 4 to 5 seconds (warm) health-checking Sources before the list appears. KaijuFlow's one cold miss was The Wire S01E01 (a season pack that showed the failure video on Usenet Ultimate too); it was marked dead, and the warm run played 10 of 10 on both.</p>
    <p>Sources shown: the addon lists about 156.0 per title, KaijuFlow and Usenet Ultimate about 281.0. AltMount asks each indexer for one page of 100 results and then removes duplicates; KaijuFlow pages through everything. Compare speed and reliability, not the counts. The afternoon run (one indexer on the addon, titles already played) is in the tables below and said the same thing.</p>
  </div>

  <div class="answer">
    <h3>2. Does AltMount play the same video as NzbDAV?</h3>
    <div class="big">Yes, twice over. Fresh titles: all 10 play on both, 9 of 10 are the exact same bytes. Afternoon: all 10 play, 9 of 10 identical.</div>
    <p>The one fresh title not counted, Band of Brothers S01E02, had a different top pick on each side after the cold run (Usenet Ultimate marked a 4K season pack dead; KaijuFlow with AltMount had played it), so there was nothing to compare. In the afternoon it was Game of Thrones S02E03 for the same reason. No fresh title needed Unscramble at this point: the three Scrambled RAR sets among the fresh picks were Unscrambled during the cold run.</p>
  </div>

  <div class="answer">
    <h3>3. How fast does a video start, and how fast can you jump around in it?</h3>
    <div class="big">Cold start: AltMount through KaijuFlow is about a second slower than NzbDAV, and the second is the Unscramble step. Warm start: AltMount is 4 to 5 times faster. Jumping is under half a second on both.</div>
    <table class="mini">
      <thead><tr><th scope="col"></th><th scope="col">NzbDAV (via Usenet Ultimate)</th><th scope="col">AltMount (via KaijuFlow)</th><th scope="col">AltMount (via its own addon)</th></tr></thead>
      <tbody>
        <tr><th scope="row">Start, first time ever (cold)</th><td class="num">3.42 s</td><td class="num">4.53 s</td><td class="num">2.5 s</td></tr>
        <tr><th scope="row">Start, played before (warm)</th><td class="num">0.28 s</td><td class="num">0.06 s</td><td class="num">0.04 s</td></tr>
        <tr><th scope="row">Jump to the middle, first time</th><td class="num">0.29 s</td><td class="num">0.45 s</td><td class="num">–</td></tr>
        <tr><th scope="row">Jump near the end, first time</th><td class="num">0.33 s</td><td class="num">0.41 s</td><td class="num">–</td></tr>
        <tr><th scope="row">Jump, same spots again (afternoon)</th><td class="num">0.2 / 0.2 s</td><td class="num">0.01 / 0.01 s</td><td class="num">–</td></tr>
      </tbody>
    </table>
    <p>Start times are the top pick of each fresh title, medians over the titles whose top pick played (8 / 9 / 8 titles cold). Cold means the Backend had never seen the file and had to import it. KaijuFlow's cold start includes the Unscramble step from the afternoon's fix: 0.6 to 1.6 s to find out a set is not scrambled, and 3.3 to 4.0 s to rename one that is (three of the evening's picks were: Severance S01E01 as a top pick at 9.4 s, Blade Runner 2049 and Mad Max: Fury Road as third picks). Without that step the two Backends import at about the same speed; the addon, which skips it, is the fastest cold starter but rejects Scrambled sets outright. Once a file has been played, AltMount answers in well under a tenth of a second where NzbDAV takes a quarter to a third.</p>
    <p>Jumping: the first jump into an unseen part of the file fetches it from Usenet on both Backends, 0.3 to 0.5 s. The afternoon run jumped to spots that had been read before, and there AltMount answered from what it had (0.01 s) while NzbDAV fetched again (0.2 s).</p>
  </div>

  <div class="answer">
    <h3>4. The cold run, side by side</h3>
    <div class="big">Nothing in the cold run changed the picture: KaijuFlow with AltMount is as reliable as today's setup, slower to start the very first time by the Unscramble second, and faster every time after.</div>
    <table class="mini">
      <thead><tr><th scope="col"></th><th scope="col">Start cold → warm</th><th scope="col">List cold → warm</th><th scope="col">Top pick plays cold → warm</th></tr></thead>
      <tbody>
        <tr><th scope="row">AltMount's own addon</th><td class="num">2.5 → 0.04 s</td><td class="num">1.19 → 0.71 s</td><td>8 → 8 of 10</td></tr>
        <tr><th scope="row">KaijuFlow with AltMount</th><td class="num">4.53 → 0.06 s</td><td class="num">9.24 → 4.67 s</td><td>9 → 10 of 10</td></tr>
        <tr><th scope="row">Usenet Ultimate today</th><td class="num">3.42 → 0.28 s</td><td class="num">8.94 → 4.42 s</td><td>8 → 10 of 10</td></tr>
      </tbody>
    </table>
    <p>Cold is the first run on the fresh titles (nothing imported, no health-check memory, no dead marks). Warm is the same titles a few minutes later. The list time halves on KaijuFlow and Usenet Ultimate because the health checks remember what they found; the addon never checked anything, so it has nothing to remember and fails the same two picks again.</p>
  </div>
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

WORTH_KNOWING = """<section>
  <h2>Worth knowing</h2>
  <ul>
    <li><strong>altHUB was out for everyone.</strong> Its daily limit was reached before the evening run (HTTP 429 on every search), so all three sides searched NinjaCentral and DrunkenSlug only. That is why the Source counts are lower than in the afternoon. The comparison between sides is still fair.</li>
    <li><strong>The Unscramble second.</strong> It is the one place where KaijuFlow with AltMount is slower than today's setup, and only on the very first play of a file. If that matters, the not-scrambled check (0.6 to 1.6 s) is the part to look at; the real Unscramble (3 to 4 s) only runs on sets that would otherwise not play at all.</li>
    <li><strong>What broke on AltMount's addon.</strong> Whiplash and Band of Brothers S01E02 top picks (HTTP 503 after AltMount's own article check), and second or third picks on Severance and The Bear; the same two top picks failed again in the warm run. Blade Runner 2049 showed only 2 Sources because AltMount's relevance filter dropped 191 results for that title (it tripped over the "2049" in the name).</li>
    <li><strong>What broke on the other two (corrected).</strong> Most of these were not bad Sources. From 16:18 UTC DrunkenSlug refused NZB downloads with "Request limit reached" (its daily grab limit), so every DrunkenSlug pick after that showed the failure video: one The Wire, one Whiplash, two Severance and two Better Call Saul picks. The Sources stay alive (ADR 0004). Only two failures came from AltMount itself: The Wire S01 season pack ("invalid NZB: total size is zero") and a Martian release ("all files failed validation"). The Band of Brothers S01 4K pack showed the failure video on NzbDAV and played on AltMount.</li>
    <li><strong>Side effects on Brain.</strong> The evening run added 55 imports to AltMount's queue under Movies and TV from the addon (37 of them failed) and 25 under the kaijuflow category (2 failed), on top of the afternoon's 44 + 6. Removing them is the owner's call. The live containers were not changed; the test container was started from the existing image, used, and stopped.</li>
    <li><strong>Not covered.</strong> Real playback on a TV (these are byte-level reads), and altHUB on any side in the evening.</li>
  </ul>
</section>"""

FOOTER = """<footer>
  <div>Tools: <code>tools/brain/search.py</code> and <code>tools/brain/parity.py</code> in the KaijuFlow repo, run with <code>python3 -I</code> under a hard <code>timeout</code>. Evening: cold search 9.1 min, warm search 2.8 min, parity 1.0 min (16:14 to 16:28 UTC). Afternoon: search 7.5 min, parity 2 min.</div>
  <div>Raw data in <code>/home/ryan/kaijuflow-notes/brain-1338/</code>: <code>cold-search.json</code>, <code>warm-search.json</code>, <code>parity-fresh.json</code> (+ <code>.md</code> tables and logs), afternoon <code>search.json</code> and <code>parity-run3.json</code>. Test image built from main a809872; AltMount v0.4.0 in plain HTTP mode (no mount), three indexers on its addon since the evening.</div>
</footer>"""

# (open, summary, note) in page order: evening cold search, evening warm search, evening parity, afternoon search, afternoon parity.
DETAILS_1109 = [
    (True, 'All numbers: evening cold run, search side by side, per title (3 Streams tried)', 'Fresh titles, first time for every side. Each side was asked for the list, then the first 3 Streams were played (64 KiB at the start). Sides ran one after the other, with the order rotating per title. The addon and KaijuFlow share the same AltMount, so when both picked the same release the second one to play it got a warm start; the top-pick medians above are taken as recorded.'),
    (False, 'All numbers: evening warm run, same titles again (top pick only)', 'Same 10 titles a few minutes after the cold run; only the top pick was played. "Broken of 1" is the top pick itself.'),
    (False, 'All numbers: evening Backend parity on the fresh titles, per title', 'NzbDAV = Usenet Ultimate on 1337, AltMount = the KaijuFlow test container on 1338, both warm for the start (the files were imported in the cold run) and cold for the jumps (first read of those spots). "Same video bytes" compares the SHA-256 of the three reads on both sides.'),
    (False, 'All numbers: afternoon search side by side, per title (3 Streams tried, addon with one indexer)', 'Titles the Backends had played earlier that day, so KaijuFlow and Usenet Ultimate were warm and the addon (one indexer, NinjaCentral) was cold.'),
    (False, 'All numbers: afternoon Backend parity, per title (warm)', 'Interstellar is the Scrambled RAR set that AltMount used to reject; it was already Unscrambled and imported in the morning, so no Unscramble ran here.'),
]


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


def verdict(kind, text):
    return f'<td class="{kind}">{text}</td>'


def hhmm(stamp):
    return stamp[11:16] if stamp else None


# ---------- one timed run (raw.json visits) ----------
def played(v):
    return bool(v['tries'] and v['tries'][0]['plays'])


class Run:
    """The numbers of one timed run folder."""

    def __init__(self, folder):
        self.folder = folder.rstrip('/') + '/'
        self.meta = json.load(open(self.folder + 'meta.json'))
        self.name = self.meta.get('name') or os.path.basename(self.folder.rstrip('/'))
        self.visits = json.load(open(self.folder + 'raw.json'))['visits']
        self.titles = []
        for v in self.visits:
            if v['title'] not in self.titles:
                self.titles.append(v['title'])
        seen = {v['side'] for v in self.visits}
        self.sides = [(n, label) for n, label in SIDES if n in seen] + [(n, n) for n in sorted(seen) if n not in dict(SIDES)]
        self.record = None   # meta of the matching recording folder, set by the caller
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

    def steps(self, side, phase, name, where=lambda st: True):
        return [st['ms'] / 1000 for v in self.group(side, phase) for st in v['steps'] if st['step'] == name and where(st)]

    def failed_titles(self, side):
        return sorted({v['title'] for v in self.group(side) if not played(v) and not v.get('not_recorded')}, key=self.titles.index)

    def misses(self, phase):
        return sum(len(v.get('misses') or []) for v in self.visits if v['phase'] == phase)

    def titles_with_misses(self, side):
        return sorted({v['title'] for v in self.group(side, 'warm', 1) if v.get('misses')}, key=self.titles.index)

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


def run_details(run, miss_titles=None):
    """The two per-title detail blocks of a run: slots in the page, the tables themselves go to tables.json."""
    start_id, list_id = f'{run.id}-start', f'{run.id}-list'
    list_note = ''
    if miss_titles:
        list_note = f"KaijuFlow's and Usenet Ultimate's warm list times are too low for {esc(', '.join(miss_titles))} (see above)."
    html_ = f'''  <details>
    <summary>All numbers: start time per title (s)</summary>
    {slot(start_id)}
    <p class="note">"fails" = the top pick did not play. Each setup plays its own top pick, so the three setups are not always starting the same file: the addon usually picks a larger one.</p>
  </details>
  <details>
    <summary>All numbers: list time per title (s)</summary>
    {slot(list_id)}
    <p class="note">{list_note}</p>
  </details>'''
    if not list_note:
        html_ = html_.replace('\n    <p class="note"></p>', '')
    tables = {start_id: detail_table(run, 'start_s'), list_id: detail_table(run, 'list_s')}
    return html_, tables


# ---------- the hand-written baseline section of 2026-11-10 (NinjaCentral only) ----------
def baseline_nc_section(run, record):
    """The baseline-nc text. The words are the owner-reviewed v5 text; the numbers come from the run folder.
    Returns None if this run does not have the shape the words were written for (then the generic section is used)."""
    V = run
    kf_c, kf_w = V.plays('kaijuflow', 'cold'), V.plays('kaijuflow', 'warm')
    am_c, am_w = V.plays('altmount-addon', 'cold'), V.plays('altmount-addon', 'warm')
    kf_all, am_all = (kf_c[0] + kf_w[0], kf_c[1] + kf_w[1]), (am_c[0] + am_w[0], am_c[1] + am_w[1])
    kf_cs, uu_cs, am_cs = (V.start(n, 'cold') for n in ('kaijuflow', 'uu', 'altmount-addon'))
    kf_ws, am_ws = V.start('kaijuflow', 'warm'), V.start('altmount-addon', 'warm')
    kf_wl, kf_cl = V.listtime('kaijuflow', 'warm'), V.listtime('kaijuflow', 'cold')
    kf_miss, uu_miss = V.titles_with_misses('kaijuflow'), V.titles_with_misses('uu')
    warm_misses = V.misses('warm')
    clean = [t for t in V.titles if t not in kf_miss]
    health = [sum(st['ms'] for st in v['steps'] if st['step'] == 'health_batch') / 1000 for v in V.group('kaijuflow', 'cold')]
    indexer = [v['indexer_s'] for v in V.group('kaijuflow', 'cold') if v.get('indexer_s') is not None]
    imports = V.steps('kaijuflow', 'cold', 'import_wait', where=lambda st: st['ok'])
    not_rar5 = V.steps('kaijuflow', 'cold', 'unscramble', where=lambda st: st.get('result') == 'not-rar5')
    unscrambled = V.steps('kaijuflow', 'cold', 'unscramble', where=lambda st: st.get('result') == 'unscrambled')
    not_rar5_titles = sorted({v['title'] for v in V.group('kaijuflow', 'cold') for st in v['steps'] if st['step'] == 'unscramble' and st.get('result') == 'not-rar5'}, key=V.titles.index)
    spread = max(abs((V.start(n, 'cold', 1) or 0) - (V.start(n, 'cold', 2) or 0)) for n, _ in V.sides)
    addon_fail = V.failed_titles('altmount-addon')
    shape_ok = (V.failed_titles('kaijuflow') == ['Oppenheimer'] and V.misses('cold') == 0 and not_rar5 and unscrambled and imports
                and indexer and health and addon_fail and len(V.titles) == 10 and kf_wl is not None)
    if not shape_ok:
        return None
    times = ''
    if record and record.get('started') and record.get('finished'):
        times = f'Recording {hhmm(record["started"])} to {hhmm(record["finished"])} UTC, timed run {hhmm(min(v["t_start"] for v in V.visits))} to {hhmm(V.meta.get("finished"))} UTC. '
    run_name = os.path.basename(V.folder.rstrip('/'))
    details, tables = run_details(V, kf_miss)
    text = f'''<!-- {V.id} start -->
<section>
  <h2>Baseline run, 2026-11-10 (NinjaCentral only)</h2>
  <p>The first timed run on the test copies, the starting point that every later change is measured against. Three setups, 10 titles, four rounds: cold, warm, cold, warm. The indexer answers were recorded once and replayed to every setup, so all three searched the same NinjaCentral results. {times}No errors and no indexer limit. The live services were not touched.</p>

  <div class="answer">
    <h3>Where KaijuFlow stands against the targets</h3>
    <div class="big">Four of the six targets are met at the start. One is missed by a single title, and that miss is a fixable KaijuFlow problem, not a bad Source. One cannot be judged from this run.</div>
    <table class="mini">
      <thead><tr><th scope="col">Target</th><th scope="col">Baseline</th><th scope="col">Result</th></tr></thead>
      <tbody>
        <tr><th scope="row">Top pick plays on 10 of 10 titles, cold and warm</th><td>Cold {of(V.plays('kaijuflow', 'cold', 1))} and {of(V.plays('kaijuflow', 'cold', 2))}; warm {of(V.plays('kaijuflow', 'warm', 1))} and {of(V.plays('kaijuflow', 'warm', 2))}</td>{verdict('bad', 'Not met when cold')}</tr>
        <tr><th scope="row">Cold start no slower than Usenet Ultimate</th><td>KaijuFlow {s(kf_cs)} s, Usenet Ultimate {s(uu_cs)} s</td>{verdict('ok', 'Met (level)')}</tr>
        <tr><th scope="row">Warm list no slower than 4.7 s</th><td>{s(kf_wl)} s measured, but too low to trust</td>{verdict('warn', 'Cannot tell yet')}</tr>
        <tr><th scope="row">Top pick plays more often than AltMount's own addon</th><td>KaijuFlow {of(kf_all)}, addon {of(am_all)}</td>{verdict('ok', 'Met')}</tr>
        <tr><th scope="row">Warm start within 0.05 s of the addon</th><td>KaijuFlow {s(kf_ws)} s, addon {s(am_ws)} s</td>{verdict('ok', 'Met (faster)')}</tr>
        <tr><th scope="row">Cold start within 1 s of the addon</th><td>KaijuFlow {s(kf_cs)} s, addon {s(am_cs)} s</td>{verdict('ok', 'Met (faster)')}</tr>
      </tbody>
    </table>
    <p class="note">Start = seconds from pressing play on the top pick until the first bytes of video arrive. List = seconds from asking for a title until the list of Sources arrives. Every time is the median over the titles of the rounds named. Cold = the Backend is empty and has to import the file. Warm = the same titles again right after.</p>
  </div>

  <div class="answer">
    <h3>The numbers, round by round</h3>
    <div class="big">KaijuFlow with AltMount and Usenet Ultimate with NzbDAV start a cold video in about the same time. Once a file has been played, AltMount starts it about three times faster.</div>
    {round_table(V)}
    <p class="note">The two cold rounds of one setup differ by up to {s(spread, 1)} s, so a gap of under a second between setups means nothing. The addon's warm rounds count 9 titles: Breaking Bad S01E01 is left out because the recording did not hold what the addon asked for the second time.</p>
  </div>

  <div class="answer">
    <h3>What the run found</h3>
    <ul>
      <li><strong>KaijuFlow's one miss is a good Source that it gave up on.</strong> Oppenheimer's top pick played on Usenet Ultimate with NzbDAV. It was the same Source on both. Its release name ends in ".mkv". AltMount took it in without complaint and stored it as a folder with that name holding the file. The address KaijuFlow then asked for is the folder, not the file. AltMount answered "400" to it twice, and KaijuFlow showed the failure video and marked the Source dead. In the warm rounds the next Source played. This is the only thing between KaijuFlow and 10 of 10 in the cold rounds.</li>
      <li><strong>Where the cold list time goes.</strong> Of KaijuFlow's {s(kf_cl, 1)} s, about {s(med(indexer), 1)} s is waiting for the indexer and about {s(med(health), 1)} s is health checks. Usenet Ultimate's list takes the same time; it does the same work.</li>
      <li><strong>A warm list costs about 2 seconds before any checking.</strong> With the search already remembered, KaijuFlow still spent about 2 s going through a list of 300 Sources and 0.3 s on a list of 70, before any health check. Read from the log's timestamps; the cause was not looked into.</li>
      <li><strong>The Unscramble check costs time on half of the cold plays.</strong> On {len(not_rar5_titles)} of 10 top picks KaijuFlow spent {s(min(not_rar5), 1)} to {s(max(not_rar5), 1)} s finding out that the set needs no Unscramble. Interstellar, the one Scrambled RAR set, took {s(min(unscrambled), 1)} to {s(max(unscrambled), 1)} s to Unscramble. AltMount's import itself took {s(med(imports), 1)} s (median).</li>
      <li><strong>AltMount's own addon fails the same picks every round.</strong> {esc(' and '.join(addon_fail))} failed in all four rounds (HTTP 503 after AltMount's own check). It keeps no memory of a bad Source, as on 2026-11-09.</li>
    </ul>
  </div>

  <div class="answer">
    <h3>What this baseline cannot be used for yet</h3>
    <ul>
      <li><strong>Warm list times are too low.</strong> In a warm round KaijuFlow and Usenet Ultimate leave out the Sources that failed in the cold round and health-check a few replacements. The recording was made in one cold pass, so it does not hold the files for those replacements ({warm_misses} requests in the warm rounds, none in the cold rounds). Each of those checks ended at once and cost nothing. This touched {len(kf_miss)} of 10 titles on KaijuFlow and {len(uu_miss)} of 10 on Usenet Ultimate. The clean titles ({esc(', '.join(clean))}) are right. Play counts and start times are not affected.</li>
      <li><strong>Usenet Ultimate's import time is blank.</strong> NzbDAV's log does not say when an import starts or ends, so only its start time as seen from outside is known.</li>
      <li><strong>The fourth setup was not run.</strong> "KaijuFlow, one page per indexer" was planned as a fourth side. The recording tool stopped that copy and never started it again, so it recorded nothing and was left out of the timed run.</li>
      <li><strong>One indexer only.</strong> With NinjaCentral alone the lists are about half as long as on 2026-11-09, so these numbers do not compare with the ones further down this page. Later runs have to use the same recording to compare with this one.</li>
    </ul>
  </div>

{details}
  <p class="note">Run record: <code>/home/ryan/kaijuflow-notes/brain-runs/{esc(run_name)}/</code> (report, raw data, logs, settings). Tool: <code>tools/brain/brainrun.py</code>, KaijuFlow test image from main a7406e9. Each test Backend capped at 25 Usenet connections.</p>
</section>
<!-- {V.id} end -->
'''
    return text, tables


# ---------- the generic section for any other timed run: numbers only, no hand-written story ----------
def generic_section(run, record):
    V = run
    indexers = ', '.join(V.meta.get('indexers') or []) or 'indexers not named'
    head = f'Run {esc(V.name)}, {esc(V.date())} ({esc(indexers)})'
    lines = []
    for n, label in V.sides:
        c, w = V.plays(n, 'cold'), V.plays(n, 'warm')
        lines.append(f'<tr><th scope="row">{esc(label)}</th><td class="num">{s(V.start(n, "cold"))} s</td><td class="num">{s(V.start(n, "warm"))} s</td>'
                     f'<td class="num">{s(V.listtime(n, "cold"))} s</td><td class="num">{s(V.listtime(n, "warm"))} s</td><td>{of(c)}</td><td>{of(w)}</td></tr>')
    fails = []
    for n, label in V.sides:
        bad = V.failed_titles(n)
        if bad:
            fails.append(f'<li><strong>{esc(label)}:</strong> the top pick did not play for {esc(", ".join(bad))}.</li>')
    fail_block = ('<ul>' + ''.join(fails) + '</ul>') if fails else '<p>Every top pick played on every side.</p>'
    err = V.meta.get('error')
    status = f'<p class="note">The run stopped with an error: {esc(err)}</p>' if err else ''
    details, tables = run_details(V)
    text = f'''<!-- {V.id} start -->
<section>
  <h2>{head}</h2>
  <p>{len(V.titles)} titles, {len(V.sides)} setups, rounds {esc(', '.join(f'{p} {r}' for p, r in ROUNDS))}. Numbers only; no written story for this run yet.</p>
  <div class="answer">
    <h3>Summary</h3>
    <table class="mini">
      <thead><tr><th scope="col">Setup</th><th scope="col">Start, cold</th><th scope="col">Start, warm</th><th scope="col">List, cold</th><th scope="col">List, warm</th><th scope="col">Top pick plays, cold</th><th scope="col">Top pick plays, warm</th></tr></thead>
      <tbody>{''.join(lines)}</tbody>
    </table>
    <p class="note">Start = seconds from pressing play on the top pick until the first bytes of video arrive. List = seconds from asking for a title until the list of Sources arrives. Every time is the median over the titles. Cold = the Backend is empty and has to import the file. Warm = the same titles again right after.</p>
  </div>
  <div class="answer">
    <h3>The numbers, round by round</h3>
    {round_table(V)}
  </div>
  <div class="answer">
    <h3>Top picks that did not play</h3>
    {fail_block}
    {status}
  </div>
{details}
</section>
<!-- {V.id} end -->
'''
    return text, tables


# ---------- the 2026-11-09 tables, from the old result files ----------
def med2(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def fv(v):
    return '–' if v is None else f'{v}'


def agg_search(search):
    agg = {n: {'sources': [], 'list_s': [], 'fb': [], 'first': 0, 'broken': 0, 'titles': 0} for n, _ in SIDES_1109}
    for r in search:
        for n, _ in SIDES_1109:
            d, a = r[n], agg[n]
            a['sources'].append(d.get('sources', 0))
            a['list_s'].append(d.get('list_s'))
            if d.get('first_byte_s') is not None:
                a['fb'].append(d['first_byte_s'])
            if d.get('sources'):
                a['titles'] += 1
                a['first'] += 1 if d.get('first_try_plays') else 0
                a['broken'] += d.get('broken', 0)
    return agg


def search_table(search, tries_n):
    agg = agg_search(search)
    rows = []
    for r in search:
        cells = []
        for n, _ in SIDES_1109:
            d = r[n]
            first = d.get('first_try_plays')
            broken = d.get('broken', 0) if d.get('sources') else None
            bad = sorted({str(t.get('note')) for t in d.get('tries', []) if not t.get('plays')})
            why = '; '.join(bad) if bad else ''
            cells.append(f'<td class="num">{fv(d.get("sources"))}</td><td class="num">{fv(d.get("list_s"))}</td>'
                         f'<td class="{"ok" if first else "bad"}">{"yes" if first else "no"}</td>'
                         f'<td class="num">{fv(d.get("first_byte_s"))}</td>'
                         f'<td class="num {"ok" if broken == 0 else "bad"}">{fv(broken)}' + (f'<span class="why">{esc(why)}</span>' if why else '') + '</td>')
        rows.append(f'<tr><th scope="row">{esc(r["title"])}</th>' + ''.join(cells) + '</tr>')
    medrow = ''.join(f'<td class="num">{fv(med2(agg[n]["sources"]))}</td><td class="num">{fv(med2(agg[n]["list_s"]))}</td>'
                     f'<td>{agg[n]["first"]} of {agg[n]["titles"]}</td><td class="num">{fv(med2(agg[n]["fb"]))}</td><td class="num">{agg[n]["broken"]} total</td>' for n, _ in SIDES_1109)
    return f'''<div class="scroll"><table class="grid">
<thead>
<tr><th rowspan="2" scope="col">Title</th>{''.join(f'<th colspan="5" scope="colgroup" class="side">{esc(l)}</th>' for _, l in SIDES_1109)}</tr>
<tr>{''.join(f'<th scope="col">Sources shown</th><th scope="col">List shows after (s)</th><th scope="col">Top pick plays</th><th scope="col">Video starts after (s)</th><th scope="col">Broken of {tries_n}</th>' for _ in SIDES_1109)}</tr>
</thead>
<tbody>{''.join(rows)}</tbody>
<tfoot><tr><th scope="row">Median</th>{medrow}</tr></tfoot>
</table></div>'''


def parity_plays(d):
    return bool(d.get('size')) and not d.get('failure_video')


def parity_table(parity):
    ready = {}
    for side in ('nzbdav', 'altmount'):
        ok = [r[side] for r in parity if parity_plays(r[side])]
        ready[side] = {'ready': med2([x.get('ready_s') for x in ok]), 's50': med2([x.get('seek50', {}).get('s') for x in ok]),
                       's90': med2([x.get('seek90', {}).get('s') for x in ok])}
    rows = []
    for r in parity:
        n, a = r['nzbdav'], r['altmount']

        def tri(d, key):
            if not parity_plays(d):
                return None
            return d.get(key) if not key.startswith('seek') else d.get(key, {}).get('s')
        u = a.get('unscramble')
        utxt = f'{u["parts"]} parts, {u["ms"]} ms' if isinstance(u, dict) and 'ms' in u else '–'
        same = r.get('bytes_match')
        same_txt = 'yes' if same else ('different picks, not comparable' if not r.get('same_file') else 'no')
        rows.append(f'<tr><th scope="row">{esc(r["title"])}</th>'
                    f'<td class="{"ok" if parity_plays(n) else "bad"}">{"yes" if parity_plays(n) else "no"}</td><td class="{"ok" if parity_plays(a) else "bad"}">{"yes" if parity_plays(a) else "no"}</td>'
                    f'<td class="num">{fv(tri(n, "ready_s"))}</td><td class="num">{fv(tri(a, "ready_s"))}</td>'
                    f'<td class="num">{fv(tri(n, "seek50"))}</td><td class="num">{fv(tri(a, "seek50"))}</td>'
                    f'<td class="num">{fv(tri(n, "seek90"))}</td><td class="num">{fv(tri(a, "seek90"))}</td>'
                    f'<td>{utxt}</td><td class="{"ok" if same else "warn"}">{same_txt}</td></tr>')
    nz, am = ready['nzbdav'], ready['altmount']
    return f'''<div class="scroll"><table class="grid">
<thead>
<tr><th rowspan="2" scope="col">Title</th><th colspan="2" scope="colgroup" class="side">Plays</th><th colspan="2" scope="colgroup" class="side">Video starts after (s)</th><th colspan="2" scope="colgroup" class="side">Jump to the middle (s)</th><th colspan="2" scope="colgroup" class="side">Jump near the end (s)</th><th rowspan="2" scope="col">Unscramble (AltMount)</th><th rowspan="2" scope="col">Same video bytes</th></tr>
<tr>{'<th scope="col">NzbDAV</th><th scope="col">AltMount</th>' * 4}</tr>
</thead>
<tbody>{''.join(rows)}</tbody>
<tfoot><tr><th scope="row">Median</th><td></td><td></td>
<td class="num">{fv(nz["ready"])}</td><td class="num">{fv(am["ready"])}</td>
<td class="num">{fv(nz["s50"])}</td><td class="num">{fv(am["s50"])}</td>
<td class="num">{fv(nz["s90"])}</td><td class="num">{fv(am["s90"])}</td><td></td><td></td></tr></tfoot>
</table></div>'''


def tables_1109(notes):
    """The five 2026-11-09 per-title tables as (id, html), in the page order of DETAILS_1109."""
    def load(name):
        return json.load(open(os.path.join(notes, name)))
    return [('evening-cold', search_table(load('cold-search.json'), 3)),
            ('evening-warm', search_table(load('warm-search.json'), 1)),
            ('evening-parity', parity_table(load('parity-fresh.json'))),
            ('afternoon-search', search_table(load('search.json'), 3)),
            ('afternoon-parity', parity_table(load('parity-run3.json')))]


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
    """Split the given folders into timed runs (raw.json) and recordings (meta mode 'record'); newest timed run first."""
    runs, records = [], {}
    for f in folders:
        meta = json.load(open(os.path.join(f, 'meta.json')))
        if os.path.exists(os.path.join(f, 'raw.json')):
            runs.append(Run(f))
        elif meta.get('mode') == 'record':
            records[meta.get('name')] = meta
        else:
            raise SystemExit(f'{f}: neither a timed run (raw.json) nor a recording (meta.json with mode "record")')
    if not runs:
        raise SystemExit('Give at least one timed run folder (one that holds raw.json).')
    runs.sort(key=lambda r: os.path.basename(r.folder.rstrip('/')), reverse=True)
    return runs, records


def build(folders, notes=DEFAULT_NOTES, with_1109=True):
    """Returns (index_html, tables) as strings and a dict."""
    runs, records = find_runs(folders)
    tables = {}
    run_sections = []
    for run in runs:
        record = records.get(run.name)
        made = baseline_nc_section(run, record) if run.name == 'baseline-nc' else None
        text, t = made or generic_section(run, record)
        run_sections.append(text)
        tables.update(t)
    known = [r.name for r in runs] == ['baseline-nc'] and with_1109
    parts = [HEAD, '<main>\n<header>\n',
             f'  <div class="eyebrow">{EYEBROW if known else "Brain · timed runs" + (" · 2026-11-09 live runs" if with_1109 else "")}</div>\n',
             '  <h1>KaijuFlow Speed Check</h1>\n',
             f'  <p class="lede">{LEDE if known else GENERIC_LEDE}</p>\n</header>\n\n', WHO, '\n\n', '\n'.join(run_sections)]
    if with_1109:
        parts += ['\n', ANSWERS_1109, '\n\n', WORDS, '\n\n']
        for (is_open, summary, note), (tid, table_html) in zip(DETAILS_1109, tables_1109(notes)):
            tables[tid] = table_html
            parts.append(f'<section>\n  <details{" open" if is_open else ""}>\n    <summary>{summary}</summary>\n    {slot(tid)}\n    <p class="note">{note}</p>\n  </details>\n</section>\n\n')
        parts += [WORTH_KNOWING, '\n\n']
    else:
        parts += ['\n', WORDS, '\n\n']
    parts += [FOOTER, '\n</main>\n', SCRIPT]
    return ''.join(parts), tables


def write(folders, out=DEFAULT_OUT, notes=DEFAULT_NOTES, with_1109=True):
    index, tables = build(folders, notes, with_1109)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'index.html'), 'w') as fh:
        fh.write(index)
    with open(os.path.join(out, 'tables.json'), 'w') as fh:
        json.dump(tables, fh, ensure_ascii=False, indent=1)
    return index, tables


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the speed-check page (index.html + tables.json) from run folders. Does not publish.')
    ap.add_argument('runs', nargs='+', help='run folders, e.g. /home/ryan/kaijuflow-notes/brain-runs/<run>/')
    ap.add_argument('--out', default=DEFAULT_OUT, help='output folder (default %(default)s)')
    ap.add_argument('--notes', default=DEFAULT_NOTES, help='folder with the 2026-11-09 result files (default %(default)s)')
    ap.add_argument('--no-1109', action='store_true', help='leave the 2026-11-09 part out')
    a = ap.parse_args(argv)
    index, tables = write(a.runs, a.out, a.notes, not a.no_1109)
    print(f'wrote {a.out}index.html ({len(index)} bytes) and tables.json ({len(tables)} tables)' if a.out.endswith('/') else
          f'wrote {a.out}/index.html ({len(index)} bytes) and tables.json ({len(tables)} tables)')


if __name__ == '__main__':
    main()
