"""Shared pieces of the Brain tools: the ten titles, the timed HTTP read and the table helpers.

parity.py and search.py both import this, so their tables stay comparable: change the title list here only.
The scripts run under `python3 -I`, which leaves the script's folder off sys.path; each one adds it before importing.
"""
import os, statistics, sys, time, urllib.request, urllib.error

FAILURE_SIZE = 1242455  # UU/KaijuFlow failure video, served when a Source cannot play
TITLES = [
    ('movie', 'tt1375666', 'Inception'), ('movie', 'tt0816692', 'Interstellar'),
    ('movie', 'tt15398776', 'Oppenheimer'), ('movie', 'tt0133093', 'The Matrix'),
    ('movie', 'tt1160419', 'Dune'), ('movie', 'tt0468569', 'The Dark Knight'),
    ('movie', 'tt0110912', 'Pulp Fiction'), ('series', 'tt0903747:1:1', 'Breaking Bad S01E01'),
    ('series', 'tt7366338:1:2', 'Chernobyl S01E02'), ('series', 'tt0944947:2:3', 'Game of Thrones S02E03'),
]


def pick_titles(env_name):
    """TITLES, or the subset whose label contains one of the comma-separated names in os.environ[env_name]."""
    only = [t.strip() for t in os.environ.get(env_name, '').split(',') if t.strip()]
    titles = [t for t in TITLES if not only or any(o.lower() in t[2].lower() for o in only)]
    if not titles:
        sys.exit(f'{env_name}={only} matches none of: ' + ', '.join(t[2] for t in TITLES))
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
