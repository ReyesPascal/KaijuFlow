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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import common  # noqa: E402
import indexer_standin  # noqa: E402

SIDE_NAMES = {
    'kaijuflow': 'KaijuFlow',
    'uu': 'Usenet Ultimate',
    'altmount-addon': "AltMount direct",
    'kaijuflow-1page': 'KaijuFlow, one page per indexer',
}
SHORT_NAMES = {'kaijuflow': 'KaijuFlow', 'uu': 'Usenet Ultimate', 'altmount-addon': 'AltMount direct',
               'kaijuflow-1page': 'KaijuFlow with one page per indexer'}  # the sides as a short run's text names them (GLOSSARY)
RUN_ORDER = [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)]
CAUSES = [('indexer_limit', 'Indexer limit'), ('backend_rejection', 'Backend rejection'),
          ('failure_video', 'Failure video'), ('other', 'Other'), ('not_recorded', 'Not recorded')]
SEARCH_STEPS = ('indexer_page', 'health_batch')

COLUMN_HELP = {
    'Side': 'which setup was tested.',
    'Run': 'Cold 1 and Cold 2 start from an empty Backend (nothing imported yet); Warm 1 and Warm 2 follow right after, '
           'so the Backend already knows the titles. The number is the first or second time the whole round was done.',
    'Search': 'seconds from asking for the Stream list of a title until the list arrived. For KaijuFlow and Usenet '
              'Ultimate this includes their health checks; AltMount direct has none.',
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
    'Top pick plays': 'titles where the first Source in the list played on the first try, out of the titles in the round. A '
                      'top pick that failed only because a request was not recorded is left out of both numbers (see Not recorded).',
    'Fallback': 'titles where video arrived only after the top pick\'s own import failed (the side fell back to another Source '
                'or to a file it already held). They count as not played.',
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
    'Result': '"plays" when the top pick delivered video on the first try; "played after N fallbacks" when video arrived only '
              'after N imports failed, the top pick\'s own among them; otherwise the failure kind and a short note.',
}
SHARED_COLS = ['Side', 'Run', 'Search', 'Indexers', "Side's own work", 'NZB fetch', 'Import', 'First byte']
EXTRA_COLS = ['Side', 'Run', 'Indexer wait', 'Health checks', 'Unscramble', 'Backend probe']
FAIL_COLS = ['Side', 'Run', 'Top pick plays', 'Fallback'] + [c for _, c in CAUSES]
TITLE_COLS = ['Title', 'Side', 'Run', 'Top pick', 'Size', 'Sources', 'Search', 'First byte', 'Result']
# A run on a tagged title list (#167) shows each title's list and its title to video too; a run without tags shows neither.
LIST_COLUMN_HELP = {
    'List': 'the title list the title is on: easy (popular, well kept) or hard (older releases, takedown-prone shows, less '
            'popular titles).',
    'Title to video': 'seconds from asking for the title until video arrived: Search plus First byte. "-" for a fail: no '
                      'video, or video only after a fallback.',
}
TAGGED_TITLE_COLS = ['Title', 'List', 'Side', 'Run', 'Top pick', 'Size', 'Sources', 'Search', 'First byte', 'Title to video',
                     'Result']

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


def top_pick(v):
    """The top pick of one visit, the first Source in the side's list: {'name', 'size', 'listed'}, or None when the side
    listed none.

    name: the release name where KaijuFlow's own log gives it (`played_source`), otherwise the text the side showed for the
    Source in its list. size: bytes of the file as the Backend served it, only when the top pick played (a failed play serves
    the failure video, and a fallback another file, whose size says nothing about the Source). listed: the size the list
    text states, or None. KaijuFlow, Usenet Ultimate and AltMount direct all write it after a disk sign ("... 💾 95.01
    GB 🔊 DTS-HD MA ...", "... 💾 4.05 GB 🌐 ninja"); common.play_stream reads it from the whole text (`listed_size`), and a record made before that is read
    from the 140 characters of text it kept.
    """
    tries = v.get('tries') or []
    if not tries:
        return None
    first = tries[0]
    text = str(first.get('title') or '')
    return {'name': v.get('played_source') or text or None,
            'size': first.get('size') if first.get('plays') and first.get('size') and not fallbacks(v) else None,
            'listed': first.get('listed_size') or common.listed_size(text)}


IMPORT_TAG = re.compile(r'-[0-9a-f]{16}$')  # AltMount names an import after the release, with 16 hex digits after it


def _release(name):
    """An import's name as a release name to match: without '.nzb' (NzbDAV) or AltMount's tag, run together (`_norm`)."""
    return _norm(IMPORT_TAG.sub('', str(name or '').removesuffix('.nzb')))


def pick_imports(v):
    """The imports of a visit's top pick: those whose release name is in the top pick's name (KaijuFlow's own log) or in the
    text its list showed. When none is, the visit's first import, unless KaijuFlow's log names the top pick: KaijuFlow and
    Usenet Ultimate also queue the next Sources of the list, so another import of theirs is not the top pick's."""
    imports = v.get('imports') or []
    tries = v.get('tries') or []
    names = [_norm(x) for x in (v.get('played_source'), tries[0].get('title') if tries else None) if x]
    mine = [i for i in imports if (r := _release(i.get('name'))) and any(r in n for n in names)]
    return mine if mine or v.get('played_source') else imports[:1]


def fallbacks(v):
    """How many imports failed in a visit that served video only after its top pick's own import failed (a fallback, such as
    AltMount's max_fallback_releases); 0 for a first-try play and for a visit that served no video."""
    if not v.get('ok') or not any(i.get('ok') is False for i in pick_imports(v)):
        return 0
    return sum(1 for i in v.get('imports') or [] if i.get('ok') is False)


def plays(v):
    """Whether a visit's top pick played on the first try: video arrived, and not after a fallback (#143)."""
    return bool(v.get('ok')) and not fallbacks(v)


def title_to_video(v):
    """Seconds from asking for the title until video arrived (#167): the list time plus the start time. None for a fail
    (no video, or video only after a fallback: GLOSSARY.md, "a fail has no title-to-video time") and without both times."""
    if not plays(v) or v.get('list_s') is None or v.get('start_s') is None:
        return None
    return round(v['list_s'] + v['start_s'], 3)


def top_picks_played(counts):
    """The sentence of how many top picks played, per side and round, in the words `check` and the record command share:
    `Top picks played, KaijuFlow: cold 9 of 10, warm 10 of 10; Usenet Ultimate: ...`. counts: [(side, {'cold': (played,
    of), 'warm': (played, of)})], in the order to name them."""
    return 'Top picks played, ' + '; '.join(
        f"{SIDE_NAMES.get(side, side)}: " + ', '.join(f'{phase} {p} of {n}' for phase, (p, n) in by.items())
        for side, by in counts) + '.'


