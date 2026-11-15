"""The Speed Check page in the owner's "Starting line" design (#132): every time is drawn on a ruler that begins when play
is pressed, each setup is a lane that ends when its video starts, limits are upright lines across the lanes, and KaijuFlow
is the one yellow lane.

Pure rendering: every function takes plain numbers and words and returns HTML; nothing here reads a run folder or judges
a target. build_page.py makes the page model from run folders (numbers through brainreport, verdicts from
brainreport.target_results) and calls page(). The one-page report (#133) is meant to reuse the same pieces: scale/pct,
ruler, status, target_rows and CSS.

The mock-up is ~/kaijuflow-notes/designs/speed-check-2026-11-15/project/StartLine.dc.html; its wording rules are in
CONTENT.md beside it. Fixed over the mock-up: a limit line is drawn over the bars (it used to hide behind KaijuFlow's
bar), the grey lanes are at least 3:1 against the paper, and a bar's time sits just past its end, where a line crossing
the bar cannot run through it.
"""
import html
import math
import re

KAIJUFLOW = 'kaijuflow'
# The setups in the page's words (CONTENT.md, GLOSSARY.md); the IDs are the run folders' side names.
SETUP_NAMES = {'kaijuflow': 'KaijuFlow', 'uu': 'Usenet Ultimate', 'altmount-addon': 'AltMount direct',
               'kaijuflow-1page': 'KaijuFlow, one page'}
MAX_STEPS, MIN_STEPS = 8, 4  # a ruler has at most 8 equal steps, and at least 4 where its end allows
STEPS = (1, 2, 2.5, 5)  # times a power of ten: the step sizes a ruler may use
NUMBER_WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']


def esc(s):
    return html.escape(str(s))


def secs(x):
    """'4.82 s', or a dash when there is no figure."""
    return '–' if x is None else f'{x:.2f} s'


def plays_text(p):
    return '–' if p is None or not p[1] else f'{p[0]} of {p[1]}'


def num(x):
    """A tick label: 0.5, 2, 2.5, never 2.0."""
    return f'{x:g}'


def counted(n, word):
    """'One target', 'Two targets': for headings, which start with the count."""
    head = NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else str(n)
    return f'{head} {word}' + ('' if n == 1 else 's')


# ---------- where the marks go ----------
def scale(longest):
    """(end, ticks) of a ruler whose longest mark is `longest`: it ends on the first round number at or past it, in equal
    steps of 1, 2, 2.5 or 5 times a power of ten, at most MAX_STEPS of them and, where the same end allows, at least
    MIN_STEPS, the fewest that do."""
    if not longest or longest <= 0:
        return 1, [0, 1]
    power = 10 ** math.floor(math.log10(longest / MAX_STEPS))
    found = []
    for mult in [m * power * p for p in (1, 10) for m in STEPS]:
        n = math.ceil(round(longest / mult, 9))
        if n <= MAX_STEPS:
            found.append((round(n * mult, 9), n, mult))
    end = min(e for e, _, _ in found)
    same = [(n, mult) for e, n, mult in found if e == end]
    n, mult = min((x for x in same if x[0] >= MIN_STEPS), default=max(same))
    return _tidy(end), [_tidy(round(i * mult, 9)) for i in range(n + 1)]


def _tidy(x):
    return int(x) if float(x).is_integer() else x


def pct(value, end):
    """Where a value sits on a ruler that ends at `end`, in percent of its length."""
    return _tidy(round(value / end * 100, 2))


# ---------- small marks ----------
ICON_MET = ('<svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2">'
            '<circle cx="10" cy="10" r="8"/><path d="m6.2 10.3 2.6 2.6 5-5.6"/></svg>')
ICON_NOT_MET = ('<svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" '
                'stroke-linejoin="round"><path d="M10 2.5 18.5 17h-17z"/><path d="M10 8v4.5M10 14.4v.4"/></svg>')
ICON_NOT_MEASURED = ('<svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2">'
                     '<rect x="2.5" y="2.5" width="15" height="15"/><path d="M6.5 10h7"/></svg>')
ICON_DOWN = ('<svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
             'stroke-width="2"><path d="M8 2v11M3.5 8.5 8 13l4.5-4.5"/></svg>')
ICON_UP = ('<svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
           'stroke-width="2"><path d="M8 14V3M3.5 7.5 8 3l4.5 4.5"/></svg>')


def status(result, words=None):
    """A target's result as a shape and a word, never colour alone: 'met', 'not met' or 'not measured'."""
    icon, cls = {'met': (ICON_MET, ''), 'not met': (ICON_NOT_MET, ' sl-st-no'),
                 'not measured': (ICON_NOT_MEASURED, ' sl-st-none')}[result]
    return f'<span class="sl-st{cls}">{icon}{esc(words or result.capitalize())}</span>'


