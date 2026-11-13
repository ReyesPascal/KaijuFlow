"""Merge, report and run records for the Brain runs (spec #58, ticket #62). Pure logic: no Docker, no network.

brainrun.py collects one "visit" per run phase, side and title; this module turns visits into
medians, a failure split, a diff against the previous run, the targets of targets.json judged on
the run, the plain-language report and the run folder / INDEX.md bookkeeping.
"""
import datetime
import json
import os
import re
import statistics

SIDE_NAMES = {
    'kaijuflow': 'KaijuFlow',
    'uu': 'Usenet Ultimate',
    'altmount-addon': "AltMount's own addon",
    'kaijuflow-1page': 'KaijuFlow, one page per indexer',
}
RUN_ORDER = [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)]
CAUSES = [('indexer_limit', 'Indexer limit'), ('backend_rejection', 'Backend rejection'),
          ('failure_video', 'Failure video'), ('other', 'Other'), ('not_recorded', 'Not recorded')]
SEARCH_STEPS = ('indexer_page', 'health_batch')

COLUMN_HELP = {
    'Side': 'which setup was tested.',
    'Run': 'Cold 1 and Cold 2 start from an empty Backend (nothing imported yet); Warm 1 and Warm 2 follow right after, '
           'so the Backend already knows the titles. The number is the first or second time the whole round was done.',
    'Search': 'seconds from asking for the Stream list of a title until the list arrived. For KaijuFlow and Usenet '
              'Ultimate this includes their health checks; AltMount\'s own addon has none.',
    'NZB fetch': 'seconds to download the chosen Source\'s NZB file from the indexer stand-in. Only KaijuFlow reports '
                 'it; the other sides do not show it from outside, so it reads "-".',
    'Import': 'seconds the Backend needed to take the NZB in and make the video ready. KaijuFlow: its own timing, to the '
              'millisecond. Usenet Ultimate: NzbDAV\'s own job time, whole seconds only (NzbDAV reports no fractions). '
              'AltMount: read from its log, start to finish, to the millisecond. "-" means the source showed no figure '
              '(for NzbDAV: no new job, for example when the item was already imported).',
    'First byte': 'seconds from pressing play on the top pick until the first piece of video arrived. This is the '
                  'whole start and includes the NZB fetch and the import.',
    'Indexer wait': 'KaijuFlow only: seconds spent waiting for indexers during the search (the slowest indexer, its '
                    'pages added up; indexers are asked at the same time).',
    'Health checks': 'seconds spent checking whether Sources look downloadable (the checks of one list added up; '
                     'if they overlap, the real wait was shorter). KaijuFlow only.',
    'Unscramble': 'KaijuFlow only: seconds spent putting scrambled RAR parts in order before the import.',
    'Backend probe': 'KaijuFlow only: seconds KaijuFlow waited for the Backend to deliver the first byte after the import.',
    'Indexers': 'seconds of the search time that were the indexers\' answering time (for a replayed answer, the time the real '
                'indexer took when it was recorded; indexers are asked at the same time, so the slowest one counts). '
                '"-" means no stand-in log line was matched to the visit; 0 means the replay wait was off.',
    "Side's own work": 'Search minus Indexers: what the side itself added to the list time (health checks, merging, its own requests).',
    'Top pick plays': 'titles where the first Source in the list played, out of the titles in the round. A top pick that failed '
                      'only because a request was not recorded is left out of both numbers (see Not recorded).',
    'Indexer limit': 'failures caused by an indexer saying its limit was reached (such a run is stopped, so this '
                     'should stay 0 in a finished run).',
    'Backend rejection': 'failures where the Backend (AltMount or NzbDAV) refused or could not import the NZB, or took the import '
                         'but did not deliver the first byte of the file (the cause is shown in the Result column of the title tables).',
    'Failure video': 'failures where the side served its "this Source failed" video, with no cause found.',
    'Other': 'any other failure: no Sources, an error, a timeout, a video too short to be a film.',
    'Not recorded': 'failures where a miss can be the cause: the list came back empty after a request the recording does not hold, '
                    'or the NZB file of the top pick was not recorded. This says nothing about the side or the Source: top up the recording.',
    'Title': 'the film or episode asked for.',
    'Top pick': 'the first Source in the side\'s list, the one that was played: its release name where KaijuFlow\'s own log '
                'gives it, otherwise the text the side showed for it in its list. "-" means there was none: the side listed no Source.',
    'Size': 'the size of the top pick\'s file as the Backend served it, in GB of 1000 x 1000 x 1000 bytes. For a top pick that '
            'did not play it is the size the side states in its list, marked "listed": the indexer\'s figure for the post, '
            'not the measured size of the file (KaijuFlow counts it in GB of 1024 x 1024 x 1024 bytes).',
    'Sources': 'how many Sources the side listed.',
    'Result': '"plays" when the top pick delivered video, otherwise the failure kind and a short note.',
}
SHARED_COLS = ['Side', 'Run', 'Search', 'Indexers', "Side's own work", 'NZB fetch', 'Import', 'First byte']
EXTRA_COLS = ['Side', 'Run', 'Indexer wait', 'Health checks', 'Unscramble', 'Backend probe']
FAIL_COLS = ['Side', 'Run', 'Top pick plays'] + [c for _, c in CAUSES]
TITLE_COLS = ['Title', 'Side', 'Run', 'Top pick', 'Size', 'Sources', 'Search', 'First byte', 'Result']

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