RESOLUTIONS = {'2160p': ('2160p', '4k|uhd'), '1080p': ('1080p', 'fhd'), '720p': ('720p', '')}  # (stated number, words)


def _first_of(text, pick):
    """The resolution whose pattern (pick: 0 the number, 1 the words) comes first in the text, or None."""
    words = '|'.join(f'(?P<r{res}>{w[pick]})' for res, w in RESOLUTIONS.items() if w[pick])
    m = re.search(rf'(?<![a-z0-9])(?:{words})(?![a-z0-9])', text)
    return m and m.lastgroup[1:]


def resolution(text):
    """The resolution a top pick's name or list text states ('2160p', '1080p', '720p'), or None when it states none (#154).
    A stated number wins over the words 4K, UHD (2160p) and FHD (1080p), which count only when no number is stated: "1080p
    UHD BluRay" is a 1080p encode from a 4K disc. A side's own label ("AltMount FHD - ... [1080p]", "4K BluRay") is read
    with the release name as one text, so the first stated number wins (tools/brain/docs/rules.md, "Like for like")."""
    text = str(text or '').lower()
    return _first_of(text, 0) or _first_of(text, 1)


def _rule_break(v, rules):
    """Why a visit's top pick is outside the like-for-like rules (#142), or None: a disc image, or a served file over the size
    cap of its kind. The served size is held to the cap the indexer's post size is held to; the file is never larger than
    its post, so a file over the cap means its post was over it too. Season packs have no cap (indexer_standin.keep_post)."""
    pick = top_pick(v)
    kind = {'movie': 'film', 'series': 'episode'}.get(v.get('kind'))
    if not pick or not rules or not kind or indexer_standin.keep_post(pick['name'], pick['size'], kind, rules):
        return None
    if rules['disc'].search(str(pick['name'] or '')):
        return 'a disc image'
    return f"{pick['size'] / 1e9:.1f} GB served, over the cap for {'a film' if kind == 'film' else 'an episode'} " \
           f"({rules[kind] / 1e9:.1f} GB)"


def unlike_titles(visits):
    """{side: {title: why}}: the titles whose top picks are not like for like between KaijuFlow and another setup (not a
    KaijuFlow variant such as one page per indexer, which no target is held against), with the first round that shows it.
    Not like for like: in one round the two top picks state different resolutions, or either one breaks the like-for-like
    rules (_rule_break). A title is left out of judging KaijuFlow against that side (#143)."""
    try:
        rules = indexer_standin.like_for_like_rules()
    except ValueError:  # the expected settings file cannot be used: the preflight says so; resolutions are still compared
        rules = None
    by = {(v['side'], v['title'], _run_label(v['phase'], v['round'])): v for v in visits if v.get('tries')}
    labels = [_run_label(phase, rnd) for phase, rnd in RUN_ORDER]
    me = SIDE_NAMES[JUDGED]
    out = {}
    for side in [s for s in SIDE_NAMES if not s.startswith(JUDGED)]:
        for title in dict.fromkeys(v['title'] for v in visits):
            for label in labels:
                mine, theirs = by.get((JUDGED, title, label)), by.get((side, title, label))
                if not mine or not theirs:
                    continue
                a, b = (resolution((top_pick(x) or {}).get('name')) for x in (mine, theirs))
                if a and b and a != b:
                    why = f"{me}'s top pick is {a}, {SIDE_NAMES[side]}'s is {b} ({label})"
                else:
                    broken = [(x, r) for x in (mine, theirs) for r in [_rule_break(x, rules)] if r]
                    why = broken and (f"{SIDE_NAMES[broken[0][0]['side']]}'s top pick breaks the like-for-like rules "
                                      f"({label}): {broken[0][1]}")
                if why:
                    out.setdefault(side, {})[title] = why
                    break
    return out


LIKE_FOR_LIKE_HELP = (
    "Each title's top pick of every setup is compared with KaijuFlow's, round by round: the resolution its name or list "
    'states, and whether its served file keeps the like-for-like rules (the size cap of its kind, no disc images; '
    'tools/brain/docs/rules.md, "Like for like"). Two files of one resolution inside the cap count as like for like, '
    'whatever their sizes. A title that is not is left out of the targets held against that setup.')


def like_for_like_lines(visits):
    """The like-for-like lines the report and the check both show: one line that every title is like for like, or a head
    line and one line per setup and title that is not; one line instead when no round holds top picks of KaijuFlow and
    another setup (a run of KaijuFlow alone, or a record that kept no tries)."""
    def rounds(keep):
        return {(v['title'], v['phase'], v['round']) for v in visits if keep(v['side']) and v.get('tries')}
    if not rounds(lambda s: s == JUDGED) & rounds(lambda s: not s.startswith(JUDGED)):
        return [f'No title has top picks of {SIDE_NAMES[JUDGED]} and another setup to compare, so like for like is not judged.']
    unlike = unlike_titles(visits)
    if not unlike:
        return ["Every title's top picks are like for like: the same resolution, inside the size caps, no disc images."]
    return [f'Not like for like with {SIDE_NAMES[JUDGED]}, so left out of the targets against that setup:'] + [
        f'- {SIDE_NAMES[side]}, {title}: {why}.' for side, titles in unlike.items() for title, why in titles.items()]


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


def top_pick_table(visits):
    """The check's per-title table (#154): per title and side, the resolution the like-for-like check reads from the top
    pick (`resolution`) and its size (served, else listed), in the first round that holds top picks; [] when none does."""
    picks = top_picks(visits)
    held = {x for side in picks.values() for rounds in side.values() for x in rounds}
    label = next((x for x in (_run_label(p, r) for p, r in RUN_ORDER) if x in held), None)
    if not label:
        return []
    sides = [s for s in SIDE_NAMES if s in picks]

    def cell(pick):
        return f"{resolution(pick['name']) or '-'}, {_pick_size(pick)}" if pick else '-'
    return ([f'Top picks per title, {label}: the resolution the like-for-like check reads, and the size served (else listed).',
             '| Title | ' + ' | '.join(SIDE_NAMES[s] for s in sides) + ' |', '|---' * (len(sides) + 1) + '|'] +
            [f'| {title} | ' + ' | '.join(cell(picks[s].get(title, {}).get(label)) for s in sides) + ' |'
             for title in dict.fromkeys(v['title'] for v in visits)])


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
    if plays(v):
        return None
    if v.get('ok'):
        return 'fallback'
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


