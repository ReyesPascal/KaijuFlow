"""Tests for pool.py (the pool of titles and the draw command), on temporary pool files. No network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.parse

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

    def refused(self, extra):
        """(exit code, printed text) of a draw from an otherwise good pool with `extra` added; asserts nothing changed."""
        self.write(make_pool(films=8, episodes=5, extra=extra))
        before = self.read(self.pool)
        code, out = self.draw('Test 2')
        self.assertEqual(self.read(self.pool), before)
        self.assertFalse(os.path.exists(self.out))
        return code, out.strip()

    def test_the_old_lists_ten_titles_are_refused(self):
        for kind, tid, label in [('movie', 'tt1375666', 'Inception'), ('series', 'tt7366338:1:2', 'Chernobyl S01E02')]:
            old = {'type': kind, 'id': tid, 'label': label, 'list': 'easy', 'reason': 'popular'}
            self.assertEqual(self.refused([old]), (1, f"The pool holds {label} ({tid}), one of Test 1's ten titles, "
                                                      'which a speed test never draws: take it out.'))

    def test_a_title_without_its_fields_or_twice_in_the_pool_is_refused(self):
        no_reason = dict(entry(60, 'movie', 'hard'), reason=' ')
        self.assertEqual(self.refused([no_reason]),
                         (1, 'The pool cannot be used: hard movie 60 (tt9000060) has no reason for its list.'))
        wrong_list = dict(entry(61, 'movie', 'hard'), list='medium')
        self.assertEqual(self.refused([wrong_list]),
                         (1, "The pool cannot be used: hard movie 61 (tt9000061) has the list 'medium', not easy or hard."))
        film_as_episode = dict(entry(62, 'movie', 'hard'), id='tt9000062:1:1')
        self.assertEqual(self.refused([film_as_episode]),
                         (1, "The pool cannot be used: hard movie 62 (tt9000062:1:1) has an ID that is not a film's "
                             '(tt and digits) or an episode\'s (tt and digits:season:episode) for its type movie.'))
        twice = entry(1, 'movie', 'hard')
        self.assertEqual(self.refused([twice]), (1, 'The pool cannot be used: tt9000001 is in it twice.'))


TMDB_SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', '2026-11-15-tmdb')
KEY = 'abc123notarealkey'


def sample(name):
    """(status, body bytes) of an answer captured from TMDB on 2026-11-15."""
    with open(os.path.join(TMDB_SAMPLES, name + '.json')) as f:
        s = json.load(f)
    return s['status'], json.dumps(s['body']).encode()


class FakeTmdb:
    """Answers as TMDB did: 401 without the right key, the captured answer for the paths sampled, an empty find for
    any other IMDb ID and a 404 for any other episode."""

    def __init__(self):
        self.urls = []

    def __call__(self, url, headers):
        self.urls.append(url)
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if query.get('api_key') != [KEY]:
            return sample('refused-key')
        path = parsed.path.removeprefix('/3/')
        if path.startswith('find/'):
            if query.get('external_source') != ['imdb_id']:
                return sample('refused-key')
            name = 'find-' + path.split('/')[1]
            return sample(name if os.path.exists(os.path.join(TMDB_SAMPLES, name + '.json')) else 'find-none')
        if path == 'tv/1668/season/1/episode/1':
            return sample('tv-1668-season-1-episode-1')
        return sample('tv-1668-season-1-episode-99')


class CheckIdsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.pool = os.path.join(self.dir.name, 'pool.json')
        self.test_dir = os.path.join(self.dir.name, 'test')
        os.makedirs(os.path.join(self.test_dir, 'config'))
        self.set_key(KEY)
        self.tmdb = FakeTmdb()

    def tearDown(self):
        self.dir.cleanup()

    def set_key(self, key):
        with open(os.path.join(self.test_dir, 'config', 'config.json'), 'w') as f:
            json.dump({'searchConfig': {'tmdbApiKey': key}, 'port': 1338}, f)

    def check(self, titles):
        with open(self.pool, 'w') as f:
            json.dump({'about': 'test pool', 'titles': [dict(t, list='easy', reason='popular') for t in titles]}, f)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = pool.main(['check-ids', '--pool', self.pool, '--test-dir', self.test_dir], http=self.tmdb)
        self.assertNotIn(KEY, buf.getvalue())
        return code, buf.getvalue().strip().splitlines()

    def test_a_film_and_an_episode_tmdb_has_are_found(self):
        code, lines = self.check([{'type': 'movie', 'id': 'tt0111161', 'label': 'The Shawshank Redemption'},
                                  {'type': 'series', 'id': 'tt0108778:1:1', 'label': 'Friends S01E01'}])
        self.assertEqual(code, 0)
        self.assertEqual(lines, [
            'OK The Shawshank Redemption (tt0111161): film The Shawshank Redemption (1994), TMDB 278.',
            'OK Friends S01E01 (tt0108778:1:1): show Friends (1994), TMDB 1668, S01E01 '
            '"Pilot" (1994-09-22).',
            '2 titles checked against TMDB: all as the pool says.'])

    def test_an_id_or_episode_tmdb_does_not_have_or_a_label_that_differs_is_named(self):
        code, lines = self.check([
            {'type': 'movie', 'id': 'tt0000000', 'label': 'Nothing'},
            {'type': 'movie', 'id': 'tt0108778', 'label': 'Friends'},
            {'type': 'series', 'id': 'tt0111161:1:1', 'label': 'Shawshank S01E01'},
            {'type': 'series', 'id': 'tt0108778:1:99', 'label': 'Friends S01E99'},
            {'type': 'series', 'id': 'tt0108778:1:1', 'label': 'Friends S01E02'},
            {'type': 'movie', 'id': 'tt0111161', 'label': 'The Green Mile'}])
        self.assertEqual(code, 1)
        self.assertEqual(lines, [
            'NOT FOUND Nothing (tt0000000): TMDB has no film with this IMDb ID.',
            'NOT FOUND Friends (tt0108778): TMDB has a show with this IMDb ID (Friends), not a film.',
            'NOT FOUND Shawshank S01E01 (tt0111161:1:1): TMDB has no show with the IMDb ID tt0111161.',
            'NOT FOUND Friends S01E99 (tt0108778:1:99): TMDB has the show Friends (1994), TMDB 1668, '
            'but no season 1 episode 99.',
            'LABEL DIFFERS Friends S01E02 (tt0108778:1:1): TMDB has the show Friends (1994), TMDB 1668, S01E01 '
            '"Pilot" (1994-09-22).',
            'LABEL DIFFERS The Green Mile (tt0111161): TMDB has film The Shawshank Redemption (1994), TMDB 278.',
            '6 titles checked against TMDB: 6 not as the pool says.'])

    def test_a_missing_or_refused_key_is_one_sentence_and_never_printed(self):
        self.set_key('wrong-key-never-printed')
        code, lines = self.check([{'type': 'movie', 'id': 'tt0111161', 'label': 'The Shawshank Redemption'}])
        self.assertEqual((code, lines), (1, ["TMDB refused the key of KaijuFlow's test copy (HTTP 401), so no ID can be checked."]))
        self.assertNotIn('wrong-key-never-printed', '\n'.join(lines))
        self.set_key('')
        code, lines = self.check([{'type': 'movie', 'id': 'tt0111161', 'label': 'The Shawshank Redemption'}])
        self.assertEqual((code, lines), (1, [f"There is no TMDB key in KaijuFlow's test copy ({self.test_dir}/config/config.json, "
                                             'searchConfig.tmdbApiKey), so no ID can be checked.']))


if __name__ == '__main__':
    unittest.main()