def nzbdav_job_imports(before, after):
    """Import figures of NzbDAV from its own history answer (mode=history, the answer's `history.slots`).
    `before` and `after` are the answers read before and after one visit; a job is the visit's when it is new in `after`.
    The figure is NzbDAV's own `download_time`: whole seconds the job took (NzbDAV does not report fractions)."""
    def slots(answer):
        h = (answer or {}).get('history') or {}
        return [x for x in (h.get('slots') or []) if isinstance(x, dict)]
    if before is None or after is None:  # an answer that could not be read: no figure, never a guess
        return []
    seen = {x.get('nzo_id') for x in slots(before)}
    recs = []
    for x in slots(after):
        if x.get('nzo_id') in seen:
            continue
        t = x.get('download_time')
        ok = str(x.get('status') or '').lower()
        recs.append({'name': str(x.get('nzb_name') or x.get('name') or ''),
                     'seconds': float(t) if isinstance(t, (int, float)) and not isinstance(t, bool) else None,
                     'ok': True if ok == 'completed' else False if ok == 'failed' else None})
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


# The stand-in's request lines (indexer_standin.py) end with `from=<client address> t=<epoch ms the answer was sent>`:
#   HIT <slug> <request> wait_ms=<n> from=.. t=..   MISS <slug> <request> from=.. t=..
#   RECORD <slug> <request> -> <status> <n> bytes from=.. t=..   ERROR <slug> <request> -> <status> from=.. t=..
# The runner maps each address to the test container that sent it and each container to its visits (assign_standin).
LINE_RE = re.compile(r'^(HIT|MISS|RECORD|ERROR) (\S+) (.*?)(?:\swait_ms=(\d+))? from=(\S+) t=(\d+)$')
# The test container that sends a side's indexer requests (the one-page side uses KaijuFlow's container too).
CLIENT_CONTAINER = {'kaijuflow': 'kaijuflow-test', 'kaijuflow-1page': 'kaijuflow-test', 'uu': 'uu-test',
                    'altmount-addon': 'altmount-addon-test'}
LIST_SLACK_MS = 100  # the list time is rounded; a search answer sent just before the list arrived still counts


def parse_standin_line(line):
    """{'kind', 'slug', 'request', 'wait_ms', 'ip', 't'} of one request line, or None (other lines, or no address/time)."""
    m = LINE_RE.match(line.strip())
    if not m:
        return None
    return {'kind': m.group(1), 'slug': m.group(2), 'request': m.group(3), 'wait_ms': int(m.group(4) or 0),
            'ip': m.group(5), 't': int(m.group(6))}


def _is_search_request(req):
    return req.startswith('api ') and 't=get' not in req[4:].split('&')


def _is_nzb_request(req):
    return req.startswith('nzb ') or (req.startswith('api ') and 't=get' in req[4:].split('&'))


def _union_s(intervals):
    total, end = 0, None
    for a, b in sorted(intervals):
        if end is None or a > end:
            total, end = total + (b - a), b
        elif b > end:
            total, end = total + (b - end), b
    return total / 1000


def _ms(iso_time):
    return parse_ts(iso_time).timestamp() * 1000


def assign_standin(visits, lines, addresses=None):
    """Give every visit (that has a `t_start`) its misses, indexer time and whether a miss can be why its top pick failed.

    addresses: {test container: [client addresses]}. A line belongs to the side whose container sent it, and within the
    side to the visit that was current for that side when the line was sent (its start until that side's next start).
    A line from an unknown address goes to the visit in progress at that time (any side); the number of those is returned.
    Sets on each visit: misses ['<slug> <request>', ...] (every miss), indexer_s (the time the side waited on replayed search
    answers while the list loaded, parallel waits counted once) and not_recorded (True when the list came back empty after a
    search miss, or an NZB miss came while the top pick played).
    """
    ip_container = {ip: c for c, ips in (addresses or {}).items() for ip in (ips if isinstance(ips, list) else [ips])}
    marked = sorted((v for v in visits if v.get('t_start')), key=lambda v: _ms(v['t_start']))
    per_container, got = {}, {id(v): [] for v in marked}
    for v in marked:
        per_container.setdefault(CLIENT_CONTAINER.get(v['side']), []).append(v)

    def current(candidates, t):
        found = None
        for v in candidates:  # sorted by start
            if _ms(v['t_start']) <= t:
                found = v
        return found

    unmatched = 0
    for raw in lines:
        p = parse_standin_line(raw)
        if not p:
            continue
        container = ip_container.get(p['ip'])
        if container and container in per_container:
            v = current(per_container[container], p['t'])
        else:
            v = current(marked, p['t'])
            unmatched += 1 if v else 0
        if v:
            got[id(v)].append(p)
    for v in marked:
        mine = got[id(v)]
        start = _ms(v['t_start'])
        list_end = start + v['list_s'] * 1000 if v.get('list_s') is not None else _ms(v['t_end']) if v.get('t_end') else start
        miss = [p for p in mine if p['kind'] == 'MISS']
        waits = [(max(p['t'] - p['wait_ms'], start), p['t']) for p in mine
                 if p['kind'] == 'HIT' and p['wait_ms'] and _is_search_request(p['request']) and p['t'] <= list_end + LIST_SLACK_MS]
        play_end = _ms(v['t_end']) if v.get('t_end') else float('inf')
        search_miss = any(_is_search_request(p['request']) for p in miss)
        play_miss = any(_is_nzb_request(p['request']) and list_end <= p['t'] <= play_end for p in miss)
        v['misses'] = [f"{p['slug']} {p['request']}" for p in miss]
        v['indexer_s'] = round(_union_s(waits), 3)
        v['not_recorded'] = bool(not v.get('ok') and ((not v.get('sources') and search_miss) or play_miss))
    return unmatched


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
        'indexer_s': v.get('indexer_s'),
        'own_s': round(max(v['list_s'] - v['indexer_s'], 0), 3)
        if v.get('list_s') is not None and v.get('indexer_s') is not None else None,
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


