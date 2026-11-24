"""Case logs (#287, spec #279): the record of a failure with no proved cause yet, kept until the cause is proved.

A check's failure that Diagnosis could not prove (new, or suspected) opens a Case log, or joins the open one with the
same fingerprint: `<cases root>/<id>/case.json`, with a readable `CASE.md` written from it. Code writes the first
attempt (the play's path to its first wrong step, what changed since the last check that passed, the leads it tried, and
every Clue in the library run once on the failure); then the diagnosing agent works the log through `diagnosis.py case`
(tools/brain/docs/diagnosing-agent.md), every claim it writes checked against the evidence it quotes. A Clue already
run on an occurrence is never run on it again. Formats: tools/brain/docs/formats.md, "Case log".
"""
import datetime
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
import clues  # noqa: E402
import evidence  # noqa: E402

FORMAT = 1
CASE = 'case.json'
READABLE = 'CASE.md'
CASES = os.path.expanduser('~/kaijuflow-notes/diagnosis/cases')  # in the notes repo, beside the evidence it quotes
OPEN = 'open'
MIN_QUOTE = 10  # characters that are not spaces: a shorter quote ("503", "ok") would fit almost any file


class Refused(Exception):
    """A write the Case log does not take, with why (a quote the evidence does not hold, a missing refutation, ...)."""


def _now():
    return br.iso(datetime.datetime.now(datetime.timezone.utc))


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-') or 'none'


def case_id(failure):
    """`<kind>-<failing step>-<8 hex of the fingerprint>`: one Case log per fingerprint."""
    step = failure['where'].split(' ')[0]
    return f"{_slug(failure['kind'])}-{_slug(step)}-{hashlib.sha1(failure['fingerprint'].encode()).hexdigest()[:8]}"


def load(case_dir):
    with open(os.path.join(case_dir, CASE)) as f:
        log = json.load(f)
    if log.get('format') != FORMAT:
        raise Refused(f"{case_dir}: Case log format {log.get('format')!r}, this reader knows {FORMAT}")
    return log


def save(case_dir, log):
    os.makedirs(case_dir, exist_ok=True)
    tmp = os.path.join(case_dir, CASE + '.tmp')
    with open(tmp, 'w') as f:
        f.write(json.dumps(log, indent=1, ensure_ascii=False) + '\n')
    os.replace(tmp, os.path.join(case_dir, CASE))
    with open(os.path.join(case_dir, READABLE), 'w') as f:
        f.write(render(log))


def evidence_folder(case_dir, occ):
    """The evidence folder one occurrence names (kept relative to the Case log's folder)."""
    return os.path.normpath(os.path.join(case_dir, occ['evidence']))


# --------------------------------------------------------------------------- the first attempt, by code

def _raw_step_lines(folder):
    with open(os.path.join(folder, 'steps.jsonl')) as f:
        return [line.rstrip('\n') for line in f if line.strip()]


def _raw_line(folder, step):
    return next((line for line in _raw_step_lines(folder) if json.loads(line) == step), None)


def _path_steps(ev, failure):
    import diagnosis  # noqa: PLC0415  (diagnosis imports this module)
    if failure['release']:
        return [s for s in ev.steps if s.get('title') == failure['release']]
    return [s for s in ev.steps if s.get('step') not in diagnosis.EVENTS]


def _path_text(steps):
    out = []
    for s in steps:
        word = f"{s['step']} {'ok' if s.get('ok') else 'not ok'}" + (f" ({s['result']})" if s.get('result') else '')
        if out and out[-1][0] == word:
            out[-1][1] += 1
        else:
            out.append([word, 1])
    return ', '.join(w if n == 1 else f'{w} x{n}' for w, n in out)


def path_observation(ev, failure):
    """The play (or its failed Source) followed along its path: its step lines in order, and the first that was not
    ok, quoted from steps.jsonl."""
    steps = _path_steps(ev, failure)
    who = failure['release'] or 'the play'
    if not steps:
        return {'says': f'{who} has no step line', 'quotes': []}
    bad = next((s for s in steps if not s.get('ok')), None)
    says = f'the path of {who}: {_path_text(steps)}; '
    if bad is None:
        return {'says': says + 'every step line was ok', 'quotes': []}
    line = _raw_line(ev.folder, bad)
    return {'says': says + f"the first step whose output is wrong: {bad['step']} not ok",
            'quotes': [{'occurrence': None, 'file': 'steps.jsonl', 'text': line}] if line else []}


def _ran(log, occurrence):
    return {r['clue'] for r in log['clue_runs'] if r['occurrence'] == occurrence}


