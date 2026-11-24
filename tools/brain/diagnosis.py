"""Diagnosis (#283, spec #279): one call, an evidence folder in, and for each failure of that play one answer.

    python3 -I tools/brain/diagnosis.py diagnose <check folder | evidence folder>   diagnose and write diagnosis.json
    python3 -I tools/brain/diagnosis.py record <check folder>     put its proved occurrences and ruled-out leads on the Casebook
    python3 -I tools/brain/diagnosis.py refingerprint [runs root]  fingerprint every stored failure with the current rules
    python3 -I tools/brain/diagnosis.py fix <check folder> [--casebook DIR] [--dry-run]   its proved causes' fixes (#288)
    python3 -I tools/brain/diagnosis.py case <list|show|run|add|repeat|entry> ...   work a Case log (#287; case --help)

The answers: *found: X, proved by Clues A, B* (a lead's confirming recipe passed on this failure's own evidence),
*suspected: X (no confirming test)* (a look-alike whose recipe cannot run yet), or *new* (no entry matches, or every
lead was ruled out). A fingerprint match only orders the leads; only a passing recipe names a cause. A lead whose recipe
fails is ruled out for this failure. The fingerprint (kind | where it failed | the reason, masked) follows the masking
rules in masking-rules.json; every answer records the rules' version, and a new version fingerprints every stored
failure again. Formats: tools/brain/docs/formats.md, "Diagnosis".
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
import casebook  # noqa: E402
import caselog  # noqa: E402
import clues  # noqa: E402
import evidence  # noqa: E402
import fixing  # noqa: E402
import scoreboard  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, 'masking-rules.json')
LIST_OWN = ('list_filter', 'list_sort', 'fallback_group', 'list_build', 'head_start', 'list')
EVENTS = ('played', 'play_failed')
SEARCH_LINES = ('search',)  # Kaiju Search's evidence lines (dev switch only, #285): no step, so never where it failed
FAILED_LINE = re.compile(r'❌ (?:Failed: (?P<a>.*)|Stream failed \[\d+/\d+\] .*?: (?P<b>AltMount .*|.*))$')
NEAR_S = 2  # a KaijuFlow failure line belongs to the failed step it is this near to (builds before play_failed)


# --------------------------------------------------------------------------- the fingerprint

def load_rules(path=RULES):
    with open(path) as f:
        rules = json.load(f)
    if not isinstance(rules.get('version'), int) or rules['version'] < 1:
        raise ValueError(f'{path}: version must be a whole number from 1')
    return rules


def _checked(ev, release):
    return any(s.get('step') == 'play_check' and s.get('ok') and s.get('title') == release for s in ev.steps)


def _line(s):
    return f"{s['step']} {'ok' if s.get('ok') else 'not ok'}"


def _failing_step(ev, release):
    """The step line where one Source failed: its first prepare step that was not ok, else its last prepare step."""
    steps = [s for s in ev.steps if s.get('title') == release and s.get('step') in clues.PREPARE]
    bad = [s for s in steps if not s.get('ok')]
    return bad[0] if bad else (steps[-1] if steps else None)


def _reason(ev, release, step):
    """Why one Source failed: its `play_failed` reason, or (builds from before #242) KaijuFlow's own failure line
    nearest to its failing step."""
    for s in ev.steps:
        if s.get('step') == 'play_failed' and s.get('title') == release and s.get('reason'):
            return s['reason']
    if step is None:
        return ''
    at, best = br.parse_ts(step['t']), None
    for line in ev.kf_lines:
        m = FAILED_LINE.search(line)
        t = clues._ts(line)
        if not m or t is None:
            continue
        gap = abs((t - at).total_seconds())
        if gap <= NEAR_S and (best is None or gap < best[0]):
            best = (gap, (m.group('a') or m.group('b') or '').strip())
    return best[1] if best else ''


def failures(ev):
    """The failures of one play: one per Source that failed for it (AltMount refused it, or it failed after its check),
    in the order they failed, and one for the play itself when no Source failed (nothing to play, a fail before any
    Source, a slow play) or when the wrong title played (story 71: its refused Sources are their own failures, check
    misses or fallbacks, as video came). Each: release, kind, step (the failing step line or None), where, reason."""
    o = ev.meta.get('outcome') or {}
    if not ev.meta.get('kept_because'):
        return []  # a play that went fine (a Drill-down keeps its folder too, #272) has no failure
    if o.get('outcome') == 'fail':
        play_kind = 'wrong title' if (o.get('why') or '').startswith('the wrong title played') else 'fail'
    elif o.get('outcome') == 'nothing to play':
        play_kind = 'nothing to play'
    else:
        play_kind = None
    out = []
    for f in ev.meta.get('failed_sources') or []:
        if f.get('failed') not in ('play', 'import'):
            continue  # a Source its Play-time check stopped is the check working, not a failure
        release = f['release']
        step = _failing_step(ev, release)
        kind = play_kind if play_kind in ('fail', 'nothing to play') else \
            ('check miss' if _checked(ev, release) else 'fallback')
        out.append({'release': release, 'kind': kind, 'step': step, 'where': _line(step) if step else 'none',
                    'reason': _reason(ev, release, step)})
    if out and play_kind != 'wrong title':
        return out
    steps = [s for s in ev.steps if s.get('step') not in LIST_OWN + EVENTS + SEARCH_LINES]  # the last step line
    step = steps[-1] if steps else None
    kind = play_kind or ('slow play' if o.get('slow') else ev.meta.get('kept_because') or 'fail')
    return out + [{'release': None, 'kind': kind, 'step': step, 'where': _line(step) if step else 'none',
                   'reason': o.get('why') or '' if play_kind else ''}]


def _never_a_sign(ev):
    """{placeholder: [values]} of what the evidence names that is never part of a fingerprint."""
    meta = ev.meta
    title = meta.get('title') or []
    titles = {meta.get('label'), title[2] if len(title) > 2 else None}
    titles |= {re.sub(r'\s+S\d+E\d+$', '', t) for t in titles if t}
    releases = {s.get('title') for s in ev.steps} | {f.get('release') for f in meta.get('failed_sources') or []}
    releases.add((meta.get('outcome') or {}).get('release'))
    indexers = {s.get('source') for s in ev.steps}
    indexers |= {i.get('indexer') for i in (meta.get('outcome') or {}).get('indexers') or [] if isinstance(i, dict)}
    jobs = {str(s['job']) for s in ev.steps if s.get('job') is not None}
    return {'title': titles, 'indexer': indexers, 'release': releases, 'job': jobs}


def mask(reason, ev, rules):
    """The reason with what is never a sign replaced (the title, indexer, release names and job ids the evidence
    names), then the masks in order; a `keep` mask protects what it matches from the masks after it."""
    parts = [(reason or '', False)]  # (text, done)

    def apply(pattern, repl, flags=0):
        nonlocal parts
        out = []
        for text, done in parts:
            if done:
                out.append((text, done))
                continue
            at = 0
            for m in re.finditer(pattern, text, flags):
                if m.start() == m.end():
                    continue
                out.append((text[at:m.start()], False))
                out.append((m.group(0) if repl is None else repl, True))
                at = m.end()
            out.append((text[at:], False))
        parts = [(t, d) for t, d in out if t]

    values = []
    for name, found in _never_a_sign(ev).items():
        placeholder = rules['never_a_sign'].get(name)
        if placeholder:
            values += [(v, placeholder) for v in found if v and len(v) >= 2]
    for value, placeholder in sorted(values, key=lambda v: -len(v[0])):
        edge = r'(?<![A-Za-z0-9])' if value[0].isalnum() else ''
        tail = r'(?![A-Za-z0-9])' if value[-1].isalnum() else ''
        apply(edge + re.escape(value) + tail, placeholder, re.I)
    for m in rules['masks']:
        apply(m['pattern'], None if m.get('keep') else m['with'])
    return re.sub(r'\s+', ' ', ''.join(t for t, _ in parts)).strip()


def fingerprint(failure, ev, rules):
    return f"{failure['kind']} | {failure['where']} | {mask(failure['reason'], ev, rules) or '-'}"


# --------------------------------------------------------------------------- matching and proving

def sign_fits(sign, fp):
    """Whether a Casebook sign (`<kind> | <step> ok|not ok | <reason>`, `*` for anything) fits a fingerprint."""
    want, got = sign.split(' | ', 2), fp.split(' | ', 2)
    if len(want) != 3 or len(got) != 3:
        return False
    for w, g in zip(want[:2], got[:2]):
        if w != '*' and w != g:
            return False
    pattern = '.*'.join(re.escape(p) for p in want[2].split('*'))
    return re.fullmatch(pattern, got[2], re.S) is not None


def load_index(folder=None):
    folder = casebook.FOLDER if folder is None else folder
    with open(os.path.join(folder, casebook.INDEX)) as f:
        return json.load(f)['entries']


def leads(fp, entries):
    """The entries whose match fits, most occurrences first, each with the sign that fit."""
    out = []
    for e in entries:
        sign = next((m for m in e['match'] if sign_fits(m['sign'], fp)), None)
        if sign:
            out.append({'id': e['id'], 'sign': sign['sign'], 'sign_rules': sign['rules'], 'occurrences': e['occurrences'],
                        'status': e['status'], 'whose': e['whose'], 'confirm': e['confirm']})
    return sorted(out, key=lambda lead: (-lead['occurrences'], lead['id']))


def prove(lead, ev, failure, library):
    """Runs the lead's confirming recipe on this failure's evidence: `result` proved, ruled out (an answer opposite to the
    recipe's), can't tell, or no confirming test (no evidence kept, or a Clue not built yet)."""
    confirm = lead['confirm']
    if confirm == casebook.NO_EVIDENCE:
        return dict(lead, result='no confirming test', why=casebook.NO_EVIDENCE, clues=[])
    missing = [c['clue'] for c in confirm if c['clue'] not in library]
    if missing:
        return dict(lead, result='no confirming test', why='Clues not built yet: ' + ', '.join(missing), clues=[])
    ran = []
    for item in confirm:
        r = clues.run(item['clue'], ev, failure, library)
        ran.append(dict(r, wanted=item['answer']))
    if any(r['answer'] != r['wanted'] and r['answer'] in (clues.YES, clues.NO) for r in ran):
        result = 'ruled out'
    elif all(r['answer'] == r['wanted'] for r in ran):
        result = 'proved'
    else:
        result = "can't tell"
    return dict(lead, result=result, clues=ran)


def verdict(tried):
    """(verdict, cause, proved_by, says) from the tried leads."""
    proved = [t for t in tried if t['result'] == 'proved']
    if proved:
        names = [c['clue'] for c in proved[0]['clues']]
        also = ''.join(f"; also found: {t['id']}" for t in proved[1:])
        return 'found', proved[0]['id'], names, f"found: {proved[0]['id']}, proved by Clues {', '.join(names)}{also}"
    open_ = [t for t in tried if t['result'] in ('no confirming test', "can't tell")]
    if open_:
        t = open_[0]
        why = 'no confirming test' if t['result'] == 'no confirming test' else "its confirming test could not tell"
        return 'suspected', t['id'], [], f"suspected: {t['id']} ({why})"
    if tried:
        return 'new', None, [], 'new: every lead was ruled out (' + ', '.join(t['id'] for t in tried) + ')'
    return 'new', None, [], 'new: no Casebook entry matches'


def diagnose(folder, entries=None, library=None, rules=None):
    """Diagnosis of one evidence folder: {'folder', 'check', 'title', 'label', 'rules', 'failures': [...]}, each failure
    {'release', 'kind', 'where', 'reason', 'fingerprint', 'leads' (tried, in order), 'verdict', 'cause', 'proved_by',
    'says'}."""
    ev = evidence.read(folder)
    entries = load_index() if entries is None else entries
    library = clues.CLUES if library is None else library
    rules = load_rules() if rules is None else rules
    out = []
    for f in failures(ev):
        fp = fingerprint(f, ev, rules)
        tried = [prove(lead, ev, f, library) for lead in leads(fp, entries)]
        v, cause, proved_by, says = verdict(tried)
        out.append({'release': f['release'], 'kind': f['kind'], 'where': f['where'], 'reason': f['reason'],
                    'fingerprint': fp, 'leads': tried, 'verdict': v, 'cause': cause, 'proved_by': proved_by, 'says': says})
    meta = ev.meta
    return {'folder': os.path.basename(os.path.normpath(folder)), 'check': meta.get('check'), 'title': meta.get('title'),
            'label': meta.get('label'), 'rules': rules['version'], 'failures': out}


# --------------------------------------------------------------------------- stored failures: a check's evidence folders

STORED = 'diagnosis.json'  # in each evidence folder (that play's answers) and in the check's folder (the summary)


def _write_json(path, data):
    with open(path, 'w') as f:
        f.write(json.dumps(data, indent=1, ensure_ascii=False) + '\n')


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def evidence_folders(run_dir):
    d = os.path.join(run_dir, evidence.DIR)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    return [os.path.join(d, n) for n in names if os.path.exists(os.path.join(d, n, 'evidence.json'))]


def store(folder, result, earlier=()):
    """Writes one play's answers into its evidence folder, with the fingerprints of earlier rule versions."""
    _write_json(os.path.join(folder, STORED), dict(result, earlier=list(earlier)))


def diagnose_stored(folder, entries=None, library=None, rules=None):
    """Diagnoses one stored evidence folder and writes its diagnosis.json; an earlier answer made with other rules goes
    into `earlier` (its version and fingerprints)."""
    old = _read_json(os.path.join(folder, STORED))
    result = diagnose(folder, entries, library, rules)
    earlier = list((old or {}).get('earlier') or [])
    if old and old.get('rules') != result['rules']:
        earlier.append({'rules': old.get('rules'), 'fingerprints': [f.get('fingerprint') for f in old.get('failures') or []]})
    store(folder, result, earlier)
    return dict(result, earlier=earlier)


def counts(plays):
    """The report's numbers over a check's answers (story 57)."""
    fs = [f for p in plays for f in p.get('failures') or []]
    return {'failures': len(fs), 'new': sum(1 for f in fs if not f['leads']), 'matched': sum(1 for f in fs if f['leads']),
            'proved': sum(1 for f in fs if f['verdict'] == 'found'),
            'unexplained': sum(1 for f in fs if f['verdict'] != 'found'),
            'suspected': sum(1 for f in fs if f['verdict'] == 'suspected'),
            'unreadable': sum(1 for p in plays if p.get('error'))}


def summarize(run_dir, plays, rules, library=None, kept=None):
    """Writes the check's summary; `kept` are the fields of its earlier summary to keep (a new masking version)."""
    keep = ('release', 'kind', 'fingerprint', 'verdict', 'cause', 'proved_by', 'says')
    out = dict(kept or {}, rules=rules['version'], counts=counts(plays), plays=[])
    if library is not None:
        out['library'] = sorted(library)  # the Clues there were, so the next check tells reused from new (#288)
    for p in plays:
        row = {'evidence': os.path.relpath(p['path'], run_dir), 'label': p.get('label')}
        if p.get('error'):
            row['error'] = p['error']
        row['failures'] = [{k: f.get(k) for k in keep} for f in p.get('failures') or []]
        out['plays'].append(row)
    _write_json(os.path.join(run_dir, STORED), out)
    return out


def diagnose_check(run_dir, entries=None, library=None, rules=None):
    """Diagnoses every evidence folder of one check (its run folder): each folder's diagnosis.json, and the check's
    summary in <run folder>/diagnosis.json. An unreadable folder is said in the summary and the others go on."""
    entries = load_index() if entries is None else entries
    rules = load_rules() if rules is None else rules
    plays = []
    for folder in evidence_folders(run_dir):
        try:
            plays.append(dict(diagnose_stored(folder, entries, library, rules), path=folder))
        except Exception as e:  # noqa: BLE001  (one broken folder never stops the others)
            plays.append({'path': folder, 'error': br.scrub_text(f'{type(e).__name__}: {e}'), 'failures': []})
    return summarize(run_dir, plays, rules, clues.CLUES if library is None else library)


def stored_checks(root):
    """The run folders under `root` (and its archive/) that hold an evidence folder."""
    out = []
    for base in (root, os.path.join(root, 'archive')):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        out += [os.path.join(base, n) for n in names if evidence_folders(os.path.join(base, n))]
    return out


def refingerprint(root, rules=None, entries=None, library=None):
    """Fingerprints again every stored failure under the runs root whose answers were made with another rules version
    (and diagnoses it again: the leads follow the fingerprint); returns the evidence folders it changed."""
    rules = load_rules() if rules is None else rules
    entries = load_index() if entries is None else entries
    changed = []
    for run_dir in stored_checks(root):
        mine = []
        for folder in evidence_folders(run_dir):
            old = _read_json(os.path.join(folder, STORED))
            if old is not None and old.get('rules') != rules['version']:
                mine.append(folder)
        if mine:
            for folder in mine:
                diagnose_stored(folder, entries, library, rules)
            changed += mine
            plays = []
            for folder in evidence_folders(run_dir):
                d = _read_json(os.path.join(folder, STORED))
                if d is not None:
                    plays.append(dict(d, path=folder))
            old = _read_json(os.path.join(run_dir, STORED)) or {}
            summarize(run_dir, plays, rules, kept={k: v for k, v in old.items() if k not in ('rules', 'counts', 'plays')})
    return changed


# --------------------------------------------------------------------------- after a check, and its report

def live_clues(run_dir, open_usenet, now=None):
    """The live read-only Clues (clues.LIVE), asked once for every failed Source of the check whose NZB its evidence
    folder kept, over one connection (`open_usenet()`, opened only when there is something to ask and closed at the
    end); each folder's answers go into its live.json. Returns how many Sources were asked about."""
    jobs = []
    for folder in evidence_folders(run_dir):
        ev = evidence.read(folder)
        mine = [f for f in failures(ev) if f['release'] and ev.nzb(f['release']) is not None]
        if mine:
            jobs.append((folder, ev, mine))
    if not jobs:
        return 0
    when = br.iso(now or datetime.datetime.now(datetime.timezone.utc))
    try:
        usenet = open_usenet()
    except Exception as e:  # noqa: BLE001  (no provider login: the Clues that need it say they could not tell)
        for folder, _, _ in jobs:
            _write_json(os.path.join(folder, evidence.LIVE), {'t': when, 'error': br.scrub_text(f'{type(e).__name__}: {e}')})
        return 0
    asked = 0
    try:
        for folder, ev, mine in jobs:
            answers = {}
            for f in mine:
                asked += 1
                for name in sorted(clues.LIVE):
                    r = clues.run_live(name, ev, f, usenet)
                    answers.setdefault(name, {})[f['release']] = {'answer': r['answer'], 'facts': r['facts']}
            _write_json(os.path.join(folder, evidence.LIVE), {'t': when, 'clues': answers})
    finally:
        usenet.close()
    return asked


def open_cases(run_dir, cases, library=None):
    """A Case log for every failure of the check with no proved cause (new or suspected): opened, or joined when one
    with its fingerprint is there, the code's attempt written into it (caselog.open_or_join). [{'id', 'status',
    'occurrences', 'new'}], one per Case log, in the order the failures came."""
    out = {}
    for folder in evidence_folders(run_dir):
        d = _read_json(os.path.join(folder, STORED))
        if not d:
            continue
        ev = evidence.read(folder)
        for f, said in zip(failures(ev), d['failures']):
            if said['verdict'] == 'found':
                continue
            f = dict(f, fingerprint=said['fingerprint'])
            cid, new, _ = caselog.open_or_join(cases, folder, ev, f, dict(said, rules=d['rules']), library)
            log = caselog.load(os.path.join(cases, cid))
            row = out.setdefault(cid, {'id': cid, 'status': log['status'], 'occurrences': 0, 'new': False})
            row.update(status=log['status'], occurrences=len(log['occurrences']), new=row['new'] or new)
    return list(out.values())


def _start_agent(summary, run_dir, cases, agent, alert):
    """Starts the diagnosing agent on the check's open Case logs and tells the owner in one line (story 49)."""
    waiting = [k['id'] for k in summary.get('cases') or [] if k['status'] == caselog.OPEN]
    if not waiting or agent is None:
        return
    try:
        started, error = agent(cases, waiting, run_dir), None
    except Exception as e:  # noqa: BLE001  (the check's report comes first; the line says so)
        started, error = None, br.scrub_text(f'{type(e).__name__}: {e}')
    summary['agent'] = {'started': started, 'error': error, 'cases': waiting}
    n = sum(1 for p in summary['plays'] for f in p['failures'] if f['verdict'] != 'found')
    logs = f"Case log{'s' if len(waiting) > 1 else ''} {', '.join(waiting)}"
    line = f"Diagnosis: {_plural(n, 'failure')} in {os.path.basename(os.path.normpath(run_dir))} " \
           f"{'has' if n == 1 else 'have'} no proved cause; "
    line += f'the diagnosing agent is on {logs} ({started}).' if error is None else \
        f"the diagnosing agent could not start ({error}): {logs} wait{'s' if len(waiting) == 1 else ''} for it."
    if alert is not None:
        try:
            alert(line)
        except Exception:  # noqa: BLE001, S110  (an alert that fails never stops the check)
            pass


def stored_plays(run_dir):
    """Every diagnosed evidence folder of a check: {'path', 'evidence' (relative to the run folder), 'meta', 'diagnosis'}."""
    out = []
    for folder in evidence_folders(run_dir):
        d = _read_json(os.path.join(folder, STORED))
        if d is not None:
            out.append({'path': folder, 'evidence': os.path.relpath(folder, run_dir), 'meta': evidence.read(folder).meta,
                        'diagnosis': d})
    return out


def after_check(run_dir, runs_root, entries=None, library=None, rules=None, usenet=None, cases=None, agent=None,
                alert=None, book=None, tracker=None):
    """What a check runs by itself at its end when a play left an evidence folder: the live Clues asked once (when
    `usenet` opens the connection for them), every stored failure under the runs root fingerprinted again if the masking
    rules changed, then this check's plays diagnosed against the Casebook in `book` (default the repo's), every proved
    cause's fix (fixing.after_check: a KaijuFlow cause's ticket, filed through `tracker` unless it is None, a dry run),
    and every failure with no proved cause put in its Case log under `cases`; when one of those logs is open,
    `agent(cases, ids, run_dir)` starts the diagnosing agent on them and `alert(line)` tells the owner in one line. The
    summary, or None when the check left no evidence folder."""
    if not evidence_folders(run_dir):
        return None
    if usenet is not None:
        live_clues(run_dir, usenet)
    book = casebook.FOLDER if book is None else book
    rules = load_rules() if rules is None else rules
    entries = load_index(book) if entries is None else entries
    refingerprint(runs_root, rules, entries, library)
    summary = diagnose_check(run_dir, entries, library, rules)
    summary['fixes'] = fixing.after_check(run_dir, stored_plays(run_dir), book, tracker)
    if cases is not None:
        summary['cases'] = open_cases(run_dir, cases, library)
        summary['open_cases'] = caselog.count_open(cases)
        _start_agent(summary, run_dir, cases, agent, alert)
    summary['scoreboard'] = score(run_dir, runs_root, summary, library, book, cases)
    _write_json(os.path.join(run_dir, STORED), summary)
    return summary


def score(run_dir, runs_root, summary, library, book, cases):
    """The scoreboard's four extra numbers (story 58, scoreboard.score) for a check just diagnosed."""
    name = os.path.basename(os.path.normpath(run_dir))
    earlier = []
    for d in stored_checks(runs_root):
        other = os.path.basename(os.path.normpath(d))
        s = _read_json(os.path.join(d, STORED)) if other < name else None
        if s is not None:
            earlier.append((other, s))
    earlier.sort(key=lambda e: e[0])
    return scoreboard.score(name, summary, stored_plays(run_dir), clues.CLUES if library is None else library, earlier,
                            casebook.load(book)[0], None if cases is None else caselog.logs(cases))


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def report_section(summary, error=None):
    """The check report's Diagnosis section (story 57): the numbers, then one line per failure."""
    lines = ['## Diagnosis', '']
    if error:
        return lines + [f'Diagnosis could not run: {error}.']
    if not summary:
        return lines + ['None: no play failed or fell back.']
    c = summary['counts']
    open_ = summary.get('open_cases')
    lines.append(f"{_plural(c['failures'], 'failure')}: {c['new']} new, {c['matched']} matched, {c['proved']} proved, "
                 f"{c['unexplained']} unexplained; open Case logs: {'not kept' if open_ is None else open_}.")
    lines.append('')
    for p in summary['plays']:
        if p.get('error'):
            lines.append(f"- {p.get('label') or p['evidence']}: its evidence folder could not be read: {p['error']}.")
        for f in p['failures']:
            source = f"{f['release']}: " if f.get('release') else ''
            lines.append(f"- {p.get('label') or p['evidence']}: {source}{f['says']}.")
    if summary.get('fixes'):
        lines += ['', 'Fixing:', ''] + fixing.report_lines(summary['fixes'])
    if summary.get('cases'):
        lines.append('')
        for k in summary['cases']:
            lines.append(f"- Case log `{k['id']}`: {'opened' if k['new'] else 'one more occurrence'} "
                         f"({_plural(k['occurrences'], 'occurrence')}, {k['status']}).")
    a = summary.get('agent')
    if a:
        lines += ['', f"The diagnosing agent started: {a['started']}." if a['error'] is None else
                  f"The diagnosing agent could not start: {a['error']}."]
    if summary.get('scoreboard'):
        lines += [''] + scoreboard.report_lines(summary['scoreboard'])
    return lines


# --------------------------------------------------------------------------- recording on the Casebook

_value = casebook.written


def _seen_lines(item):
    keys = [k for k in ('check', 'title', 'play', 'date', 'rules') if k in item]
    return [f'  - {keys[0]}: {_value(item[keys[0]])}'] + [f'    {k}: {_value(item[k])}' for k in keys[1:]]


def _ruled_out_line(when, check, label, play, lead):
    said = '; '.join(f"{c['clue']} answered {c['answer']} (wanted {c['wanted']})" for c in lead['clues']
                     if c['answer'] != c['wanted'])
    return (f"- {when}, {check}, {label} ({play}): matched `{lead['sign']}` (rules {lead['sign_rules']}), but its "
            f"confirming test said no: {said}. (Diagnosis, #283)")


def _add_to_entry(path, seen=(), ruled=()):
    with open(path) as f:
        lines = f.read().split('\n')
    end = lines.index('---', 1)
    if seen:
        if lines[end - 1].strip() == 'seen: []':
            lines[end - 1] = 'seen:'
        lines[end:end] = [line for item in seen for line in _seen_lines(item)]
    if ruled:
        at = lines.index('## Ruled out')
        nxt = next(i for i in range(at + 1, len(lines)) if lines[i].startswith('## '))
        body = [line for line in lines[at + 1:nxt] if line.strip()]
        if body == ['Nothing tested and rejected yet.']:
            body = []
        lines[at + 1:nxt] = [''] + body + list(ruled) + ['']
    with open(path, 'w') as f:
        f.write('\n'.join(lines))


def record(run_dir, folder=casebook.FOLDER):
    """Puts a diagnosed check on the Casebook: every proved lead's occurrence in its entry's `seen` (with the rules
    version), every ruled-out lead in its entry's Ruled out, then the index written again. An occurrence or line already
    there is not added twice. Returns {entry id: {'seen': n, 'ruled_out': n}}. The check's own run leaves the Casebook
    alone (the repository stays clean for the next check's preflight): run this, then commit the entries."""
    entries, problems = casebook.load(folder)
    if problems:
        raise casebook.FormatError('\n'.join(problems))
    texts = {}
    for i, e in entries.items():
        with open(os.path.join(folder, e['file'])) as f:
            texts[i] = f.read()
    add = {}
    for ev_folder in evidence_folders(run_dir):
        d = _read_json(os.path.join(ev_folder, STORED))
        if not d:
            continue
        meta = evidence.read(ev_folder).meta
        when = (meta.get('t_start') or '')[:10]
        play = os.path.relpath(ev_folder, run_dir)
        check, label = meta.get('check'), meta.get('label')
        for f in d['failures']:
            for lead in f['leads']:
                if lead['id'] not in entries:
                    continue
                slot = add.setdefault(lead['id'], {'seen': [], 'ruled_out': []})
                if lead['result'] == 'proved':
                    item = {'check': check, 'title': label, 'play': play, 'date': when, 'rules': d['rules']}
                    have = [{k: s.get(k) for k in ('check', 'title', 'play')} for s in entries[lead['id']]['seen']]
                    if {k: item[k] for k in ('check', 'title', 'play')} not in have + [
                            {k: s[k] for k in ('check', 'title', 'play')} for s in slot['seen']]:
                        slot['seen'].append(item)
                elif lead['result'] == 'ruled out':
                    line = _ruled_out_line(when, check, label, play, lead)
                    if line not in texts[lead['id']] and line not in slot['ruled_out']:
                        slot['ruled_out'].append(line)
    out = {}
    for i, slot in sorted(add.items()):
        if slot['seen'] or slot['ruled_out']:
            _add_to_entry(os.path.join(folder, entries[i]['file']), slot['seen'], slot['ruled_out'])
            out[i] = {'seen': len(slot['seen']), 'ruled_out': len(slot['ruled_out'])}
    summary = _read_json(os.path.join(run_dir, STORED)) or {}
    # a Drill-down's marks first (#272): a comeback it reopened is then not reopened again by its fix
    for i, changed in fixing.record_drill(summary.get('drill'), folder).items():
        out.setdefault(i, {'seen': 0, 'ruled_out': 0})['drill'] = changed
    for i, changed in fixing.record(run_dir, summary.get('fixes') or [], folder).items():
        out.setdefault(i, {'seen': 0, 'ruled_out': 0})['fixes'] = changed
    casebook.write_index(folder)
    return out


# --------------------------------------------------------------------------- the command

def _say(play):
    name = os.path.basename(play['path'])
    if play.get('error'):
        return [f"{name}: its evidence folder could not be read: {play['error']}"]
    return [f"{name}: {play.get('label')}: " + (f"{f['release']}: " if f.get('release') else '') + f['says']
            for f in play['failures']]


def diagnose_again(run_dir, entries=None):
    """A check diagnosed again by hand (`diagnose`, `fix`): its plays' answers new, the rest of its summary (fixes, the
    Drill-down's marks, Case logs, scoreboard, ...) kept and written back. The summary."""
    old = _read_json(os.path.join(run_dir, STORED)) or {}
    summary = dict(old, **diagnose_check(run_dir, entries))
    _write_json(os.path.join(run_dir, STORED), summary)
    return summary


def fix(run_dir, book=None, tracker=None):
    """`diagnosis.py fix`: the check diagnosed again against the Casebook in `book` (one that has the cause now: a Case
    log written up as an entry) and its fixes made as after the check (fixing.after_check); the rest of the check's
    summary is kept. Returns the fixes."""
    book = casebook.FOLDER if book is None else book
    summary = diagnose_again(run_dir, load_index(book))
    summary['fixes'] = fixing.after_check(run_dir, stored_plays(run_dir), book, tracker)
    _write_json(os.path.join(run_dir, STORED), summary)
    return summary['fixes']


def main(argv):
    if len(argv) > 1 and argv[1] == 'case':
        return caselog.main(argv[2:])
    if len(argv) > 1 and argv[1] == 'fix':
        import argparse  # noqa: PLC0415
        ap = argparse.ArgumentParser(prog='diagnosis.py fix', description='Diagnose a check again with the Casebook as it '
                                     'is now, and make its proved causes\' fixes (a KaijuFlow cause files its ticket).')
        ap.add_argument('folder', help='the check folder')
        ap.add_argument('--casebook', help='the Casebook folder (default the repo\'s)')
        ap.add_argument('--dry-run', action='store_true', help='write the fix tickets\' text, file none')
        a = ap.parse_args(argv[2:])
        fixes = fix(a.folder, a.casebook, None if a.dry_run else fixing.GitHub())
        for line in fixing.report_lines(fixes) or ['No proved cause: nothing to fix.']:
            print(line)
        return 0
    if len(argv) < 2 or argv[1] not in ('diagnose', 'record', 'refingerprint') or \
            len(argv) > 3 or (argv[1] != 'refingerprint' and len(argv) != 3):
        print(__doc__.strip().split('\n\n')[1], file=sys.stderr)
        return 2
    if argv[1] == 'refingerprint':
        root = argv[2] if len(argv) == 3 else os.path.expanduser('~/kaijuflow-notes/brain-runs')
        changed = refingerprint(root)
        print(f"{_plural(len(changed), 'stored failure')} fingerprinted again with rules version {load_rules()['version']}")
        return 0
    folder = argv[2]
    if argv[1] == 'record':
        for i, n in record(folder).items():
            print(f"{i}: {_plural(n['seen'], 'occurrence')} added, {_plural(n['ruled_out'], 'ruled-out line')} added"
                  + ''.join(f"; {what}: {', '.join(n[k])}" for k, what in (('drill', 'Drill-down'), ('fixes', 'fixes'))
                            if n.get(k)))
        print('Casebook index written again: commit the entries and the index.')
        return 0
    if os.path.exists(os.path.join(folder, 'evidence.json')):
        for line in _say(dict(diagnose_stored(folder), path=folder)):
            print(line)
        return 0
    summary = diagnose_again(folder)
    for p, row in zip(evidence_folders(folder), summary['plays']):
        for line in _say(dict(row, path=p)):
            print(line)
    c = summary['counts']
    print(f"{_plural(c['failures'], 'failure')}: {c['new']} new, {c['matched']} matched, {c['proved']} proved, "
          f"{c['unexplained']} unexplained")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