def played_source(text):
    """The release name of the Source KaijuFlow played in one visit, from its own log: the name on the first
    'Starting new stream preparation' (a cold play) or 'Streaming' (a play that reused what the Backend held) line
    after the '/stream hit' line. None when the log shows neither."""
    seen = False
    for _, msg in _lines(text):
        if '/stream hit' in msg:
            seen = True
        elif seen:
            m = re.search(r'Starting new stream preparation: (.+?)\s*$', msg) or re.search(r'Streaming (.+?): \d+ requests', msg)
            if m:
                return m.group(1)
    return None


# The size a side states for a Source in its list text. KaijuFlow, Usenet Ultimate and AltMount's own addon all write it
# after a disk sign: "... 💾 95.01 GB 🔊 DTS-HD MA ...", "... 💾 4.05 GB 🌐 ninja".
LISTED_SIZE_RE = re.compile(r'💾\s*(\d+(?:\.\d+)?\s?[KMGT]?B)\b')


def top_pick(v):
    """The top pick of one visit, the first Source in the side's list: {'name', 'size', 'listed'}, or None when the side
    listed none.

    name: the release name where KaijuFlow's own log gives it (`played_source`), otherwise the text the side showed for the
    Source in its list. size: bytes of the file as the Backend served it, only when the top pick played (a failed play serves
    the failure video, whose size says nothing about the Source). listed: the size the list text states, or None.
    """
    tries = v.get('tries') or []
    if not tries:
        return None
    first = tries[0]
    text = str(first.get('title') or '')
    stated = LISTED_SIZE_RE.search(text)
    return {'name': v.get('played_source') or text or None,
            'size': first.get('size') if first.get('plays') and first.get('size') else None,
            'listed': stated.group(1) if stated else None}


def _pick_size(pick):
    """The size of a top pick as the report shows it: of the served file, else the listed one, else '-'."""
    if pick['size']:
        return f"{pick['size'] / 1e9:.1f} GB"
    return f"{pick['listed']} listed" if pick['listed'] else '-'


def _pick_cells(pick):
    """The Top pick and Size cells of a per-title row."""
    if not pick:
        return ['-', '-']
    return [str(pick['name'] or '-').replace('|', '/'), _pick_size(pick)]


def top_picks(visits):
    """{side: {title: {'Cold 1': top pick, ...}}} of a run's visits. A visit that holds no record of what was tried (a run
    folder cut down, or written before plays were kept) is left out, so it is never compared."""
    out = {}
    for v in visits:
        if 'tries' in v:
            out.setdefault(v['side'], {}).setdefault(v['title'], {})[_run_label(v['phase'], v['round'])] = top_pick(v)
    return out


def _same_pick(a, b):
    """Whether two top picks are the same Source: by the size of the served file when both played, else by the size both
    lists state, else by name. The name alone does not do: a side's list text also holds the Source's age and health-check
    mark, which change from run to run."""
    if a is None or b is None:
        return a is b
    for key in ('size', 'listed'):
        if a[key] and b[key]:
            return a[key] == b[key]
    return a['name'] == b['name']


def _pick_text(pick):
    if not pick:
        return 'no top pick'
    return ', '.join(x for x in (str(pick['name'] or 'no name'), _pick_size(pick)) if x != '-')


def top_pick_changes(before, now):
    """One line per title and side whose top pick differs between two runs (both as top_picks gives them): the rounds it
    differs in, then the old and the new pick of the first of them. Only rounds both runs hold are compared."""
    labels = [_run_label(phase, rnd) for phase, rnd in RUN_ORDER]
    titles = list(dict.fromkeys(t for side in now.values() for t in side))
    lines = []
    for title in titles:
        for side in SIDE_NAMES:
            old, new = before.get(side, {}).get(title, {}), now.get(side, {}).get(title, {})
            differ = [x for x in labels if x in old and x in new and not _same_pick(old[x], new[x])]
            if differ:
                lines.append(f"Top pick changed: {SIDE_NAMES[side]}, {title} ({', '.join(differ)}): "
                             f"{_pick_text(old[differ[0]])} -> {_pick_text(new[differ[0]])}")
    return lines


def _picks_of(meta):
    """The top picks of a run meta: kept in it (previous_run reads them from the run folder) or made from its visits; None
    when the meta holds neither."""
    if 'top_picks' in meta:
        return meta['top_picks']
    return (top_picks(meta['visits']) or None) if isinstance(meta.get('visits'), list) else None


def failure_cause(text):
    """Why KaijuFlow's top pick failed, in KaijuFlow's own words for the visit: the reason on its 'Stream failed' line (without
    the file path) and the Backend's answer at the first byte ('AltMount probe returned 400'). '' when it logged neither."""
    reason = status = ''
    for _, msg in _lines(text):
        if not status:
            m = re.search(r'(\w+) probe returned (\d+)', msg)
            if m:
                status = m.group(0)
        if not reason:
            m = re.search(r'Stream failed \[\d+/\d+\] .+?: (.+)$', msg)
            if m:
                reason = re.sub(r':\s*/\S.*$', '', m.group(1)).strip()
    return scrub_text('; '.join(x for x in (reason, status) if x))


