"""Merge, report and run records for the Brain runs (spec #58, ticket #62). Pure logic: no Docker, no network.

brainrun.py collects one "visit" per run phase, side and title; this module turns visits into
medians, a failure split, a diff against the previous run, the plain-language report and the run folder / INDEX.md
bookkeeping. The run is judged against the previous run in runcheck.py; the Speed Check page's targets, held against
other setups, are in pagetargets.py (page code, #187).
"""
import datetime
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import common  # noqa: E402

# A run plays KaijuFlow, and with --one-page its one-page side (#185). Usenet Ultimate and AltMount direct are the sides of
# the runs before #185, named here only so an earlier or archived run still reads as it was (#187).
SIDE_NAMES = {
    'kaijuflow': 'KaijuFlow',
    'uu': 'Usenet Ultimate',
    'altmount-addon': "AltMount direct",
    'kaijuflow-1page': 'KaijuFlow, one page per indexer',
}
SHORT_NAMES = {'kaijuflow': 'KaijuFlow',
               'kaijuflow-1page': 'KaijuFlow with one page per indexer'}  # the sides as a short run's text names them (GLOSSARY)
RUN_ORDER = [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)]
CAUSES = [('indexer_limit', 'Indexer limit'), ('backend_rejection', 'Backend rejection'),
          ('failure_video', 'Failure video'), ('other', 'Other'), ('not_recorded', 'Not recorded')]
SEARCH_STEPS = ('indexer_page', 'health_batch')
# The stream list's own lines (#249): the whole request with a trace of the process (`list`), then its parts. They carry
# `ref` like the search-side lines and are kept by it.
LIST_STEPS = ('list', 'list_filter', 'list_sort', 'list_build', 'fallback_group', 'head_start')
REF_STEPS = SEARCH_STEPS + LIST_STEPS
PLAY_CHECK = 'play_check'  # one line per Source the Play-time check checked (#190): Best checks several, a list entry one

