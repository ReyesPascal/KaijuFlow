"""Parity check on Brain: the same titles through UU 1337 (NzbDAV) and the KaijuFlow test container on 1338.

Usage: python3 -I tools/brain/parity.py <user-id> <out.json>
For each title and side: Source count, first Source played (start, 50%, 90% reads), failure video or not,
and whether both sides served the same bytes.
"""
import hashlib, json, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

U = sys.argv[1] if len(sys.argv) > 1 else ''  # the user id in the manifest URL
SIDES = {'nzbdav': 'http://localhost:1337', 'altmount': 'http://localhost:1338'}
FAILURE_SIZE = 1242455  # failure video
TITLES = [
    ('movie', 'tt1375666', 'Inception'), ('movie', 'tt0816692', 'Interstellar'),
    ('movie', 'tt15398776', 'Oppenheimer'), ('movie', 'tt0133093', 'The Matrix'),
    ('movie', 'tt1160419', 'Dune'), ('movie', 'tt0468569', 'The Dark Knight'),
    ('movie', 'tt0110912', 'Pulp Fiction'), ('series', 'tt0903747:1:1', 'Breaking Bad S01E01'),
    ('series', 'tt7366338:1:2', 'Chernobyl S01E02'), ('series', 'tt0944947:2:3', 'Game of Thrones S02E03'),
]


def get(url, rng=None, timeout=330, limit=70000):
    req = urllib.request.Request(url, headers={'Range': f'bytes={rng}'} if rng else {})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(limit) if limit else r.read()
            return r.status, dict(r.headers), body, time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b'', time.time() - t
    except Exception as e:  # noqa
        return None, {'error': str(e)}, b'', time.time() - t


def side(name, base, kind, vid):
    out = {}
    st, _, body, dt = get(f"{base}/{U}/stream/{kind}/{vid}.json", timeout=120, limit=0)
    streams = json.loads(body or b'{}').get('streams', []) if st == 200 else []
    out['sources'] = len(streams)
    out['search_s'] = round(dt, 1)
    if not streams:
        return out
    url = streams[0]['url']
    out['first_title'] = streams[0].get('title', '').split('\n')[0:3]
    st, h, body, dt = get(url, '0-65535')
    total = int(h.get('Content-Range', h.get('content-range', '/0')).split('/')[-1] or 0) if st == 206 else int(h.get('Content-Length', 0) or 0)
    out.update(play_status=st, start_s=round(dt, 1), size=total, ctype=h.get('Content-Type'),
               failure_video=(total == FAILURE_SIZE), head_sha=hashlib.sha256(body).hexdigest()[:16])
    if st in (200, 206) and total and total != FAILURE_SIZE:
        for label, off in (('seek50', total // 2), ('seek90', total * 9 // 10)):
            st2, h2, b2, dt2 = get(url, f'{off}-{off + 65535}')
            out[label] = {'status': st2, 'bytes': len(b2), 's': round(dt2, 1),
                          'range': h2.get('Content-Range'), 'sha': hashlib.sha256(b2).hexdigest()[:16]}
    return out


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
            row['bytes_match'] = a.get('head_sha') == n.get('head_sha') and a.get('seek50', {}).get('sha') == n.get('seek50', {}).get('sha')
        results.append(row)
        print(json.dumps(row), flush=True)
    json.dump(results, open(sys.argv[2], 'w'), indent=2)


if len(sys.argv) != 3:
    sys.exit('usage: python3 -I tools/brain/parity.py <user-id> <out.json>')
main()
