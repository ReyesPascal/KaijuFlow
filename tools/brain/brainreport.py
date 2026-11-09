"""Merge, report and run records for the Brain runs (spec #58, ticket #62). Pure logic: no Docker, no network.

brainrun.py collects one "visit" per run phase, side and title; this module turns visits into
medians, a failure split, a diff against the previous run, the plain-language report and the
run folder / INDEX.md bookkeeping.
"""
import datetime
import json
import os
import re
import statistics
from urllib.parse import unquote_plus

SIDE_NAMES = {
    'kaijuflow': 'KaijuFlow',
    'uu': 'Usenet Ultimate',
    'altmount-addon': "AltMount's own addon",
    'kaijuflow-1page': 'KaijuFlow, one page per indexer',
}
RUN_ORDER = [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)]
CAUSES = [('indexer_limit', 'Indexer limit'), ('backend_rejection', 'Backend rejection'),
          ('failure_video', 'Failure video'), ('other', 'Other')]
SEARCH_STEPS = ('indexer_page', 'health_batch')

COLUMN_HELP = {
    'Side': 'which setup was tested.',
    'Run': 'Cold 1 and Cold 2 start from an empty Backend (nothing imported yet); Warm 1 and Warm 2 follow right after, '
           'so the Backend already knows the titles. The number is the first or second time the whole round was done.',
    'Search': 'seconds from asking for the Stream list of a title until the list arrived. For KaijuFlow and Usenet '
              'Ultimate this includes their health checks; AltMount\'s own addon has none.',
    'NZB fetch': 'seconds to download the chosen Source\'s NZB file from the indexer stand-in. Only KaijuFlow reports '
                 'it; the other sides do not show it from outside, so it reads "-".',
    'Import': 'seconds the Backend needed to take the NZB in and make the video ready (KaijuFlow: its own timing; '
              'the others: from the Backend\'s own log, start to finish). "-" means the log did not show it.',
    'First byte': 'seconds from pressing play on the top pick until the first piece of video arrived. This is the '
                  'whole start and includes the NZB fetch and the import.',
    'Indexer wait': 'KaijuFlow only: seconds spent waiting for indexers during the search (the slowest indexer, its '
                    'pages added up; indexers are asked at the same time).',
    'Health checks': 'seconds spent checking whether Sources look downloadable (the checks of one list added up; '
                     'if they overlap, the real wait was shorter). KaijuFlow only.',
    'Unscramble': 'KaijuFlow only: seconds spent putting scrambled RAR parts in order before the import.',
    'Backend probe': 'KaijuFlow only: seconds KaijuFlow waited for the Backend to deliver the first byte after the import.',
    'Top pick plays': 'titles where the first Source in the list played, out of all titles in the round.',
    'Indexer limit': 'failures caused by an indexer saying its limit was reached (such a run is stopped, so this '
                     'should stay 0 in a finished run).',
    'Backend rejection': 'failures where the Backend (AltMount or NzbDAV) refused or could not import the NZB.',
    'Failure video': 'failures where the side served its "this Source failed" video, with no cause found.',
    'Other': 'any other failure: no Sources, an error, a timeout, a video too short to be a film.',
    'Title': 'the film or episode asked for.',
    'Sources': 'how many Sources the side listed.',
    'Result': '"plays" when the top pick delivered video, otherwise the failure kind and a short note.',
}
SHARED_COLS = ['Side', 'Run', 'Search', 'NZB fetch', 'Import', 'First byte']
EXTRA_COLS = ['Side', 'Run', 'Indexer wait', 'Health checks', 'Unscramble', 'Backend probe']
FAIL_COLS = ['Side', 'Run', 'Top pick plays'] + [c for _, c in CAUSES]
TITLE_COLS = ['Title', 'Side', 'Run', 'Sources', 'Search', 'First byte', 'Result']

# --------------------------------------------------------------------------- parsing

TS_RE = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z?)\s')