COLUMN_HELP = {
    'Side': 'KaijuFlow, or KaijuFlow with one page per indexer (`--one-page`).',
    'Run': 'Cold 1 and Cold 2 start from an empty Backend (nothing imported yet); Warm 1 and Warm 2 follow right after, '
           'so the Backend already knows the titles. The number is the first or second time the whole round was done.',
    'Search': 'seconds from asking for the Stream list of a title until the list arrived, KaijuFlow\'s health checks '
              'included.',
    'NZB fetch': 'seconds to download the chosen Source\'s NZB file from the indexer stand-in, from KaijuFlow\'s own '
                 'step lines; "-" when they show none.',
    'Import': 'seconds the Backend needed to take the NZB in and make the video ready: KaijuFlow\'s own timing, to the '
              'millisecond. "-" means it showed no figure.',
    'First byte': 'seconds from pressing play on the top pick until the first piece of video arrived. This is the '
                  'whole start and includes the NZB fetch and the import.',
    'Indexer wait': 'KaijuFlow only: seconds spent waiting for indexers during the search (the slowest indexer, its '
                    'pages added up; indexers are asked at the same time).',
    'Health checks': 'seconds spent checking whether Sources look downloadable (the checks of one list added up; '
                     'if they overlap, the real wait was shorter), plus the wait for the Play-time checks after the press '
                     '(#190; checks run together count once). KaijuFlow only.',
    'Unscramble': 'KaijuFlow only: seconds spent putting scrambled RAR parts in order before the import.',
    'Backend probe': 'KaijuFlow only: seconds KaijuFlow waited for the Backend to deliver the first byte after the import.',
    'Indexers': 'seconds of the search time that were the indexers\' answering time (for a replayed answer, the time the real '
                'indexer took when it was recorded; indexers are asked at the same time, so the slowest one counts). '
                '"-" means no stand-in log line was matched to the visit; 0 means the replay wait was off.',
    "Side's own work": 'Search minus Indexers: what the side itself added to the list time (health checks, merging, its own requests).',
    'Top pick plays': 'titles whose top pick played, out of the titles in the round: on the first try or after a fallback. A '
                      'top pick that failed only because a request was not recorded is left out of both numbers (see Not recorded).',
    'Fallback': 'titles where video arrived only after the top pick\'s own import failed (the side fell back to another Source '
                'or to a file it already held). They count as played (#185), with the seconds the fallback took in their '
                'title to video.',
    'Indexer limit': 'failures caused by an indexer saying its limit was reached (such a run is stopped, so this '
                     'should stay 0 in a finished run).',
    'Backend rejection': 'failures where the Backend (AltMount) refused or could not import the NZB, or took the import '
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
    'Sources': 'how many Sources the side listed (KaijuFlow\'s Best entry is none, #190).',
    'Result': '"plays" when the top pick delivered video on the first try; "played after N fallbacks, S s extra" when video '
              'arrived only after N imports failed, the top pick\'s own among them, and S seconds is what those imports took; '
              'otherwise the failure kind and a short note.',
}
SHARED_COLS = ['Side', 'Run', 'Search', 'Indexers', "Side's own work", 'NZB fetch', 'Import', 'First byte']
EXTRA_COLS = ['Side', 'Run', 'Indexer wait', 'Health checks', 'Unscramble', 'Backend probe']
FAIL_COLS = ['Side', 'Run', 'Top pick plays', 'Fallback'] + [c for _, c in CAUSES]
TITLE_COLS = ['Title', 'Side', 'Run', 'Top pick', 'Size', 'Sources', 'Search', 'First byte', 'Result']
# A run on a tagged title list (#167) shows each title's list and its title to video too; a run without tags shows neither.
LIST_COLUMN_HELP = {
    'List': 'the title list the title is on: easy (popular, well kept) or hard (older releases, takedown-prone shows, less '
            'popular titles).',
    'Title to video': 'seconds from asking for the title until video arrived: Search plus First byte, a fallback\'s seconds '
                      'included. "-" for a fail: no video.',
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


# The wordings the sides really print when an indexer says "limit reached" (read from the live logs, read-only):
#  - the indexer's own newznab text, passed on by AltMount ("newznab API error 500: Request limit reached. Retry in
#    113 minutes", "search returned HTTP 429 (althub)") and by KaijuFlow's searchers,
#  - KaijuFlow's NZB grab (src/backends/nzbGrab.ts): "Failed to download NZB from <indexer>: 429 ...",
#  - the stand-in's own "LIMIT_REACHED indexer=<slug>" line.
# Loose phrases ("api limit", "limit reached" alone) are not used: "Backup processing limit reached" is a benign
# KaijuFlow line.
LIMIT_RE = re.compile(
    r'(?i)\b(?:request|grab|api|download|daily|nzb)s? limits? (?:has been |was )?(?:reached|exceeded)'
    r'|LIMIT_REACHED indexer='
    r'|\bHTTP 429\b'
    r'|Failed to download NZB from .+: 429\b'
    r'|Request failed with status code 429'
    r'|retry in \d+ minutes?')


def scrub_text(s):
    s = re.sub(r'(?i)((?:api_?key|key|token|password|pass)=)[^&\s"]+', r'\1***', s)
    return re.sub(r'://[^/@\s]+@', '://***@', s)


def limit_event(text, indexers):
    """First line that says an indexer's limit was reached: {indexer, time, line} or None."""
    for line in text.splitlines():
        if not LIMIT_RE.search(line):
            continue
        m = re.match(r'(\d{4}-\d\d-\d\dT[\d:.]+Z?)', line)
        name = next((n for n in indexers if n.lower() in line.lower()), 'unknown')
        return {'indexer': name, 'time': m.group(1) if m else None, 'line': scrub_text(line)[:300]}
    return None


# The stand-in's request lines (indexer_standin.py) end with `from=<client address> t=<epoch ms the answer was sent>`:
#   HIT <slug> <request> wait_ms=<n> from=.. t=..   MISS <slug> <request> from=.. t=..
#   RECORD <slug> <request> -> <status> <n> bytes from=.. t=..   ERROR <slug> <request> -> <status> from=.. t=..
# The runner maps each address to the test container that sent it and each container to its visits (assign_standin).
LINE_RE = re.compile(r'^(HIT|MISS|RECORD|ERROR) (\S+) (.*?)(?:\swait_ms=(\d+))? from=(\S+) t=(\d+)$')
# The test container that sends every side's indexer requests (the one-page side is KaijuFlow's container too).
CLIENT_CONTAINER = 'kaijuflow-test'
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
        per_container.setdefault(CLIENT_CONTAINER, []).append(v)

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



def unplayed_release(miss, visit):
    """True when a miss is an NZB grab of a release the visit never played (owner's decision on #218, #235: such a miss does
    not make a run unusable). Only for a visit that played, and only for a miss that names its release (#229) other than
    the visit's played Source; any other miss (a search, the played release, an NZB with no title) counts."""
    parts = miss.split(' ', 3)
    if not visit.get('ok') or len(parts) < 4 or parts[1] != 'nzb' or parts[3].startswith('(no title'):
        return False
    return parts[3] != (visit.get('played_source') or '')


def counted_misses(visit):
    """The visit's misses that make a run unusable: all of them but the unplayed releases."""
    return [m for m in visit.get('misses') or [] if not unplayed_release(m, visit)]

# --------------------------------------------------------------------------- metrics

def median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def _sum_ms(steps, name):
    ms = [s['ms'] for s in steps if s.get('step') == name]
    return round(sum(ms) / 1000, 3) if ms else None


def play_check_s(v):
    """Seconds the visit waited for its Play-time checks (#190): from the first check's start until the played Source's
    own check ended (the last check's end when no check names it). Best checks several Sources at once, so this is the
    time they covered together, not their sum; checks that ran on after the played Source was found are left out. None
    when the visit has no play_check line."""
    checks = [s for s in v.get('steps', []) if s.get('step') == PLAY_CHECK and s.get('t')]
    if not checks:
        return None
    src = _norm(v.get('played_source') or '')
    mine = [_ms(s['t']) for s in checks if src and _norm(s.get('title', '')) == src]
    until = max(mine) if mine else max(_ms(s['t']) for s in checks)
    return round(_union_s([(_ms(s['t']) - s['ms'], _ms(s['t'])) for s in checks if _ms(s['t']) <= until]), 3)


def visit_metrics(v):
    steps = [s for s in v.get('steps', []) if s.get('step') not in REF_STEPS or s.get('ref') == v.get('id')]
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
        # the list-time batches (before the list) and the Play-time checks (after the press, #190)
        'health_s': None if _sum_ms(steps, 'health_batch') is None and play_check_s(v) is None
        else round((_sum_ms(steps, 'health_batch') or 0) + (play_check_s(v) or 0), 3),
        'unscramble_s': _sum_ms(steps, 'unscramble'),
        'indexer_wait_s': round(max(pages.values()) / 1000, 3) if pages else None,
        'probe_s': _sum_ms(steps, 'first_byte'),
    }