def visit_cause(v):
    """The cause shown for a failed visit: KaijuFlow's own words, else its first-byte step line, else ''."""
    if v.get('cause'):
        return v['cause']
    for s in v.get('steps', []):
        if s.get('step') == 'first_byte' and s.get('ok') is False:
            return f"first byte failed after {s.get('ms', 0) / 1000:.1f} s"
    return ''


def attribute_steps(visit, steps, end=None):
    """The step lines that belong to one visit of one side.

    Search-side lines (indexer_page, health_batch) carry `ref`: kept when ref is the visit's id, from the visit's start until
    `end` (the start of that side's next visit; None = no end), however late they are written. Prepare-side lines carry the
    release `title` of the Source: kept only for the Source that was played, found by its name in the visit's `played_source`
    (from KaijuFlow's log) or in the played stream's text. No Source found means no prepare-side lines: a play that reused what
    the Backend held shows no import and no Unscramble, and another Source's background work never lands here.
    """
    lo = parse_ts(visit['t_start']) - datetime.timedelta(seconds=1)

    def inside(s):
        try:
            t = parse_ts(s['t'])
        except (KeyError, ValueError):
            return False
        return t >= lo and (end is None or t < end)

    out = [s for s in steps if s.get('step') in SEARCH_STEPS and s.get('ref') == visit.get('id') and inside(s)]
    played = ' '.join(str(t.get('title', '')) for t in visit.get('tries', [])[:1])
    src = _norm(visit.get('played_source') or '')
    for s in steps:
        if s.get('step') in SEARCH_STEPS or not s.get('title') or not inside(s):
            continue
        n = _norm(s['title'])
        if (src and n == src) or (len(n) >= 8 and n in _norm(played)):
            out.append(s)
    return sorted(out, key=lambda s: s['t'])


def classify_failure(v):
    if v.get('ok'):
        return None
    if v.get('limit'):
        return 'indexer_limit'
    if v.get('not_recorded'):  # a miss that can be the cause (see assign_standin): not a verdict on the side or the Source
        return 'not_recorded'
    rejected = any(i.get('ok') is False for i in v.get('imports', [])) or \
        any(s.get('step') == 'import_wait' and s.get('ok') is False for s in v.get('steps', []))
    if rejected:
        return 'backend_rejection'
    if any(s.get('step') == 'first_byte' and s.get('ok') is False for s in v.get('steps', [])):
        return 'backend_rejection'  # the Backend took the import but could not serve the file
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


def _settings_and_facts(meta):
    """(settings of the test copies, run-level facts) of a run meta. Runs recorded in the older shape kept the replay wait
    under settings['stand-in'] and the one-page side under settings['kaijuflow-1page']; they are read as facts."""
    settings = {k: v for k, v in (meta.get('settings') or {}).items() if k not in ('stand-in', 'kaijuflow-1page')}
    facts = dict(meta.get('facts') or {})
    old = meta.get('settings') or {}
    if 'facts' not in meta:
        if (old.get('stand-in') or {}).get('replay wait'):
            facts['stand-in replay wait'] = old['stand-in']['replay wait']
        facts['one-page side'] = 'yes' if 'kaijuflow-1page' in old or 'kaijuflow-1page' in (meta.get('sides') or []) else 'no'
    return settings, facts


def diff_runs(prev, cur, nulls=None):
    """Plain list of every difference between two run metas (settings, code, titles, indexers, time of day).

    nulls: metas of the null runs that lie between the two (see null_runs_between); they are counted with their times.
    """
    if prev is None:
        return ['No earlier run to compare with: this is the first one.']
    out = []
    ps, pf = _settings_and_facts(prev)
    cs, cf = _settings_and_facts(cur)
    lines = []
    for side in sorted(set(ps) | set(cs)):
        a, b = ps.get(side, {}), cs.get(side, {})
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                lines.append(f"{side} {k}: {a.get(k, '(not set)')} -> {b.get(k, '(not set)')}")
    lines += [f"{k}: {pf.get(k, '(not set)')} -> {cf.get(k, '(not set)')}" for k in sorted(set(pf) | set(cf)) if pf.get(k) != cf.get(k)]
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
    picks_before, picks_now = _picks_of(prev), _picks_of(cur)
    compared = picks_before is not None and picks_now is not None  # an earlier run whose top picks are not known is not compared
    if compared:
        out += top_pick_changes(picks_before, picks_now)
    if not out:
        out.append(f"Nothing changed in the settings, KaijuFlow code, titles, indexers{', sides or top picks' if compared else ' or sides'}.")
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


# --------------------------------------------------------------------------- targets

TARGETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'targets.json')
JUDGED = 'kaijuflow'  # the side the targets are set for
# What each measure is held against: a fixed limit, another side (against), or either of the two.
TARGET_MEASURES = {'plays per round': 'limit', 'plays': 'against',
                   'cold start': 'either', 'warm start': 'either', 'cold list': 'either', 'warm list': 'either'}
NO_FIGURE = 'no figure'  # the run holds nothing to measure a target with (a side or a round is not in it)


def _secs(x):
    return NO_FIGURE if x is None else f'{x:.2f} s'


def _plays_text(plays):
    """'p of n' for (top picks that played, top picks counted), or 'no figure' when none was counted."""
    return f'{plays[0]} of {plays[1]}' if plays[1] else NO_FIGURE


def _time(visits, side, phase, what, rnd=None):
    """Median start (top picks that played) or list time (every visit) of one side: both rounds of a phase, or one round."""
    vs = [v for v in visits if v['side'] == side and v['phase'] == phase and rnd in (None, v['round'])]
    return median([v.get('start_s') for v in vs if v.get('ok')] if what == 'start' else [v.get('list_s') for v in vs])


