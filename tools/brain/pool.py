"""The pool of titles that speed tests draw from (#165), and the draw command.

    python3 -I tools/brain/pool.py draw --test <speed test> --out <titles.json> [--pool tools/brain/pool.json]

`draw` takes the first 6 films and 4 episodes of each list (easy, hard) that no speed test has used, writes them as the
speed test's tagged title list ([type, id, label, list]) and marks them used by that speed test in the pool.
The pool and the tagged title list are described in docs/formats.md, "The pool".
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402

OLD_LIST = common.TITLES  # Test 1's ten titles: a speed test never draws them (ADR 0007, new titles every speed test)
ID_SHAPE = {'movie': re.compile(r'tt\d+'), 'series': re.compile(r'tt\d+:\d+:\d+')}
DEFAULT_POOL = os.path.join(HERE, 'pool.json')
LISTS = ('easy', 'hard')
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
    write_json(a.out, dump_lines(tagged) + '\n')
    write_json(a.pool, '{"about": ' + json.dumps(data.get('about', ''), ensure_ascii=False)
               + ',\n "titles": ' + dump_lines(data['titles']) + '}\n')
    print(f'Drew {len(tagged)} titles for {a.test} into {a.out}; the pool marks them used.')
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog='pool.py', description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('draw', help="draw a speed test's titles and mark them used")
    d.add_argument('--test', required=True, help='the speed test the titles are for, e.g. "Test 2"')
    d.add_argument('--out', required=True, help='where to write the tagged title list (JSON)')
    d.add_argument('--pool', default=DEFAULT_POOL)
    a = ap.parse_args(argv)
    return draw_command(a)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