# ---------- the ruler ----------
def ruler(lanes, limits=(), end=None, hero=False, play_label=False):
    """A time ruler. lanes: [(name, seconds or None, is KaijuFlow, note)] in the order drawn (fastest first); a lane
    without a time is drawn empty with its note. limits: [(seconds, label, status html)], each an upright line from its own
    label row down through every lane. end: the ruler's end (default: from the longest mark)."""
    marks = [v for _, v, _, _ in lanes if v is not None] + [at for at, _, _ in limits]
    end, ticks = scale(max(marks, default=0)) if end is None else (end, scale(end)[1])
    # A label ends at its line when the line is right of the middle, else starts there. So that no line runs down
    # through another's label, those ending at their line come first, rightmost on top, then those starting there,
    # leftmost on top.
    limits = sorted(limits, key=lambda lim: (pct(lim[0], end) < 50, -lim[0] if pct(lim[0], end) >= 50 else lim[0]))
    k = len(limits)
    rows = []
    for i, (at, label, st) in enumerate(limits, 1):
        x = pct(at, end)
        side = 'l' if x >= 50 else 'r'
        where = f'width:{x}%' if side == 'l' else f'margin-left:{x}%'
        head, colon, rest = label.partition(': ')
        words = f'<span class="sl-fl">{esc(head + colon.strip())}</span>' + (f' <span>{esc(rest)}</span>' if rest else '')
        tail = f' &nbsp; {st}' if st else ''
        rows.append(f'<p class="sl-flag sl-flag-{side}" style="grid-row:{i};{where}">{words}{tail}</p>')
    for i, (at, _, _) in enumerate(limits, 1):
        rows.append(f'<i class="sl-lim" style="grid-row:{i} / {k + 2};left:{pct(at, end)}%"></i>')
    rows.append(f'<i class="sl-start" style="grid-row:{k + 1}"></i>')
    items = []
    for name, value, kf, note in lanes:
        if value is None:
            track = f'<span class="sl-track"><span class="sl-none">{esc(note)}</span></span>'
        else:
            x = pct(value, end)
            extra = f'<small>{esc(note)}</small>' if note else ''
            track = (f'<span class="sl-track"><span class="sl-bar" style="width:{x}%"></span>'
                     f'<span class="sl-val" style="left:{x}%"><b>{secs(value)}</b>{extra}</span></span>')
        items.append(f'<li class="sl-lane{" sl-kf" if kf else ""}"><span class="sl-name">{esc(name)}</span>{track}</li>')
    rows.append(f'<ol class="sl-lanes" style="grid-row:{k + 1}">{"".join(items)}</ol>')
    labels = []
    for i, t in enumerate(ticks):
        text = f'{num(t)} s' if i in (0, len(ticks) - 1) else num(t)
        labels.append(f'<span class="sl-tick{" sl-t0" if i == 0 else ""}" style="left:{pct(t, end)}%">{text}</span>')
    play = '<span class="sl-play">Play pressed</span>' if play_label else ''
    rows.append(f'<div class="sl-axis" style="grid-row:{k + 2}" aria-hidden="true">{play}{"".join(labels)}</div>')
    return f'<div class="sl-plot{" sl-hero" if hero else ""}">{"".join(rows)}</div>'


def ruler_text(lanes, limits=()):
    """The ruler's values in words, for a screen reader (every chart has a text twin)."""
    parts = [f'{name} {secs(v) if v is not None else note}' for name, v, _, note in lanes]
    lims = [label for _, label, _ in limits]
    return '; '.join(parts) + ('. ' + '; '.join(lims) if lims else '') + '.'


def figure(caption_html, lanes, limits=(), **kw):
    """A ruler under its caption. A screen reader gets the caption and every value in words instead of the drawing."""
    words = html.unescape(re.sub(r'<[^>]+>', ' ', caption_html)).split()
    return (f'<figure class="sl-fig" role="img" aria-label="{esc(" ".join(words))} {esc(ruler_text(lanes, limits))}">'
            f'<figcaption class="sl-cap">{caption_html}</figcaption>{ruler(lanes, limits, **kw)}</figure>')


def mini(value, limit):
    """The small ruler of a time target: KaijuFlow's bar against the limit's line, on a scale that holds both."""
    end, _ = scale(max(value, limit))
    return (f'<div class="sl-mini" aria-hidden="true"><div class="sl-mtrack"><span class="sl-mbar" style="width:{pct(value, end)}%">'
            f'</span><i class="sl-mlim" style="left:{pct(limit, end)}%"></i></div>'
            f'<div class="sl-mscale"><span>0 s</span><span>{num(end)} s</span></div></div>')


# ---------- the targets ----------
def target_figures(t):
    """(KaijuFlow, limit, margin words) of one target of the model, as the page prints them."""
    v, lim, result = t['value'], t['limit'], t['result']
    if result == 'not measured':
        return '–', '–', 'No figure in this run'
    if isinstance(v, tuple):  # plays: (played, counted)
        if t['measure'] == 'plays per round':
            short = lim[0] - v[0]
            words = 'Every top pick played' if result == 'met' else f'{short} top pick{"s" if short != 1 else ""} did not play'
        elif v[0] == v[1] and lim[0] == lim[1]:
            words = 'Both played every top pick'
        else:
            mine, theirs = v[0] / v[1], lim[0] / lim[1]
            words = ('More often' if mine > theirs else 'As often, and not every time' if mine == theirs else 'Less often')
        return plays_text(v), plays_text(lim), words
    gap = round(lim - v, 2)
    words = f'{gap:.2f} s to spare' if gap > 0 else 'Right at the limit' if gap == 0 else f'{-gap:.2f} s over'
    return secs(v), secs(lim), words


def noise_words(t):
    n = t.get('noise')
    if not n:
        return ''
    a, b = n['rounds']
    return (f"Inside the noise: KaijuFlow's two {n['phase']} rounds differ by {abs(a - b):.2f} s "
            f"({a:.2f} and {b:.2f} s), more than that.")


def target_rows(targets):
    rows = []
    for t in targets:
        mine, lim, words = target_figures(t)
        margin = f'<b>{esc(words)}</b>' if t['result'] == 'not met' else esc(words)
        noise = noise_words(t)
        if noise:
            margin += f'<small>{esc(noise)}</small>'
        draw = (mini(t['value'], t['limit']) if t['result'] != 'not measured' and not isinstance(t['value'], tuple)
                else '<span class="sl-empty"></span>')
        rows.append(f'<li class="sl-trow"><span class="sl-ts">{status(t["result"])}</span><span class="sl-tt">{esc(t["text"])}</span>'
                    f'<span class="sl-num sl-r"><span class="sl-lab">KaijuFlow</span>{mine}</span>'
                    f'<span class="sl-num sl-r"><span class="sl-lab">Limit</span>{lim}</span><span class="sl-tm">{margin}</span>{draw}</li>')
    return ''.join(rows)