def _plays(visits, side, phase=None, rnd=None):
    """(top picks that played, top picks counted) of one side: every round, or one round."""
    vs = _counted([v for v in visits if v['side'] == side and phase in (None, v['phase']) and rnd in (None, v['round'])])
    return sum(1 for v in vs if v.get('ok')), len(vs)


MET, NOT_MET, NOT_MEASURED = 'met', 'not met', 'not measured'


def _verdict(result, slower_s=None, noise=None):
    """A target's verdict as a value: the result (MET, NOT_MET or NOT_MEASURED); for a time target that is not met, how many
    seconds KaijuFlow is slower than what it is held against; and the noise: None, or KaijuFlow's two rounds of the phase
    with how far the target is met or missed by, when those two rounds differ by more than that."""
    return {'result': result, 'slower_s': slower_s, 'noise': noise}


def verdict_text(verdict):
    """The Result words of a verdict, as the report's table and the check's lines show them."""
    text = verdict['result'].capitalize()
    if verdict['result'] == NOT_MET and verdict['slower_s'] is not None:
        text += f" ({_secs(verdict['slower_s'])} slower)"
    noise = verdict['noise']
    if noise:
        a, b = noise['rounds']
        text += (f", inside the noise: {SIDE_NAMES[JUDGED]}'s two {noise['phase']} rounds differ by {_secs(abs(a - b))} "
                 f"({a:.2f} and {b:.2f} s), more than the {_secs(noise['by'])} the target is "
                 f"{'missed' if verdict['result'] == NOT_MET else 'met'} by")
    return text


def _measure_target(visits, t):
    """(measured values, verdict) of one entry of the targets file."""
    me, margin = SIDE_NAMES[JUDGED], t['margin']
    if t['measure'] == 'plays per round':  # every round the run holds, cold and warm
        rounds = {phase: [x for p, r in RUN_ORDER if p == phase for x in [_plays(visits, JUDGED, phase, r)] if x[1]]
                  for phase in ('cold', 'warm')}
        measured = ', '.join(f'{phase} ' + (' and '.join(_plays_text(x) for x in rs) or NO_FIGURE) for phase, rs in rounds.items())
        if not all(rounds.values()):
            return measured, _verdict(NOT_MEASURED)
        met = all(p >= t['limit'] - margin and n - p <= margin for rs in rounds.values() for p, n in rs)
        return measured, _verdict(MET if met else NOT_MET)
    if t['measure'] == 'plays':  # the share of top picks that played, every round together
        (p, n), (q, m) = _plays(visits, JUDGED), _plays(visits, t['against'])
        measured = f"{me} {_plays_text((p, n))}, {SIDE_NAMES[t['against']]} {_plays_text((q, m))}"
        if not n or not m:
            return measured, _verdict(NOT_MEASURED)
        return measured, _verdict(MET if p * m > (q - margin * m) * n else NOT_MET)
    phase, what = t['measure'].split()
    mine = _time(visits, JUDGED, phase, what)
    ref = t['limit'] if 'limit' in t else _time(visits, t['against'], phase, what)
    measured = f'{me} {_secs(mine)}' + ('' if 'limit' in t else f", {SIDE_NAMES[t['against']]} {_secs(ref)}")
    if mine is None or ref is None:
        return measured, _verdict(NOT_MEASURED)
    over = round(mine - ref - margin, 2)  # above 0: the target is missed by this much; below: met by this much
    a, b = (_time(visits, JUDGED, phase, what, r) for r in (1, 2))
    noise = ({'phase': phase, 'rounds': (a, b), 'by': abs(over)}
             if a is not None and b is not None and round(abs(a - b), 2) > abs(over) else None)
    return measured, _verdict(MET, noise=noise) if over <= 0 else _verdict(NOT_MET, mine - ref, noise)


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def load_targets(path=TARGETS_FILE):
    """The entries of the targets file. ValueError with a plain reason when the file or one of its entries cannot be used."""
    name = os.path.basename(path)
    try:
        with open(path) as f:
            targets = json.load(f)['targets']
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f'{name} cannot be read: {type(e).__name__}') from None
    if not isinstance(targets, list):
        raise ValueError(f'{name} cannot be read: "targets" is not a list')
    for i, t in enumerate(targets, 1):
        if not isinstance(t, dict) or not isinstance(t.get('target'), str):
            why = 'it has no target text'
        elif t.get('measure') not in TARGET_MEASURES:
            why = f"the measure \"{t.get('measure')}\" is not known"
        elif not _is_number(t.get('margin')) or t['margin'] < 0:
            why = 'the margin is not a number from 0 up'
        elif 'against' in t and t['against'] not in SIDE_NAMES:
            why = f"the side \"{t['against']}\" is not known"
        elif TARGET_MEASURES[t['measure']] == 'limit' and ('against' in t or not _is_number(t.get('limit'))):
            why = f"\"{t['measure']}\" takes a fixed limit, not a side"
        elif TARGET_MEASURES[t['measure']] == 'against' and ('limit' in t or 'against' not in t):
            why = f"\"{t['measure']}\" takes a side (against), not a fixed limit"
        elif ('against' in t) == ('limit' in t) or ('limit' in t and not _is_number(t['limit'])):
            why = f"\"{t['measure']}\" takes a side (against) or a fixed limit, one of the two"
        else:
            continue
        raise ValueError(f'{name}, entry {i}: {why}')
    return targets


