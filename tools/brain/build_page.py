"""The one builder for the KaijuFlow Speed Check page and its one-page report (spec #77; tickets #89, #115, #132 and #133, the Starting line design).

    python3 -I tools/brain/build_page.py RUN_DIR [RUN_DIR ...] [--out DIR]

RUN_DIR is a run folder from brainrun.py (for example ~/kaijuflow-notes/brain-runs/<run>/). A timed run folder holds
raw.json and meta.json. Its recording folder (only meta.json) may be named too; nothing is read from it.
Nothing is published: the script writes index.html, the whole page, and report.html, the one-page Letter report, into the output folder (default
~/kaijuflow-notes/brain-1338/page/). RUNBOOK.md, "Publish the page", has the steps from there.

The page is about one run: the newest timed run given, which must be finished (status "ok"), because its targets are
judged. The newest finished run before it that is not marked never compared with (#153), when one is given, is what it is compared with ("what changed", the change
under each headline number), and every timed run given gets a row in "Every run so far".

Where things come from, never typed into the page by hand:

  numbers      raw.json of each run, through brainreport (the same medians the targets are judged on)
  verdicts     brainreport.target_results and targets.json; for a speed test (a tagged run, #171) brainreport.speed_test_judgement:
               its three targets on each list, the outcome line and the final bar
  what changed meta.json "changes" of the newest run (brainrun's diff against the run before it)
  findings     findings.html in the newest run's folder, written by hand: the findings and the next step
               (docs/formats.md, "The page"). Without it the page has neither section.

startline.py draws both from the one model page_model() makes: page() the page, report() the report, so they show the same
numbers and verdicts.
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


def fails(f):
    """A fail figure (brainreport.fail_figure) with its words, '2 titles failed · 4 of 40 plays', as every count shows it."""
    return {**f, 'words': br.fails_words(f)}


class Run:
    """One timed run folder: its meta.json and its visits."""

    def __init__(self, folder):
        self.folder = folder.rstrip('/') + '/'
        self.folder_name = os.path.basename(self.folder.rstrip('/'))
        with open(self.folder + 'meta.json') as fh:
            self.meta = json.load(fh)
        self.name = self.meta.get('label') or self.meta.get('name') or self.folder_name  # a label (#153) is the readable name
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
                'plays': br.side_plays(self.visits, side),
                'fails': fails(br.fail_figure(self.visits, side))}

    def list_numbers(self, side, lst):
        """A setup's figures on one list of a speed test: its fails (fails, top picks counted) over every round, and its
        median title to video of both rounds of each kind."""
        return {'fails': fails(br.fail_figure(self.visits, side, lst=lst)),
                'cold_video': br.side_time(self.visits, side, 'cold', 'video', lst=lst),
                'warm_video': br.side_time(self.visits, side, 'warm', 'video', lst=lst)}

    def speed_cell(self, side, title):
        """One setup's title in a speed test: the median cold title to video of the rounds whose top pick played, and its
        fails in every round, as [(round, after a fallback)] in the order played. None when the setup never played it."""
        vs = [v for v in self.visits if v['side'] == side and v['title'] == title]
        if not vs:
            return None
        return {'value': br.side_time(vs, side, 'cold', 'video'),
                'fails': [(f"{v['phase'].capitalize()} {v['round']}", br.fallbacks(v) > 0) for v in br.fail_visits(vs, side)]}

    def title_cell(self, side, title):
        """One setup's cold start of one title: the median of the cold rounds whose top pick played on the first try, and how
        many of the counted cold rounds played. None when the setup never played the title cold."""
        vs = [v for v in self.visits if v['side'] == side and v['title'] == title and v['phase'] == 'cold']
        counted = [v for v in vs if br.classify_failure(v) != 'not_recorded']
        if not counted:
            return None
        times = [v['start_s'] for v in counted if br.plays(v) and v.get('start_s') is not None]
        value = br.median(times)
        return {'value': value, 'played': len(times), 'rounds': len(counted)}

    @property
    def tagged(self):
        """Whether the run is a speed test: its titles are on the easy and hard lists (#167)."""
        return br.tagged(self.visits)

    def judgement(self):
        """A speed test's judgement (#169): its targets per list, the outcome line and the final bar."""
        return br.speed_test_judgement(self.visits)

    def targets(self):
        """The targets judged on this run: target_results with each entry's measure, side and margin beside its verdict;
        for a speed test, its three targets on each list (never the final bar), each with its list and measured words."""
        if self.tagged:
            measures = [t['measure'] for t in br.load_speed_targets()['targets']]
            out = []
            for r in self.judgement()['targets']:
                t = {'text': r['target'], 'measure': measures[r['number'] - 1], 'list': r['list'], 'measured': r['measured'],
                     'against': None, 'margin': 0, **r['verdict']}
                if t['measure'] == 'fails' and t['result'] != br.NOT_MEASURED:  # the two fail figures it was judged on
                    t.update(value=fails(t['value']), limit=fails(t['limit']))
                out.append(t)
            return out
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


def refuse_archived_run(folder):
    """An archived run (#144) is from before the like-for-like rules: it is never on the page, not even as a comparison."""
    if br.is_archived(folder):
        raise SystemExit(f'{folder}: the run is {br.ARCHIVED_TEXT}, so the page does not show it.')


def find_runs(folders):
    """The timed runs among the given folders (those with raw.json), newest first. A recording folder (meta mode
    'record') may be named beside its run; nothing on the page is read from it."""
    runs = []
    for f in folders:
        refuse_archived_run(f)
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


def by_kaijuflow(rows):
    """Title rows sorted by KaijuFlow's time, fastest first; a title it has no time for last."""
    def value(r):
        return (r['cells'].get(startline.KAIJUFLOW) or {}).get('value')
    return sorted(rows, key=lambda r: (value(r) is None, value(r) or 0))


def speed_model(run):
    """What the page shows of a speed test beside its targets: the outcome line and the final bar (#169)."""
    j = run.judgement()
    bar = j['final_bar']
    lists = [{'list': x, 'name': f'{x.capitalize()} list',
              'setups': [{'id': side, 'name': startline.SETUP_NAMES.get(side, side), **run.list_numbers(side, x)} for side in run.sides],
              'titles': by_kaijuflow([{'title': t, 'cells': {side: run.speed_cell(side, t) for side in run.sides}}
                                      for t in run.titles if any(v['title'] == t and v.get('list') == x for v in run.visits)])}
             for x in br.run_lists(run.visits)]
    return {'lists': lists, 'outcome': j['outcome']['text'],
            'final_bar': {'result': bar['verdict']['result'], 'text': bar['target'],
                          'lists': [(f'{x.capitalize()} list', r['result'], r['why']) for x, r in bar['lists'].items()]}}


def page_model(runs):
    """Everything the page shows, as plain values, from runs (newest first). The newest must be finished."""
    run = runs[0]
    why = br.targets_not_judged(run.status)
    if why:
        raise SystemExit(f'{run.folder}: no page for this run: {why}.')
    # A speed test is compared with a speed test, a run without tags with one without: their titles are not alike.
    prev = next((r for r in runs[1:] if r.status == 'ok' and not br.never_compared(r.meta) and r.tagged == run.tagged), None)
    targets = run.targets()
    findings, next_step = read_findings(run)
    setups = [{'id': side, 'name': startline.SETUP_NAMES.get(side, side), **run.numbers(side)} for side in run.sides]
    rows = by_kaijuflow([{'title': t, 'cells': {side: run.title_cell(side, t) for side in run.sides}} for t in run.titles])
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
        'speed': speed_model(run) if run.tagged else None,
        'prev_speed': speed_model(prev) if prev and run.tagged else None,
        'findings': findings, 'next': next_step,
        'history': [history_row(r) for r in runs],
    }


def build(folders):
    """The page (index.html) as a string, from run folders."""
    return startline.page(page_model(find_runs(folders)))


def build_report(folders):
    """The one-page Letter report (report.html) as a string, from the same run folders and model as the page."""
    return startline.report(page_model(find_runs(folders)))


def write(folders, out=DEFAULT_OUT):
    """Write index.html and report.html into out, both from one model; return {file name: html}."""
    m = page_model(find_runs(folders))
    files = {'index.html': startline.page(m), 'report.html': startline.report(m)}
    os.makedirs(out, exist_ok=True)
    for name, words in files.items():
        with open(os.path.join(out, name), 'w') as fh:
            fh.write(words)
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the Speed Check page (index.html) and its one-page report (report.html) '
                                             'from run folders. Does not publish.')
    ap.add_argument('runs', nargs='+', help='run folders, e.g. ~/kaijuflow-notes/brain-runs/<run>/')
    ap.add_argument('--out', default=DEFAULT_OUT, help='output folder (default %(default)s)')
    a = ap.parse_args(argv)
    for name, words in write(a.runs, a.out).items():
        print(f'wrote {os.path.join(a.out, name)} ({len(words)} bytes)')


if __name__ == '__main__':
    main()