def limit_label(t):
    """The words on a target's line on a ruler: 'Limit 4.70 s: AltMount direct + 1 s'."""
    head = f'Limit {secs(t["limit"])}'
    if not t.get('against'):
        return head
    plus = f' + {num(t["margin"])} s' if t['margin'] else ''
    return f'{head}: {SETUP_NAMES.get(t["against"], t["against"])}{plus}'


def limits_on(targets, measure, with_status=False):
    """The lines of every measured time target on one measure ('cold start', ...), for a ruler of that measure."""
    out = []
    for t in targets:
        if t['measure'] == measure and t['result'] != 'not measured':
            st = status(t['result'], f'{t["result"].capitalize()}, {target_figures(t)[2].lower()}') if with_status else ''
            out.append((t['limit'], limit_label(t), st))
    return out


# ---------- the page ----------
CSS = """/* Starting line (#132). Colours are tokens; the lanes are at least 3:1 against the paper in both themes. */
:root { color-scheme: light; }
body { margin: 0; background: #F1F3F5; }
.sl {
  --paper: #F1F3F5; --ink: #15191E; --slate: #4A525C; --lane: #7D8691; --rule: #C5CAD1; --yellow: #FFD400; --on-yellow: #15191E;
  --edge: #15191E; --nw: 184px; --gut: 5rem;
  background: var(--paper); color: var(--ink); font-family: Archivo, system-ui, sans-serif; font-size: 18px; line-height: 1.5;
  -webkit-font-smoothing: antialiased; min-height: 100vh }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .sl {
  --paper: #131619; --ink: #E6E9EC; --slate: #A3ACB6; --lane: #6B7480; --rule: #353C44; --yellow: #FFD400; --on-yellow: #15191E;
  --edge: #15191E } :root:not([data-theme="light"]) { color-scheme: dark; } :root:not([data-theme="light"]) body { background: #131619; } }
:root[data-theme="dark"] .sl {
  --paper: #131619; --ink: #E6E9EC; --slate: #A3ACB6; --lane: #6B7480; --rule: #353C44; --yellow: #FFD400; --on-yellow: #15191E;
  --edge: #15191E }
:root[data-theme="dark"] { color-scheme: dark; }
:root[data-theme="dark"] body { background: #131619; }
.sl * { box-sizing: border-box }
.sl .sl-wrap { max-width: 1104px; margin: 0 auto; padding: 0 max(32px, env(safe-area-inset-right, 0px)) 96px max(32px, env(safe-area-inset-left, 0px)) }
.sl p { margin: 0 }
.sl ol, .sl ul, .sl dl, .sl dd, .sl figure { margin: 0; padding: 0; list-style: none }
.sl svg { display: inline-block; vertical-align: -0.18em; flex: none }
.sl h1, .sl h2, .sl h3 { font-stretch: 84%; font-weight: 600; margin: 0; text-wrap: balance }
.sl h1 { font-size: 76px; line-height: 1; letter-spacing: -0.02em }
.sl h2 { font-size: 34px; line-height: 1.15; letter-spacing: -0.01em; margin-bottom: 16px }
.sl h3 { font-size: 22px; line-height: 1.25; margin-bottom: 8px }
.sl .sl-num { font-stretch: 84%; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap }
.sl .sl-quiet { color: var(--slate) }
.sl .sl-small { font-size: 16px; line-height: 1.4 }
.sl .sl-text { max-width: 660px }
.sl .sl-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 32px; padding: 24px 0 16px; border-bottom: 1px solid var(--rule) }
.sl .sl-brand { font-stretch: 84%; font-weight: 650; font-size: 22px; line-height: 1.2 }
.sl .sl-meta { font-size: 16px; line-height: 1.4; color: var(--slate); flex: 1 1 320px }
.sl .sl-meta b { color: var(--ink); font-weight: 600 }
.sl .sl-sec { padding-top: 96px }
.sl .sl-sec > .sl-sub { margin-bottom: 32px }
.sl .sl-verdict { padding-top: 48px }
.sl .sl-vtop { display: grid; grid-template-columns: minmax(0, 1fr) 400px; gap: 64px; align-items: start; margin-bottom: 48px }
.sl .sl-lead { font-size: 21px; line-height: 1.45; margin-top: 20px; max-width: 600px }
.sl .sl-lead b { font-weight: 600 }
.sl .sl-heads { display: grid; grid-template-columns: 1fr 1fr; column-gap: 32px }
.sl .sl-heads li { border-top: 1px solid var(--ink); padding: 12px 0 20px }
.sl .sl-heads .sl-k { font-size: 16px; line-height: 1.3; color: var(--slate) }
.sl .sl-heads .sl-v { display: block; font-size: 34px; line-height: 1.15; letter-spacing: -0.01em; font-stretch: 84%; font-weight: 600 }
.sl .sl-heads .sl-c { font-size: 16px; line-height: 1.3; font-weight: 500 }
.sl .sl-headnote { font-size: 16px; line-height: 1.4; color: var(--slate); grid-column: 1 / -1; border-top: 1px solid var(--rule); padding-top: 8px }
/* the ruler: a grid of label rows, the lanes and the axis; column 2 is the scale, column 3 room for the last time */
.sl .sl-cap { font-size: 17px; line-height: 1.4; margin-bottom: 16px; max-width: 700px }
.sl .sl-cap b { font-weight: 650; font-stretch: 84%; font-size: 20px }
.sl .sl-plot { display: grid; grid-template-columns: var(--nw) minmax(0, 1fr) var(--gut); isolation: isolate }
.sl .sl-flag { grid-column: 2; font-size: 15px; line-height: 1.35; padding: 2px 10px 6px; min-width: 0 }
.sl .sl-flag span { display: inline-block; white-space: nowrap }
.sl .sl-flag .sl-fl { font-weight: 600 }
.sl .sl-flag-l { text-align: right; padding-left: 0; justify-self: start }
.sl .sl-flag-r { padding-right: 0 }
.sl .sl-lim { grid-column: 2; justify-self: start; position: relative; width: 2px; margin-left: -1px; background: var(--ink); z-index: 2 }
.sl .sl-start { grid-column: 2; justify-self: start; width: 3px; margin-left: -3px; background: var(--ink); position: relative; z-index: 2 }
.sl .sl-lanes { grid-column: 1 / -1; padding: 6px 0 }
.sl .sl-lane { display: grid; grid-template-columns: var(--nw) minmax(0, 1fr) var(--gut); align-items: center; padding: 6px 0 }
.sl .sl-name { font-size: 16px; line-height: 1.25; padding-right: 12px; white-space: nowrap }
.sl .sl-kf .sl-name { font-weight: 700 }
.sl .sl-track { display: block; height: 26px; position: relative }
.sl .sl-bar { display: block; height: 100%; background: var(--lane); position: relative; z-index: 1 }
.sl .sl-kf .sl-bar { background: var(--yellow); box-shadow: inset 0 0 0 1.5px var(--edge) }
.sl .sl-val { position: absolute; top: 50%; transform: translateY(-50%); margin-left: 4px; padding: 0 4px; background: var(--paper);
  white-space: nowrap; line-height: 1.1; z-index: 3 }
.sl .sl-val b { font-size: 16px; font-stretch: 84%; font-weight: 600; font-variant-numeric: tabular-nums }
.sl .sl-val small { font-size: 14px; color: var(--slate); margin-left: 6px }
.sl .sl-kf .sl-val b { font-weight: 700 }
.sl .sl-none { position: absolute; top: 50%; transform: translateY(-50%); left: 8px; font-size: 15px; color: var(--slate); white-space: nowrap }
.sl .sl-axis { grid-column: 2; position: relative; height: 36px; border-top: 1px solid var(--ink); font-size: 15px; line-height: 1; color: var(--slate); font-variant-numeric: tabular-nums }
.sl .sl-tick { position: absolute; top: 14px; transform: translateX(-50%); white-space: nowrap }
.sl .sl-tick::before { content: ""; position: absolute; top: -14px; left: 50%; width: 1px; height: 8px; background: var(--ink) }
.sl .sl-tick.sl-t0 { transform: none }
.sl .sl-tick.sl-t0::before { left: 0 }
.sl .sl-play { position: absolute; top: 14px; right: 100%; margin-right: 14px; color: var(--ink); font-weight: 600; white-space: nowrap }
.sl .sl-hero .sl-lane { padding: 8px 0 }
.sl .sl-hero .sl-name { font-size: 18px }
.sl .sl-hero .sl-track { height: 38px }
.sl .sl-hero .sl-val b { font-size: 21px }
.sl .sl-hero .sl-flag { font-size: 16px; padding-bottom: 8px }
.sl .sl-hero .sl-axis { height: 40px; font-size: 16px }
.sl .sl-st { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; white-space: nowrap }
.sl .sl-st svg { width: 20px; height: 20px }
.sl .sl-st-no { background: var(--ink); color: var(--paper); padding: 3px 9px 3px 7px }
.sl .sl-st-none { color: var(--slate) }
.sl .sl-targets { border-top: 1px solid var(--ink) }
.sl .sl-trow { display: grid; grid-template-columns: 128px minmax(0, 1fr) 96px 96px 196px 200px; column-gap: 24px; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--rule) }
.sl .sl-thead { font-size: 16px; color: var(--slate); padding: 8px 0; border-bottom: 1px solid var(--ink) }
.sl .sl-thead .sl-r, .sl .sl-trow .sl-r { text-align: right }
.sl .sl-trow .sl-lab { display: none }
.sl .sl-trow .sl-tt { line-height: 1.35 }
.sl .sl-tm small { display: block; font-size: 14px; line-height: 1.35; color: var(--slate); margin-top: 4px }
.sl .sl-mtrack { position: relative; height: 32px; box-shadow: -3px 0 0 var(--ink) }
.sl .sl-mlim { position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px; background: var(--ink); z-index: 2 }
.sl .sl-mbar { position: absolute; top: 7px; bottom: 7px; left: 0; background: var(--yellow); box-shadow: inset 0 0 0 1.5px var(--edge); z-index: 1 }
.sl .sl-mscale { display: flex; justify-content: space-between; font-size: 14px; line-height: 1; color: var(--slate); border-top: 1px solid var(--ink); padding-top: 5px; font-variant-numeric: tabular-nums }
.sl .sl-tnote { font-size: 16px; color: var(--slate); margin-top: 12px; max-width: 760px }
.sl .sl-changes { display: grid; gap: 4px; margin-bottom: 24px; max-width: 760px }
.sl .sl-changes li { padding-left: 16px; text-indent: -16px }
.sl .sl-changes li::before { content: "– "; color: var(--slate) }
.sl .sl-pairs { border-top: 1px solid var(--ink) }
.sl .sl-pair { display: grid; grid-template-columns: 168px minmax(0, 1fr) 216px; column-gap: 24px; align-items: center; padding: 14px 0; border-bottom: 1px solid var(--rule) }
.sl .sl-pair h3 { margin: 0 }
.sl .sl-pair .sl-plot { --nw: 84px }
.sl .sl-pair .sl-lane { padding: 3px 0 }
.sl .sl-pair .sl-name { font-size: 15px; color: var(--slate) }
.sl .sl-pair .sl-axis { display: none }
.sl .sl-plain { font-size: 16px; font-stretch: 84%; font-weight: 600; font-variant-numeric: tabular-nums }
.sl .sl-chg { font-weight: 600 }
.sl .sl-chg small { font-size: 16px; font-weight: 400; color: var(--slate) }
.sl .sl-four { display: grid; grid-template-columns: 1fr 1fr; gap: 56px 48px; --nw: 152px }
.sl .sl-four .sl-cap { margin-bottom: 8px }
.sl .sl-nolim { font-size: 15px; line-height: 1.35; color: var(--slate); padding: 2px 0 6px }
.sl .sl-plays { margin-top: 56px; border-top: 1px solid var(--ink); padding-top: 16px; display: grid; grid-template-columns: 188px repeat(4, minmax(0, 1fr)); column-gap: 24px; align-items: baseline }
.sl .sl-plays h3 { margin: 0 }
.sl .sl-plays .sl-pv { display: block; font-size: 22px; line-height: 1.2 }
.sl .sl-plays .sl-pn { font-size: 16px; line-height: 1.3; color: var(--slate) }
.sl .sl-plays .sl-pk .sl-pn { color: var(--ink); font-weight: 700 }
.sl .sl-scroll { overflow-x: auto }
.sl table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums }
.sl caption { text-align: left; font-size: 16px; color: var(--slate); padding-bottom: 8px; caption-side: top }
.sl th, .sl td { text-align: left; padding: 10px 16px 10px 0; vertical-align: top; border-bottom: 1px solid var(--rule); font-weight: 400; line-height: 1.35 }
.sl thead th { font-size: 16px; color: var(--slate); border-bottom: 1px solid var(--ink); vertical-align: bottom }
.sl tbody th { font-weight: 500 }
.sl th.sl-r, .sl td.sl-r { text-align: right; padding-right: 0; padding-left: 16px }
.sl td.sl-r { font-stretch: 84%; font-weight: 500; white-space: nowrap }
.sl td small, .sl th small { display: block; font-size: 15px; color: var(--slate); font-weight: 400; font-stretch: 100% }
.sl thead th.sl-kfh span { display: inline-block; background: var(--yellow); color: var(--on-yellow); font-weight: 700; padding: 2px 8px; margin-right: -8px }
.sl td.sl-kfc { font-weight: 700 }
.sl tr.sl-new th, .sl tr.sl-new td { font-weight: 650 }
.sl tr.sl-new small { font-weight: 400 }
.sl .sl-titles { --nw: 216px; margin-bottom: 48px }
.sl .sl-finds { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 32px 48px; margin-top: 8px }
.sl .sl-finds li { border-top: 1px solid var(--ink); padding-top: 16px }
.sl .sl-next p { max-width: 660px }
.sl .sl-words { display: grid; grid-template-columns: 1fr 1fr; gap: 0 64px; margin-top: 8px }
.sl .sl-words div { display: grid; grid-template-columns: 96px minmax(0, 1fr); column-gap: 16px; padding: 12px 0; border-top: 1px solid var(--rule) }
.sl .sl-words dt { font-weight: 650; font-stretch: 84%; font-size: 19px }
@media (max-width: 860px) {
  .sl { --nw: 0px; --gut: 4.5rem; font-size: 17px }
  .sl .sl-wrap { padding: 0 max(16px, env(safe-area-inset-right, 0px)) 64px max(16px, env(safe-area-inset-left, 0px)) }
  .sl h1 { font-size: 50px }
  .sl h2 { font-size: 28px }
  .sl h3 { font-size: 20px }
  .sl .sl-sec { padding-top: 64px }
  .sl .sl-verdict { padding-top: 32px }
  .sl .sl-vtop { grid-template-columns: minmax(0, 1fr); gap: 32px; margin-bottom: 40px }
  .sl .sl-lead { font-size: 19px }
  .sl .sl-heads { column-gap: 16px }
  .sl .sl-heads .sl-v { font-size: 30px }
  .sl .sl-lane, .sl .sl-hero .sl-lane { grid-template-columns: minmax(0, 1fr) var(--gut); padding: 5px 0 }
  .sl .sl-name, .sl .sl-hero .sl-name { grid-column: 1 / -1; justify-self: start; font-size: 16px; padding: 0 4px 3px; margin-left: 4px;
    background: var(--paper); position: relative; z-index: 3 }
  .sl .sl-plot { grid-template-columns: 0 minmax(0, 1fr) var(--gut); margin-left: 3px }
  .sl .sl-hero .sl-track { height: 32px }
  .sl .sl-hero .sl-val b { font-size: 18px }
  .sl .sl-hero .sl-flag { font-size: 15px }
  .sl .sl-hero .sl-axis { height: 60px }
  .sl .sl-play { right: auto; left: 0; top: 40px; margin: 0 }
  .sl .sl-thead { display: none }
  .sl .sl-trow { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px 16px; padding: 16px 0 }
  .sl .sl-trow .sl-ts { grid-column: 1; grid-row: 1 }
  .sl .sl-trow .sl-tm { grid-column: 2; grid-row: 1; text-align: right; font-size: 16px }
  .sl .sl-trow .sl-tt { grid-column: 1 / -1 }
  .sl .sl-trow .sl-r { text-align: left }
  .sl .sl-trow .sl-lab { display: inline; font-size: 16px; color: var(--slate); margin-right: 8px; font-weight: 400 }
  .sl .sl-trow .sl-mini { grid-column: 1 / -1; margin-left: 3px }
  .sl .sl-trow .sl-empty { display: none }
  .sl .sl-pair { grid-template-columns: minmax(0, 1fr) auto; gap: 8px 16px }
  .sl .sl-pair .sl-plot, .sl .sl-pair .sl-pl { grid-column: 1 / -1; grid-row: 2 }
  .sl .sl-pair .sl-lane, .sl .sl-pair .sl-plot { grid-template-columns: 76px minmax(0, 1fr) var(--gut) }
  .sl .sl-pair .sl-plot { margin-left: 0 }
  .sl .sl-pair .sl-name { grid-column: auto; padding: 0 8px 0 0 }
  .sl .sl-chg { text-align: right; font-size: 16px }
  .sl .sl-four { grid-template-columns: minmax(0, 1fr); gap: 48px }
  .sl .sl-plays { grid-template-columns: 1fr 1fr; gap: 16px }
  .sl .sl-plays h3 { grid-column: 1 / -1 }
  .sl .sl-finds { grid-template-columns: minmax(0, 1fr) }
  .sl .sl-words { grid-template-columns: minmax(0, 1fr) }
  .sl .sl-words div { grid-template-columns: 80px minmax(0, 1fr) }
  .sl table { min-width: 560px }
  .sl caption span { display: block; position: sticky; left: 0; max-width: calc(100vw - 32px) }
}
"""