YAML_MAP_LINE = re.compile(r'[^\s:#"\'][^:#]*:(\s|$)')  # `key: value` or `key:`; a scalar such as `http://x` is not one


def _yaml_scalar(val):
    """A YAML scalar as text: quotes taken off ("..." read with its escapes, '...' with '' as one quote), plain as it is."""
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] == '"':
        try:
            return json.loads(val)  # YAML's double-quoted escapes are JSON's (\\, \", \n, \u....)
        except ValueError:
            return val[1:-1]
    if len(val) >= 2 and val[0] == val[-1] == "'":
        return val[1:-1].replace("''", "'")
    return val


def flatten_yaml(text):
    """Indentation-based flattening of simple YAML (AltMount's config.yaml); secrets replaced by ***. A list of plain values
    (`- iso`) is read as name[0], name[1], ... like a list of maps."""
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
            if not YAML_MAP_LINE.match(c):  # a plain value in a list
                path = ''.join(('.' if i and not n.startswith('[') else '') + n for i, (_, n) in enumerate(stack))
                out[path] = _scrub_value(path, _yaml_scalar(c))
                continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key, sep, val = c.partition(':')
        if not sep:
            continue
        val = _yaml_scalar(val)
        stack.append((indent, key.strip()))
        if val:
            path = ''.join(('.' if i and not n.startswith('[') else '') + n for i, (_, n) in enumerate(stack))
            out[path] = _scrub_value(path, val)
    return out


def short_run_text(sides, rounds, titles):
    """What a short run played, in the words its report, its INDEX.md row and `check` use: `KaijuFlow, 1 round, 10 titles`."""
    names = [SHORT_NAMES[s] for s in SHORT_NAMES if s in sides]
    return f"{', '.join(names)}, {rounds} round{'' if rounds == 1 else 's'}, {len(titles)} title{'' if len(titles) == 1 else 's'}"


def limit_to_played(baseline, cur):
    """The baseline as far as a short run compares with it: its sides and titles cut down to the ones `cur` played, so what
    the short run left out does not show as removed. Rounds need no cut: the top picks are compared in the rounds both hold."""
    limited = dict(baseline)
    for key in ('sides', 'titles'):
        limited[key] = [x for x in baseline.get(key, []) if x in cur.get(key, [])]
    return limited


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


ARCHIVE = 'archive'  # #144: runs from before the like-for-like rules, kept as a record; never the baseline, a comparison or on the page
ARCHIVED_TEXT = 'archived (not like for like)'


def run_folders(root):
    """The names in the runs root that can be runs, oldest first: everything but the archive folder (#144)."""
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root) if d != ARCHIVE)


def is_archived(folder):
    """True when a run folder sits in a runs root's archive folder (#144)."""
    return os.path.basename(os.path.dirname(os.path.abspath(folder).rstrip(os.sep))) == ARCHIVE


def never_compared(meta):
    """True when a run's meta.json marks it never compared with (#153): kept and shown under its "label", never a comparison."""
    return bool(meta.get('never_compared'))


def null_runs_between(root, since, exclude=None):
    """meta.json of every null run in the runs root that started after `since` (ISO time), oldest first."""
    found = []
    for d in run_folders(root):
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


def _time(visits, side, phase, what, rnd=None, lst=None):
    """Median start or title to video (top picks that played) or list time (every visit) of one side: both rounds of a
    phase, or one round; every title, or the titles of one list (#167)."""
    vs = [v for v in visits if v['side'] == side and v['phase'] == phase and rnd in (None, v['round'])
          and lst in (None, v.get('list'))]
    if what == 'list':
        return median([v.get('list_s') for v in vs])
    return median([v.get('start_s') if what == 'start' else title_to_video(v) for v in vs if plays(v)])  # a fail has neither


def _plays(visits, side, phase=None, rnd=None, lst=None):
    """(top picks that played, top picks counted) of one side: every round, or one round; every title, or one list's."""
    vs = _counted([v for v in visits if v['side'] == side and phase in (None, v['phase']) and rnd in (None, v['round'])
                   and lst in (None, v.get('list'))])
    return sum(1 for v in vs if plays(v)), len(vs)


def side_time(visits, side, phase, what, lst=None):
    """The median start, list or title to video ('start', 'list', 'video') of one side over both rounds of a phase: the
    figure the targets judge, for the Speed Check page (build_page.py), so the page and the verdict show one number. With
    `lst` ('easy' or 'hard'), over the titles of that list alone (#167); title to video is over the top picks that played."""
    return _time(visits, side, phase, what, lst=lst)


def side_fails(visits, side, phase=None, rnd=None, lst=None):
    """How many of one side's counted top picks failed (#167): every round, one phase or one round; every title, or the
    titles of one list. A fail is a top pick that did not play on its one try: no video, the failure video, a refusal, or
    video only after a fallback. Each visit counts on its own, so a cold fail stays a fail when the warm play after it works."""
    played, counted = _plays(visits, side, phase, rnd, lst)
    return counted - played


def fail_figure(visits, side, phase=None, rnd=None, lst=None):
    """One side's fails as every count shows them (#167, owner: "Plays, say both"): {'titles': titles with at least one
    failed play, 'fails': failed plays, 'counted': plays counted}, over every round, one phase or one round, and every
    title or one list's. The targets, the outcome and the final bar are judged on 'fails', the failed plays."""
    vs = _counted([v for v in visits if v['side'] == side and phase in (None, v['phase']) and rnd in (None, v['round'])
                   and lst in (None, v.get('list'))])
    failed = [v for v in vs if not plays(v)]
    return {'titles': len({v['title'] for v in failed}), 'fails': len(failed), 'counted': len(vs)}


def fails_words(f):
    """'2 titles failed · 4 of 40 plays': a fail figure (fail_figure) in words, the titles and the plays both named, or
    'no figure' when no play was counted."""
    if not f['counted']:
        return NO_FIGURE
    return f"{f['titles']} title{'' if f['titles'] == 1 else 's'} failed · {f['fails']} of {f['counted']} plays"


def fail_visits(visits, side, lst=None):
    """The counted visits of one side (of one list) whose top pick failed, in the order they were played."""
    return [v for v in _counted([v for v in visits if v['side'] == side and lst in (None, v.get('list'))]) if not plays(v)]


def side_plays(visits, side, lst=None):
    """(top picks that played, top picks counted) of one side over every round, as the targets count them; with `lst`,
    over the titles of that list alone (#167)."""
    return _plays(visits, side, lst=lst)


MET, NOT_MET, NOT_MEASURED = 'met', 'not met', 'not measured'


