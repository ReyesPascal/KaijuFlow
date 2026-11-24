"""Diagnosis (#283, spec #279): one call, an evidence folder in, and for each failure of that play one answer.

    python3 -I tools/brain/diagnosis.py diagnose <check folder | evidence folder>   diagnose and write diagnosis.json
    python3 -I tools/brain/diagnosis.py record <check folder>     put its proved occurrences and ruled-out leads on the Casebook
    python3 -I tools/brain/diagnosis.py refingerprint [runs root]  fingerprint every stored failure with the current rules

The answers: *found: X, proved by Clues A, B* (a lead's confirming recipe passed on this failure's own evidence),
*suspected: X (no confirming test)* (a look-alike whose recipe cannot run yet), or *new* (no entry matches, or every
lead was ruled out). A fingerprint match only orders the leads; only a passing recipe names a cause. A lead whose recipe
fails is ruled out for this failure. The fingerprint (kind | where it failed | the reason, masked) follows the masking
rules in masking-rules.json; every answer records the rules' version, and a new version fingerprints every stored
failure again. Formats: tools/brain/docs/formats.md, "Diagnosis".
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
import casebook  # noqa: E402
import clues  # noqa: E402
import evidence  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, 'masking-rules.json')
LIST_OWN = ('list_filter', 'list_sort', 'fallback_group', 'list_build', 'head_start', 'list')
EVENTS = ('played', 'play_failed')
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
    in the order they failed, or one for the play itself when no Source failed (nothing to play, a fail before any
    Source, a slow play). Each: release, kind, step (the failing step line or None), where, reason."""
    o = ev.meta.get('outcome') or {}
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
        kind = play_kind or ('check miss' if _checked(ev, release) else 'fallback')
        out.append({'release': release, 'kind': kind, 'step': step, 'where': _line(step) if step else 'none',
                    'reason': _reason(ev, release, step)})
    if out:
        return out
    steps = [s for s in ev.steps if s.get('step') not in LIST_OWN + EVENTS]
    step = steps[-1] if steps else None
    kind = play_kind or ('slow play' if o.get('slow') else ev.meta.get('kept_because') or 'fail')
    return [{'release': None, 'kind': kind, 'step': step, 'where': _line(step) if step else 'none',
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


def load_index(folder=casebook.FOLDER):
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
        r = clues.run(item['clue'], ev, failure)
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