HEAD = ('<title>KaijuFlow Speed Check</title>\n'
        '<meta name="claude:viewport-fit-sides" content="cover">\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,100..900&amp;display=swap">\n')

WORDS = [('Setup', 'One way of searching and playing that the test times, such as KaijuFlow with AltMount.'),
         ('Top pick', 'The first Source in the list, the one a viewer presses play on.'),
         ('Start', 'Seconds from pressing play on the top pick until the first bytes of video arrive.'),
         ('List', 'Seconds from asking for a title until the list of Sources arrives.'),
         ('Cold', 'The first time a title is played, when the file still has to be fetched and prepared.'),
         ('Warm', 'The same title again right after.'),
         ('Median', 'The middle value over the {titles} titles, so one slow title cannot drag the number.'),
         ('Round', 'One pass over all {titles} titles. A run has four: cold, warm, cold, warm.'),
         ('Inside the noise', "KaijuFlow's own two rounds differ by more than a target is met or missed by, so the same run "
                              'done again could turn the result around.')]


def change_words(before, now, plays=False):
    """'0.59 s faster (11%)', '0.20 s slower (4%)', 'No change'; for plays (played, counted): '1 more', '2 fewer'."""
    if before is None or now is None:
        return ''
    if plays:
        d = now[0] - before[0]
        return 'No change' if d == 0 else f'{abs(d)} {"more" if d > 0 else "fewer"}'
    d = round(before - now, 2)
    if d == 0:
        return 'No change'
    share = f' ({round(abs(d) / before * 100)}%)' if before else ''
    return f'{abs(d):.2f} s {"faster" if d > 0 else "slower"}{share}'