def run_clues(log, case_dir, occurrence, names, library=None, by='code', ran_by_diagnosis=()):
    """Runs the named Clues on one occurrence, each only if it has not run on it before; ({ran}, {skipped})."""
    library = clues.CLUES if library is None else library
    occ = next(o for o in log['occurrences'] if o['n'] == occurrence)
    have = _ran(log, occurrence)
    ran, skipped = [], []
    t = _now()
    for r in ran_by_diagnosis:  # the recipes Diagnosis already ran on this failure count as run
        if r['clue'] not in have:
            log['clue_runs'].append({'clue': r['clue'], 'occurrence': occurrence, 'answer': r['answer'], 'facts': r['facts'],
                                     't': t, 'by': 'diagnosis'})
            have.add(r['clue'])
            ran.append(r['clue'])
    unknown = [n for n in names if n not in library and n not in have]
    if unknown:
        raise Refused(f"no Clue named {', '.join(unknown)} in the library")
    ev = failure = None
    for name in names:
        if name in have:
            skipped.append(name)
            continue
        if ev is None:
            ev = evidence.read(evidence_folder(case_dir, occ))
            failure = _failure_of(ev, occ)
        r = clues.run(name, ev, failure, library)
        log['clue_runs'].append({'clue': name, 'occurrence': occurrence, 'answer': r['answer'], 'facts': r['facts'], 't': t,
                                 'by': by})
        have.add(name)
        ran.append(name)
    return ran, skipped


def _failure_of(ev, occ):
    import diagnosis  # noqa: PLC0415
    rules = diagnosis.load_rules()
    for f in diagnosis.failures(ev):
        if f['release'] == occ['release']:
            return dict(f, fingerprint=diagnosis.fingerprint(f, ev, rules))
    raise Refused(f"the evidence folder of occurrence {occ['n']} has no failure for {occ['release'] or 'the play'}")


def _new_log(failure, cid, when):
    return {'format': FORMAT, 'id': cid, 'fingerprint': failure['fingerprint'], 'kind': failure['kind'],
            'where': failure['where'], 'reason': failure['reason'], 'status': OPEN, 'opened': when,
            'occurrences': [], 'observations': [], 'hypotheses': [], 'clue_runs': [], 'attempts': [], 'research': [],
            'tickets': [], 'asks': [], 'conclusion': None, 'entry': None}


def _note(log, kind, item, by, t=None):
    rows = log[kind]
    item = dict(item, n=len(rows) + 1, by=by, t=t or _now())
    rows.append(item)
    return item


def open_or_join(cases, folder, ev, failure, diagnosed, library=None):
    """Opens the Case log of one unproved failure, or adds this occurrence to the one with its fingerprint, and writes
    the code's attempt for it. Returns (id, whether the log is new, whether the occurrence is new)."""
    cid = case_id(failure)
    case_dir = os.path.join(cases, cid)
    new = not os.path.exists(os.path.join(case_dir, CASE))
    t = _now()
    log = _new_log(failure, cid, t) if new else load(case_dir)
    where = os.path.relpath(folder, case_dir)
    if any(os.path.normpath(os.path.join(case_dir, o['evidence'])) == os.path.normpath(folder) and
           o['release'] == failure['release'] for o in log['occurrences']):
        return cid, False, False
    meta = ev.meta
    n = len(log['occurrences']) + 1
    log['occurrences'].append({'n': n, 'evidence': where, 'check': meta.get('check'), 'label': meta.get('label'),
                               'release': failure['release'], 'date': (meta.get('t_start') or '')[:10],
                               'rules': diagnosed.get('rules'), 'how': 'check'})
    obs = path_observation(ev, failure)
    for q in obs['quotes']:
        q['occurrence'] = n
    _note(log, 'observations', {'occurrence': n, **obs}, 'code', t)
    for lead in diagnosed.get('leads') or []:
        _note(log, 'observations', {'occurrence': n, 'says': _lead_text(lead),
                                    'quotes': [{'occurrence': n, 'clue': c['clue'], 'text': c['facts'][0]}
                                               for c in lead.get('clues') or [] if c.get('facts')]}, 'code', t)
    names = sorted(clues.CLUES if library is None else library)
    done = [c for lead in diagnosed.get('leads') or [] for c in lead.get('clues') or []]
    ran, skipped = run_clues(log, case_dir, n, names, library, 'code', done)
    _note(log, 'attempts', {'occurrence': n, 'ran': ran, 'skipped': skipped, 'next': None}, 'code', t)
    save(case_dir, log)
    return cid, new, True