def parse_ts(s):
    s = s.strip()
    m = re.match(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?', s)
    if not m:
        raise ValueError('bad time: ' + s)
    frac = (m.group(2) or '')[:7]
    d = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S')
    if frac:
        d = d.replace(microsecond=int(float('0' + frac) * 1e6))
    return d.replace(tzinfo=datetime.timezone.utc)


def iso(d):
    return d.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (d.microsecond // 1000)


def parse_step_lines(text):
    out = []
    for line in text.splitlines():
        if '[KF-STEP] ' not in line:
            continue
        try:
            out.append(json.loads(line.split('[KF-STEP] ', 1)[1]))
        except ValueError:
            continue
    return out


def _lines(text):
    for line in text.splitlines():
        m = TS_RE.match(line)
        if m:
            yield parse_ts(m.group(1)), line[m.end():]


def _file_name(msg):
    m = re.search(r'file=(?:"([^"]*)"|(\S+))', msg)
    if not m:
        return ''
    return os.path.basename(m.group(1) or m.group(2)).removesuffix('.nzb')


def altmount_imports(text):
    """Import start/end of AltMount from its own log (docker --timestamps lines)."""
    by_id, order = {}, []
    for ts, msg in _lines(text):
        q = re.search(r'queue_id=(\d+)', msg)
        if not q:
            continue
        qid = q.group(1)
        if 'msg="Added NZB file to queue"' in msg:
            rec = {'name': _file_name(msg), 'queue_id': qid, 'start': iso(ts), 'end': None, 'seconds': None, 'ok': None}
            by_id[qid] = (rec, ts)
            order.append(rec)
        elif qid in by_id and ('msg="Successfully processed queue item"' in msg or 'msg="Item failed"' in msg
                               or 'msg="Processing failed"' in msg):
            rec, t0 = by_id[qid]
            if rec['end'] is None:
                rec['end'] = iso(ts)
                rec['seconds'] = round((ts - t0).total_seconds(), 3)
                rec['ok'] = 'Successfully' in msg
    return order


def nzbdav_imports(text):
    """Import start/end of NzbDAV: the addfile request is the start; a later 'completed/finished/imported' line naming
    the release is the end. If NzbDAV logs no end, seconds stays None (shown as '-')."""
    recs = []
    lines = list(_lines(text))
    for i, (ts, msg) in enumerate(lines):
        m = re.search(r'POST /api\?[^ ]*mode=addfile[^ ]*', msg)
        if not m:
            continue
        nm = re.search(r'nzbname=([^&\s]+)', m.group(0))
        st = re.search(r'\s(\d{3})\s', msg[m.end():])
        name = unquote_plus(nm.group(1)) if nm else ''
        rec = {'name': name, 'start': iso(ts), 'end': None, 'seconds': None, 'ok': None}
        if st and int(st.group(1)) >= 400:
            rec['ok'] = False
        else:
            for ts2, msg2 in lines[i + 1:]:
                if name and name in msg2 and re.search(r'(?i)complet|finish|imported|success', msg2) \
                        and 'mode=addfile' not in msg2:
                    rec.update(end=iso(ts2), seconds=round((ts2 - ts).total_seconds(), 3), ok=True)
                    break
        recs.append(rec)
    return recs


# The wordings the sides really print when an indexer says "limit reached" (read from the live logs, read-only):
#  - the indexer's own newznab text, passed on by AltMount ("newznab API error 500: Request limit reached. Retry in
#    113 minutes", "search returned HTTP 429 (althub)") and by KaijuFlow's searchers,
#  - Usenet Ultimate: "Search error for <indexer>:" followed by a line "Status: 429",
#  - KaijuFlow's NZB grab (src/nzbdav/nzbdavApi.ts): "Failed to download NZB from <indexer>: 429 ...",
#  - the stand-in's own "LIMIT_REACHED indexer=<slug>" line.
# Loose phrases ("api limit", "limit reached" alone) are not used: "Backup processing limit reached" is a benign
# KaijuFlow line.
LIMIT_RE = re.compile(
    r'(?i)\b(?:request|grab|api|download|daily|nzb)s? limits? (?:has been |was )?(?:reached|exceeded)'
    r'|LIMIT_REACHED indexer='
    r'|\bHTTP 429\b'
    r'|Failed to download NZB from .+: 429\b'
    r'|Request failed with status code 429'
    r'|(?:^|\s)Status: 429\s*$'
    r'|retry in \d+ minutes?')


def scrub_text(s):
    s = re.sub(r'(?i)((?:api_?key|key|token|password|pass)=)[^&\s"]+', r'\1***', s)
    return re.sub(r'://[^/@\s]+@', '://***@', s)


def limit_event(text, indexers):
    """First line that says an indexer's limit was reached: {indexer, time, line} or None."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not LIMIT_RE.search(line):
            continue
        m = re.match(r'(\d{4}-\d\d-\d\dT[\d:.]+Z?)', line)
        near = line + ' ' + (lines[i - 1] if i else '')  # UU prints the indexer on the line before "Status: 429"
        name = next((n for n in indexers if n.lower() in near.lower()), 'unknown')
        return {'indexer': name, 'time': m.group(1) if m else None, 'line': scrub_text(line)[:300]}
    return None


# --------------------------------------------------------------------------- metrics

def median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def _sum_ms(steps, name):
    ms = [s['ms'] for s in steps if s.get('step') == name]
    return round(sum(ms) / 1000, 3) if ms else None


def visit_metrics(v):
    steps = [s for s in v.get('steps', []) if s.get('step') not in SEARCH_STEPS or s.get('ref') == v.get('id')]
    pages = {}
    for s in steps:
        if s.get('step') == 'indexer_page':
            pages[s.get('source')] = pages.get(s.get('source'), 0) + s['ms']
    import_s = None
    waits = [s for s in steps if s.get('step') == 'import_wait']
    if waits:
        ups = [] if any(s.get('includes_upload') for s in waits) else [s for s in steps if s.get('step') == 'upload']
        import_s = round(sum(s['ms'] for s in waits + ups) / 1000, 3)
    else:
        secs = [i['seconds'] for i in v.get('imports', []) if i.get('seconds') is not None]
        import_s = secs[-1] if secs else None
    return {
        'search_s': v.get('list_s'),
        'nzb_fetch_s': _sum_ms(steps, 'nzb_fetch'),
        'import_s': import_s,
        'start_s': v.get('start_s'),
        'health_s': _sum_ms(steps, 'health_batch'),
        'unscramble_s': _sum_ms(steps, 'unscramble'),
        'indexer_wait_s': round(max(pages.values()) / 1000, 3) if pages else None,
        'probe_s': _sum_ms(steps, 'first_byte'),
    }


def _norm(text):
    return re.sub(r'[^a-z0-9]+', '', str(text).lower())


def attribute_steps(visit, steps, end=None):
    """The step lines that belong to one visit of one side.

    Search-side lines (indexer_page, health_batch) carry `ref`: kept when ref is the visit's id, from the visit's start until
    `end` (the start of that side's next visit; None = no end), however late they are written. Prepare-side lines carry the
    release `title` of the Source: only the Source that was played is kept, found by (1) its name in the played stream's text
    and otherwise (2) work that began after this visit began, so a previous title's background work cannot land here.
    """
    lo = parse_ts(visit['t_start']) - datetime.timedelta(seconds=1)

    def inside(s):
        try:
            t = parse_ts(s['t'])
        except (KeyError, ValueError):
            return False
        return t >= lo and (end is None or t < end)

    out = [s for s in steps if s.get('step') in SEARCH_STEPS and s.get('ref') == visit.get('id') and inside(s)]
    prep = [s for s in steps if s.get('step') not in SEARCH_STEPS and inside(s) and s.get('title')]
    groups = {}
    for s in prep:
        begun = parse_ts(s['t']) - datetime.timedelta(milliseconds=s.get('ms', 0))
        g = groups.setdefault(s['title'], {'begun': begun, 'lines': []})
        g['begun'] = min(g['begun'], begun)
        g['lines'].append(s)
    played = ' '.join(str(t.get('title', '')) for t in visit.get('tries', [])[:1])
    pick = [t for t in groups if len(_norm(t)) >= 8 and _norm(t) in _norm(played)]
    if not pick:
        fresh = [t for t, g in groups.items() if g['begun'] >= lo]
        pick = sorted(fresh, key=lambda t: groups[t]['begun'])[:1]
    for t in pick:
        out += groups[t]['lines']
    return sorted(out, key=lambda s: s['t'])


def classify_failure(v):
    if v.get('ok'):
        return None
    if v.get('limit'):
        return 'indexer_limit'
    rejected = any(i.get('ok') is False for i in v.get('imports', [])) or \
        any(s.get('step') == 'import_wait' and s.get('ok') is False for s in v.get('steps', []))
    if rejected:
        return 'backend_rejection'
    if v.get('note') == 'failure video':
        return 'failure_video'
    return 'other'


# --------------------------------------------------------------------------- settings and diff

SECRET_WORDS = {'key', 'keys', 'apikey', 'secret', 'secrets', 'pass', 'passwd', 'password', 'passwords', 'token', 'tokens',
                'jwt', 'login', 'logins', 'user', 'username', 'auth', 'authorization', 'cookie', 'cookies',
                'credential', 'credentials'}


def is_secret_name(name):
    """True when one whole word of the setting name (camelCase, snake_case, kebab-case) is a secret word."""
    words = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', name))
    return any(w in SECRET_WORDS for w in re.split(r'[^A-Za-z0-9]+', words.lower()) if w)


def _scrub_value(k, v):
    if is_secret_name(k.split('.')[-1].split('[')[0]) and v not in (None, '', False, True):
        return '***'
    return scrub_text(v) if isinstance(v, str) else v


def flatten(obj, prefix=''):
    """Nested JSON to {dotted.key: value}, secrets replaced by ***."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f'{prefix}.{k}' if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            tag = v['name'] if isinstance(v, dict) and isinstance(v.get('name'), str) else str(i)
            out.update(flatten(v, f'{prefix}[{tag}]'))
        if not obj:
            out[prefix] = '[]'
    else:
        out[prefix] = _scrub_value(prefix, obj)
    return out


def flatten_yaml(text):
    """Indentation-based flattening of simple YAML (AltMount's config.yaml); secrets replaced by ***."""
    out, stack, counts = {}, [], {}
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip())
        c = raw.strip()
        if c.startswith('- ') or c == '-':
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = ''.join(('.' if i and not n.startswith('[') else '') + n for i, (_, n) in enumerate(stack))
            idx = counts.get(parent, 0)
            counts[parent] = idx + 1
            stack.append((indent, f'[{idx}]'))
            c, indent = c[1:].strip(), indent + 2
            if not c:
                continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key, sep, val = c.partition(':')
        if not sep:
            continue
        val = val.strip().strip('"\'')
        stack.append((indent, key.strip()))
        if val:
            path = ''.join(('.' if i and not n.startswith('[') else '') + n for i, (_, n) in enumerate(stack))
            out[path] = _scrub_value(path, val)
    return out


def _stamp(d):
    return f'{d:%Y-%m-%d %H:%M} UTC'


def diff_runs(prev, cur, nulls=None):
    """Plain list of every difference between two run metas (settings, code, titles, indexers, time of day).

    nulls: metas of the null runs that lie between the two (see null_runs_between); they are counted with their times.
    """
    if prev is None:
        return ['No earlier run to compare with: this is the first one.']
    out = []
    ps, cs = prev.get('settings', {}), cur.get('settings', {})
    lines = []
    for side in sorted(set(ps) | set(cs)):
        a, b = ps.get(side, {}), cs.get(side, {})
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                lines.append(f"{side} {k}: {a.get(k, '(not set)')} -> {b.get(k, '(not set)')}")
    out += lines[:60] + ([f'... and {len(lines) - 60} more setting differences'] if len(lines) > 60 else [])
    if (prev.get('commit'), prev.get('dirty')) != (cur.get('commit'), cur.get('dirty')):
        dirty = ' (uncommitted changes)' if cur.get('dirty') else ''
        out.append(f"KaijuFlow code: {prev.get('commit')} -> {cur.get('commit')}{dirty}")
    for key, label in (('titles', 'Titles'), ('indexers', 'Indexers'), ('sides', 'Sides')):
        a, b = prev.get(key, []), cur.get(key, [])
        if [x for x in b if x not in a]:
            out.append(f"{label} added: {', '.join(x for x in b if x not in a)}")
        if [x for x in a if x not in b]:
            out.append(f"{label} removed: {', '.join(x for x in a if x not in b)}")
    if not out:
        out.append('Nothing changed in the settings, KaijuFlow code, titles, indexers or sides.')
    try:  # the time of day of both runs is always listed (indexers can answer differently by time of day)
        out.append(f"Time of day: previous run {_stamp(parse_ts(prev['started']))}, this run {_stamp(parse_ts(cur['started']))}")
    except (KeyError, ValueError):
        pass
    if nulls:
        when = ', '.join(_stamp(parse_ts(n['started'])) for n in nulls if n.get('started'))
        out.append(f"{len(nulls)} null run{'' if len(nulls) == 1 else 's'} (stopped by an indexer limit, results not used) "
                   f"lie between the two runs: {when}")
    return out


def null_runs_between(root, since, exclude=None):
    """meta.json of every null run in the runs root that started after `since` (ISO time), oldest first."""
    found = []
    if not os.path.isdir(root):
        return found
    for d in sorted(os.listdir(root)):
        if d == exclude:
            continue
        try:
            meta = json.loads(_slurp(os.path.join(root, d, 'meta.json')))
        except (OSError, ValueError):
            continue
        if meta.get('status') == 'null' and meta.get('started') and parse_ts(meta['started']) > parse_ts(since):
            found.append(meta)
    return sorted(found, key=lambda m: m['started'])


# --------------------------------------------------------------------------- report

def _groups(run):
    g = {}
    for v in run['visits']:
        g.setdefault((v['side'], v['phase'], v['round']), []).append(v)
    return g


def _run_label(phase, rnd):
    return f'{phase.capitalize()} {rnd}'


def _cell(x):
    return '-' if x is None else f'{x:g}'


def _sides(run):
    return [s for s in SIDE_NAMES if s in run['sides']]


def answer_sentence(run):
    g = _groups(run)
    parts = {}
    for phase in ('cold', 'warm'):
        starts = []
        for s in _sides(run):
            vs = [v for r in (1, 2) for v in g.get((s, phase, r), [])]
            starts.append((s, median([v.get('start_s') for v in vs if v.get('ok')]), sum(1 for v in vs if v.get('ok')), len(vs)))
        parts[phase] = starts
    def fmt(phase):
        return ', '.join(f"{SIDE_NAMES[s]} {_cell(m)} s ({p} of {n} top picks played)" for s, m, p, n in parts[phase])
    n = len(run.get('titles', []))
    return (f"Across {n} title{'' if n == 1 else 's'}, each round done twice, the median time from pressing play to the first byte was, "
            f"cold: {fmt('cold')}; warm: {fmt('warm')}.")


def headline(run):
    g = _groups(run)
    bits = []
    for s in _sides(run):
        c = median([v.get('start_s') for r in (1, 2) for v in g.get((s, 'cold', r), []) if v.get('ok')])
        w = median([v.get('start_s') for r in (1, 2) for v in g.get((s, 'warm', r), []) if v.get('ok')])
        vs = [v for v in run['visits'] if v['side'] == s]
        bits.append(f"{SIDE_NAMES[s]} cold {_cell(c)} s / warm {_cell(w)} s, plays {sum(1 for v in vs if v.get('ok'))}/{len(vs)}")
    return '; '.join(bits)


def _table(cols, rows):
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return out


def _defs(cols):
    return [f'- **{c}**: {COLUMN_HELP[c]}' for c in cols]


def render_report(run, changes):
    g = _groups(run)
    lines = [answer_sentence(run), '',
             f"Run: {run['name']}. KaijuFlow code {run.get('commit')}{' (with uncommitted changes)' if run.get('dirty') else ''}. "
             f"Started {run.get('started')}. All times are medians over the titles of one round, in seconds; "
             "\"-\" means that side does not show the step from outside.", '',
             '## What changed since the last run', ''] + [f'- {c}' for c in changes] + ['']
    if run.get('standin_misses'):
        lines += [f"Warning: the indexer stand-in had {run['standin_misses']} requests it had not recorded (a side asked "
                  "for something the recording does not hold), so the sides did not all see the same Sources.", '']
    shared, extra, fail = [], [], []
    for s in _sides(run):
        for phase, rnd in RUN_ORDER:
            vs = g.get((s, phase, rnd))
            if not vs:
                continue
            ms = [visit_metrics(v) for v in vs]
            lab = _run_label(phase, rnd)
            md = lambda k: _cell(median([m[k] for m, v in zip(ms, vs) if v.get('ok') or k == 'search_s']))  # noqa: E731
            shared.append([SIDE_NAMES[s], lab, md('search_s'), md('nzb_fetch_s'), md('import_s'), md('start_s')])
            extra.append([SIDE_NAMES[s], lab, md('indexer_wait_s'), md('health_s'), md('unscramble_s'), md('probe_s')])
            causes = [classify_failure(v) for v in vs]
            fail.append([SIDE_NAMES[s], lab, f"{sum(1 for v in vs if v.get('ok'))} of {len(vs)}"]
                        + [sum(1 for c in causes if c == k) for k, _ in CAUSES])
    lines += ['## Steps every side shares', ''] + _table(SHARED_COLS, shared) + [''] + _defs(SHARED_COLS) + ['']
    lines += ['## Extras (steps only some sides have)', ''] + _table(EXTRA_COLS, extra) + [''] + _defs(EXTRA_COLS[2:]) + ['']
    lines += ['## Failures', ''] + _table(FAIL_COLS, fail) + [''] + _defs(FAIL_COLS[2:]) + ['']
    rows = []
    for t in run.get('titles', []):
        for s in _sides(run):
            for phase, rnd in RUN_ORDER:
                for v in g.get((s, phase, rnd), []):
                    if v['title'] != t:
                        continue
                    m = visit_metrics(v)
                    cause = classify_failure(v)
                    res = 'plays' if v.get('ok') else f"{dict(CAUSES)[cause].lower()}: {v.get('note') or ''}".strip(': ')
                    rows.append([t, SIDE_NAMES[s], _run_label(phase, rnd), v.get('sources', '-'), _cell(m['search_s']),
                                 _cell(m['start_s']), res])
    lines += ['## Per title', ''] + _table(TITLE_COLS, rows) + [''] + _defs(TITLE_COLS) + ['']
    return '\n'.join(lines)


def render_null_report(run):
    n = run.get('null') or {}
    return '\n'.join([
        'This run is NULL: it was stopped and none of its results may be used.', '',
        f"An indexer ({n.get('indexer', 'unknown')}) answered that its limit was reached, at {n.get('time', 'an unknown time')}.",
        f"Where it was seen: {n.get('where', 'unknown')}.", '',
        'By the cap rule the run stopped at once. No report was made from it; the raw files in this folder are kept '
        'only to show what happened. Start a new run after the indexer has reset.', ''])


# --------------------------------------------------------------------------- run records

def create_run_dir(root, name, now):
    safe = re.sub(r'[^A-Za-z0-9._-]+', '-', name).strip('-') or 'run'
    base = os.path.join(root, f'{now:%Y-%m-%dT%H%M%SZ}-{safe}')
    os.makedirs(root, exist_ok=True)
    path, n = base, 1
    while True:
        try:
            os.mkdir(path)
            return path
        except FileExistsError:
            n += 1
            path = f'{base}-{n}'


INDEX_HEAD = ('# Brain runs\n\nOne row per run, never edited. NULL = the run was stopped by an indexer limit and its numbers '
              'are not used.\n\n| Date (UTC) | Name | Result | What changed from the previous run | Headline numbers | Folder |\n'
              '|---|---|---|---|---|---|\n')


def _slurp(path):
    with open(path) as f:
        return f.read()


def append_index_row(path, row):
    def cell(x):
        return str(x).replace('|', '/').replace('\n', ' ')
    old = _slurp(path) if os.path.exists(path) else INDEX_HEAD
    link = "](%s/)" % row['folder']
    if link in old:
        raise ValueError('INDEX.md already has a row for ' + row['folder'])
    line = (f"| {cell(row['date'])} | {cell(row['name'])} | {cell(row['result'])} | {cell('; '.join(row['changed']))} | "
            f"{cell(row['headline'])} | [{row['folder']}]({row['folder']}/) |\n")
    with open(path, 'a') as f:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            f.write(INDEX_HEAD)
        elif not old.endswith('\n'):
            f.write('\n')
        f.write(line)


def previous_run(root, exclude=None):
    """meta.json of the newest earlier finished (non-null) run, or None."""
    if not os.path.isdir(root):
        return None
    for d in sorted(os.listdir(root), reverse=True):
        if d == exclude:
            continue
        try:
            meta = json.loads(_slurp(os.path.join(root, d, 'meta.json')))
        except (OSError, ValueError):
            continue
        if meta.get('status') == 'ok':
            return meta
    return None