def _norm(text):
    return re.sub(r'[^a-z0-9]+', '', str(text).lower())


PLAY_STEPS = ('played', 'play_failed')  # a play's two events, step lines KaijuFlow writes since #242


def read_play(text, visit):
    """What KaijuFlow's step lines say of one visit's play (#242), the only reading of KaijuFlow's log for it:
    {'played_source', 'cause'}, the fields collect_visit stores in raw.json (a run from before #242 is read from its stored
    raw.json, never again from its log).

    played_source: the release name of the visit's top pick, the first Source KaijuFlow tried for the play: the title of
    the first `played` line (its video was served) or `play_failed` line (it failed and the play went on, or showed the
    failure video), whichever comes first. A Head start writes the lines of its prepare before the press (#206), so they
    count as a press-started Best's do. None when there is no such line.
    cause: the reason on the first `play_failed` line, in KaijuFlow's words; '' when there is none.

    The lines are the visit's from its start on (a second before, as attribute_steps); a line naming another title's
    `ref` is that title's."""
    lo = parse_ts(visit['t_start']) - datetime.timedelta(seconds=1)

    def mine(s):
        try:
            return s.get('step') in PLAY_STEPS and s.get('title') and s.get('ref') in (None, visit.get('id')) \
                and parse_ts(s['t']) >= lo
        except (KeyError, ValueError, AttributeError):
            return False
    lines = [s for s in parse_step_lines(text) if mine(s)]
    failed = next((s for s in lines if s['step'] == 'play_failed'), None)
    return {'played_source': lines[0]['title'] if lines else None,
            'cause': scrub_text(str(failed.get('reason') or '')) if failed else ''}