def _lead_text(lead):
    if lead['result'] == 'no confirming test':
        return f"looked like {lead['id']} (`{lead['sign']}`), which has no confirming test: {lead.get('why')}"
    said = ', '.join(f"{c['clue']} answered {c['answer']} (wanted {c['wanted']})" for c in lead.get('clues') or [])
    return f"looked like {lead['id']} (`{lead['sign']}`); its confirming test: {lead['result']}: {said}"


def logs(cases):
    """Every Case log under the cases root, by id."""
    try:
        names = sorted(os.listdir(cases))
    except OSError:
        return {}
    return {n: load(os.path.join(cases, n)) for n in names if os.path.exists(os.path.join(cases, n, CASE))}


def count_open(cases):
    return sum(1 for log in logs(cases).values() if not log.get('entry'))


# --------------------------------------------------------------------------- the agent's commands

def case_dir_of(cases, cid):
    d = os.path.join(cases, cid)
    if not os.path.exists(os.path.join(d, CASE)):
        raise Refused(f'no Case log {cid} under {cases}')
    return d


def run_command(cases, cid, names, occurrence=None, library=None):
    """`case run`: the named Clues on every occurrence (or one), each only where it has not run; the lines it says."""
    d = case_dir_of(cases, cid)
    log = load(d)
    occs = [o for o in log['occurrences'] if occurrence is None or o['n'] == occurrence]
    if not occs:
        raise Refused(f'{cid} has no occurrence {occurrence}')
    said, t = [], _now()
    for o in occs:
        ran, skipped = run_clues(log, d, o['n'], names, library, 'agent')
        _note(log, 'attempts', {'occurrence': o['n'], 'ran': ran, 'skipped': skipped, 'next': None}, 'agent', t)
        answers = {r['clue']: r for r in log['clue_runs'] if r['occurrence'] == o['n']}
        for name in sorted(set(names)):
            r = answers[name]
            if name in ran:
                said.append(f"occurrence {o['n']}: {name}: {r['answer']}" + (f": {r['facts'][0]}" if r['facts'] else ''))
            else:
                said.append(f"occurrence {o['n']}: {name}: already run ({r['answer']}), not run again")
    save(d, log)
    return said


