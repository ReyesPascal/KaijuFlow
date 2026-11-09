"""Parity check on Brain: the same titles through UU 1337 (NzbDAV) and the KaijuFlow test container on 1338.

Usage: python3 -I tools/brain/parity.py <user-id> <out.json>
For each title and side: Source count, first Source played, whether both sides served the same bytes
(start, 50%, 90%), and the speed of each side (#46): time to the Stream being ready (response headers,
i.e. KaijuFlow's prepare incl. the Backend), time to the first byte, the 64 KiB start read, the 50% and
90% seek reads, and on the test container the Unscramble time from KaijuFlow's log. Medians per side
are printed as a Markdown table and written next to the JSON (<out>.md).
"""
import hashlib, json, re, statistics, subprocess, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

U = sys.argv[1] if len(sys.argv) > 1 else ''  # the user id in the manifest URL
SIDES = {'nzbdav': 'http://localhost:1337', 'altmount': 'http://localhost:1338'}
LOG_CONTAINER = {'altmount': 'kaijuflow-test'}  # sides whose KaijuFlow log we can read for Unscramble lines
FAILURE_SIZE = 1242455  # failure video
TITLES = [
    ('movie', 'tt1375666', 'Inception'), ('movie', 'tt0816692', 'Interstellar'),
    ('movie', 'tt15398776', 'Oppenheimer'), ('movie', 'tt0133093', 'The Matrix'),
    ('movie', 'tt1160419', 'Dune'), ('movie', 'tt0468569', 'The Dark Knight'),
    ('movie', 'tt0110912', 'Pulp Fiction'), ('series', 'tt0903747:1:1', 'Breaking Bad S01E01'),
    ('series', 'tt7366338:1:2', 'Chernobyl S01E02'), ('series', 'tt0944947:2:3', 'Game of Thrones S02E03'),
]
UNSCRAMBLE_RE = re.compile(r'Unscrambled RAR set: (\d+) parts .*?\((\d+) ms\)|Unscramble skipped \(([^,]+), (\d+) parts, (\d+) ms\)')