def top_pick(v):
    """The top pick of one visit, the first Source in the side's list: {'name', 'size', 'listed'}, or None when the side
    listed none.

    name: the release name where KaijuFlow's step lines give it (`read_play`), otherwise the text the side showed for the
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
    KaijuFlow's Ultimate Fallback); 0 for a first-try play and for a visit that served no video."""
    if not v.get('ok') or not any(i.get('ok') is False for i in pick_imports(v)):
        return 0
    return sum(1 for i in v.get('imports') or [] if i.get('ok') is False)


def fallback_s(v):
    """The seconds a fallback added to its visit's title to video (#185): what the visit's failed imports took, added up.
    None for a visit that is no fallback, or when a failed import's time is not known."""
    secs = [i.get('seconds') for i in v.get('imports') or [] if i.get('ok') is False] if fallbacks(v) else [None]
    return None if any(s is None for s in secs) else round(sum(secs), 3)


def fallback_count(visits, side, lst=None):
    """How many of one side's plays fell back, every round of one list (or every title) together (spec #183)."""
    return sum(1 for v in visits if v['side'] == side and lst in (None, v.get('list')) and fallbacks(v))


def fallback_total_s(visits, side, lst=None):
    """The seconds one side's fallbacks added, every round of one list (or every title) together (owner, 2026-11-20, #187):
    fallback_s of each fallback, added up; 0 when nothing fell back. None when one fallback's extra seconds are not known:
    unknown, never counted as 0."""
    secs = [fallback_s(v) for v in visits if v['side'] == side and lst in (None, v.get('list')) and fallbacks(v)]
    return None if any(s is None for s in secs) else round(sum(secs), 3)


def fallback_text(v):
    """'played after 1 fallback, 2.50 s extra': a fallback as the report and `check` name it (the extra seconds left out
    when they are not known)."""
    n, extra = fallbacks(v), fallback_s(v)
    return f"played after {n} fallback{'' if n == 1 else 's'}" + ('' if extra is None else f', {extra:.2f} s extra')


def plays(v):
    """Whether a visit's play gave video, on the first try or after a fallback. A fallback counts as played
    (#185). Since #190 a round plays the Best entry: video from the first healthy Source counts as played, and a Source
    AltMount refused before it is a fallback; fallbacks() and fallback_s() say how many and how slow (rules.md)."""
    return bool(v.get('ok'))


def title_to_video(v):
    """Seconds from asking for the title until video arrived (#167): the list time plus the start time, a fallback's seconds
    included. None for a fail (no video: GLOSSARY.md, "a fail has no title-to-video time") and without both times."""
    if not plays(v) or v.get('list_s') is None or v.get('start_s') is None:
        return None
    return round(v['list_s'] + v['start_s'], 3)


def top_picks_played(counts):
    """The sentence of how many top picks played, per side and round, in the words `check` and the record command share:
    `Top picks played, KaijuFlow: cold 9 of 10, warm 10 of 10.`. counts: [(side, {'cold': (played,
    of), 'warm': (played, of)})], in the order to name them."""
    return 'Top picks played, ' + '; '.join(
        f"{SIDE_NAMES.get(side, side)}: " + ', '.join(f'{phase} {p} of {n}' for phase, (p, n) in by.items())
        for side, by in counts) + '.'


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
    """The top picks of a run meta: kept in it or made from its visits (runs.load reads them from the run folder); None
    when the meta holds neither."""
    if 'top_picks' in meta:
        return meta['top_picks']
    return (top_picks(meta['visits']) or None) if isinstance(meta.get('visits'), list) else None


def visit_cause(v):
    """The cause shown for a failed visit: KaijuFlow's own words (read_play), else its first-byte step line, else ''."""
    if v.get('cause'):
        return v['cause']
    for s in v.get('steps', []):
        if s.get('step') == 'first_byte' and s.get('ok') is False:
            return f"first byte failed after {s.get('ms', 0) / 1000:.1f} s"
    return ''