def _fold(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def check_quotes(log, case_dir, quotes, what):
    """Refused unless every quote is in the evidence it names: {'occurrence', 'file' (a file in that occurrence's
    evidence folder), 'text'}, or {'occurrence', 'clue', 'text'} (what that Clue said when it ran on it). Each text is
    looked up whole, spaces folded; none may be shorter than MIN_QUOTE."""
    if not quotes:
        raise Refused(f'{what} quotes the evidence it rests on: no quote given')
    occs = {o['n']: o for o in log['occurrences']}
    for i, q in enumerate(quotes, 1):
        text = q.get('text') if isinstance(q, dict) else None
        if not isinstance(text, str) or len(re.sub(r'\s', '', text)) < MIN_QUOTE:
            raise Refused(f'quote {i} is too short to check (at least {MIN_QUOTE} characters that are not spaces)')
        n = q.get('occurrence')
        if n not in occs:
            raise Refused(f'quote {i} names occurrence {n}; this Case log has {len(occs)}')
        if q.get('clue'):
            facts = [f.rstrip('…') for r in log['clue_runs'] if r['clue'] == q['clue'] and r['occurrence'] == n
                     for f in r['facts']]
            if not any(_fold(text) in _fold(f) for f in facts):
                raise Refused(f"quote {i} is not in what Clue {q['clue']} said on occurrence {n}: \"{text}\"")
            continue
        rel = q.get('file') or ''
        folder = evidence_folder(case_dir, occs[n])
        path = os.path.normpath(os.path.join(folder, rel))
        if not rel or os.path.isabs(rel) or not path.startswith(folder + os.sep) or not os.path.isfile(path):
            raise Refused(f'quote {i} names {rel or "no file"}, not a file in the evidence folder')
        with open(path, errors='replace') as f:
            if _fold(text) not in _fold(f.read()):
                raise Refused(f"quote {i} is not in occurrence {n}'s {rel}: \"{text}\"")


def _text(write, field, what):
    v = write.get(field)
    if not isinstance(v, str) or not v.strip():
        raise Refused(f'{what} ({field})')
    return v.strip()


def _hypothesis(log, n):
    h = next((h for h in log['hypotheses'] if h['n'] == n), None)
    if h is None:
        raise Refused(f'this Case log has no hypothesis {n}')
    return h


WRITES = ('observation', 'hypothesis', 'result', 'research', 'ticket', 'ask', 'pause', 'conclude')
ASKS = ('live go', 'login')  # what only the owner can give (spec #279, story 47)
NEXT = ('research', 'clue', 'ticket', 'owner', 'capture')  # what a stuck case does next: never nothing (story 44)
TICKET = re.compile(r'^(#\d+|https://github\.com/\S+/(issues|pull)/\d+)$')


def add(cases, cid, write):
    """`case add`: one write of the agent's into the Case log, refused (and nothing written) unless it holds. Returns
    the line it says."""
    d = case_dir_of(cases, cid)
    log = load(d)
    kind = write.get('write') if isinstance(write, dict) else None
    if kind not in WRITES:
        raise Refused(f"no write named {kind} ({', '.join(WRITES)})")
    quotes = write.get('quotes') or []
    if kind == 'observation':
        says = _text(write, 'says', 'an observation says what was seen')
        check_quotes(log, d, quotes, 'an observation')
        item = _note(log, 'observations', {'occurrence': None, 'says': says, 'quotes': quotes}, 'agent')
        line = f"observation {item['n']} written"
    elif kind == 'hypothesis':
        says = _text(write, 'says', 'a hypothesis says what the cause may be')
        refuted_if = _text(write, 'refuted_if', 'a hypothesis says what result would refute it')
        check_quotes(log, d, quotes, 'a hypothesis')
        item = _note(log, 'hypotheses', {'says': says, 'refuted_if': refuted_if, 'quotes': quotes, 'status': OPEN,
                                         'result': None}, 'agent')
        line = f"hypothesis {item['n']} written"
    elif kind == 'research':
        item = _note(log, 'research', {'question': _text(write, 'question', 'research names its question'),
                                       'source': _text(write, 'source', 'research names where it looked (a link or a file)'),
                                       'found': _text(write, 'found', 'research says what it found'),
                                       'used': bool(write.get('used'))}, 'agent')
        line = f"research {item['n']} written"
    elif kind == 'ticket':
        ref = _text(write, 'ref', 'a ticket is named by its number (#123) or its link')
        if not TICKET.match(ref):
            raise Refused('a ticket is named by its number (#123) or its link')
        item = _note(log, 'tickets', {'ref': ref, 'fact': _text(write, 'fact', 'a ticket says what KaijuFlow should record')},
                     'agent')
        line = f"ticket {item['n']} written"
    elif kind == 'ask':
        if write.get('kind') not in ASKS:
            raise Refused('a Case log comes to the owner only for what only they can give: a live go or a login (kind)')
        item = _note(log, 'asks', {'kind': write['kind'], 'what': _text(write, 'what', 'an ask says what is needed')}, 'agent')
        line = f"ask {item['n']} written: tell the owner in one line (kf-alert)"
    elif kind == 'pause':
        if len(log['hypotheses']) < 2:
            raise Refused(f"keep several hypotheses at once: this Case log has {len(log['hypotheses'])}")
        nxt = write.get('next')
        if not isinstance(nxt, dict) or nxt.get('do') not in NEXT or not str(nxt.get('what') or '').strip():
            raise Refused(f"a stuck case keeps going: say what comes next (next.do: {', '.join(NEXT)})")
        if nxt['do'] == 'owner' and not log['asks']:
            raise Refused('the next step is the owner only after an ask (a live go or a login)')
        item = _note(log, 'attempts', {'occurrence': None, 'ran': [], 'skipped': [],
                                       'next': {'do': nxt['do'], 'what': nxt['what'].strip()}}, 'agent')
        line = f"attempt {item['n']} paused; next: {nxt['do']}"
    elif kind == 'conclude':
        raise Refused('conclude is not built yet')
    else:
        h = _hypothesis(log, write.get('hypothesis'))
        now = write.get('now')
        if now not in ('refuted', 'holds'):
            raise Refused('a result says whether the hypothesis is now refuted or holds (now)')
        says = _text(write, 'says', 'a result says what the test showed')
        check_quotes(log, d, quotes, 'a result')
        h['status'], h['result'] = now, {'says': says, 'quotes': quotes, 't': _now()}
        line = f"hypothesis {h['n']} now {now}"
    save(d, log)
    return f'{cid}: {line}'


def show(cases, cid):
    return render(load(case_dir_of(cases, cid)))


def main(argv):
    """`diagnosis.py case ...` (argv from `case` on)."""
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(prog='diagnosis.py case', description='Work a Case log (#287).')
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--cases', default=CASES, help='the Case logs folder (default %(default)s)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list', parents=[common], help='every Case log, its status and occurrences')
    p = sub.add_parser('show', parents=[common], help='the Case log as CASE.md has it')
    p.add_argument('id')
    p = sub.add_parser('run', parents=[common],
                       help='run Clues on the failure (a Clue already run on an occurrence is not run again)')
    p.add_argument('id')
    p.add_argument('clues', nargs='+')
    p.add_argument('--occurrence', type=int)
    p = sub.add_parser('add', parents=[common], help='one write from a JSON file (- for stdin): observation, hypothesis, '
                       'result, research, ticket, ask, pause, conclude; every quote is checked against the evidence')
    p.add_argument('id')
    p.add_argument('file')
    a = ap.parse_args(argv)
    try:
        if a.cmd == 'list':
            for cid, log in logs(a.cases).items():
                print(f"{cid}: {log['status']}, {len(log['occurrences'])} occurrence(s): {log['fingerprint']}")
        elif a.cmd == 'show':
            print(show(a.cases, a.id), end='')
        elif a.cmd == 'run':
            print('\n'.join(run_command(a.cases, a.id, a.clues, a.occurrence)))
        elif a.cmd == 'add':
            try:
                with (sys.stdin if a.file == '-' else open(a.file)) as f:
                    write = json.load(f)
            except (OSError, ValueError) as e:
                raise Refused(f'{a.file}: not a JSON write: {e}') from e
            print(add(a.cases, a.id, write))
    except Refused as e:
        print(f'refused: {e}')
        return 1
    return 0


# --------------------------------------------------------------------------- the readable copy

def _quote_md(q):
    where = f"clue {q['clue']}" if q.get('clue') else q.get('file')
    return f"    > {q['text']}  \n    > ({where}, occurrence {q.get('occurrence')})"


def render(log):
    lines = [f"# Case log {log['id']}", '', f"**Status:** {log['status']}" +
             (f" (Casebook entry `{log['entry']}`)" if log.get('entry') else ''), '',
             f"**Fingerprint:** `{log['fingerprint']}`", '', f"Opened {log['opened']}. Written from `{CASE}` (#287): "
             'never edit this file, use `diagnosis.py case`.', '', '## Occurrences', '']
    for o in log['occurrences']:
        lines.append(f"{o['n']}. {o['date']}, {o['check']}, {o['label']}" + (f": {o['release']}" if o['release'] else '') +
                     f" ({o['how']}; `{o['evidence']}`)")
    for title, key in (('Observations', 'observations'), ('Hypotheses', 'hypotheses')):
        lines += ['', f'## {title}', '']
        if not log[key]:
            lines.append('None yet.')
        for item in log[key]:
            head = f"{item['n']}. ({item['by']}) {item['says']}"
            if key == 'hypotheses':
                head += f" *Refuted if:* {item['refuted_if']} *Now:* {item['status']}" + \
                    (f" ({item['result']['says']})" if item.get('result') else '')
            lines.append(head)
            lines += [_quote_md(q) for q in item.get('quotes') or []]
    lines += ['', '## Clues run', '']
    for r in log['clue_runs']:
        lines.append(f"- {r['clue']} on occurrence {r['occurrence']}: **{r['answer']}** ({r['by']})" +
                     (f": {r['facts'][0]}" if r['facts'] else ''))
    lines += ['', '## Attempts', '']
    for a in log['attempts']:
        lines.append(f"{a['n']}. {a['t']} ({a['by']}): ran {', '.join(a['ran']) or 'nothing'}" +
                     (f"; skipped (already run) {', '.join(a['skipped'])}" if a['skipped'] else '') +
                     (f"; next: {a['next']['do']}: {a['next']['what']}" if a.get('next') else ''))
    for title, key, fmt in (('Research', 'research', lambda r: f"{r['question']} ({r['source']}): {r['found']}"),
                            ('Tickets', 'tickets', lambda r: f"{r['ref']}: {r['fact']}"),
                            ('Asked of the owner', 'asks', lambda r: f"{r['kind']}: {r['what']}")):
        if log[key]:
            lines += ['', f'## {title}', ''] + [f"{r['n']}. {fmt(r)}" for r in log[key]]
    c = log.get('conclusion')
    if c:
        lines += ['', '## Conclusion', '', f"**{c['result']}**: {c['title']} ({c['whose']}, step {c['step']}). {c['cause']}",
                  '', 'Recipe: ' + ', '.join(f"{r['clue']} = {r['answer']}" for r in c['recipe'])]
    return '\n'.join(lines) + '\n'