def _verdict(result, slower_s=None, noise=None, value=None, limit=None, **held):
    """A target's verdict as a value: the result (MET, NOT_MET or NOT_MEASURED); for a time target that is not met, how many
    seconds KaijuFlow is slower than what it is held against; the noise: None, or KaijuFlow's two rounds of the phase
    with how far the target is met or missed by, when those two rounds differ by more than that; and the two figures the
    result compares (None when not measured): KaijuFlow's value and the limit it is held to, both in seconds for a time
    target (the limit includes the margin), both (top picks that played, top picks counted) for a plays target, both fail
    figures (fail_figure) for a speed test's fails target. A speed test's verdict also names what the two figures were
    judged on (`held`): 'held_against', the setup the limit is from (None for a fixed limit), and 'left_out', how many
    titles were left out of both figures as not like for like."""
    return {'result': result, 'slower_s': slower_s, 'noise': noise, 'value': value, 'limit': limit, **held}


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


def _measure_target(visits, t, unlike=None):
    """(measured values, verdict) of one entry of the targets file. A target held against a side leaves out the titles that
    are not like for like between KaijuFlow and that side (`unlike`, as unlike_titles gives it), and says how many."""
    left_out = (unlike or {}).get(t.get('against'), {})
    if left_out:
        visits = [v for v in visits if v['title'] not in left_out]
        n = len(left_out)
        measured, verdict = _measure_target(visits, t)
        return f"{measured} ({n} title{'' if n == 1 else 's'} left out: not like for like)", verdict
    me, margin = SIDE_NAMES[JUDGED], t['margin']
    if t['measure'] == 'plays per round':  # every round the run holds, cold and warm
        rounds = {phase: [x for p, r in RUN_ORDER if p == phase for x in [_plays(visits, JUDGED, phase, r)] if x[1]]
                  for phase in ('cold', 'warm')}
        measured = ', '.join(f'{phase} ' + (' and '.join(_plays_text(x) for x in rs) or NO_FIGURE) for phase, rs in rounds.items())
        if not all(rounds.values()):
            return measured, _verdict(NOT_MEASURED)
        met = all(p >= t['limit'] - margin and n - p <= margin for rs in rounds.values() for p, n in rs)
        every = [x for rs in rounds.values() for x in rs]
        value = (sum(p for p, _ in every), sum(n for _, n in every))
        limit = (sum(t['limit'] - margin for _ in every), value[1])
        return measured, _verdict(MET if met else NOT_MET, value=value, limit=limit)
    if t['measure'] == 'plays':  # the share of top picks that played, every round together
        (p, n), (q, m) = _plays(visits, JUDGED), _plays(visits, t['against'])
        measured = f"{me} {_plays_text((p, n))}, {SIDE_NAMES[t['against']]} {_plays_text((q, m))}"
        if not n or not m:
            return measured, _verdict(NOT_MEASURED)
        # At least as often, and more often unless both play every time (spec #58; owner, 2026-11-15): a tie at the
        # maximum is met, any other tie is not.
        more_often = p * m > (q - margin * m) * n
        both_every_time = p == n and q == m
        return measured, _verdict(MET if more_often or both_every_time else NOT_MET, value=(p, n), limit=(q, m))
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
    figures = {'value': mine, 'limit': round(ref + margin, 2)}
    return measured, _verdict(MET, noise=noise, **figures) if over <= 0 else _verdict(NOT_MET, mine - ref, noise, **figures)


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
    unlike = unlike_titles(visits)
    return [(t['target'],) + _measure_target(visits, t, unlike) for t in load_targets(path)]


SPEED_MEASURES = ('fails', 'cold title to video', 'warm title to video')  # a speed test's measures (#169), judged per list


def load_speed_targets(path=TARGETS_FILE):
    """The speed test's part of the targets file: {'targets': [entry]}. ValueError with a plain reason when it cannot be used."""
    name = os.path.basename(path)
    try:
        with open(path) as f:
            speed = json.load(f)['speed_test']
        targets = speed['targets']
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f'{name} cannot be read: {type(e).__name__} in "speed_test"') from None
    for i, t in enumerate(targets, 1):
        if not isinstance(t, dict) or not isinstance(t.get('target'), str):
            why = 'it has no target text'
        elif t.get('measure') not in SPEED_MEASURES:
            why = f"the measure \"{t.get('measure')}\" is not known"
        elif t['measure'] == 'warm title to video' and not _is_number(t.get('limit')):
            why = '"warm title to video" takes a fixed limit'
        else:
            continue
        raise ValueError(f'{name}, speed test entry {i}: {why}')
    if not isinstance(speed.get('final_bar'), str):
        raise ValueError(f'{name}, speed test: the final bar has no text')
    return speed


def _others(visits):
    """The setups KaijuFlow is held against in a run: every side but KaijuFlow and its variants, in SIDE_NAMES order."""
    return [s for s in SIDE_NAMES if not s.startswith(JUDGED) and any(v['side'] == s for v in visits)]


def _pair(visits, side, lst, unlike):
    """KaijuFlow against one other setup on one list, on the titles that are like for like between the two:
    {'side', 'mine', 'theirs', 'left_out', 'rounds'}, where mine and theirs are fail figures (fail_figure) with 'video'
    added (the median cold title to video, None without a top pick that played), left_out is how many of the list's titles
    were left out of both, and rounds is KaijuFlow's cold title to video in each of its two cold rounds."""
    left_out = unlike.get(side, {})
    vs = [v for v in visits if v.get('list') == lst and v['title'] not in left_out]
    titles = {v['title'] for v in visits if v.get('list') == lst}

    def figures(s):
        return {**fail_figure(vs, s, lst=lst), 'video': _time(vs, s, 'cold', 'video', lst=lst)}
    return {'side': side, 'mine': figures(JUDGED), 'theirs': figures(side), 'left_out': len(titles & set(left_out)),
            'rounds': tuple(_time(vs, JUDGED, 'cold', 'video', r, lst) for r in (1, 2))}


def left_out_words(n):
    """'1 title left out: not like for like', or '' when none was."""
    return f"{n} title{'' if n == 1 else 's'} left out: not like for like" if n else ''


def _fails_part(f):
    return [fails_words(f)]


def _video_part(f):
    return [_secs(f['video']), fails_words(f)]


def _part_text(part):
    """'3.50 s (1 title failed · 1 of 8 plays; more failed plays: not held against it)' from [main, detail...]."""
    main, *details = part
    return main + (f" ({'; '.join(details)})" if details else '')