def attribute_steps(visit, steps, end=None):
    """The step lines that belong to one visit of one side.

    Search-side lines (indexer_page, health_batch) and the list's own lines (LIST_STEPS, #249) carry `ref`: kept when ref is the visit's id, from the visit's start until
    `end` (the start of that side's next visit; None = no end), however late they are written. Play-time check lines
    (play_check, #190) are kept for every Source checked inside that window, played or not: Best checks several Sources and
    skips the ones whose check fails, and that wait is the visit's. Other prepare-side lines carry the release `title` of the
    Source: kept only for the Source that was played, found by its name in the visit's `played_source` (from KaijuFlow's step
    lines, read_play) or in the played stream's text. No Source found means no such lines: a play that reused what the Backend held shows no
    import and no Unscramble, and another Source's background work (Best's backups) never lands here. The play's own
    events (`played`, `play_failed`, #242) are no steps: read_play reads them.
    """
    lo = parse_ts(visit['t_start']) - datetime.timedelta(seconds=1)

    def inside(s):
        try:
            t = parse_ts(s['t'])
        except (KeyError, ValueError):
            return False
        return t >= lo and (end is None or t < end)

    out = [s for s in steps if s.get('step') in REF_STEPS and s.get('ref') == visit.get('id') and inside(s)]
    out += [s for s in steps if s.get('step') == PLAY_CHECK and inside(s)]
    played = ' '.join(str(t.get('title', '')) for t in visit.get('tries', [])[:1])
    src = _norm(visit.get('played_source') or '')
    for s in steps:
        if s.get('step') in REF_STEPS + (PLAY_CHECK,) + PLAY_STEPS or not s.get('title') or not inside(s):
            continue
        n = _norm(s['title'])
        if (src and n == src) or (len(n) >= 8 and n in _norm(played)):
            out.append(s)
    return sorted(out, key=lambda s: s['t'])


def classify_failure(v):
    if plays(v):
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
    facts.setdefault('browse pause', pause_text(browse_pause_of(meta)))  # a run from before #205 waited none
    return settings, facts