def _arrow(words):
    if words.endswith('more') or 'slower' in words:
        return ICON_UP
    return ICON_DOWN if words and words != 'No change' else ''


def header(m):
    prev = m['prev']
    against = (f' Compared with the {esc(prev["label"])} of {esc(prev["date_long"])}.' if prev
               else ' No earlier run on this page to compare with.')
    return (f'<header class="sl-head"><span class="sl-brand">KaijuFlow Speed Check</span>'
            f'<span class="sl-meta"><b>{esc(m["run"]["label"].capitalize())}, {esc(m["run"]["date_long"])}.</b>{against}</span></header>')


HEADLINES = [('Cold start', 'cold_start'), ('Warm start', 'warm_start'), ('Warm list', 'warm_list'), ('Top pick plays', 'plays')]


def headline_numbers(m):
    kf, before = m['kaijuflow'], m['prev_kaijuflow']
    items = []
    for label, key in HEADLINES:
        is_plays = key == 'plays'
        value = plays_text(kf[key]) if is_plays else secs(kf[key])
        words = change_words(before[key], kf[key], is_plays) if before else ''
        change = f'<span class="sl-c">{_arrow(words)} {esc(words)}</span>' if words else ''
        items.append(f'<li><span class="sl-k">{label}</span><span class="sl-v">{value}</span>{change}</li>')
    note = 'KaijuFlow in this run' + (', with the change since the run it is compared with.' if before else '.')
    return f'<ul class="sl-heads">{"".join(items)}<li class="sl-headnote">{note}</li></ul>'


