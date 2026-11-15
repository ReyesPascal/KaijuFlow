"""The pool of titles that speed tests draw from (#165), and the draw command.

    python3 -I tools/brain/pool.py draw --test <speed test> --out <titles.json> [--pool tools/brain/pool.json]
    python3 -I tools/brain/pool.py check-ids [--pool tools/brain/pool.json] [--test-dir ~/kaijuflow-test]

`draw` takes the first 6 films and 4 episodes of each list (easy, hard) that no speed test has used, writes them as the
speed test's tagged title list ([type, id, label, list]) and marks them used by that speed test in the pool.
`check-ids` looks every pool title up on TMDB (the film, or the show and its season and episode) with the metadata key
of KaijuFlow's test copy, which it reads itself and never prints; one line per title as it goes, then `done in N s`;
exit 1 when any is not as the pool says. It is the tool's only network call.
The pool and the tagged title list are described in docs/formats.md, "The pool".
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402

OLD_LIST = common.TITLES  # Test 1's ten titles: a speed test never draws them (ADR 0007, new titles every speed test)
ID_SHAPE = {'movie': re.compile(r'tt\d+'), 'series': re.compile(r'tt\d+:\d+:\d+')}
DEFAULT_POOL = os.path.join(HERE, 'pool.json')
LISTS = common.LISTS
PER_LIST = {'movie': 6, 'series': 4}  # a speed test's films and episodes on each list


def read_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, text):
    """Writes the text through a temporary file, so a failed write leaves the old file whole."""
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(text)
    os.replace(tmp, path)


def dump_lines(items):
    """A JSON list with one item per line, so a change to the pool is one line in a diff."""
    return '[\n' + ',\n'.join('  ' + json.dumps(i, ensure_ascii=False) for i in items) + '\n]'


NOUN = {'movie': 'films', 'series': 'episodes'}


class Refused(Exception):
    """The one sentence that says why the pool or the draw is refused."""


def unused(data, lst, kind):
    return [t for t in data['titles'] if t['list'] == lst and t['type'] == kind and not t.get('used_by')]


def check_pool(data):
    """Refused with one sentence when the pool cannot be drawn from: a title of the old list, a title twice,
    or a title without its fields."""
    old = {tid: label for _, tid, label in OLD_LIST}
    seen = set()
    for t in data['titles']:
        tid, name = t.get('id'), f"{t.get('label')} ({t.get('id')})"
        if tid in old:
            raise Refused(f"The pool holds {old[tid]} ({tid}), one of Test 1's ten titles, which a speed test never "
                          'draws: take it out.')
        if tid in seen:
            raise Refused(f'The pool cannot be used: {tid} is in it twice.')
        seen.add(tid)
        if t.get('list') not in LISTS:
            raise Refused(f"The pool cannot be used: {name} has the list {t.get('list')!r}, not easy or hard.")
        if t.get('type') not in ID_SHAPE or not ID_SHAPE[t['type']].fullmatch(tid or ''):
            raise Refused(f"The pool cannot be used: {name} has an ID that is not a film's (tt and digits) or an "
                          f"episode's (tt and digits:season:episode) for its type {t.get('type')}.")
        if not str(t.get('reason') or '').strip():
            raise Refused(f'The pool cannot be used: {name} has no reason for its list.')


def draw(data, test):
    """The tagged title list for a speed test from the pool's unused titles; marks them used in `data`.
    Refused, with nothing marked, when the pool cannot be used or a list has too few unused films or episodes."""
    check_pool(data)
    short = []
    for lst in LISTS:
        missing = [f'{len(unused(data, lst, kind))} unused {NOUN[kind]} of the {count}'
                   for kind, count in PER_LIST.items() if len(unused(data, lst, kind)) < count]
        if missing:
            short.append(f'the {lst} list has ' + ' and '.join(missing))
    if short:
        raise Refused(f'The pool is too small for {test}: ' + ', and '.join(short) + ' a speed test needs.')
    drawn = []
    for lst in LISTS:
        for kind, count in PER_LIST.items():
            drawn += unused(data, lst, kind)[:count]
    for t in drawn:
        t['used_by'] = test
    return [[t['type'], t['id'], t['label'], t['list']] for t in drawn]


def draw_command(a):
    data = read_json(a.pool)
    try:
        tagged = draw(data, a.test)
    except Refused as e:
        print(e)
        return 1
    # The pool first: a failure after it can only waste the drawn titles, never let a later draw take them again.
    write_json(a.pool, '{"about": ' + json.dumps(data.get('about', ''), ensure_ascii=False)
               + ',\n "titles": ' + dump_lines(data['titles']) + '}\n')
    try:
        write_json(a.out, dump_lines(tagged) + '\n')
    except OSError as e:
        print(f'The pool marks {len(tagged)} titles used by {a.test}, but the title list could not be written to {a.out} '
              f'({type(e).__name__}): those titles are spent; draw again under another speed test name.')
        return 1
    print(f'Drew {len(tagged)} titles for {a.test} into {a.out}; the pool marks them used.')
    return 0


TMDB = 'https://api.themoviedb.org/3'


class TmdbError(Exception):
    """One sentence about a TMDB call that failed, with the key never in it."""


def real_http(url, headers):
    """(status, body bytes) of a GET; TmdbError on a network error."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        raise TmdbError(f'TMDB did not answer ({type(e).__name__})') from None