def target_results(visits, path=TARGETS_FILE):
    """[(target, measured values, verdict)] for every entry of the targets file, in its order."""
    return [(t['target'],) + _measure_target(visits, t) for t in load_targets(path)]


def targets_not_judged(status):
    """The one gate of the targets, which the report and the check both go through: None for a finished run (status
    'ok'), else why its targets are not judged. A stopped, null or failed run holds part of its plays or none, so no
    verdict is made from it."""
    if status == 'ok':
        return None
    why = {'stopped': 'the run was stopped before its last play',
           'null': 'the run is null (an indexer said its limit was reached)'}.get(status, 'the run did not finish')
    return f'{why}, and the targets are judged on a finished run alone'


def target_lines(run, path=TARGETS_FILE):
    """One plain line per target of a run ({'status', 'visits'}), as the check prints them; one sentence when its targets
    are not judged (targets_not_judged) or the targets file cannot be used."""
    why = targets_not_judged(run.get('status'))
    if why:
        return [f'Targets: not judged: {why}.']
    try:
        return [f'Target: {t}. Measured: {m}. {verdict_text(v)}.' for t, m, v in target_results(run['visits'], path)]
    except ValueError as e:
        return [f'Targets: not judged ({e}).']


TARGETS_HELP = (
    'Start = seconds from pressing play on the top pick until the first byte. List = seconds from asking for a title until '
    'its Stream list arrived. Each time is the median over the titles of both cold rounds or both warm rounds together (the '
    'start over the top picks that played, the list over every title). Plays leave out a top pick that failed only because a '
    'request was not recorded. "Inside the noise": KaijuFlow\'s own two rounds differ by more than the target is met or '
    'missed by, so the same run done again could turn the result around. "Not measured": the run holds no figure for it.')


def targets_section(run, path=TARGETS_FILE):
    """The report's table of the targets of a run ({'status', 'visits'}): one row per target, then how many are met and
    what the words mean. One sentence instead when its targets are not judged (targets_not_judged)."""
    why = targets_not_judged(run.get('status'))
    if why:
        return ['## Targets', '', f'Not judged: {why}.', '']
    try:  # a targets file that cannot be used must not cost a finished run its report
        rows = target_results(run['visits'], path)
    except ValueError as e:
        return ['## Targets', '', f'Not judged ({e}).', '']
    met = sum(1 for _, _, verdict in rows if verdict['result'] == MET)
    return ['## Targets', ''] + _table(['Target', 'This run', 'Result'], [(t, m, verdict_text(v)) for t, m, v in rows]) + [
        '', f"{met} of {len(rows)} targets met. {TARGETS_HELP}", '']


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


def _counted(vs):
    """The visits that count towards a plays-out-of figure: not the ones that failed only because of a miss."""
    return [v for v in vs if classify_failure(v) != 'not_recorded']


def answer_sentence(run):
    vs = run['visits']

    def fmt(phase):
        return ', '.join(f"{SIDE_NAMES[s]} {_cell(_time(vs, s, phase, 'start'))} s "
                         f"({' of '.join(str(x) for x in _plays(vs, s, phase))} top picks played)" for s in _sides(run))
    n = len(run.get('titles', []))
    return (f"Across {n} title{'' if n == 1 else 's'}, each round done twice, the median time from pressing play to the first byte was, "
            f"cold: {fmt('cold')}; warm: {fmt('warm')}.")


def headline(run):
    vs = run['visits']
    return '; '.join(f"{SIDE_NAMES[s]} cold {_cell(_time(vs, s, 'cold', 'start'))} s / warm {_cell(_time(vs, s, 'warm', 'start'))} s, "
                     f"plays {'/'.join(str(x) for x in _plays(vs, s))}" for s in _sides(run))


def _table(cols, rows):
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return out


def _defs(cols):
    return [f'- **{c}**: {COLUMN_HELP[c]}' for c in cols]