def lead(m):
    open_ = [t for t in m['targets'] if t['result'] != 'met']
    parts = []
    if m['prev'] and m['prev_met'] is not None:
        d = m['met'] - m['prev_met']
        parts.append(f'<b>{abs(d)} {"more" if d > 0 else "fewer"} than the {esc(m["prev"]["label"])}.</b>' if d
                     else f'<b>As many as the {esc(m["prev"]["label"])}.</b>')
    if not open_:
        parts.append('Every target is met.')
    else:
        misses = [t for t in open_ if t['result'] == 'not met']
        times = sorted((t for t in misses if not isinstance(t['value'], tuple)), key=lambda t: t['value'] - t['limit'])
        parts.append(f'{counted(len(open_), "target")} still open.')
        if times:
            t = times[0]
            parts.append(f'The closest: {esc(t["text"][0].lower() + t["text"][1:])}, {target_figures(t)[2]}.')
    return f'<p class="sl-lead">{" ".join(parts)}</p>'


def setup_lanes(m, key, sort=True):
    lanes = [(s['name'], s[key], s['id'] == KAIJUFLOW, 'no top pick played' if s[key] is None else '') for s in m['setups']]
    return sorted(lanes, key=lambda x: (x[1] is None, x[1] or 0)) if sort else lanes