def _pairs_text(pairs, mine, part, note=None):
    """'KaijuFlow 1 title failed · 1 of 8 plays, Usenet Ultimate 2 titles failed · 2 of 8 plays, AltMount direct 1 title
    failed · 1 of 6 plays (KaijuFlow 1 title failed · 1 of 6 plays on the same titles; 1 title left out: not like for
    like)': KaijuFlow's figure, then each other setup's, with what note(pair) says of it and KaijuFlow's figure on the same
    titles when some were left out."""
    out = [f'{SHORT_NAMES[JUDGED]} {_part_text(part(mine))}']
    for p in pairs:
        main, *details = part(p['theirs'])
        details += [x for x in [note and note(p)] if x]
        if p['left_out']:
            details.append(f"{SHORT_NAMES[JUDGED]} {_part_text(part(p['mine']))} on the same titles; {left_out_words(p['left_out'])}")
        out.append(f"{SHORT_NAMES[p['side']]} {_part_text([main] + details)}")
    return ', '.join(out)


def _vs(p):
    """'KaijuFlow 1 title failed · 2 of 8 plays against Usenet Ultimate 0 titles failed · 0 of 8 plays', the two figures of
    a pair on the titles they were judged on, with how many were left out."""
    words = (f"{SHORT_NAMES[JUDGED]} {fails_words(p['mine'])} against {SHORT_NAMES[p['side']]} "
             f"{fails_words(p['theirs'])}")
    return words + (f"; {left_out_words(p['left_out'])}" if p['left_out'] else '')


def _time_verdict(mine, limit, rounds, phase, strict=False, **held):
    """The verdict of a time target: met when KaijuFlow's figure is no higher than the limit (lower, when strict), with
    the noise of KaijuFlow's two rounds of the phase (`rounds`) as the targets of before have it."""
    over = round(mine - limit, 2)  # above 0: missed by this much; below: met by this much
    a, b = rounds
    noise = ({'phase': phase, 'rounds': (a, b), 'by': abs(over)}
             if a is not None and b is not None and round(abs(a - b), 2) > abs(over) else None)
    if over < 0 or (over == 0 and not strict):
        return _verdict(MET, noise=noise, value=mine, limit=limit, **held)
    return _verdict(NOT_MET, over, noise, value=mine, limit=limit, **held)


def _judge_fails(visits, lst, pairs, entry):
    """Target 1 on one list: KaijuFlow fails no more plays than any other setup, and none on the easy list. Against a
    setup it is judged on the titles like for like with it; the no-fail rule of the easy list is a fixed limit and keeps
    every title. The verdict's figures are the ones the result was decided on: on the easy list KaijuFlow's against no
    fail, on the hard list KaijuFlow's against the setup it is closest to failing more than (on the same titles)."""
    mine = _pair(visits, JUDGED, lst, {})['mine']
    measured = _pairs_text(pairs, mine, _fails_part)
    if not mine['counted'] or not pairs:
        return measured, _verdict(NOT_MEASURED)
    met = all(p['mine']['fails'] <= p['theirs']['fails'] for p in pairs) and not (lst == 'easy' and mine['fails'])
    if lst == 'easy':
        none = {'titles': 0, 'fails': 0, 'counted': mine['counted']}
        return measured, _verdict(MET if met else NOT_MET, value=mine, limit=none, held_against=None, left_out=0)
    p = max(pairs, key=lambda p: (p['mine']['fails'] - p['theirs']['fails'], -p['left_out']))
    return measured, _verdict(MET if met else NOT_MET, value=p['mine'], limit=p['theirs'], held_against=p['side'],
                              left_out=p['left_out'])


def _judge_cold_video(visits, lst, pairs, entry):
    """Target 2 on one list: KaijuFlow's median cold title to video, over the titles it played, is no slower than that of
    any setup with as few fails or fewer (owner, 2026-11-15): a faster setup that fails more plays than KaijuFlow is not
    held against it (fails come first), nor is a setup with no title to video."""
    mine = _pair(visits, JUDGED, lst, {})['mine']
    measured = _pairs_text(pairs, mine, _video_part,
                           lambda p: 'more failed plays: not held against it' if p['theirs']['fails'] > p['mine']['fails'] else None)
    if mine['video'] is None or not pairs:
        return measured, _verdict(NOT_MEASURED)
    held = [p for p in pairs if p['theirs']['fails'] <= p['mine']['fails'] and None not in (p['mine']['video'], p['theirs']['video'])]
    if not held:
        return measured + '; every other setup fails more plays', _verdict(MET, value=mine['video'], held_against=None, left_out=0)
    p = max(held, key=lambda p: p['mine']['video'] - p['theirs']['video'])  # the setup KaijuFlow is furthest behind
    return measured, _time_verdict(p['mine']['video'], p['theirs']['video'], p['rounds'], 'cold', held_against=p['side'],
                                   left_out=p['left_out'])


def _judge_warm_video(visits, lst, pairs, entry):
    """Target 3 on one list: KaijuFlow's median warm title to video is under the limit (1.00 s is not under 1 s)."""
    mine = _time(visits, JUDGED, 'warm', 'video', lst=lst)
    measured = f'{SHORT_NAMES[JUDGED]} {_secs(mine)}'
    if mine is None:
        return measured, _verdict(NOT_MEASURED)
    rounds = tuple(_time(visits, JUDGED, 'warm', 'video', r, lst) for r in (1, 2))
    return measured, _time_verdict(mine, entry['limit'], rounds, 'warm', strict=True, held_against=None, left_out=0)


SPEED_JUDGES = {'fails': _judge_fails, 'cold title to video': _judge_cold_video, 'warm title to video': _judge_warm_video}


# The three outcomes of the hard list, decided before the first speed test (ADR 0007, spec #159), and what each says to do.
OUTCOME_TUNE, OUTCOME_NO_PRE_LIST_CHECK, OUTCOME_BUG = 'tune its speed', 'try without its pre-list check', 'find the bug'
OUTCOME_HEAD = 'Outcome on the hard list: '
ALTMOUNT = 'altmount-addon'  # the setup the outcome compares KaijuFlow with: AltMount direct