def render_report(run, changes, opening=None):
    g = _groups(run)
    lines = [opening or answer_sentence(run), '',
             f"Run: {run['name']}. KaijuFlow code {run.get('commit')}{' (with uncommitted changes)' if run.get('dirty') else ''}. "
             f"Started {run.get('started')}. All times are medians over the titles of one round, in seconds; "
             "\"-\" means that side does not show the step from outside.", ''] + targets_section(run) + [
             '## What changed since the last run', ''] + [f'- {c}' for c in changes] + ['']
    if run.get('standin_misses'):
        lines += [f"Warning: the indexer stand-in had {run['standin_misses']} requests it had not recorded (a side asked "
                  "for something the recording does not hold), so the sides did not all see the same Sources.", '']
    if run.get('standin_unmatched'):
        lines += [f"{run['standin_unmatched']} indexer stand-in requests came from an address that is not a test container, "
                  "so they were matched by time to the visit in progress (a late request of an earlier side may sit on the wrong visit).", '']
    shared, extra, fail = [], [], []
    for s in _sides(run):
        for phase, rnd in RUN_ORDER:
            vs = g.get((s, phase, rnd))
            if not vs:
                continue
            ms = [visit_metrics(v) for v in vs]
            lab = _run_label(phase, rnd)
            md = lambda k: _cell(median([m[k] for m, v in zip(ms, vs)  # noqa: E731
                                         if v.get('ok') or k in ('search_s', 'indexer_s', 'own_s')]))
            shared.append([SIDE_NAMES[s], lab, md('search_s'), md('indexer_s'), md('own_s'), md('nzb_fetch_s'), md('import_s'),
                           md('start_s')])
            extra.append([SIDE_NAMES[s], lab, md('indexer_wait_s'), md('health_s'), md('unscramble_s'), md('probe_s')])
            causes = [classify_failure(v) for v in vs]
            counted = _counted(vs)
            fail.append([SIDE_NAMES[s], lab, f"{sum(1 for v in counted if v.get('ok'))} of {len(counted)}"]
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
                    res = 'plays' if v.get('ok') else failed_result(v, cause)
                    rows.append([t, SIDE_NAMES[s], _run_label(phase, rnd)] + _pick_cells(top_pick(v))
                                + [v.get('sources', '-'), _cell(m['search_s']), _cell(m['start_s']), res])
    lines += ['## Per title', ''] + _table(TITLE_COLS, rows) + [''] + _defs(TITLE_COLS) + ['']
    lines += not_recorded_section(run)
    lines += time_section(run)
    return '\n'.join(lines)


def not_recorded_section(run):
    """Misses per side and title, the top picks left out of the plays figure and the top-up command; empty without misses."""
    rows, left_out = [], []
    for t in run.get('titles', []):
        for s in _sides(run):
            n = sum(len(v.get('misses') or []) for v in run['visits'] if v['side'] == s and v['title'] == t)
            if n:
                rows.append([SIDE_NAMES[s], t, n])
    for s in _sides(run):
        for phase, rnd in RUN_ORDER:
            for v in _groups(run).get((s, phase, rnd), []):
                if classify_failure(v) == 'not_recorded':
                    left_out.append(f"{SIDE_NAMES[s]}, {v['title']}, {_run_label(phase, rnd)}")
    if not rows:
        return []
    top_up = run.get('topup_command') or 'the record command with the same title list'
    out = ['## Not recorded', '',
           'A side asked the indexer stand-in for something the recording does not hold. That says nothing about the side or '
           'the Source, so these requests are counted here and not as bad Sources. Requests per side and title, all rounds:', '']
    out += _table(['Side', 'Title', 'Requests not recorded'], rows) + ['']
    out += ['Top picks left out of the plays-out-of-ten figures (a miss can be why they failed): '
            + ('; '.join(left_out) if left_out else 'none (every top pick still played).'), '',
            f'To fill the gaps, top up the recording (no indexer is asked for something already stored): `{top_up}`', '']
    return out


# --------------------------------------------------------------------------- where the time went (#112)

# The five parts the wall-clock time of a run is split into: key in meta.json's timing.parts, name in the report.
TIME_PARTS = [('measured_s', 'Measured list and start time'), ('pauses_s', 'Pauses (`--settle`)'),
              ('failed_s', 'Failed plays'), ('resets_s', 'Resets'), ('other_s', 'Everything else')]


def visit_wall_s(v):
    """Wall-clock seconds of one visit, from asking for the list until the play ended or gave up; None without both times."""
    try:
        return round((parse_ts(v['t_end']) - parse_ts(v['t_start'])).total_seconds(), 3)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def failed_result(v, cause):
    """The Result cell of a top pick that did not play: the failure kind, the cause or note, and how long the whole visit took."""
    text = f"{dict(CAUSES)[cause].lower()}: {visit_cause(v) or v.get('note') or ''}".strip(': ')
    took = visit_wall_s(v)
    return text if took is None else f'{text} (the whole visit took {took:.1f} s)'


def time_parts(run):
    """Where the wall-clock time of a run went, in seconds, as the five TIME_PARTS. They add up to the run's total
    (timing.seconds): four are measured (the list and start times of the top picks that played, the pauses and the resets
    as the run timed them, the whole visits of the top picks that failed), and `other_s` is what is left of the total.
    Works on a run that ended early: it takes whatever visits, rounds and resets the run holds."""
    timing = run.get('timing') or {}
    visits = run.get('visits') or []
    parts = {'measured_s': sum((v.get('list_s') or 0) + (v.get('start_s') or 0) for v in visits if v.get('ok')),
             'pauses_s': sum(r.get('pause_s') or 0 for r in timing.get('rounds') or []),
             'failed_s': sum(visit_wall_s(v) or 0 for v in visits if not v.get('ok')),
             'resets_s': sum(r.get('seconds') or 0 for r in timing.get('resets') or [])}
    parts = {k: round(x, 3) for k, x in parts.items()}
    parts['other_s'] = round((timing.get('seconds') or 0) - sum(parts.values()), 3)
    return parts


def _s(x):
    return '-' if x is None else f'{x:.1f}'


def _minutes(x):
    return '-' if x is None else f'{x / 60:.1f}'


def _took(x):
    return f'{_minutes(x)} minutes ({_s(x)} s)'


def _time_of_day(iso_time):
    return str(iso_time)[11:19]


def time_section(run):
    """The report's section on the run's wall-clock time: the whole run and each pass in one sentence, the five parts that
    add up to the whole run, then each round with the reset before it. Seconds are shown to one decimal, so the parts as
    printed are within a second of the total. [] for a run that holds no timing (made before #112)."""
    timing = run.get('timing') or {}
    parts = timing.get('parts')
    if not parts:
        return []
    visits = run.get('visits') or []
    rounds, resets = timing.get('rounds') or [], timing.get('resets') or []
    passes = ', '.join(f"the {p.get('name')} {_took(p.get('seconds'))}" for p in timing.get('passes') or [])
    out = ['## Where the time went', '',
           f"The whole run took {_took(timing.get('seconds'))}, from {_time_of_day(run.get('started'))} to "
           f"{_time_of_day(run.get('finished'))} UTC{': ' + passes if passes else ''}.", '']
    rows = [[name, _s(parts.get(key)), _minutes(parts.get(key))] for key, name in TIME_PARTS]
    out += _table(['Part', 'Seconds', 'Minutes'], rows + [['The whole run', _s(timing.get('seconds')), _minutes(timing.get('seconds'))]])
    failed = sum(1 for v in visits if not v.get('ok'))
    out += ['',
            '- **Measured list and start time**: for every top pick that played, the seconds until its Stream list arrived plus '
            'the seconds from pressing play to the first byte. The tables above are made from these.',
            f"- **Pauses (`--settle`)**: the pause after every play, {_cell(timing.get('settle_s'))} s each "
            f"({sum(r.get('plays') or 0 for r in rounds)} plays).",
            f"- **Failed plays**: the whole visit of every top pick that did not play, from asking for the list until the play "
            f"gave up ({failed} visit{'' if failed == 1 else 's'}; each one's time is in the Result column of \"Per title\").",
            '- **Resets**: emptying and restarting the test copies before each cold round. The first reset of the one-page '
            'side includes the switch to one page.',
            '- **Everything else**: what is left of the whole run: the seek checks after a top pick played, reading the logs '
            'after each play, starting and stopping the indexer stand-in and the test copies.', '']
    out += _table(['Pass', 'Round', 'Started (UTC)', 'Reset before it (s)', 'Plays', 'Round (s)', 'Round (minutes)'],
                  _round_rows(rounds, resets))
    out += ['',
            '- **Pass**: the main sides (KaijuFlow, Usenet Ultimate, AltMount\'s own addon) are played in turn, title by '
            'title, in one pass; the one-page side has its own pass after them.',
            '- **Round**: the cold or warm round of every side of the pass, played together, from the first play to the end '
            'of the pause after the last play. The reset before a cold round is not part of it.', '']
    return out


def _round_rows(rounds, resets):
    """One row per round of each pass, in the order they were played, with the reset that came before it. A reset with no
    round after it (the run ended during the reset) gets a row too, so every reset is shown."""
    def which(r):
        return r.get('pass'), r.get('phase'), r.get('round')
    reset_of, round_of = {which(r): r for r in resets}, {which(r): r for r in rounds}
    rows = []
    for key in dict.fromkeys(which(r) for r in sorted(resets + rounds, key=lambda r: str(r.get('start')))):
        r = round_of.get(key) or {}
        rows.append([str(key[0]).capitalize(), _run_label(str(key[1]), key[2]), _time_of_day(r.get('start')) if r else '-',
                     _s(reset_of.get(key, {}).get('seconds')), r.get('plays', 0), _s(r.get('seconds')), _minutes(r.get('seconds'))])
    return rows


def render_null_report(run):
    n = run.get('null') or {}
    return '\n'.join([
        'This run is NULL: it was stopped and none of its results may be used.', '',
        f"An indexer ({n.get('indexer', 'unknown')}) answered that its limit was reached, at {n.get('time', 'an unknown time')}.",
        f"Where it was seen: {n.get('where', 'unknown')}.", '',
        'By the cap rule the run stopped at once. No report was made from it; the raw files in this folder are kept '
        'only to show what happened. Start a new run after the indexer has reset.', ''])


# The signals that stop a run or a record the normal way (#110): the name kept in `stopped.signal`, and how it is said.
STOP_SIGNALS = {'SIGINT': 'Ctrl-C (SIGINT)', 'SIGTERM': 'SIGTERM'}


def stopped_text(stopped):
    """How a run or a record that was stopped by a signal ended, as the rest of a sentence: by what, when, in which stage,
    how many plays had finished, and the play it was in. `stopped` is what brainrun.stop_note keeps (meta.json's
    `stopped`); the run and the record keep it in the same shape."""
    s = stopped or {}
    d = s.get('during')
    if d:
        rnd = '' if d.get('round') is None else f" {d['round']}"
        where = f"it stopped during the next one ({SIDE_NAMES.get(d['side'], d['side'])}, {d['phase']}{rnd}, {d['title']})"
    else:
        where = 'it stopped between two plays' if s.get('plays_done') else 'it stopped before its first play'
    stage = f" in {s['stage']}" if s.get('stage') else ''
    return (f"stopped by {STOP_SIGNALS.get(s.get('signal'), 'hand')} at {s.get('time', 'an unknown time')}{stage}: "
            f"{s.get('plays_done', 0)} of {s.get('plays_planned', 'an unknown number of')} plays had finished, and {where}")


def render_stopped_report(run, changes):
    """The report of a run that was stopped by hand: it opens by saying so and how far the run got, then holds the usual
    sections, made from the plays that finished."""
    return render_report(run, changes, opening=f"This run was {stopped_text(run.get('stopped'))}. The tables below are made "
                                               "from the finished plays alone, so the run is not a baseline.")


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
              'are not used. stopped = the run was stopped by hand before its last play and is not a baseline.\n\n| Date (UTC) | Name | Result | What changed from the previous run | Headline numbers | Folder |\n'
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
    """meta.json of the newest earlier finished (non-null) run, or None. Its top picks are added from the folder's raw.json
    (`top_picks`), so the next run can be compared with them; a folder that holds none stays without."""
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
            try:
                picks = top_picks(json.loads(_slurp(os.path.join(root, d, 'raw.json')))['visits'])
            except (OSError, ValueError, KeyError, TypeError):
                picks = None
            if picks:
                meta['top_picks'] = picks
            return meta
    return None