def verdict_section(m):
    lanes = setup_lanes(m, 'cold_start')
    cap = ('<b>Cold start.</b> Seconds from pressing play until the video starts, the first time a title is played. '
           'Each bar ends where the video starts. Shorter is faster.')
    return (f'<section class="sl-sec sl-verdict"><div class="sl-vtop"><div><h1>{m["met"]} of {m["total"]} targets met</h1>{lead(m)}</div>'
            f'{headline_numbers(m)}</div>'
            f'{figure(cap, lanes, limits_on(m["targets"], "cold start", with_status=True), hero=True, play_label=True)}</section>')


def targets_heading(met, total):
    if met == total:
        return 'Every target met'
    if met == 0:
        return 'No target met yet'
    return f'{counted(met, "target")} met, {NUMBER_WORDS[total - met].lower() if total - met < 11 else total - met} still open'


def targets_section(m):
    head = ('<div class="sl-trow sl-thead" aria-hidden="true"><span>Result</span><span>Target</span><span class="sl-r">KaijuFlow</span>'
            '<span class="sl-r">Limit</span><span>Margin</span><span>KaijuFlow against the limit</span></div>')
    return (f'<section class="sl-sec"><h2>{targets_heading(m["met"], m["total"])}</h2>'
            '<p class="sl-text sl-sub">Each target compares KaijuFlow with a limit. On the small rulers the yellow bar is KaijuFlow '
            'and the upright line is the limit. Every time is the median over the titles of both rounds of its kind.</p>'
            f'<div class="sl-targets">{head}<ul>{target_rows(m["targets"])}</ul></div></section>')


PAIRS = [('Cold start', 'cold_start'), ('Warm start', 'warm_start'), ('Cold list', 'cold_list'), ('Warm list', 'warm_list')]


def change_section(m):
    changes = ''.join(f'<li>{esc(c)}</li>' for c in m['changes'])
    before = m['prev_kaijuflow']
    if not before:
        return (f'<section class="sl-sec"><h2>What changed since the last run</h2>'
                f'<ul class="sl-changes">{changes}</ul></section>') if changes else ''
    kf = m['kaijuflow']
    faster = sum(1 for _, k in PAIRS if before[k] is not None and kf[k] is not None and kf[k] < before[k])
    measured = sum(1 for _, k in PAIRS if before[k] is not None and kf[k] is not None)
    since = f'the {m["prev"]["label"]}'
    heading = (f'Every time got faster since {since}' if faster == measured else f'No time got faster since {since}' if not faster
               else f'{NUMBER_WORDS[faster]} of the {NUMBER_WORDS[measured].lower()} times got faster since {since}')
    rows = []
    for label, k in PAIRS:
        lanes = [('Before', before[k], False, ''), ('This run', kf[k], True, '')]
        rows.append(f'<div class="sl-pair"><h3>{label}</h3>{ruler(lanes, end=max([v for _, v, _, _ in lanes if v] or [1]))}'
                    f'<p class="sl-chg">{esc(change_words(before[k], kf[k]))}</p></div>')
    rows.append(f'<div class="sl-pair"><h3>Top pick plays</h3><ol class="sl-pl"><li class="sl-plain">Before: {plays_text(before["plays"])}</li>'
                f'<li class="sl-plain">This run: {plays_text(kf["plays"])}</li></ol>'
                f'<p class="sl-chg">{esc(change_words(before["plays"], kf["plays"], plays=True))} <small>(a count, so no bar)</small></p></div>')
    return (f'<section class="sl-sec"><h2>{esc(heading)}</h2><ul class="sl-changes">{changes}</ul>'
            f'<p class="sl-small sl-quiet" style="margin-bottom:8px">KaijuFlow in the {esc(m["prev"]["label"])} of '
            f'{esc(m["prev"]["date_long"])} (before) and in this run. Each pair has its own scale, from 0 s to the longer time. '
            f'Shorter is faster.</p><div class="sl-pairs">{"".join(rows)}</div></section>')


FOUR = [('Start, cold', 'cold_start', 'cold start'), ('Start, warm', 'warm_start', 'warm start'),
        ('List, cold', 'cold_list', 'cold list'), ('List, warm', 'warm_list', 'warm list')]


def setups_heading(m):
    by = {s['id']: s for s in m['setups']}
    kf, uu = by.get(KAIJUFLOW, {}).get('cold_start'), by.get('uu', {}).get('cold_start')
    if kf is None or uu is None:
        return 'How the setups compare'
    return f'KaijuFlow starts {"faster than" if kf < uu else "slower than" if kf > uu else "as fast as"} Usenet Ultimate'