def _outcome(visits, unlike):
    """{'outcome', 'text'}: which outcome the hard list gave, KaijuFlow against AltMount direct on the titles like for
    like between the two (failed plays first, then the median cold title to video). The same fails with KaijuFlow no
    slower is "as reliable and no slower: tune its speed" (owner, 2026-11-15). Outcome None when it cannot be named."""
    if 'hard' not in run_lists(visits) or ALTMOUNT not in _others(visits):
        why = 'the run has no hard list' if 'hard' not in run_lists(visits) else f'{SHORT_NAMES[ALTMOUNT]} is not in the run'
        return {'outcome': None, 'text': f'{OUTCOME_HEAD}not named: {why}.'}
    p = _pair(visits, ALTMOUNT, 'hard', unlike)
    me, them, (a, b) = SHORT_NAMES[JUDGED], SHORT_NAMES[ALTMOUNT], (p['mine'], p['theirs'])
    if a['fails'] < b['fails']:
        return {'outcome': OUTCOME_TUNE, 'text': f'{OUTCOME_HEAD}{me} fails fewer plays than {them} ({_vs(p)}), so tune its speed.'}
    if a['fails'] > b['fails']:
        return {'outcome': OUTCOME_BUG, 'text': f"{OUTCOME_HEAD}{them} fails fewer plays than {me} ({_vs(p)}), so {me}'s "
                                                'checking has a bug to find first.'}
    if a['video'] is None or b['video'] is None:
        return {'outcome': None, 'text': f'{OUTCOME_HEAD}not named: {me} and {them} fail as many plays ({_vs(p)}), and one '
                                         'of them has no cold title to video.'}
    video = f"cold title to video {_secs(a['video'])} against {_secs(b['video'])}"
    if b['video'] < a['video']:
        return {'outcome': OUTCOME_NO_PRE_LIST_CHECK, 'text': (
            f"{OUTCOME_HEAD}{me} and {them} fail as many plays ({_vs(p)}) and {them} is faster (cold title to video "
            f"{_secs(b['video'])} against {_secs(a['video'])}), so try {me} without its own pre-list check, behind AltMount.")}
    return {'outcome': OUTCOME_TUNE, 'text': f'{OUTCOME_HEAD}{me} is as reliable and no slower: tune its speed ({_vs(p)}; {video}).'}


def _bar_on_list(visits, lst, pairs):
    """{'result', 'why'}: the final bar on one list. Fewest fails: no more failed plays than any other setup, any tie
    counting as fewest (owner, 2026-11-15); then strictly the fastest median cold title to video among the setups with as
    few. A setup that fails more is not held against KaijuFlow's speed. Each comparison is on the titles like for like."""
    me, mine = SHORT_NAMES[JUDGED], _pair(visits, JUDGED, lst, {})['mine']
    if not mine['counted'] or not pairs:
        return {'result': NOT_MEASURED, 'why': f'no {"figure" if pairs else "other setup"} to judge it on'}
    for p in pairs:
        if p['theirs']['fails'] < p['mine']['fails']:
            return {'result': NOT_MET, 'why': f"{SHORT_NAMES[p['side']]} fails fewer plays ({_vs(p)})"}
    tied = [p for p in pairs if p['theirs']['fails'] == p['mine']['fails']]
    for p in tied:
        a, b = p['mine'], p['theirs']
        if a['video'] is None or (b['video'] is not None and b['video'] <= a['video']):
            return {'result': NOT_MET, 'why': f"{SHORT_NAMES[p['side']]} fails as few plays ({_vs(p)}) and is as fast or "
                                              f"faster (cold title to video {_secs(b['video'])} against {me}'s {_secs(a['video'])})"}
    speed = ('; '.join(f"cold title to video {_secs(p['mine']['video'])} against {SHORT_NAMES[p['side']]}'s "
                       f"{_secs(p['theirs']['video'])}" for p in tied) if tied else 'no other setup fails as few plays')
    return {'result': MET, 'why': f"{me} fails the fewest plays ({'; '.join(_vs(p) for p in pairs)}) and is the fastest "
                                  f'among setups with as few ({speed})'}


def _final_bar(visits, lists, text):
    """{'target', 'lists': {list: {'result', 'why'}}, 'verdict'}: the final bar on each list and on both together. Met
    when met on both lists; not measured when the run lacks a list or a list holds no figure for it."""
    results = [r['result'] for r in lists.values()]
    if set(run_lists(visits)) != set(LISTS) or NOT_MEASURED in results:
        result = NOT_MEASURED
    else:
        result = MET if all(r == MET for r in results) else NOT_MET
    return {'target': text, 'lists': lists, 'verdict': _verdict(result)}


def speed_test_judgement(visits, path=TARGETS_FILE):
    """The judgement of a tagged run (#169), for the check, the report and the page: {'targets': [{'number', 'target',
    'list', 'measured', 'verdict'}], 'outcome': {'outcome', 'text'}, 'final_bar': {'target', 'lists', 'verdict'}}: each
    target of the targets file's speed test part judged on each list of the run, list by list; the outcome of the hard
    list (_outcome); and the owner's final bar (_final_bar), which is shown apart and never counted with the targets.
    ValueError when the targets file cannot be used."""
    speed = load_speed_targets(path)
    unlike = unlike_titles(visits)
    rows, bar = [], {}
    for lst in run_lists(visits):
        pairs = [_pair(visits, s, lst, unlike) for s in _others(visits)]
        for n, t in enumerate(speed['targets'], 1):
            measured, verdict = SPEED_JUDGES[t['measure']](visits, lst, pairs, t)
            rows.append({'number': n, 'target': t['target'], 'list': lst, 'measured': measured, 'verdict': verdict})
        bar[lst] = _bar_on_list(visits, lst, pairs)
    return {'targets': rows, 'outcome': _outcome(visits, unlike), 'final_bar': _final_bar(visits, bar, speed['final_bar'])}


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
        if tagged(run['visits']):
            return speed_test_lines(speed_test_judgement(run['visits'], path))
        return [f'Target: {t}. Measured: {m}. {verdict_text(v)}.' for t, m, v in target_results(run['visits'], path)]
    except ValueError as e:
        return [f'Targets: not judged ({e}).']


SPEED_TARGETS_HEAD = 'Speed test targets, judged per list (an untagged run is judged on the six of before):'
FINAL_BAR_NOTE = 'shown apart from the targets, not counted towards usable'
FINAL_BAR_HEAD = f'Final bar ({FINAL_BAR_NOTE}): '


def met_count(rows):
    """'5 of 6 targets met.' for a speed test's target rows (speed_test_judgement); the final bar is never one of them."""
    return f"{sum(1 for r in rows if r['verdict']['result'] == MET)} of {len(rows)} targets met."


def final_bar_text(bar):
    """The final bar in one sentence after its text: its result, then each list's result and why."""
    return (f"{bar['target']} {bar['verdict']['result'].capitalize()}. " +
            ' '.join(f"{x.capitalize()} list: {r['result']}, {r['why']}." for x, r in bar['lists'].items()))