def get(url, rng=None, timeout=330, limit=70000):
    """status, headers, body, timings {ready, first_byte, total} in seconds."""
    req = urllib.request.Request(url, headers={'Range': f'bytes={rng}'} if rng else {})
    t = time.time()
    timings = {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            timings['ready'] = time.time() - t
            first = r.read(1) if limit else b''
            timings['first_byte'] = time.time() - t
            body = first + (r.read(limit - 1) if limit else r.read())
            timings['total'] = time.time() - t
            return r.status, dict(r.headers), body, timings
    except urllib.error.HTTPError as e:
        timings.setdefault('ready', time.time() - t)
        return e.code, dict(e.headers), b'', timings
    except Exception as e:  # noqa
        timings.setdefault('ready', time.time() - t)
        return None, {'error': str(e)}, b'', timings


def unscramble_from_log(container, since, until):
    """Unscramble line(s) KaijuFlow logged in the window: {parts, ms, reason?}."""
    try:
        log = subprocess.run(['docker', 'logs', container, '--since', str(int(since)), '--until', str(int(until) + 1)],
                             capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa
        return {'error': str(e)}
    out = []
    for m in UNSCRAMBLE_RE.finditer(log.stdout + log.stderr):
        if m.group(1):
            out.append({'parts': int(m.group(1)), 'ms': int(m.group(2))})
        else:
            out.append({'reason': m.group(3), 'parts': int(m.group(4)), 'ms': int(m.group(5))})
    return out[-1] if out else None


def side(name, base, kind, vid):
    out = {}
    st, _, body, t = get(f"{base}/{U}/stream/{kind}/{vid}.json", timeout=120, limit=0)
    streams = json.loads(body or b'{}').get('streams', []) if st == 200 else []
    out['sources'] = len(streams)
    out['search_s'] = round(t.get('total', t['ready']), 1)
    if not streams:
        return out
    url = streams[0]['url']
    out['first_title'] = streams[0].get('title', '').split('\n')[0:3]
    play_started = time.time()
    st, h, body, t = get(url, '0-65535')
    play_ended = time.time()
    total = int(h.get('Content-Range', h.get('content-range', '/0')).split('/')[-1] or 0) if st == 206 else int(h.get('Content-Length', 0) or 0)
    out.update(play_status=st, ready_s=round(t['ready'], 2), first_byte_s=round(t.get('first_byte', t['ready']), 2),
               start_s=round(t.get('total', t['ready']), 2), size=total, ctype=h.get('Content-Type'),
               failure_video=(total == FAILURE_SIZE), head_sha=hashlib.sha256(body).hexdigest()[:16])
    if name in LOG_CONTAINER:
        out['unscramble'] = unscramble_from_log(LOG_CONTAINER[name], play_started, play_ended)
    if st in (200, 206) and total and total != FAILURE_SIZE:
        for label, off in (('seek50', total // 2), ('seek90', total * 9 // 10)):
            st2, h2, b2, t2 = get(url, f'{off}-{off + 65535}')
            out[label] = {'status': st2, 'bytes': len(b2), 's': round(t2.get('total', t2['ready']), 2),
                          'first_byte_s': round(t2.get('first_byte', t2['ready']), 2),
                          'range': h2.get('Content-Range'), 'sha': hashlib.sha256(b2).hexdigest()[:16]}
    return out


def fmt(v, unit=''):
    return '-' if v is None else f'{v}{unit}'


def speed_table(results):
    """Markdown table: both sides per row, medians per side."""
    cols = [('ready_s', 'ready s'), ('first_byte_s', '1st byte s'), ('seek50', 'seek 50% s'), ('seek90', 'seek 90% s')]
    head = '| Title | Plays N / A | ' + ' | '.join(f'{c} N / A' for _, c in cols) + ' | Unscramble (A) | Same bytes |'
    lines = [head, '|' + '---|' * (len(cols) + 4)]
    series = {s: {c: [] for c, _ in cols} for s in SIDES}
    unscr = []
    for row in results:
        cells = []
        for key, _ in cols:
            vals = []
            for s in SIDES:
                d = row[s]
                v = d.get(key) if key.startswith('seek') is False else d.get(key, {}).get('s')
                if d.get('failure_video') or not d.get('size'):
                    v = None
                vals.append(v)
                if v is not None:
                    series[s][key].append(v)
            cells.append(' / '.join(fmt(v) for v in vals))
        plays = ' / '.join('yes' if (row[s].get('size') and not row[s].get('failure_video')) else ('failure video' if row[s].get('failure_video') else 'no') for s in SIDES)
        u = row['altmount'].get('unscramble')
        if isinstance(u, dict) and 'ms' in u:
            utxt = f"{u['parts']} parts, {u['ms']} ms" + (f" ({u['reason']})" if u.get('reason') else '')
            if not u.get('reason'):
                unscr.append(u['ms'])
        else:
            utxt = '-'
        lines.append(f"| {row['title']} | {plays} | " + ' | '.join(cells) + f" | {utxt} | {'yes' if row.get('bytes_match') else 'no'} |")
    med = lambda xs: round(statistics.median(xs), 2) if xs else None  # noqa
    lines.append('| **Median** | | ' + ' | '.join(' / '.join(fmt(med(series[s][key])) for s in SIDES) for key, _ in cols) +
                 f" | {fmt(med(unscr), ' ms')} | |")
    lines.append('')
    lines.append('N = NzbDAV via UU 1337, A = AltMount via KaijuFlow test container 1338. ready = response headers '
                 '(Stream prepared, Backend stream open), 1st byte = first body byte, seeks = 64 KiB reads at 50% and 90%.')
    return '\n'.join(lines)


def main():
    results = []
    for kind, vid, label in TITLES:
        with ThreadPoolExecutor(2) as ex:
            futs = {n: ex.submit(side, n, b, kind, vid) for n, b in SIDES.items()}
            row = {'title': label, 'id': vid, **{n: f.result() for n, f in futs.items()}}
        a, n = row['altmount'], row['nzbdav']
        same = a.get('size') and a.get('size') == n.get('size')
        row['same_file'] = bool(same)
        if same:
            row['bytes_match'] = all(
                a.get(k, {}).get('sha') == n.get(k, {}).get('sha') if k != 'head_sha' else a.get(k) == n.get(k)
                for k in ('head_sha', 'seek50', 'seek90'))
        results.append(row)
        print(json.dumps(row), flush=True)
    json.dump(results, open(sys.argv[2], 'w'), indent=2)
    table = speed_table(results)
    open(re.sub(r'\.json$', '', sys.argv[2]) + '.md', 'w').write(table + '\n')
    print(table)


if len(sys.argv) != 3:
    sys.exit('usage: python3 -I tools/brain/parity.py <user-id> <out.json>')
main()
