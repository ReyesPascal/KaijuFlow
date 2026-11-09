"""Parity check on Brain: the same titles through UU 1337 (NzbDAV) and the KaijuFlow test container on 1338.

Usage: python3 -I tools/brain/parity.py <user-id> <out.json>
PARITY_TITLES="Interstellar,Game of Thrones" limits a rerun to the titles whose label contains one of the names.
For each title and side: Source count, first Source played, whether both sides served the same bytes
(start, 50%, 90%), and the speed of each side (#46): time to the Stream being ready (response headers,
i.e. KaijuFlow's prepare incl. the Backend), time to the first byte, the 64 KiB start read, the 50% and
90% seek reads, and on the test container the Unscramble time from KaijuFlow's log. Medians per side
are printed as a Markdown table and written next to the JSON (<out>.md).
"""
import hashlib, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
from common import FAILURE_SIZE, finish, fmt, get, med, pick_titles, took  # noqa: E402

U = sys.argv[1] if len(sys.argv) > 1 else ''  # the user id in the manifest URL
SIDES = {'nzbdav': 'http://localhost:1337', 'altmount': 'http://localhost:1338'}
LOG_CONTAINER = {'altmount': 'kaijuflow-test'}  # sides whose KaijuFlow log we can read for Unscramble lines
UNSCRAMBLE_RE = re.compile(r'Unscrambled RAR set: (\d+) parts .*?\((\d+) ms\)|Unscramble skipped \(([^,]+), (\d+) parts, (\d+) ms\)')


def rfc3339(ts):
    """docker logs --since/--until with sub-second precision."""
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(ts)) + f'.{int((ts % 1) * 1e9):09d}Z'


def unscramble_from_log(container, since, until):
    """Unscramble line(s) KaijuFlow logged in the window: {parts, ms, reason?}."""
    try:
        log = subprocess.run(['docker', 'logs', container, '--since', rfc3339(since), '--until', rfc3339(until + 0.5)],
                             capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa
        return {'error': str(e)}
    if log.returncode != 0:
        return {'error': f'docker logs exit {log.returncode}: {log.stderr.strip()[:200]}'}
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
    out['search_s'] = round(took(t), 1)
    if not streams:
        return out
    url = streams[0]['url']
    out['first_title'] = streams[0].get('title', '').split('\n')[0:3]
    play_started = time.time()
    st, h, body, t = get(url, '0-65535')
    play_ended = time.time()
    total = int(h.get('Content-Range', h.get('content-range', '/0')).split('/')[-1] or 0) if st == 206 else int(h.get('Content-Length', 0) or 0)
    out.update(play_status=st, ready_s=round(t['ready'], 2), first_byte_s=round(t.get('first_byte', t['ready']), 2),
               start_s=round(took(t), 2), size=total, ctype=h.get('Content-Type'),
               failure_video=(total == FAILURE_SIZE), head_sha=hashlib.sha256(body).hexdigest()[:16])
    if name in LOG_CONTAINER:
        out['unscramble'] = unscramble_from_log(LOG_CONTAINER[name], play_started, play_ended)
    if st in (200, 206) and total and total != FAILURE_SIZE:
        for label, off in (('seek50', total // 2), ('seek90', total * 9 // 10)):
            st2, h2, b2, t2 = get(url, f'{off}-{off + 65535}')
            out[label] = {'status': st2, 'bytes': len(b2), 's': round(took(t2), 2),
                          'first_byte_s': round(t2.get('first_byte', t2['ready']), 2),
                          'range': h2.get('Content-Range'), 'sha': hashlib.sha256(b2).hexdigest()[:16]}
    return out


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
    lines.append('| **Median** | | ' + ' | '.join(' / '.join(fmt(med(series[s][key])) for s in SIDES) for key, _ in cols) +
                 f" | {fmt(med(unscr), ' ms')} | |")
    lines.append('')
    lines.append('N = NzbDAV via UU 1337, A = AltMount via KaijuFlow test container 1338. ready = response headers '
                 '(Stream prepared, Backend stream open), 1st byte = first body byte, seeks = 64 KiB reads at 50% and 90%.')
    return '\n'.join(lines)


def main():
    started = time.time()
    results = []
    for kind, vid, label in pick_titles('PARITY_TITLES'):
        with ThreadPoolExecutor(2) as ex:
            futs = {n: ex.submit(side, n, b, kind, vid) for n, b in SIDES.items()}
            row = {'title': label, 'id': vid, **{n: f.result() for n, f in futs.items()}}
        a, n = row['altmount'], row['nzbdav']
        same = a.get('size') and a.get('size') == n.get('size')
        row['same_file'] = bool(same)
        if same:
            # Start, 50% and 90% reads must all be present on both sides and identical.
            shas = [(a.get('head_sha'), n.get('head_sha'))] + [(a.get(k, {}).get('sha'), n.get(k, {}).get('sha')) for k in ('seek50', 'seek90')]
            row['bytes_match'] = all(x and x == y for x, y in shas)
        results.append(row)
        print(json.dumps(row), flush=True)
    json.dump(results, open(sys.argv[2], 'w'), indent=2)
    table = speed_table(results)
    open(re.sub(r'\.json$', '', sys.argv[2]) + '.md', 'w').write(table + '\n')
    print(table)
    finish(started)


if len(sys.argv) != 3:
    sys.exit('usage: python3 -I tools/brain/parity.py <user-id> <out.json>')
main()