def speed_test_lines(judgement):
    """The check's lines of a tagged run's judgement (speed_test_judgement): one line per target and list, how many are
    met, the outcome line, and the final bar on a line of its own."""
    rows = judgement['targets']
    return ([SPEED_TARGETS_HEAD] +
            [f"Target, {r['list']} list: {r['target']}. Measured: {r['measured']}. {verdict_text(r['verdict'])}." for r in rows] +
            [met_count(rows), judgement['outcome']['text'], FINAL_BAR_HEAD + final_bar_text(judgement['final_bar'])])


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
        if tagged(run['visits']):
            return speed_targets_section(speed_test_judgement(run['visits'], path))
        rows = target_results(run['visits'], path)
    except ValueError as e:
        return ['## Targets', '', f'Not judged ({e}).', '']
    met = sum(1 for _, _, verdict in rows if verdict['result'] == MET)
    return ['## Targets', ''] + _table(['Target', 'This run', 'Result'], [(t, m, verdict_text(v)) for t, m, v in rows]) + [
        '', f"{met} of {len(rows)} targets met. {TARGETS_HELP}", '']


SPEED_TARGETS_HELP = (
    'Each target is judged on each list on its own. Fails = plays whose top pick did not play on its one try, every round '
    'together; each count names the titles with a failed play and the failed plays. Title to video = seconds from asking '
    'for the title until video arrived, the median over the top picks that played in both cold (or both warm) rounds. A '
    'setup that fails more plays than KaijuFlow is not held against its title to video. A title that is not like for like '
    'with a setup is left out of judging KaijuFlow against it, on both sides. '
    '"Inside the noise": KaijuFlow\'s own two rounds differ by more than the target is met or missed by.')


def speed_targets_section(judgement):
    """The report's Targets section of a tagged run (speed_test_judgement): one row per list and target, how many are
    met, the outcome line, and the final bar in a paragraph of its own."""
    rows = judgement['targets']
    return ['## Targets', ''] + _table(['List', 'Target', 'This run', 'Result'], [
        (r['list'], r['target'], r['measured'], verdict_text(r['verdict'])) for r in rows]) + [
        '', f'{met_count(rows)} {SPEED_TARGETS_HELP}', '', judgement['outcome']['text'], '',
        f"**Final bar** ({FINAL_BAR_NOTE}): {final_bar_text(judgement['final_bar'])}", '']


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


def _list_counts(run):
    """'4 titles (2 easy, 2 hard)'."""
    lists = run.get('lists') or {v['title']: v.get('list') for v in run['visits']}
    n = len(run.get('titles', [])) or len(lists)
    parts = ', '.join(f"{sum(1 for x in lists.values() if x == lst)} {lst}" for lst in run_lists(run['visits']))
    return f"{n} title{'' if n == 1 else 's'} ({parts})"


def _speed_answer(run):
    """A tagged run's opening sentence (#159: fails first, then title to video; list and start times stay as detail)."""
    vs, lists = run['visits'], run_lists(run['visits'])
    fails = '; '.join(f"{SIDE_NAMES[s]} " + ', '.join(f'{x} {fails_words(fail_figure(vs, s, lst=x))}' for x in lists)
                      for s in _sides(run))
    video = '; '.join(f"{SIDE_NAMES[s]} " + ', '.join(f"{x} {_cell(_time(vs, s, 'cold', 'video', lst=x))} s" for x in lists)
                      for s in _sides(run))
    return (f"Across {_list_counts(run)}, each round done {'once' if run.get('rounds') == 1 else 'twice'}. "
            f'Fails, every round: {fails}. Median cold title to video: {video}.')


def answer_sentence(run):
    if tagged(run['visits']):
        return _speed_answer(run)
    vs = run['visits']

    def fmt(phase):
        return ', '.join(f"{SIDE_NAMES[s]} {_cell(_time(vs, s, phase, 'start'))} s "
                         f"({' of '.join(str(x) for x in _plays(vs, s, phase))} top picks played)" for s in _sides(run))
    n = len(run.get('titles', []))
    return (f"Across {n} title{'' if n == 1 else 's'}, each round done {'once' if run.get('rounds') == 1 else 'twice'}, the median time from pressing play to the first byte was, "
            f"cold: {fmt('cold')}; warm: {fmt('warm')}.")


def headline(run):
    """The run's INDEX.md headline: a tagged run's fails and cold title to video per list, else its start times and plays."""
    vs = run['visits']
    if tagged(vs):
        lists = run_lists(vs)
        return '; '.join(f"{SIDE_NAMES[s]} fails " + ', '.join(f'{x} {fails_words(fail_figure(vs, s, lst=x))}' for x in lists)
                         + ', cold title to video ' + ' / '.join(f"{_cell(_time(vs, s, 'cold', 'video', lst=x))} s" for x in lists)
                         for s in _sides(run))
    return '; '.join(f"{SIDE_NAMES[s]} cold {_cell(_time(vs, s, 'cold', 'start'))} s / warm {_cell(_time(vs, s, 'warm', 'start'))} s, "
                     f"plays {'/'.join(str(x) for x in _plays(vs, s))}" for s in _sides(run))


def _table(cols, rows):
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return out


def _defs(cols):
    return [f'- **{c}**: {COLUMN_HELP.get(c) or LIST_COLUMN_HELP[c]}' for c in cols]


def load_run(folder):
    """A run folder as the report reads a run: its meta.json, with the visits of its raw.json under 'visits'."""
    with open(os.path.join(folder, 'meta.json')) as f:
        run = json.load(f)
    with open(os.path.join(folder, 'raw.json'), encoding='utf-8') as f:
        run['visits'] = json.load(f).get('visits') or []
    return run


def tagged(visits):
    """Whether a run's visits were played on a tagged title list (#167): any visit keeps its title's list."""
    return any(v.get('list') for v in visits)


LISTS = common.LISTS
LIST_SECTION = '## Fails and title to video per list'
LIST_HELP = ('Fails = plays whose top pick did not play on its one try: no video, the failure video, a refusal, or video '
             'only after a fallback ("played after N fallbacks"). "1 title failed · 2 of 20 plays" names the titles with a failed '
             'play and the failed plays out of the plays of the list in the phase, then each round. A warm play that works '
             'after a cold fail is a warm play; the cold fail stays a fail. Title to video = seconds from asking for the title '
             'until video arrived (list time plus start time), the median over the top picks that played in both rounds of the phase.')


def run_lists(visits):
    """The lists a run's titles are on, in LISTS order; [] for a run without tags."""
    return [x for x in LISTS if any(v.get('list') == x for v in visits)]


def list_section(run):
    """The report's table of a tagged run (#167): per side, list and phase, the median title to video. Empty for a run
    without tags."""
    vs = run['visits']
    rows = [[SIDE_NAMES[s], x, phase.capitalize(), _round_fails(vs, s, phase, x), _cell(_time(vs, s, phase, 'video', lst=x))]
            for s in _sides(run) for x in run_lists(vs) for phase in ('cold', 'warm')]
    if not rows:
        return []
    return [LIST_SECTION, ''] + _table(['Side', 'List', 'Phase', 'Fails', 'Title to video'], rows) + ['', LIST_HELP, '']