def setups_section(m):
    figs = []
    for caption, key, measure in FOUR:
        limits = limits_on(m['targets'], measure)
        note = ''
        if not limits:
            note = '<p class="sl-nolim">No target' + (': AltMount direct checks nothing before it lists, so its list is quickest.'
                                                      if any(s['id'] == 'altmount-addon' for s in m['setups']) else '.') + '</p>'
        figs.append(figure(f'<b>{caption}</b>{note}', setup_lanes(m, key), limits))
    plays = ''.join(f'<p class="{"sl-pk" if s["id"] == KAIJUFLOW else ""}"><span class="sl-num sl-pv">{plays_text(s["plays"])}</span>'
                    f'<span class="sl-pn">{esc(s["name"])}</span></p>' for s in m['setups'])
    return (f'<section class="sl-sec"><h2>{setups_heading(m)}</h2>'
            f'<p class="sl-text sl-sub">Medians over {m["run"]["titles"]} titles and both rounds of each kind. Each ruler has its own '
            'scale and is sorted fastest first. An upright line is a target\'s limit.</p>'
            f'<div class="sl-four">{"".join(figs)}</div><div class="sl-plays"><h3>Top pick plays</h3>{plays}</div></section>')


def title_note(cell):
    if cell is None:
        return 'not played'
    played, rounds = cell['played'], cell['rounds']
    return '' if played == rounds else 'did not play' if not played else f'{rounds - played} of {rounds} failed'


def titles_heading(rows):
    times = sorted(r['cells'][KAIJUFLOW]['value'] for r in rows if r['cells'].get(KAIJUFLOW) and r['cells'][KAIJUFLOW]['value'] is not None)
    if len(times) >= 3:
        rest = times[:-1]
        if times[-1] >= 2 * rest[len(rest) // 2]:
            slow = next(r['title'] for r in rows if r['cells'].get(KAIJUFLOW) and r['cells'][KAIJUFLOW]['value'] == times[-1])
            return f'{slow} is far slower than the rest', True
    return 'Cold start, title by title', False


def titles_section(m):
    rows = m['titles']
    heading, outlier = titles_heading(rows)
    lanes = [(r['title'], (r['cells'].get(KAIJUFLOW) or {}).get('value'), True, title_note(r['cells'].get(KAIJUFLOW))) for r in rows]
    end = scale(max([v for _, v, _, _ in lanes if v is not None], default=0))[0]
    sides = m['setups']
    head = ''.join(f'<th scope="col" class="sl-r{" sl-kfh" if s["id"] == KAIJUFLOW else ""}"><span>{esc(s["name"])}</span></th>' for s in sides)
    body = []
    for r in rows:
        cells = []
        for s in sides:
            c = r['cells'].get(s['id'])
            value = '–' if not c or c['value'] is None else f'{c["value"]:.2f}'
            note = title_note(c)
            cells.append(f'<td class="sl-r{" sl-kfc" if s["id"] == KAIJUFLOW else ""}">{value}{f"<small>{esc(note)}</small>" if note else ""}</td>')
        body.append(f'<tr><th scope="row">{esc(r["title"])}</th>{"".join(cells)}</tr>')
    sub = (f'Cold start, title by title: the median of the cold rounds whose top pick played. This ruler runs from 0 to '
           f'{num(end)} s{" to fit the slow title" if outlier else ""}.')
    return (f'<section class="sl-sec"><h2>{esc(heading)}</h2><p class="sl-text sl-sub">{sub}</p>'
            f'<div class="sl-titles">{figure("<b>KaijuFlow, cold start for each title</b>", lanes)}</div>'
            f'<div class="sl-scroll"><table><caption><span>Every setup, in seconds, fastest KaijuFlow title first. '
            f'A note says when a top pick did not play.</span></caption>'
            f'<thead><tr><th scope="col">Title</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div></section>')


def findings_section(m):
    if not m['findings']:
        return ''
    items = ''.join(f'<li>{h}{p}</li>' for h, p in m['findings'])
    return f'<section class="sl-sec"><h2>What the run found</h2><ul class="sl-finds">{items}</ul></section>'


def history_section(m):
    if len(m['history']) < 2:
        return ''
    rows = []
    for i, r in enumerate(m['history']):
        met = f'{r["met"]} of {r["total"]}' if r['met'] is not None else 'not judged'
        rows.append(f'<tr class="{"sl-new" if i == 0 else ""}"><th scope="row">{esc(r["label"].capitalize())}<small>{esc(r["date"])}</small></th>'
                    f'<td>{esc(r["changed"])}</td><td class="sl-r">{met}</td><td class="sl-r">{secs(r["cold_start"])}</td>'
                    f'<td class="sl-r">{secs(r["warm_start"])}</td><td class="sl-r">{plays_text(r["plays"])}</td></tr>')
    return ('<section class="sl-sec"><h2>Every run so far</h2><div class="sl-scroll"><table><caption><span>KaijuFlow\'s numbers, newest first.</span></caption>'
            '<thead><tr><th scope="col">Run</th><th scope="col">What changed</th><th scope="col" class="sl-r">Targets met</th>'
            '<th scope="col" class="sl-r">Cold start</th><th scope="col" class="sl-r">Warm start</th><th scope="col" class="sl-r">Top pick plays</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')


def next_section(m):
    if not m['next']:
        return ''
    h, body = m['next']
    return f'<section class="sl-sec sl-next">{h}{body}</section>'


def words_section(m):
    items = ''.join(f'<div><dt>{w}</dt><dd>{esc(d.format(titles=m["run"]["titles"]))}</dd></div>' for w, d in WORDS)
    return f'<section class="sl-sec"><h2>What the words mean</h2><dl class="sl-words">{items}</dl></section>'


def page(m):
    """The whole page (index.html) from the model build_page.page_model makes."""
    body = ''.join([header(m), verdict_section(m), targets_section(m), change_section(m), setups_section(m), titles_section(m),
                    findings_section(m), history_section(m), next_section(m), words_section(m)])
    return f'{HEAD}<style>\n{CSS}</style>\n<div class="sl"><main class="sl-wrap">\n{body}\n</main></div>\n'
