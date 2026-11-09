"""Search side-by-side on Brain: the same titles through AltMount's own Stremio addon (8085), the KaijuFlow test
container with AltMount as Backend (1338) and UU 1337 with NzbDAV as the baseline.

Usage: python3 -I tools/brain/search.py <user-id> <altmount-download-key> <out.json>
SEARCH_TITLES="Interstellar,Game of Thrones" limits a run to the titles whose label contains one of the names.
SEARCH_TRIES=3 is how many Streams from the top of each list are played (64 KiB at the start).
For each title and side: Sources shown, time until the list shows, whether the first Stream plays on the first
try, time to the first byte of the first Stream that plays, and how many of the tried Streams are broken (listed
but won't play). Sides run one after the other (not in parallel) so the indexers are not hit by three searches at
once; the order rotates per title. Medians per side are printed as a Markdown table and written to <out>.md.
"""
import hashlib, json, os, re, statistics, sys, time, urllib.request, urllib.error

if len(sys.argv) != 4:
    sys.exit('usage: python3 -I tools/brain/search.py <user-id> <altmount-download-key> <out.json>')
U, DK, OUT = sys.argv[1:4]
SIDES = [
    ('altmount-addon', f'http://localhost:8085/stremio/{DK}'),
    ('kaijuflow-altmount', f'http://localhost:1338/{U}'),
    ('uu-nzbdav', f'http://localhost:1337/{U}'),
]
SHORT = {'altmount-addon': 'AM', 'kaijuflow-altmount': 'KF', 'uu-nzbdav': 'UU'}
FAILURE_SIZE = 1242455  # UU/KaijuFlow failure video
TRIES = int(os.environ.get('SEARCH_TRIES', '3'))
TITLES = [
    ('movie', 'tt1375666', 'Inception'), ('movie', 'tt0816692', 'Interstellar'),
    ('movie', 'tt15398776', 'Oppenheimer'), ('movie', 'tt0133093', 'The Matrix'),
    ('movie', 'tt1160419', 'Dune'), ('movie', 'tt0468569', 'The Dark Knight'),
    ('movie', 'tt0110912', 'Pulp Fiction'), ('series', 'tt0903747:1:1', 'Breaking Bad S01E01'),
    ('series', 'tt7366338:1:2', 'Chernobyl S01E02'), ('series', 'tt0944947:2:3', 'Game of Thrones S02E03'),
]


