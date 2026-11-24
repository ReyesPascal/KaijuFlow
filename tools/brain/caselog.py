"""Case logs (#287, spec #279): the record of a failure with no proved cause yet, kept until the cause is proved.

A check's failure that Diagnosis could not prove (new, or suspected) opens a Case log, or joins the open one with the
same fingerprint: `<cases root>/<id>/case.json`, with a readable `CASE.md` written from it. Code writes the first
attempt (the play's path to its first wrong step, what changed since the last check that passed, the leads it tried, and
every Clue in the library run once on the failure); then the diagnosing agent works the log through `diagnosis.py case`
(tools/brain/docs/diagnosing-agent.md), every claim it writes checked against the evidence it quotes. A Clue already
run on an occurrence is never run on it again. Formats: tools/brain/docs/formats.md, "Case log".
"""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import re
import subprocess
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


@contextlib.contextmanager
def locked(case_dir):
    """One writer of a Case log at a time (two agents, or a check joining it while an agent works it): every load,
    change and save of a log runs inside its lock, so no write is lost."""
    os.makedirs(case_dir, exist_ok=True)
    with open(os.path.join(case_dir, '.lock'), 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


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


def _runs_root(folder):
    """(the runs root, the run folder) an evidence folder sits in: <runs root>/<run folder>/evidence/<NN-label>/."""
    run_dir = os.path.dirname(os.path.dirname(os.path.normpath(folder)))
    return os.path.dirname(run_dir), run_dir


def last_good_check(folder):
    """The name and meta.json of the last quick check under the runs root that passed before this play's check."""
    root, run_dir = _runs_root(folder)
    mine = br.read_json(os.path.join(run_dir, 'meta.json')) or {}
    since = mine.get('started') or (br.read_json(os.path.join(folder, 'evidence.json')) or {}).get('t_start') or ''
    for name in reversed(br.run_folders(root)):
        if name == os.path.basename(run_dir):
            continue
        meta = br.read_json(os.path.join(root, name, 'meta.json')) or {}
        if meta.get('kind') == 'quick check' and meta.get('verdict') == 'pass' and (meta.get('started') or '') < since:
            return name, meta
    return None, None


def _flat(d, at=''):
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            out.update(_flat(v, f'{at}{k}.'))
        else:
            out[f'{at}{k}'] = (k, v)
    return out


def _shown(v):
    return v if isinstance(v, str) else json.dumps(v)


def _pair(key, value):
    return f'{json.dumps(key)}: {json.dumps(value)}'


def changed_observation(ev):
    """What changed since the last quick check that passed (story 42): the image's commit, AltMount's version and the
    settings, each quoted from this play's evidence and from that check's folder."""
    name, good = last_good_check(ev.folder)
    if name is None:
        return {'says': 'no check passed before this one: nothing to compare with', 'quotes': []}
    said, quotes = [], []

    def mine(file, key, value):
        quotes.append({'occurrence': None, 'file': file, 'text': _pair(key, value)})

    def theirs(file, key, value):
        quotes.append({'occurrence': None, 'check': name, 'file': file, 'text': _pair(key, value)})
    meta = ev.meta
    if meta.get('commit') and good.get('commit'):
        if meta['commit'] != good['commit']:
            said.append(f"the commit changed ({good['commit']} to {meta['commit']})")
            mine('evidence.json', 'commit', meta['commit'])
            theirs('meta.json', 'commit', good['commit'])
        else:
            said.append('the same commit')
    else:
        said.append("the commit is not recorded in both")
    am, good_am = (meta.get('altmount') or {}).get('image'), (good.get('altmount') or {}).get('image')
    if am is None:
        said.append("AltMount's version is not recorded in this play's evidence")
    elif good_am is None:
        said.append(f'AltMount {am}; its version is not recorded in {name}')
    elif am != good_am:
        said.append(f'AltMount changed ({good_am} to {am})')
        mine('evidence.json', 'image', am)
        theirs('meta.json', 'image', good_am)
    else:
        said.append(f'the same AltMount ({am})')
    now = _flat(br.read_json(os.path.join(ev.folder, 'settings.json')))
    then = _flat(br.read_json(os.path.join(_runs_root(ev.folder)[0], name, 'settings.json')))
    if not now or not then:
        said.append('the settings are not recorded in both')
    else:
        diff = sorted(k for k in set(now) | set(then) if (now.get(k) or (None, None))[1] != (then.get(k) or (None, None))[1])
        if not diff:
            said.append('the same settings')
        else:
            words = []
            for k in diff[:10]:
                old, new = then.get(k), now.get(k)
                words.append(f"{k} {_shown(old[1]) if old else '(none)'} to {_shown(new[1]) if new else '(none)'}")
                if new and not isinstance(new[1], (dict, list)):
                    mine('settings.json', *new)
                if old and not isinstance(old[1], (dict, list)):
                    theirs('settings.json', *old)
            said.append(f"{len(diff)} setting{'' if len(diff) == 1 else 's'} changed: " + ', '.join(words) +
                        (', ...' if len(diff) > 10 else ''))
    return {'says': f'since the last check that passed ({name}): ' + '; '.join(said), 'quotes': quotes}


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


def _new_log(failure, cid, when, rules):
    return {'format': FORMAT, 'id': cid, 'fingerprint': failure['fingerprint'], 'rules': rules, 'earlier': [],
            'kind': failure['kind'],
            'where': failure['where'], 'reason': failure['reason'], 'status': OPEN, 'opened': when,
            'occurrences': [], 'observations': [], 'hypotheses': [], 'clue_runs': [], 'attempts': [], 'research': [],
            'tickets': [], 'asks': [], 'conclusion': None, 'entry': None}


def _note(log, kind, item, by, t=None):
    rows = log[kind]
    item = dict(item, n=len(rows) + 1, by=by, t=t or _now())
    rows.append(item)
    return item


def _how(ev):
    """`repeat` for the evidence folder of a play repeated at will (a Drill-down's, #272), else `check`."""
    import drill  # noqa: PLC0415  (drill imports diagnosis, which imports this module)
    return 'repeat' if ev.meta.get('kind') == drill.KIND else 'check'


def _join(log, case_dir, folder, ev, failure, rules, library=None, diagnosed=None, how=None):
    """Adds one occurrence (the evidence folder's failure) to the log and writes the code's attempt for it: its path,
    what changed since the last good check and the leads Diagnosis tried (`diagnosed`), the library run once. With a
    conclusion, its recipe runs on the new occurrence and the status follows. `how` defaults to what the evidence
    folder's check was (_how). The line it says."""
    meta = ev.meta
    n = len(log['occurrences']) + 1
    how = how or _how(ev)
    log['occurrences'].append({'n': n, 'evidence': os.path.relpath(folder, case_dir), 'check': meta.get('check'),
                               'label': meta.get('label'), 'release': failure['release'],
                               'date': (meta.get('t_start') or '')[:10], 'rules': rules, 'how': how})
    t = _now()
    for obs in (path_observation(ev, failure),) + ((changed_observation(ev),) if diagnosed is not None else ()):
        for q in obs['quotes']:
            q['occurrence'] = n
        _note(log, 'observations', {'occurrence': n, **obs}, 'code', t)
    for lead in (diagnosed or {}).get('leads') or []:
        _note(log, 'observations', {'occurrence': n, 'says': _lead_text(lead),
                                    'quotes': [{'occurrence': n, 'clue': c['clue'], 'text': c['facts'][0]}
                                               for c in lead.get('clues') or [] if c.get('facts')]}, 'code', t)
    names = sorted(clues.CLUES if library is None else library)
    done = [c for lead in (diagnosed or {}).get('leads') or [] for c in lead.get('clues') or []]
    ran, skipped = run_clues(log, case_dir, n, names, library, 'code', done)
    _note(log, 'attempts', {'occurrence': n, 'ran': ran, 'skipped': skipped, 'next': None}, 'code', t)
    line = f'occurrence {n} added ({how})'
    c = log['conclusion']
    if c:
        c['passed_on'], against = _recipe_passes(log, case_dir, c['recipe'], library)
        if against:  # the new occurrence says the concluded cause was not it: the case is open again
            c['against'] = [{'occurrence': k, 'why': why} for k, why in against]
            log['status'] = OPEN
            line += f'; the recipe says no on it ({against[0][1]}): open again'
        else:
            c['result'] = log['status'] = _result(log, c['passed_on'])
            line += f"; now {c['result']}"
    return line


def _occurrence_of(log, case_dir, folder, release=None, any_release=True):
    return next((o for o in log['occurrences'] if evidence_folder(case_dir, o) == os.path.normpath(folder)
                 and (any_release or o['release'] == release)), None)


def open_or_join(cases, folder, ev, failure, diagnosed, library=None):
    """Opens the Case log of one unproved failure, or adds this occurrence to the one with its fingerprint (as a
    `repeat` when a Drill-down played it again), and writes the code's attempt for it. Returns (id, whether the log is
    new, whether the occurrence is new)."""
    cid = next((i for i, log in logs(cases).items() if log['fingerprint'] == failure['fingerprint']), None) \
        or case_id(failure)  # a log fingerprinted again under new rules keeps its first id
    case_dir = os.path.join(cases, cid)
    with locked(case_dir):
        new = not os.path.exists(os.path.join(case_dir, CASE))
        log = _new_log(failure, cid, _now(), diagnosed.get('rules')) if new else load(case_dir)
        if _occurrence_of(log, case_dir, folder, failure['release'], any_release=False):
            return cid, False, False
        _join(log, case_dir, folder, ev, failure, diagnosed.get('rules'), library, diagnosed)
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


def _rules_of(log):
    return log.get('rules') or (log['occurrences'][0]['rules'] if log['occurrences'] else None)


def refingerprint(cases, rules):
    """Fingerprints again every Case log made with another masking version (story 25), from its first occurrence's
    evidence, so the same failure under the new rules joins it; the old fingerprint goes into `earlier`. Returns the ids
    it changed. A log whose evidence folder cannot be read keeps its fingerprint."""
    import diagnosis  # noqa: PLC0415
    changed = []
    for cid in logs(cases):
        d = os.path.join(cases, cid)
        with locked(d):
            log = load(d)
            if not log['occurrences'] or _rules_of(log) == rules['version']:
                continue
            occ = log['occurrences'][0]
            try:
                ev = evidence.read(evidence_folder(d, occ))
            except (OSError, ValueError):
                continue
            f = next((f for f in diagnosis.failures(ev) if f['release'] == occ['release']), None)
            if f is None:
                continue
            log.setdefault('earlier', []).append({'rules': _rules_of(log), 'fingerprint': log['fingerprint']})
            log['fingerprint'], log['rules'] = diagnosis.fingerprint(f, ev, rules), rules['version']
            save(d, log)
            changed.append(cid)
    return changed


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
    with locked(d):
        return _run_command(d, cid, names, occurrence, library)


def _run_command(d, cid, names, occurrence, library):
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
    looked up whole, spaces folded; none may be shorter than MIN_QUOTE. A quote with a `check` (a run folder's name)
    reads that check's folder in the same runs root instead (its meta.json, settings.json, ...)."""
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
        where = f"occurrence {n}'s {rel}"
        if q.get('check'):  # another check's folder in the same runs root (what changed since the last good one)
            root = _runs_root(folder)[0]
            folder = os.path.normpath(os.path.join(root, q['check']))
            where = f"{q['check']}'s {rel}"
            if os.path.dirname(folder) != os.path.normpath(root) or not os.path.isdir(folder):
                raise Refused(f"quote {i} names {q['check']}, not a check in the runs root")
        path = os.path.normpath(os.path.join(folder, rel))
        if not rel or os.path.isabs(rel) or not path.startswith(folder + os.sep) or not os.path.isfile(path):
            raise Refused(f'quote {i} names {rel or "no file"}, not a file in the '
                          + ('check folder' if q.get('check') else 'evidence folder'))
        with open(path, errors='replace') as f:
            if _fold(text) not in _fold(f.read()):
                raise Refused(f'quote {i} is not in {where}: "{text}"')


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
    with locked(d):
        return _add(d, cid, write)


def _add(d, cid, write):
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
        line = conclude(log, d, write)
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


WHOSE = ('KaijuFlow', 'AltMount', 'indexer', 'Usenet', 'test-only')  # the Casebook's, less `unknown`: a cause is named


def _recipe_passes(log, case_dir, recipe, library=None):
    """Runs the recipe's Clues on every occurrence (each only where it has not run): (the occurrences it passed on,
    those where a Clue gave the opposite yes or no). A can't tell is neither."""
    passed, against = [], []
    for o in log['occurrences']:
        run_clues(log, case_dir, o['n'], [r['clue'] for r in recipe], library, 'agent')
        said = {r['clue']: r['answer'] for r in log['clue_runs'] if r['occurrence'] == o['n']}
        wrong = [r for r in recipe if said[r['clue']] != r['answer']]
        if not wrong:
            passed.append(o['n'])
        elif any(said[r['clue']] in (clues.YES, clues.NO) for r in wrong):
            r = next(r for r in wrong if said[r['clue']] in (clues.YES, clues.NO))
            against.append((o['n'], f"{r['clue']} answered {said[r['clue']]} (wanted {r['answer']})"))
    return passed, against


def _result(log, passed):
    """proved when the recipe passed on a check's occurrence and on one repeated at will (a Drill-down or a replay);
    probable otherwise (spec #279, story 45)."""
    how = {o['n']: o['how'] for o in log['occurrences']}
    return 'proved' if any(how[n] == 'repeat' for n in passed) and any(how[n] == 'check' for n in passed) else 'probable'


def conclude(log, case_dir, write, library=None):
    """The agent's conclusion: the hypothesis that holds, every other one settled, the cause and the recipe of Clues
    that proves it, which must pass on the Case log's occurrences. Sets the status to proved or probable."""
    h = _hypothesis(log, write.get('hypothesis'))
    if h['status'] != 'holds':
        raise Refused(f"hypothesis {h['n']} does not hold yet ({h['status']})")
    if len(log['hypotheses']) < 2:
        raise Refused(f"keep several hypotheses at once: this Case log has {len(log['hypotheses'])}")
    still = [str(o['n']) for o in log['hypotheses'] if o['status'] == OPEN]
    if still:
        raise Refused(f"refute or hold every other hypothesis first: {', '.join(still)} still open")
    fields = {k: _text(write, k, w) for k, w in (('title', 'a conclusion names the cause in one sentence'),
                                                 ('saw', 'a conclusion says what the viewer saw'),
                                                 ('cause', 'a conclusion says what the cause is'))}
    if write.get('whose') not in WHOSE:
        raise Refused(f"whose must be one of: {', '.join(WHOSE)}")
    import casebook  # noqa: PLC0415  (the Casebook's own list of steps)
    if write.get('step') not in casebook.STEPS:
        raise Refused(f"step must be one of: {', '.join(casebook.STEPS)}")
    recipe = write.get('recipe')
    if not isinstance(recipe, list) or not recipe or any(
            not isinstance(r, dict) or r.get('answer') not in (clues.YES, clues.NO) or not r.get('clue') for r in recipe):
        raise Refused('a conclusion gives its recipe: Clues, each with the answer (yes or no) that proves the cause')
    recipe = [{'clue': r['clue'], 'answer': r['answer']} for r in recipe]
    check_quotes(log, case_dir, write.get('quotes') or [], 'a conclusion')
    passed, against = _recipe_passes(log, case_dir, recipe, library)
    if against:
        raise Refused(f'the recipe says no on occurrence {against[0][0]}: {against[0][1]}')
    if not passed:
        raise Refused("the recipe passed on no occurrence (a Clue could not tell): it proves nothing yet")
    result = _result(log, passed)
    log['conclusion'] = dict(fields, hypothesis=h['n'], whose=write['whose'], step=write['step'], recipe=recipe,
                             quotes=write['quotes'], passed_on=passed, result=result, t=_now(), by='agent')
    log['status'] = result
    return f"concluded: {result} (the recipe passed on occurrence {', '.join(map(str, passed))}" + \
        ('' if result == 'proved' else '; not repeated at will') + ')'


def repeat(cases, cid, folder, library=None):
    """`case repeat`: the evidence folder of a Drill-down or a replay that repeated the failure at will, added as an
    occurrence; with a conclusion, its recipe runs on it and the status follows."""
    d = case_dir_of(cases, cid)
    with locked(d):
        return _repeat(d, cid, folder, library)


def _repeat(d, cid, folder, library):
    import diagnosis  # noqa: PLC0415
    log = load(d)
    folder = os.path.normpath(os.path.abspath(folder))
    had = _occurrence_of(log, d, folder)
    if had:
        raise Refused(f"that evidence folder is occurrence {had['n']} already ({had['how']})")
    ev = evidence.read(folder)
    rules = diagnosis.load_rules()
    found = [dict(f, fingerprint=diagnosis.fingerprint(f, ev, rules)) for f in diagnosis.failures(ev)]
    mine = next((f for f in found if f['fingerprint'] == log['fingerprint']), None)
    if mine is None:
        raise Refused("no failure in that evidence folder has this Case log's fingerprint: "
                      + '; '.join(f['fingerprint'] for f in found))
    line = _join(log, d, folder, ev, mine, rules['version'], library, how='repeat')
    save(d, log)
    return f'{cid}: {line}'


# --------------------------------------------------------------------------- a solved case, written up

def _value(v):
    import casebook  # noqa: PLC0415
    return casebook.written(v)


def _sign(log):
    kind, where, reason = log['fingerprint'].split(' | ', 2)
    return ' | '.join((kind, where if where != 'none' else '*', reason.replace(' | ', '*') or '*'))


def _quote_line(log, q):
    occ = next(o for o in log['occurrences'] if o['n'] == q['occurrence'])
    where = f"Clue {q['clue']}" if q.get('clue') else f"`{q['file']}`"
    return f"- {where}, {occ['check']}: \"{q['text']}\""


def entry_text(log, entry_id):
    """The Casebook entry a concluded Case log is written up as (tools/brain/casebook/README.md)."""
    c = log['conclusion']
    occs = {o['n']: o for o in log['occurrences']}
    seen = []
    for n in c['passed_on']:
        o = occs[n]
        play = os.path.join(*os.path.normpath(o['evidence']).split(os.sep)[-2:])
        seen += [f"  - check: {_value(o['check'])}", f"    title: {_value(o['label'])}", f'    play: {_value(play)}',
                 f"    date: {o['date']}", f"    rules: {o['rules']}"]
    rules = occs[c['passed_on'][0]]['rules']
    front = ['---', f'id: {entry_id}', f"title: {_value(c['title'])}", f"kind: {log['kind']}", f"step: {c['step']}",
             f"whose: {c['whose']}", 'status: open', 'match:', f'  - rules: {rules}', f'    sign: {_value(_sign(log))}',
             'confirm:'] + [f"  - clue: {r['clue']}\n    answer: {r['answer']}" for r in c['recipe']] + \
        ['fix: none yet', 'seen:' if seen else 'seen: []'] + seen + ['---']
    held = _hypothesis(log, c['hypothesis'])
    quotes = []
    for q in c['quotes'] + held['quotes'] + ((held.get('result') or {}).get('quotes') or []):
        line = _quote_line(log, q)
        if line not in quotes:
            quotes.append(line)
    recipe = ', '.join(f"{r['clue']} answers {r['answer']}" for r in c['recipe'])
    checks = ', '.join(f"{occs[n]['check']} ({occs[n]['how']})" for n in c['passed_on'])
    proof = (f"Proved: it was repeated at will ({', '.join(occs[n]['check'] for n in c['passed_on'] if occs[n]['how'] == 'repeat')})."
             if c['result'] == 'proved' else
             'Probable, not proved: it was not repeated at will (no Drill-down or replay has played it again).')
    ruled = [f"- {h['says']}: refuted ({h['result']['says']}; Case log `{log['id']}`, hypothesis {h['n']})."
             for h in log['hypotheses'] if h['status'] == 'refuted']
    ruled += [f"- {o['says']} (Case log `{log['id']}`)." for o in log['observations']
              if o['by'] == 'code' and ': ruled out:' in o['says']]
    body = [
        '', '## What the viewer saw', '', c['saw'], '',
        '## Signs', '', f"The fingerprint: `{log['fingerprint']}`", ''] + quotes + [
        '', '## Cause', '', c['cause'], '',
        '## How it was proved', '', f'The confirming test is a recipe of Clues: {recipe}. It passed on {checks}. {proof}',
        f"Written up from Case log `{log['id']}` (the notes repo, `diagnosis/cases/{log['id']}/`).", '',
        '## Ruled out', ''] + (ruled or ['Nothing tested and rejected yet.']) + [
        '', '## Fix', '', 'None yet.' if c['whose'] == 'KaijuFlow' else
        f"None yet. A cause that is {c['whose']}'s gets a workaround, no ticket.", '',
        '## History', '', f"- {c['t'][:10]}: written up from Case log `{log['id']}` ({c['result']}) by the diagnosing "
        'agent (#287).', '']
    return '\n'.join(front + body)


def write_entry(cases, cid, entry_id, folder=None):
    """`case entry`: the concluded Case log written up as a Casebook entry, the format and index checked, the index
    written again. The Case log then names its entry and is no longer open."""
    import casebook  # noqa: PLC0415
    folder = casebook.FOLDER if folder is None else folder
    d = case_dir_of(cases, cid)
    with locked(d):
        return _write_entry(d, cid, entry_id, folder)


def _write_entry(d, cid, entry_id, folder):
    import casebook  # noqa: PLC0415
    log = load(d)
    if not log.get('conclusion'):
        raise Refused(f"{cid} is not concluded yet ({log['status']})")
    if not casebook.NAME.match(entry_id):
        raise Refused(f'an entry id is lower-case words joined by -, not {entry_id}')
    path = os.path.join(folder, entry_id + '.md')
    if os.path.exists(path):
        raise Refused(f'the Casebook has an entry {entry_id} already')
    with open(path, 'w') as f:
        f.write(entry_text(log, entry_id))
    try:
        casebook.read_entry(path)
    except casebook.FormatError as e:
        os.remove(path)
        raise Refused(f'the entry would break the Casebook format: {e}') from e
    casebook.write_index(folder)
    log['entry'] = entry_id
    save(d, log)
    return f'{cid}: Casebook entry {entry_id} written, index written again: commit both through review'


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
    p = sub.add_parser('repeat', parents=[common], help='add the evidence folder of a Drill-down or a replay that '
                       'repeated the failure at will')
    p.add_argument('id')
    p.add_argument('folder')
    p = sub.add_parser('entry', parents=[common], help='write a concluded Case log up as a Casebook entry')
    p.add_argument('id')
    p.add_argument('entry')
    p.add_argument('--casebook', help='the Casebook folder (default tools/brain/casebook)')
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
        elif a.cmd == 'repeat':
            print(repeat(a.cases, a.id, a.folder))
        elif a.cmd == 'entry':
            print(write_entry(a.cases, a.id, a.entry, a.casebook))
    except Refused as e:
        print(f'refused: {e}')
        return 1
    return 0


# --------------------------------------------------------------------------- starting the diagnosing agent

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the agent works in the repo
ROUTINE = 'tools/brain/docs/diagnosing-agent.md'
TOOK_MS = '20000'  # how long a started agent has to take its prompt (herdr agent wait --timeout)


def prompt(cases, ids, run_dir):
    return (f"You are the diagnosing agent (#287). Work the Case log{'s' if len(ids) > 1 else ''} {', '.join(ids)}, "
            f"opened or joined by the check {run_dir}. Follow {ROUTINE} step by step; every write goes through "
            f"`python3 -I tools/brain/diagnosis.py case <command> ... --cases {cases}`.")


def _json(r):
    return json.loads(r.stdout or '{}').get('result') or {}


def start_agent(cases, ids, run_dir, run=subprocess.run, popen=subprocess.Popen, env=None, name=None, cwd=REPO):
    """Starts the diagnosing agent and returns where it runs. Inside herdr (HERDR_ENV=1): a claude agent in a new pane
    of the workspace's `agents` tab (made when missing), prompted with the routine; outside it, `claude -p` detached,
    its output in <cases>/<name>.log."""
    env = os.environ if env is None else env
    name = name or 'diag-' + datetime.datetime.now().strftime('%m%d-%H%M%S')
    text = prompt(cases, ids, run_dir)
    if env.get('HERDR_ENV') == '1':
        def herdr(*args):
            r = run(['herdr', *args], capture_output=True, text=True, timeout=60, check=False)
            if r.returncode != 0:
                raise OSError(f"herdr {' '.join(args[:2])} failed: {(r.stderr or r.stdout or '').strip()[:200]}")
            return _json(r)

        def agents_tab():
            return next((t['tab_id'] for t in herdr('tab', 'list').get('tabs') or [] if t.get('label') == 'agents'), None)
        tab = agents_tab()
        if tab is None:
            herdr('tab', 'create', '--label', 'agents', '--cwd', cwd, '--no-focus')
            tab = agents_tab()
        pane = next((p['pane_id'] for p in herdr('pane', 'list').get('panes') or [] if p.get('tab_id') == tab), None)
        if pane is None:
            raise OSError('herdr has no pane in the agents tab')
        new = herdr('pane', 'split', pane, '--direction', 'down', '--cwd', cwd)['pane']['pane_id']
        herdr('agent', 'start', name, '--kind', 'claude', '--pane', new, '--', '--dangerously-skip-permissions')
        herdr('agent', 'prompt', name, text)  # no --wait: that waits out the agent's whole turn

        def took():  # the agent took the prompt: it is working on it (or asks, or is done already)
            r = run(['herdr', 'agent', 'wait', name, '--until', 'working', '--until', 'blocked', '--until', 'done',
                     '--timeout', TOOK_MS], capture_output=True, text=True, timeout=60, check=False)
            return r.returncode == 0
        if not took():  # the prompt sat in the input box: Enter sends it (as kf-next does)
            herdr('agent', 'send-keys', name, 'enter')
            if not took():
                raise OSError(f'herdr agent {name} did not take the prompt (not working {int(TOOK_MS) // 1000} s after '
                              'it, nor after Enter)')
        return f'herdr agent {name} in pane {new}'
    os.makedirs(cases, exist_ok=True)
    out = os.path.join(cases, name + '.log')
    with open(out, 'w') as f:
        p = popen(['claude', '-p', text, '--dangerously-skip-permissions'], cwd=cwd, stdout=f, stderr=subprocess.STDOUT,
                  stdin=subprocess.DEVNULL, start_new_session=True)
    return f'claude -p (pid {p.pid}), its output in {out}'


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
