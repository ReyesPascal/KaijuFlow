"""Tests for pool.py (the pool of titles and the draw command), on temporary pool files. No network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

import pool


def entry(n, kind, lst, used_by=None):
    """One pool title: films get tt9000NNN, episodes tt8000NNN:1:N."""
    tid = f'tt9{n:06d}' if kind == 'movie' else f'tt8{n:06d}:1:{n}'
    e = {'type': kind, 'id': tid, 'label': f'{lst} {kind} {n}', 'list': lst, 'reason': f'{lst} because {n}'}
    if used_by:
        e['used_by'] = used_by
    return e


def make_pool(films=6, episodes=4, extra=()):
    """Titles for both lists: `films` films and `episodes` episodes on each, numbered so no two share an ID."""
    titles, n = [], 0
    for lst in ('easy', 'hard'):
        for kind, count in (('movie', films), ('series', episodes)):
            for _ in range(count):
                n += 1
                titles.append(entry(n, kind, lst))
    return {'about': 'test pool', 'titles': titles + list(extra)}


class PoolTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.pool = os.path.join(self.dir.name, 'pool.json')
        self.out = os.path.join(self.dir.name, 'titles.json')

    def tearDown(self):
        self.dir.cleanup()

    def write(self, data):
        with open(self.pool, 'w') as f:
            json.dump(data, f)

    def read(self, path):
        with open(path) as f:
            return json.load(f)

    def draw(self, test, out=None):
        """(exit code, printed text) of `pool.py draw`."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = pool.main(['draw', '--pool', self.pool, '--test', test, '--out', out or self.out])
        return code, buf.getvalue()

    def test_draws_six_films_and_four_episodes_from_each_list_tagged(self):
        self.write(make_pool(films=8, episodes=5))
        code, _ = self.draw('Test 2')
        self.assertEqual(code, 0)
        drawn = self.read(self.out)
        self.assertEqual(len(drawn), 20)
        for t in drawn:
            self.assertEqual(len(t), 4)
            self.assertIn(t[3], ('easy', 'hard'))
        counts = {(lst, kind): sum(1 for t in drawn if t[3] == lst and t[0] == kind)
                  for lst in ('easy', 'hard') for kind in ('movie', 'series')}
        self.assertEqual(counts, {('easy', 'movie'): 6, ('easy', 'series'): 4, ('hard', 'movie'): 6, ('hard', 'series'): 4})
        self.assertIn(['movie', 'tt9000001', 'easy movie 1', 'easy'], drawn)
        self.assertIn(['series', 'tt8000009:1:9', 'easy series 9', 'easy'], drawn)

    def test_drawn_titles_are_marked_used_by_the_speed_test(self):
        self.write(make_pool(films=8, episodes=5))
        self.draw('Test 2')
        drawn = {t[1] for t in self.read(self.out)}
        titles = self.read(self.pool)['titles']
        self.assertEqual({t['id'] for t in titles if t.get('used_by') == 'Test 2'}, drawn)
        self.assertEqual(sum(1 for t in titles if 'used_by' not in t), 26 - 20)

    def test_a_used_title_is_never_drawn_again(self):
        used = [entry(100 + i, 'movie', 'easy', used_by='Test 1b') for i in range(3)]
        self.write(make_pool(films=12, episodes=8, extra=used))
        self.draw('Test 2')
        first = {t[1] for t in self.read(self.out)}
        second_out = os.path.join(self.dir.name, 'second.json')
        code, _ = self.draw('Test 3', out=second_out)
        self.assertEqual(code, 0)
        second = {t[1] for t in self.read(second_out)}
        self.assertEqual(len(second), 20)
        self.assertFalse(first & second)
        self.assertFalse({t['id'] for t in used} & (first | second))
        marks = {t['id']: t.get('used_by') for t in self.read(self.pool)['titles']}
        self.assertTrue(all(marks[i] == 'Test 2' for i in first))
        self.assertTrue(all(marks[t['id']] == 'Test 1b' for t in used))

    def test_a_pool_too_small_is_refused_in_one_sentence_and_nothing_is_marked(self):
        data = make_pool(films=6, episodes=4)
        data['titles'] = [t for t in data['titles'] if t['id'] not in ('tt9000011', 'tt8000017:1:17', 'tt8000018:1:18')]
        data['titles'].append(entry(50, 'series', 'hard', used_by='Test 1b'))
        self.write(data)
        before = self.read(self.pool)
        code, out = self.draw('Test 2')
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), 'The pool is too small for Test 2: the hard list has 5 unused films of the 6 '
                                      'and 2 unused episodes of the 4 a speed test needs.')
        self.assertEqual(self.read(self.pool), before)
        self.assertFalse(os.path.exists(self.out))


if __name__ == '__main__':
    unittest.main()