def get(url, rng=None, timeout=120, limit=65536):
    """status, headers, body, timings {ready, first_byte, total} in seconds; status None on a network error."""
    req = urllib.request.Request(url, headers={'Range': f'bytes={rng}'} if rng else {})
    t = time.time()
    timings = {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            timings['ready'] = time.time() - t
            first = r.read(1)
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


def total_size(st, h):
    if st == 206:
        return int((h.get('Content-Range') or h.get('content-range') or '/0').split('/')[-1] or 0)
    return int(h.get('Content-Length') or h.get('content-length') or 0)


def play(stream):
    """One 64 KiB read at the start of a Stream: does it play, and how fast."""
    url = stream.get('url', '')
    if not url:
        return {'plays': False, 'note': 'no url (external player stream?)'}
    st, h, body, t = get(url, '0-65535')
    size = total_size(st, h)
    ctype = (h.get('Content-Type') or h.get('content-type') or '').split(';')[0]
    ok = st in (200, 206) and len(body) >= 1024 and size != FAILURE_SIZE
    note = None
    if size == FAILURE_SIZE:
        note = 'failure video'
    elif st is None:
        note = h.get('error', 'network error')[:120]
    elif st not in (200, 206):
        note = f'HTTP {st}'
    elif len(body) < 1024:
        note = f'{len(body)} bytes'
    return {'plays': ok, 'status': st, 'ready_s': round(t['ready'], 2), 'first_byte_s': round(t.get('first_byte', t['ready']), 2),
            'total_s': round(t.get('total', t['ready']), 2), 'size': size, 'ctype': ctype, 'note': note,
            'sha': hashlib.sha256(body).hexdigest()[:16] if ok else None,
            'title': ' '.join((stream.get('name', '') + ' ' + stream.get('title', '')).split())[:140]}


def side(base, kind, vid):
    out = {}
    st, h, body, t = get(f'{base}/stream/{kind}/{vid}.json', timeout=180, limit=0)
    out['list_status'] = st
    out['list_s'] = round(t.get('total', t['ready']), 2)
    try:
        streams = json.loads(body or b'{}').get('streams', []) if st == 200 else []
    except Exception as e:  # noqa
        streams, out['note'] = [], f'bad JSON: {e}'[:120]
    if st != 200:
        out['note'] = h.get('error') or f'HTTP {st}'
    out['sources'] = len(streams)
    out['tries'] = [play(s) for s in streams[:TRIES]]
    out['first_try_plays'] = bool(out['tries'] and out['tries'][0]['plays'])
    out['broken'] = sum(1 for x in out['tries'] if not x['plays'])
    first_ok = next((x for x in out['tries'] if x['plays']), None)
    out['first_byte_s'] = first_ok['first_byte_s'] if first_ok else None
    return out


def fmt(v, unit=''):
    return '-' if v is None else f'{v}{unit}'


def table(results):
    names = [n for n, _ in SIDES]
    abbr = ' / '.join(SHORT[n] for n in names)
    head = f'| Title | Sources {abbr} | List s {abbr} | 1st try plays {abbr} | 1st byte s {abbr} | Broken of {TRIES} {abbr} |'
    lines = [head, '|---|---|---|---|---|---|']
    med = {n: {'sources': [], 'list_s': [], 'first_byte_s': [], 'broken': [], 'first_try': []} for n in names}
    for row in results:
        cells = {k: [] for k in ('sources', 'list_s', 'first_try', 'first_byte_s', 'broken')}
        for n in names:
            d = row[n]
            cells['sources'].append(fmt(d.get('sources')))
            cells['list_s'].append(fmt(d.get('list_s')))
            cells['first_try'].append('yes' if d.get('first_try_plays') else ('no' if d.get('sources') else 'none'))
            cells['first_byte_s'].append(fmt(d.get('first_byte_s')))
            cells['broken'].append(fmt(d.get('broken')) if d.get('sources') else '-')
            med[n]['sources'].append(d.get('sources', 0))
            med[n]['list_s'].append(d.get('list_s'))
            if d.get('first_byte_s') is not None:
                med[n]['first_byte_s'].append(d['first_byte_s'])
            if d.get('sources'):
                med[n]['broken'].append(d.get('broken', 0))
                med[n]['first_try'].append(1 if d.get('first_try_plays') else 0)
        lines.append(f"| {row['title']} | " + ' | '.join(' / '.join(cells[k]) for k in ('sources', 'list_s', 'first_try', 'first_byte_s', 'broken')) + ' |')
    m = lambda xs: round(statistics.median(xs), 2) if xs else None  # noqa
    lines.append('| **Median** | ' + ' / '.join(fmt(m(med[n]['sources'])) for n in names) + ' | ' +
                 ' / '.join(fmt(m(med[n]['list_s'])) for n in names) + ' | ' +
                 ' / '.join(f"{sum(med[n]['first_try'])}/{len(med[n]['first_try'])}" for n in names) + ' | ' +
                 ' / '.join(fmt(m(med[n]['first_byte_s'])) for n in names) + ' | ' +
                 ' / '.join(f"{sum(med[n]['broken'])} total" for n in names) + ' |')
    lines.append('')
    lines.append("AM = AltMount's own Stremio addon (8085), KF = KaijuFlow test container with AltMount as Backend (1338), "
                 'UU = Usenet Ultimate 1337 with NzbDAV (baseline). List s = time until the Stream list arrived; '
                 f'1st byte s = time to the first byte of the first Stream that played; Broken = Streams among the first {TRIES} '
                 'that returned an error or the failure video. Sides ran one after the other, order rotating per title.')
    return '\n'.join(lines)


def main():
    only = [t.strip() for t in os.environ.get('SEARCH_TITLES', '').split(',') if t.strip()]
    titles = [t for t in TITLES if not only or any(o.lower() in t[2].lower() for o in only)]
    if not titles:
        sys.exit(f'SEARCH_TITLES={only} matches none of: ' + ', '.join(t[2] for t in TITLES))
    results = []
    for i, (kind, vid, label) in enumerate(titles):
        order = SIDES[i % len(SIDES):] + SIDES[:i % len(SIDES)]
        row = {'title': label, 'id': vid, 'order': [n for n, _ in order]}
        for n, base in order:
            row[n] = side(base, kind, vid)
            time.sleep(2)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        json.dump(results, open(OUT, 'w'), indent=2, ensure_ascii=False)  # partial results survive a timeout
    t = table(results)
    open(re.sub(r'\.json$', '', OUT) + '.md', 'w').write(t + '\n')
    print(t)


main()
