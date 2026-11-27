"""The KaijuFlow Speed Check page of real-use checks (#273, ADR 0010): the newest check's verdict, its fails and its
totals (no per-title table: the report's totals only) and its indexer table (#304, #312: the rows of its report's
`## Indexers`), then every check given, one row each. Nothing is published.

    python3 -I tools/brain/checkpage.py CHECK_DIR [CHECK_DIR ...] [--out DIR]

CHECK_DIR is a check folder of brainrun.py (`check --quick` or `drill`; for example
~/kaijuflow-notes/brain-runs/<date>-quick-check/). Each is read from its meta.json, raw.json and logs/standin.log, the
way its report.md was written (quickcheck.py), so the page says what the report says. The newest check given that has a verdict leads the
page; a check with no verdict (stopped, or the cap rule) gets its row and its one sentence. The page is written as
index.html into the output folder (default ~/kaijuflow-notes/brain-1338/page/); RUNBOOK.md, "Publish the page", has the
steps from there. Checks are never compared with each other: each check plays new titles (ADR 0010).
"""
import argparse
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
import quickcheck  # noqa: E402

DEFAULT_OUT = os.path.expanduser('~/kaijuflow-notes/brain-1338/page/')
KINDS = {'quick check': 'Quick check', 'drill-down': 'Drill-down'}  # meta.json's kind -> the name the page gives it


class NotACheck(Exception):
    """The one sentence about a folder that is not a real-use check's."""


def load(folder):
    """{'folder', 'meta', 'outcomes', 'indexers'} of a check folder (`indexers`: quickcheck.indexer_rows, as its report's
    table); NotACheck when it is not one (a timed run's, or unreadable)."""
    name = os.path.basename(os.path.normpath(folder))
    meta = br.read_json(os.path.join(folder, 'meta.json'))
    if not isinstance(meta, dict) or meta.get('kind') not in KINDS:
        raise NotACheck(f'{folder} is not a real-use check: its meta.json names no quick check or Drill-down kind '
                        '(a timed run of the retired recording path is not shown, ADR 0010).')
    raw = br.read_json(os.path.join(folder, 'raw.json')) or {}
    outcomes = raw.get('outcomes') or []
    check = {'visits': raw.get('visits') or [], 'indexers': meta.get('indexers') or [], 'requests': quickcheck.requests_of(folder)}
    return {'folder': name, 'meta': meta, 'outcomes': outcomes, 'indexers': quickcheck.indexer_rows(check, outcomes)}


def page_model(checks):
    """What the page shows: the lead (the newest check with a verdict, or None) and every check, newest first."""
    rows = sorted(checks, key=lambda c: c['meta'].get('started') or '', reverse=True)
    lead = next((c for c in rows if c['meta'].get('verdict')), None)
    return {'lead': lead, 'rows': rows}


def _e(text):
    return html.escape(str(text), quote=True)


def _totals(outcomes):
    """(label, value) of the lead check's totals, as its report.md gives them."""
    count = {k: sum(1 for o in outcomes if o['outcome'] == k) for k in (quickcheck.PLAYED, quickcheck.FAIL, quickcheck.NOTHING)}
    return [('Titles', br.plural(len(outcomes), 'title')),
            ('Fails', str(count[quickcheck.FAIL])),
            (f'Slow plays (video after {quickcheck.SLOW_PLAY_S} s)', str(sum(1 for o in outcomes if o['slow']))),
            ('Check misses', str(sum(len(o['check_misses']) for o in outcomes))),
            ('Nothing to play', str(count[quickcheck.NOTHING])),
            ('Fallbacks', quickcheck.fallbacks_line(outcomes)),
            ('Typical title to video', quickcheck.typical_line(outcomes))]


