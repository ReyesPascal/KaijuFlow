"""Shared pieces of the Brain tools: the ten titles, the timed HTTP read and the table helpers.

parity.py and search.py both import this, so their tables stay comparable: change the title list here only.
The scripts run under `python3 -I`, which leaves the script's folder off sys.path; each one adds it before importing.
"""
import hashlib, json, os, statistics, sys, time, urllib.request, urllib.error

FAILURE_SIZE = 1242455  # UU/KaijuFlow failure video, served when a Source cannot play
TITLES = [
    ('movie', 'tt1375666', 'Inception'), ('movie', 'tt0816692', 'Interstellar'),
    ('movie', 'tt15398776', 'Oppenheimer'), ('movie', 'tt0133093', 'The Matrix'),
    ('movie', 'tt1160419', 'Dune'), ('movie', 'tt0468569', 'The Dark Knight'),
    ('movie', 'tt0110912', 'Pulp Fiction'), ('series', 'tt0903747:1:1', 'Breaking Bad S01E01'),
    ('series', 'tt7366338:1:2', 'Chernobyl S01E02'), ('series', 'tt0944947:2:3', 'Game of Thrones S02E03'),
]


def pick_titles(env_name):
    """The title list, or the subset whose label contains one of the comma-separated names in os.environ[env_name].

    TITLES_FILE=<path.json> swaps the list for another one (a JSON list of [kind, id, label]), e.g. fresh titles
    that no Backend on Brain has played, for a cold run.
    """
    path = os.environ.get('TITLES_FILE')
    pool = [tuple(t) for t in json.load(open(path))] if path else TITLES
    only = [t.strip() for t in os.environ.get(env_name, '').split(',') if t.strip()]
    titles = [t for t in pool if not only or any(o.lower() in t[2].lower() for o in only)]
    if not titles:
        sys.exit(f'{env_name}={only} matches none of: ' + ', '.join(t[2] for t in pool))
    return titles


def get(url, rng=None, timeout=330, limit=70000):
    """status, headers, body, timings {ready, first_byte (when a body is read), total} in seconds.

    status is None on a network error, with the message in headers['error']. limit=0 reads the whole body.
    """
    req = urllib.request.Request(url, headers={'Range': f'bytes={rng}'} if rng else {})
    t = time.time()
    timings = {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            timings['ready'] = time.time() - t
            first = r.read(1) if limit else b''
            if limit:
                timings['first_byte'] = time.time() - t
            body = first + (r.read(limit - 1) if limit else r.read())
            timings['total'] = time.time() - t
            return r.status, dict(r.headers), body, timings
    except urllib.error.HTTPError as e:
        timings.setdefault('ready', time.time() - t)
        return e.code, dict(e.headers), b'', timings
    except Exception as e:  # noqa: BLE001
        timings.setdefault('ready', time.time() - t)
        return None, {'error': str(e)}, b'', timings


def took(t):
    """Total time of a get(), or the time to the headers when the body read did not finish."""
    return t.get('total', t['ready'])


def total_size(st, h):
    """Full file size from a 206 Content-Range, else Content-Length."""
    if st == 206:
        return int((h.get('Content-Range') or h.get('content-range') or '/0').split('/')[-1] or 0)
    return int(h.get('Content-Length') or h.get('content-length') or 0)


def fmt(v, unit=''):
    return '-' if v is None else f'{v}{unit}'


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def finish(started):
    """The last log line of a run; a log without it is an unfinished run."""
    print(f'done in {time.time() - started:.1f} s', flush=True)


def play_stream(stream):
    """One 64 KiB read at the start of a Stream: does it play, and how fast."""
    url = stream.get('url', '')
    if not url:
        return {'plays': False, 'note': 'no url (external player stream?)'}
    st, h, body, t = get(url, '0-65535', timeout=120, limit=65536)
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


def seek_reads(url, size, percents=(50, 90)):
    """Seconds to the first byte of a 64 KiB read at each percent of the file, None when the read failed."""
    out = {}
    for pct in percents:
        off = size * pct // 100
        st, h, body, t = get(url, f'{off}-{off + 65535}', timeout=120, limit=65536)
        out[str(pct)] = round(t.get('first_byte', t['ready']), 2) if st in (200, 206) and body else None
    return out