def diff_runs(prev, cur, nulls=None):
    """Plain list of every difference between two run metas (settings, code, titles, indexers, time of day).

    nulls: metas of the null runs that lie between the two (runs.nulls_between); they are counted with their times.
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


# --------------------------------------------------------------------------- figures per side

JUDGED = 'kaijuflow'  # the side a run is judged on: KaijuFlow
NO_FIGURE = 'no figure'  # the run holds no visit to make the figure from (a side or a round is not in it)


def browse_pause_of(meta):
    """The Browse pause of a run, in seconds (#205, rules.md "Browse pause"); a run from before #205 waited none."""
    return meta.get('browse_pause_s') or 0


def pause_text(x):
    """A Browse pause as meta.json's facts and `check` print it: '5 s', '0 s'."""
    return f'{x:g} s'


def secs_text(x):
    """Seconds as `check`, the report and the page print them ('1.50 s'), or 'no figure'."""
    return NO_FIGURE if x is None else f'{x:.2f} s'


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
    figure `check` judges against the previous run and the Speed Check page shows (build_page.py). With
    `lst` ('easy' or 'hard'), over the titles of that list alone (#167); title to video is over the top picks that played."""
    return _time(visits, side, phase, what, lst=lst)


def side_fails(visits, side, phase=None, rnd=None, lst=None):
    """How many of one side's counted top picks failed (#167): every round, one phase or one round; every title, or the
    titles of one list. A fail is a top pick that gave no video: the failure video, a refusal or an error (video after a
    fallback is played, #185). Each visit counts on its own, so a cold fail stays a fail when the warm play after it works."""
    played, counted = _plays(visits, side, phase, rnd, lst)
    return counted - played


def fail_figure(visits, side, phase=None, rnd=None, lst=None):
    """One side's fails as every count shows them (#167, owner: "Plays, say both"): {'titles': titles with at least one
    failed play, 'fails': failed plays, 'counted': plays counted}, over every round, one phase or one round, and every
    title or one list's. A run is judged against the previous run on 'fails', the failed plays (runcheck.judged_lines)."""
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
    """(top picks that played, top picks counted) of one side over every round, as the page counts them; with `lst`,
    over the titles of that list alone (#167)."""
    return _plays(visits, side, lst=lst)


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


def tagged(visits):
    """Whether a run's visits were played on a tagged title list (#167): any visit keeps its title's list."""
    return any(v.get('list') for v in visits)


LISTS = common.LISTS
LIST_SECTION = '## Fails and title to video per list'
LIST_HELP = ('Fails = plays whose top pick gave no video: the failure video, a refusal or an error. Video after a fallback '
             '("played after N fallbacks") is played, not a fail, and its extra seconds are in its title to video (#185). '
             '"1 title failed · 2 of 20 plays" names the titles with a failed '
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
             "\"-\" means that side does not show the step from outside.", '',
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
                         sum(1 for v in vs if fallbacks(v))] + [sum(1 for c in causes if c == k) for k, _ in CAUSES])
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
                    res = (fallback_text(v) if fallbacks(v) else 'plays') if plays(v) else failed_result(v, cause)
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
    lines += list_work_section(run)
    lines += time_section(run)
    return '\n'.join(lines)


# The list's own work (#249): what KaijuFlow's list lines and the runner's CPU readings say of each list request.
# Each figure: (column, help, read from a visit). Milliseconds unless the column says otherwise.
def _step_field(name, field='ms'):
    def read(v):
        mine = [s for s in v.get('steps', []) if s.get('step') == name and s.get('ref') == v.get('id')]
        return mine[0].get(field) if mine else None
    return read


def _cpu_field(field):
    return lambda v: (v.get('list_cpu') or {}).get(field)


LIST_WORK = [
    ('List (ms)', 'the list time as the runner saw it: from asking for the Stream list until it had arrived.',
     lambda v: None if v.get('list_s') is None else round(v['list_s'] * 1000)),
    ('KaijuFlow (ms)', 'the list request inside KaijuFlow, from its `list` step line: from the request reaching the handler '
                       'until the answer was handed back.', _step_field('list')),
    ('Filters', 'dead marks and the user\'s filters (`list_filter`), the sort left out.', _step_field('list_filter')),
    ('Sort', 'the sort (`list_sort`).', _step_field('list_sort')),
    ('Build', 'building the Streams (`list_build`), the group write included.', _step_field('list_build')),
    ('Group write', 'writing the list\'s fallback group, which saves every group held to disk (`fallback_group`).',
     _step_field('fallback_group')),
    ('Groups held', 'how many fallback groups that write saved.', _step_field('fallback_group', 'groups')),
    ('Head start', 'starting the Head start, the part that runs before the answer (`head_start`).', _step_field('head_start')),
    ('CPU', 'KaijuFlow\'s process CPU time during the request, its other work at the same time included (`list` line).',
     _step_field('list', 'cpu_ms')),
    ('GC', 'garbage-collection pauses during the request (`list` line).', _step_field('list', 'gc_ms')),
    ('Loop delay', 'the longest event-loop delay during the request (`list` line): other work holding the loop.',
     _step_field('list', 'loop_max_ms')),
    ('Busy', 'the share of the request\'s time the event loop was busy, 0 to 1 (`list` line).', _step_field('list', 'elu')),
    ('Heap (MB)', 'KaijuFlow\'s heap in use as the request ended (`list` line).', _step_field('list', 'heap_mb')),
    ('KaijuFlow container CPU', 'CPU the KaijuFlow container used while the list was asked for, by its cgroup, read by the runner.',
     _cpu_field('kaijuflow_ms')),
    ('AltMount CPU', 'CPU the AltMount container used in the same time.', _cpu_field('altmount_ms')),
    ('Machine CPU', 'CPU the whole machine used in the same time, every core added up (/proc/stat).', _cpu_field('machine_ms')),
]


def list_work_section(run):
    """The list's own work, per side and round (medians) and per warm visit: where a list's time goes inside KaijuFlow
    and what the process and the machine did meanwhile (#249). [] for a run whose visits hold no `list` line."""
    visits = [v for v in run.get('visits') or [] if _step_field('list')(v) is not None]
    if not visits:
        return []
    g = {}
    for v in visits:
        g.setdefault((v['side'], v['phase'], v['round']), []).append(v)
    cols = [c for c, _, _ in LIST_WORK]
    rows = []
    for side in _sides(run):
        for phase, rnd in RUN_ORDER:
            vs = g.get((side, phase, rnd))
            if vs:
                rows.append([SIDE_NAMES[side], _run_label(phase, rnd)]
                            + [_work_cell(median([x for x in (read(v) for v in vs) if x is not None])) for _, _, read in LIST_WORK])
    out = ['## The list\'s own work', '',
           'Where a Stream list\'s time goes inside KaijuFlow, and what its process and the machine did meanwhile, from '
           'KaijuFlow\'s list step lines and the runner\'s CPU readings (#249). Milliseconds, medians over the titles of a round.', '']
    out += _table(['Side', 'Run'] + cols, rows) + ['']
    warm = [v for v in visits if v['phase'] == 'warm']
    if warm:
        out += ['Every warm list:', '']
        out += _table(['Title', 'Side', 'Run'] + cols,
                      [[v['title'], SIDE_NAMES[v['side']], _run_label(v['phase'], v['round'])]
                       + [_work_cell(read(v)) for _, _, read in LIST_WORK] for v in warm]) + ['']
    out += [f'- **{c}**: {h}' for c, h, _ in LIST_WORK] + ['']
    return out


def _work_cell(x):
    return '-' if x is None else (f'{x:.2f}' if isinstance(x, float) and x < 1 else str(round(x)))


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

# The six parts the wall-clock time of a run is split into: key in meta.json's timing.parts, name in the report.
TIME_PARTS = [('measured_s', 'Measured list and start time'), ('pauses_s', 'Pauses (`--settle`)'),
              ('browse_s', 'Browse pauses'), ('failed_s', 'Failed plays'), ('resets_s', 'Resets'),
              ('other_s', 'Everything else')]


def visit_wall_s(v):
    """Wall-clock seconds of one visit, from asking for the list until the play ended or gave up; None without both times."""
    try:
        return round((parse_ts(v['t_end']) - parse_ts(v['t_start'])).total_seconds(), 3)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def failed_visit_s(v):
    """The time of a top pick that did not play, as "Failed plays" counts it: its whole visit less its Browse pause (#205);
    None without both times."""
    took = visit_wall_s(v)
    return None if took is None else round(took - (v.get('browse_pause_s') or 0), 3)


def failed_result(v, cause):
    """The Result cell of a top pick that did not play: the failure kind, the cause or note, and how long its visit took
    less its Browse pause, the time "Failed plays" adds up."""
    text = f"{dict(CAUSES)[cause].lower()}: {visit_cause(v) or v.get('note') or ''}".strip(': ')
    took, pause = failed_visit_s(v), v.get('browse_pause_s') or 0
    if took is None:
        return text
    return f'{text} (the visit took {took:.1f} s, less its {pause_text(pause)} Browse pause)' if pause else \
        f'{text} (the whole visit took {took:.1f} s)'


def time_parts(run):
    """Where the wall-clock time of a run went, in seconds, as the six TIME_PARTS. They add up to the run's total
    (timing.seconds): five are measured (the list and start times of the top picks that played, the pauses and the resets
    as the run timed them, the Browse pauses of every visit (#205), the whole visits of the top picks that failed less their
    Browse pause), and `other_s` is what is left of the total.
    Works on a run that ended early: it takes whatever visits, rounds and resets the run holds."""
    timing = run.get('timing') or {}
    visits = run.get('visits') or []
    parts = {'measured_s': sum((v.get('list_s') or 0) + (v.get('start_s') or 0) for v in visits if v.get('ok')),
             'pauses_s': sum(r.get('pause_s') or 0 for r in timing.get('rounds') or []),
             'browse_s': sum(v.get('browse_pause_s') or 0 for v in visits),
             'failed_s': sum(failed_visit_s(v) or 0 for v in visits if not v.get('ok')),
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
    """The report's section on the run's wall-clock time: the whole run and each pass in one sentence, the six parts that
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
            f"- **Browse pauses**: the Browse pause between a list arriving and its play, "
            f"{pause_text(browse_pause_of(run))} each ({sum(1 for v in visits if v.get('browse_pause_s'))} visits); "
            "it is no part of title to video.",
            f"- **Failed plays**: the whole visit of every top pick that did not play, from asking for the list until the play "
            f"gave up, less its Browse pause ({failed} visit{'' if failed == 1 else 's'}; each one's time is in the Result column of \"Per title\").",
            '- **Resets**: emptying and restarting the test copies before each cold round. The first reset of the one-page '
            'side includes the switch to one page.',
            '- **Everything else**: what is left of the whole run: the seek checks after a top pick played, reading the logs '
            'after each play, starting and stopping the indexer stand-in and the test copies.', '']
    out += _table(['Pass', 'Round', 'Started (UTC)', 'Reset before it (s)', 'Plays', 'Round (s)', 'Round (minutes)'],
                  _round_rows(rounds, resets))
    out += ['',
            '- **Pass**: KaijuFlow is played title by title in one pass; the one-page side has its own pass after it.',
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
