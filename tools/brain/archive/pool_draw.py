"""The retired speed tests' pool (#165) and its commands, archived by ADR 0010 (#273): run only with --revive.

    python3 -I tools/brain/pool.py draw --test <speed test> --out <titles.json> [--pool tools/brain/archive/pool.json] --revive
    python3 -I tools/brain/pool.py check-ids [--pool tools/brain/archive/pool.json] [--test-dir ~/kaijuflow-test] --revive

`draw` takes the first 6 films and 4 episodes of each list (easy, hard) that no speed test has used, writes them as the
speed test's tagged title list ([type, id, label, list]) and marks them used by that speed test in the pool.
`check-ids` looks every pool title up on TMDB (the film, or the show and its season and episode) with the metadata key
of KaijuFlow's test copy, which it reads itself and never prints; one line per title as it goes, then `done in N s`;
exit 1 when any is not as the pool says. Real-use checks draw new titles from TMDB instead (draw.py, ADR 0010).
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]  # python3 -I leaves them off sys.path
import common  # noqa: E402
from pool import ID_SHAPE, TmdbError, check_title, dump_lines, read_json, real_http, tmdb_getter, write_json  # noqa: E402,F401

OLD_LIST = common.TITLES  # Test 1's ten titles: a speed test never draws them (ADR 0007, new titles every speed test)


DEFAULT_POOL = os.path.join(HERE, 'pool.json')  # archived beside this file


LISTS = common.LISTS


PER_LIST = {'movie': 6, 'series': 4}  # a speed test's films and episodes on each list


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
    import retired  # noqa: E402
    sys.exit(retired.gate('pool', 'pool.py ' + (sys.argv[1] if len(sys.argv) > 1 else ''), sys.argv[1:]))