def tmdb_getter(test_dir, http=real_http):
    """get(path) -> (status, JSON) on TMDB with the metadata key of KaijuFlow's test copy
    (`<test dir>/config/config.json`, searchConfig.tmdbApiKey). The key is read here and goes only into the request:
    never into a message, a log line or a command line."""
    try:
        with open(os.path.join(test_dir, 'config', 'config.json')) as f:
            key = ((json.load(f).get('searchConfig') or {}).get('tmdbApiKey') or '').strip()
    except (OSError, ValueError):
        key = ''
    if not key:
        raise TmdbError(f"There is no TMDB key in KaijuFlow's test copy ({test_dir}/config/config.json, "
                        'searchConfig.tmdbApiKey), so no ID can be checked.')
    bearer = len(key) > 40 or key.startswith('eyJ')  # a v4 read token, as src/idResolver.ts tells them apart

    def get(path):
        url = TMDB + path + ('' if bearer else ('&' if '?' in path else '?') + urllib.parse.urlencode({'api_key': key}))
        status, body = http(url, {'Authorization': f'Bearer {key}'} if bearer else {})
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if status == 401:
            raise TmdbError('TMDB refused the key of KaijuFlow\'s test copy (HTTP 401), so no ID can be checked.')
        return status, data
    return get


def norm(text):
    return re.sub(r'[^a-z0-9]', '', (text or '').lower())


def check_title(t, get):
    """(ok, line) for one pool title, checked against TMDB: the film, or the show and its season and episode."""
    name = f"{t['label']} ({t['id']})"
    if t['type'] == 'movie':
        _, found = get(f"/find/{t['id']}?external_source=imdb_id")
        hits, shows = (found or {}).get('movie_results') or [], (found or {}).get('tv_results') or []
        if shows:  # TMDB can list a stray film under a show's IMDb ID too (it does for Friends)
            return False, f"NOT FOUND {name}: TMDB has a show with this IMDb ID ({shows[0].get('name')}), not a film."
        if not hits:
            return False, f'NOT FOUND {name}: TMDB has no film with this IMDb ID.'
        tmdb = hits[0]
        what = f"film {tmdb.get('title')} ({(tmdb.get('release_date') or '')[:4]}), TMDB {tmdb.get('id')}"
        if norm(t['label']) not in (norm(tmdb.get('title')), norm(tmdb.get('original_title'))):
            return False, f'LABEL DIFFERS {name}: TMDB has {what}.'
        return True, f'OK {name}: {what}.'
    show_id, season, episode = t['id'].split(':')
    _, found = get(f'/find/{show_id}?external_source=imdb_id')
    hits = (found or {}).get('tv_results') or []
    if not hits:
        return False, f'NOT FOUND {name}: TMDB has no show with the IMDb ID {show_id}.'
    show = hits[0]
    what = f"show {show.get('name')} ({(show.get('first_air_date') or '')[:4]}), TMDB {show.get('id')}"
    status, ep = get(f"/tv/{show.get('id')}/season/{int(season)}/episode/{int(episode)}")
    if status != 200 or not ep:
        return False, f'NOT FOUND {name}: TMDB has the {what}, but no season {int(season)} episode {int(episode)}.'
    tag = f'S{int(season):02d}E{int(episode):02d}'
    what += f", {tag} \"{ep.get('name')}\" ({ep.get('air_date')})"
    if norm(t['label']) not in (norm(show.get('name')) + norm(tag), norm(show.get('original_name')) + norm(tag)):
        return False, f'LABEL DIFFERS {name}: TMDB has the {what}.'
    return True, f'OK {name}: {what}.'


def check_ids_command(a, http):
    """One line per title as it is checked, the count, then `done in N s` (README: a log without it is unfinished)."""
    began = time.monotonic()
    data = read_json(a.pool)
    results = []
    try:
        check_pool(data)
        get = tmdb_getter(a.test_dir, http)
        for t in data['titles']:
            results.append(check_title(t, get))
            print(results[-1][1], flush=True)
    except (Refused, TmdbError) as e:
        print(e)
        return 1
    bad = sum(1 for ok, _ in results if not ok)
    print(f'{len(results)} titles checked against TMDB: ' + (f'{bad} not as the pool says.' if bad else 'all as the pool says.'))
    print(f'done in {round(time.monotonic() - began)} s')
    return 1 if bad else 0


def main(argv, http=real_http):
    ap = argparse.ArgumentParser(prog='pool.py', description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('draw', help="draw a speed test's titles and mark them used")
    d.add_argument('--test', required=True, help='the speed test the titles are for, e.g. "Test 2"')
    d.add_argument('--out', required=True, help='where to write the tagged title list (JSON)')
    d.add_argument('--pool', default=DEFAULT_POOL)
    c = sub.add_parser('check-ids', help="check every pool title's ID (and season and episode) against TMDB")
    c.add_argument('--pool', default=DEFAULT_POOL)
    c.add_argument('--test-dir', default=os.environ.get('TEST_DIR', common.DEFAULT_TEST_DIR))
    a = ap.parse_args(argv)
    return draw_command(a) if a.cmd == 'draw' else check_ids_command(a, http)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
