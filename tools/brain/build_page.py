"""The one builder for the KaijuFlow Speed Check page (spec #77; tickets #89, #115 and #132, the Starting line design).

    python3 -I tools/brain/build_page.py RUN_DIR [RUN_DIR ...] [--out DIR]

RUN_DIR is a run folder from brainrun.py (for example ~/kaijuflow-notes/brain-runs/<run>/). A timed run folder holds
raw.json and meta.json. Its recording folder (only meta.json) may be named too; nothing is read from it.
Nothing is published: the script writes index.html, the whole page, into the output folder (default
~/kaijuflow-notes/brain-1338/page/). RUNBOOK.md, "Publish the page", has the steps from there.

The page is about one run: the newest timed run given, which must be finished (status "ok"), because its targets are
judged. The newest finished run before it, when one is given, is what it is compared with ("what changed", the change
under each headline number), and every timed run given gets a row in "Every run so far".

Where things come from, never typed into the page by hand:

  numbers      raw.json of each run, through brainreport (the same medians the targets are judged on)
  verdicts     brainreport.target_results and targets.json
  what changed meta.json "changes" of the newest run (brainrun's diff against the run before it)
  findings     findings.html in the newest run's folder, written by hand: the findings and the next step
               (docs/formats.md, "The page"). Without it the page has neither section.

startline.py draws the page from the model page_model() makes; the one-page report (#133) can reuse both.
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
import startline  # noqa: E402

DEFAULT_OUT = os.path.expanduser('~/kaijuflow-notes/brain-1338/page/')
SIDES = list(startline.SETUP_NAMES)  # the page's order of the setups
FINDINGS_FILE = 'findings.html'


class Run:
    """One timed run folder: its meta.json and its visits."""

    def __init__(self, folder):
        self.folder = folder.rstrip('/') + '/'
        self.folder_name = os.path.basename(self.folder.rstrip('/'))
        with open(self.folder + 'meta.json') as fh:
            self.meta = json.load(fh)
        self.name = self.meta.get('name') or self.folder_name
        with open(self.folder + 'raw.json') as fh:
            self.visits = json.load(fh)['visits']
        self.titles = []
        for v in self.visits:
            if v['title'] not in self.titles:
                self.titles.append(v['title'])
        seen = {v['side'] for v in self.visits}
        self.sides = [n for n in SIDES if n in seen] + sorted(seen - set(SIDES))

    @property
    def status(self):
        return self.meta.get('status')

    @property
    def label(self):
        """'baseline run', 'tuning 1 run': the run's name in a sentence."""
        name = self.name.replace('-', ' ')
        return name if name.lower().endswith('run') else f'{name} run'

    def date(self):
        return (self.meta.get('finished') or self.meta.get('started') or '')[:10]

    def date_long(self):
        d = datetime.date.fromisoformat(self.date())
        return f'{d.day} {d.strftime("%B")} {d.year}'

    def numbers(self, side):
        """A setup's headline numbers: the medians of both rounds of each kind, and its plays over every round."""
        return {'cold_start': br.side_time(self.visits, side, 'cold', 'start'),
                'warm_start': br.side_time(self.visits, side, 'warm', 'start'),
                'cold_list': br.side_time(self.visits, side, 'cold', 'list'),
                'warm_list': br.side_time(self.visits, side, 'warm', 'list'),
                'plays': br.side_plays(self.visits, side)}

    def title_cell(self, side, title):
        """One setup's cold start of one title: the median of the cold rounds whose top pick played, and how many of the
        counted cold rounds played. None when the setup never played the title cold."""
        vs = [v for v in self.visits if v['side'] == side and v['title'] == title and v['phase'] == 'cold']
        counted = [v for v in vs if br.classify_failure(v) != 'not_recorded']
        if not counted:
            return None
        times = [v['start_s'] for v in counted if v.get('ok') and v.get('start_s') is not None]
        value = br.median(times)
        return {'value': value, 'played': len(times), 'rounds': len(counted)}

    def targets(self):
        """The targets judged on this run: target_results with each entry's measure, side and margin beside its verdict."""
        entries = br.load_targets()
        out = []
        for entry, (text, _, verdict) in zip(entries, br.target_results(self.visits)):
            out.append({'text': text, 'measure': entry['measure'], 'against': entry.get('against'), 'margin': entry['margin'],
                        **verdict})
        return out