def _lead_html(c):
    meta, outcomes = c['meta'], c['outcomes']
    fails = [o for o in outcomes if o['outcome'] == quickcheck.FAIL]
    verdict = meta.get('verdict')
    out = [f'<section class="lead {"pass" if verdict == "pass" else "fail"}">',
           f'<p class="kind">{_e(KINDS[meta["kind"]])} · {_e((meta.get("started") or "")[:16].replace("T", " "))} UTC · '
           f'commit {_e(str(meta.get("commit") or "?")[:7])}</p>',
           f'<h1>{_e(meta.get("headline") or "")}</h1>']
    if fails:
        out += ['<h2>Fails</h2>', '<ul>'] + [f'<li><b>{_e(o["label"])}</b> ({_e(o["kind"])}): {_e(o["why"])}</li>' for o in fails]
        out.append('</ul>')
    out += ['<dl>'] + [f'<div><dt>{_e(k)}</dt><dd>{_e(v)}</dd></div>' for k, v in _totals(outcomes)] + ['</dl>']
    if c['indexers']:
        out += ['<h2>Indexers</h2>', '<table><thead><tr>' + ''.join(f'<th>{_e(h)}</th>' for h in quickcheck.INDEXER_HEADS)
                + '</tr></thead><tbody>']
        out += ['<tr>' + ''.join(f'<td>{_e(v)}</td>' for v in quickcheck.indexer_cells(r)) + '</tr>' for r in c['indexers']]
        out.append('</tbody></table>')
    out.append('</section>')
    return out


def page(model):
    """The whole page (index.html) as text."""
    body = _lead_html(model['lead']) if model['lead'] else ['<section class="lead"><h1>No check with a verdict yet.</h1></section>']
    body += ['<section><h2>Every check so far</h2>', '<table><thead><tr><th>Started (UTC)</th><th>Check</th><th>Verdict</th>'
             '</tr></thead><tbody>']
    for c in model['rows']:
        m = c['meta']
        body.append(f'<tr><td>{_e((m.get("started") or "")[:16].replace("T", " "))}</td><td>{_e(KINDS[m["kind"]])}</td>'
                    f'<td>{_e(m.get("headline") or "")}</td></tr>')
    body += ['</tbody></table>', '<p class="note">A check passes on zero fails alone; slow plays and the typical title to '
             'video are information. Each check plays new titles, so checks are not compared with each other (ADR 0010).</p>',
             '</section>']
    return '\n'.join([
        '<!doctype html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">', '<title>KaijuFlow Speed Check</title>',
        f'<style>{STYLE}</style>', '</head>', '<body>', '<main>', '<p class="brand">KaijuFlow Speed Check · real-use checks</p>',
        *body, '</main>', '</body>', '</html>', ''])


STYLE = '''
:root { --bg: #f7f6f2; --ink: #1c1b19; --muted: #6b6861; --line: #dedbd2; --pass: #1f7a4d; --fail: #b3261e; --card: #ffffff; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #161513; --ink: #ecebe6; --muted: #a19e96;
  --line: #34322d; --pass: #5cc48f; --fail: #f2867e; --card: #1f1e1b; } }
:root[data-theme="dark"] { --bg: #161513; --ink: #ecebe6; --muted: #a19e96; --line: #34322d; --pass: #5cc48f; --fail: #f2867e;
  --card: #1f1e1b; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; }
.brand, .kind, .note { color: var(--muted); font-size: 14px; }
.lead { background: var(--card); border: 1px solid var(--line); border-left: 6px solid var(--muted); border-radius: 8px;
  padding: 16px; margin: 16px 0 32px; }
.lead.pass { border-left-color: var(--pass); } .lead.fail { border-left-color: var(--fail); }
h1 { font-size: 26px; line-height: 1.25; margin: 4px 0 12px; } h2 { font-size: 18px; margin: 24px 0 8px; }
dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px 24px; margin: 16px 0; }
dt { color: var(--muted); font-size: 13px; } dd { margin: 0; }
table { width: 100%; border-collapse: collapse; font-size: 15px; display: block; overflow-x: auto; }
th, td { text-align: left; padding: 6px 12px 6px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 13px; }
'''


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the Speed Check page (index.html) from real-use check folders. Does not publish.')
    ap.add_argument('checks', nargs='+', help='check folders, e.g. ~/kaijuflow-notes/brain-runs/<date>-quick-check/')
    ap.add_argument('--out', default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    try:
        checks = [load(f) for f in a.checks]
    except NotACheck as e:
        print(e)
        return 1
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, 'index.html')
    with open(path, 'w') as f:
        f.write(page(page_model(checks)))
    print(f'Wrote {path} from {br.plural(len(checks), "check")}; nothing published.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