def _round_fails(vs, side, phase, lst):
    """'1 title failed · 1 of 20 plays: 1 of 10 in Cold 1, 0 of 10 in Cold 2': the fails of one side and list in a phase,
    then in each of its rounds the run holds."""
    rounds = ', '.join(f"{side_fails(vs, side, phase, r, lst)} of {n} in {_run_label(phase, r)}"
                       for p, r in RUN_ORDER if p == phase for n in [_plays(vs, side, phase, r, lst)[1]] if n)
    return f'{fails_words(fail_figure(vs, side, phase, lst=lst))}: {rounds}' if rounds else '-'



def render_report(run, changes, opening=None):
    g = _groups(run)
    lists = tagged(run['visits'])
    lines = [opening or answer_sentence(run), '',
             f"Run: {run['name']}. KaijuFlow code {run.get('commit')}{' (with uncommitted changes)' if run.get('dirty') else ''}. "
             f"Started {run.get('started')}. All times are medians over the titles of one round, in seconds; "
             "\"-\" means that side does not show the step from outside.", ''] + targets_section(run) + [
             '## Like for like', ''] + like_for_like_lines(run['visits']) + ['', LIKE_FOR_LIKE_HELP, '',
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
                                         if plays(v) or k in ('search_s', 'indexer_s', 'own_s')]))
            shared.append([SIDE_NAMES[s], lab, md('search_s'), md('indexer_s'), md('own_s'), md('nzb_fetch_s'), md('import_s'),
                           md('start_s')])
            extra.append([SIDE_NAMES[s], lab, md('indexer_wait_s'), md('health_s'), md('unscramble_s'), md('probe_s')])
            causes = [classify_failure(v) for v in vs]
            counted = _counted(vs)
            fail.append([SIDE_NAMES[s], lab, f"{sum(1 for v in counted if plays(v))} of {len(counted)}",
                         sum(1 for c in causes if c == 'fallback')] + [sum(1 for c in causes if c == k) for k, _ in CAUSES])
    lines += ['## Steps every side shares', ''] + _table(SHARED_COLS, shared) + [''] + _defs(SHARED_COLS) + ['']
    lines += ['## Extras (steps only some sides have)', ''] + _table(EXTRA_COLS, extra) + [''] + _defs(EXTRA_COLS[2:]) + ['']
    lines += list_section(run)
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
                    res = 'plays' if plays(v) else failed_result(v, cause)
                    if lists:
                        rows.append([t, v.get('list') or '-', SIDE_NAMES[s], _run_label(phase, rnd)] + _pick_cells(top_pick(v))
                                    + [v.get('sources', '-'), _cell(m['search_s']), _cell(m['start_s']),
                                       _cell(title_to_video(v)), res])
                    else:
                        rows.append([t, SIDE_NAMES[s], _run_label(phase, rnd)] + _pick_cells(top_pick(v))
                                    + [v.get('sources', '-'), _cell(m['search_s']), _cell(m['start_s']), res])
    cols = TAGGED_TITLE_COLS if lists else TITLE_COLS
    lines += ['## Per title', ''] + _table(cols, rows) + [''] + _defs(cols) + ['']
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
    """The Result cell of a top pick that did not play: the failure kind, the cause or note, and how long the whole visit took.
    A fallback says how many imports failed before the video arrived."""
    if cause == 'fallback':
        n = fallbacks(v)
        return f"played after {n} fallback{'' if n == 1 else 's'}"
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


def _seconds_cell(x):
    return '-' if x is None else f'{x:.1f}'


def _minutes(x):
    return '-' if x is None else f'{x / 60:.1f}'


def _took(x):
    return f'{_minutes(x)} minutes ({_seconds_cell(x)} s)'


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
    rows = [[name, _seconds_cell(parts.get(key)), _minutes(parts.get(key))] for key, name in TIME_PARTS]
    out += _table(['Part', 'Seconds', 'Minutes'], rows + [['The whole run', _seconds_cell(timing.get('seconds')), _minutes(timing.get('seconds'))]])
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
            '- **Pass**: the main sides (KaijuFlow, Usenet Ultimate, AltMount direct) are played in turn, title by '
            'title, in one pass; the one-page side has its own pass after them.',
            '- **Round**: the cold or warm round of every side of the pass, played together, from the first play to the end '
            'of the pause after the last play. The reset before a cold round is not part of it.', '']
    return out


def _round_rows(rounds, resets):
    """One row per round of each pass, in the order they were played, with the reset that came before it. A reset with no
    round after it (the run ended during the reset) gets a row too, so every reset is shown."""
    def round_key(r):
        return r.get('pass'), r.get('phase'), r.get('round')
    reset_of, round_of = {round_key(r): r for r in resets}, {round_key(r): r for r in rounds}
    rows = []
    for key in dict.fromkeys(round_key(r) for r in sorted(resets + rounds, key=lambda r: str(r.get('start')))):
        r = round_of.get(key) or {}
        rows.append([str(key[0]).capitalize(), _run_label(str(key[1]), key[2]), _time_of_day(r.get('start')) if r else '-',
                     _seconds_cell(reset_of.get(key, {}).get('seconds')), r.get('plays', 0), _seconds_cell(r.get('seconds')), _minutes(r.get('seconds'))])
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
              'are not used. stopped = the run was stopped (Ctrl-C or SIGTERM) before its last play and is not a baseline.\n\n| Date (UTC) | Name | Result | What changed from the previous run | Headline numbers | Folder |\n'
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


def previous_run(root, exclude=None, usable=None):
    """meta.json of the newest earlier finished (non-null) run, or None. A short run or one marked never compared with is never it. `usable(run folder)`, when
    given, must also say yes (a short run is compared with the last run usable as a baseline); the meta gets its `folder`. Its top picks are added from the folder's raw.json
    (`top_picks`), so the next run can be compared with them; a folder that holds none stays without."""
    for d in reversed(run_folders(root)):
        if d == exclude:
            continue
        try:
            meta = json.loads(_slurp(os.path.join(root, d, 'meta.json')))
        except (OSError, ValueError):
            continue
        if meta.get('status') == 'ok' and not meta.get('short') and not never_compared(meta) and (usable is None or usable(os.path.join(root, d))):
            meta['folder'] = d
            try:
                picks = top_picks(json.loads(_slurp(os.path.join(root, d, 'raw.json')))['visits'])
            except (OSError, ValueError, KeyError, TypeError):
                picks = None
            if picks:
                meta['top_picks'] = picks
            return meta
    return None