def refuse_short_run(folder):
    """A short run (brainrun's --sides, --rounds, --quick or a titles subset) is not a baseline and has no place on the page."""
    try:
        with open(os.path.join(folder, 'meta.json')) as fh:
            short = json.load(fh).get('short')
    except (OSError, ValueError):
        return
    if short:
        raise SystemExit(f'{folder}: a short run ({short}) is not a baseline, so the page does not show it.')


def find_runs(folders):
    """The timed runs among the given folders (those with raw.json), newest first. A recording folder (meta mode
    'record') may be named beside its run; nothing on the page is read from it."""
    runs = []
    for f in folders:
        refuse_short_run(f)
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


def read_findings(run):
    """(findings, next step) from findings.html in the run's folder: findings as [(h3 html, rest html)], the next step as
    (h2 html, rest html) or None. ([], None) without the file. docs/formats.md says what the file holds."""
    path = run.folder + FINDINGS_FILE
    if not os.path.exists(path):
        return [], None
    with open(path) as fh:
        words = fh.read()
    part, _, nxt = words.partition('<h2')
    chunks = re.split(r'(?=<h3[ >])', part.strip())
    if chunks[0].strip() or len(chunks) < 2:
        raise SystemExit(f'{path}: {FINDINGS_FILE} must start with a finding: an <h3> heading, then its paragraphs.')
    findings = []
    for chunk in chunks[1:]:
        head, _, body = chunk.partition('</h3>')
        findings.append((head + '</h3>', body.strip()))
    next_step = None
    if nxt:
        head, _, body = ('<h2' + nxt).partition('</h2>')
        next_step = (head + '</h2>', body.strip())
    return findings, next_step


def history_row(run):
    kf = run.numbers(startline.KAIJUFLOW)
    judged = br.targets_not_judged(run.status) is None
    targets = run.targets() if judged else []
    changes = run.meta.get('changes') or []
    return {'label': run.label, 'date': run.date(), 'changed': changes[0] if changes else '',
            'met': sum(1 for t in targets if t['result'] == br.MET) if judged else None, 'total': len(targets),
            'cold_start': kf['cold_start'], 'warm_start': kf['warm_start'], 'plays': kf['plays']}


def page_model(runs):
    """Everything the page shows, as plain values, from runs (newest first). The newest must be finished."""
    run = runs[0]
    why = br.targets_not_judged(run.status)
    if why:
        raise SystemExit(f'{run.folder}: no page for this run: {why}.')
    prev = next((r for r in runs[1:] if r.status == 'ok'), None)
    targets = run.targets()
    findings, next_step = read_findings(run)
    setups = [{'id': side, 'name': startline.SETUP_NAMES.get(side, side), **run.numbers(side)} for side in run.sides]
    rows = [{'title': t, 'cells': {side: run.title_cell(side, t) for side in run.sides}} for t in run.titles]
    rows.sort(key=lambda r: ((r['cells'].get(startline.KAIJUFLOW) or {}).get('value') is None,
                             (r['cells'].get(startline.KAIJUFLOW) or {}).get('value') or 0))
    prev_targets = prev.targets() if prev else []
    return {
        'run': {'label': run.label, 'date_long': run.date_long(), 'titles': len(run.titles)},
        'prev': {'label': prev.label, 'date_long': prev.date_long()} if prev else None,
        'targets': targets,
        'met': sum(1 for t in targets if t['result'] == br.MET), 'total': len(targets),
        'prev_met': sum(1 for t in prev_targets if t['result'] == br.MET) if prev else None,
        'setups': setups,
        'kaijuflow': run.numbers(startline.KAIJUFLOW),
        'prev_kaijuflow': prev.numbers(startline.KAIJUFLOW) if prev else None,
        'changes': run.meta.get('changes') or [],
        'titles': rows,
        'findings': findings, 'next': next_step,
        'history': [history_row(r) for r in runs],
    }


def build(folders):
    """The page (index.html) as a string, from run folders."""
    return startline.page(page_model(find_runs(folders)))


def write(folders, out=DEFAULT_OUT):
    index = build(folders)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'index.html'), 'w') as fh:
        fh.write(index)
    return index


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the Speed Check page (index.html) from run folders. Does not publish.')
    ap.add_argument('runs', nargs='+', help='run folders, e.g. ~/kaijuflow-notes/brain-runs/<run>/')
    ap.add_argument('--out', default=DEFAULT_OUT, help='output folder (default %(default)s)')
    a = ap.parse_args(argv)
    index = write(a.runs, a.out)
    print(f'wrote {os.path.join(a.out, "index.html")} ({len(index)} bytes)')


if __name__ == '__main__':
    main()
