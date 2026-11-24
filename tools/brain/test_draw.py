"""Tests for draw.py (the title draw for real-use checks and its ledger), with a fake TMDB. No network.

    python3 -I -m unittest discover -s tools/brain -p 'test_draw.py'
"""
import contextlib
import datetime
import io
import json
import os
import random
import tempfile
import unittest
import urllib.parse

import common
import draw

TODAY = '2026-11-24'
NOW = datetime.datetime(2026, 11, 24, 12, 0, tzinfo=datetime.timezone.utc)
KEY = 'fake-tmdb-key-0123'


class FakeTmdb:
    """Films and shows behind TMDB's paths the draw uses. `lists` maps a piece of a list path (`/movie/popular`,
    `with_genres=16`) to the TMDB ids it lists, the first piece found in the path winning; every page lists them all."""

    def __init__(self):
        self.films, self.shows, self.lists, self.calls = {}, {}, {}, []

    def film(self, tmdb_id, title, year, original=None, imdb=None):
        self.films[tmdb_id] = {'id': tmdb_id, 'title': title, 'original_title': original or title,
                               'release_date': f'{year}-05-01', 'imdb': imdb if imdb is not None else f'tt{tmdb_id:07d}'}

    def show(self, tmdb_id, name, seasons, imdb=None, aired=None):
        """`seasons`: {number: (episode count, first air date)}; `aired`: {(season, episode): air date} overrides."""
        self.shows[tmdb_id] = {'id': tmdb_id, 'name': name, 'original_name': name, 'seasons': seasons,
                               'aired': aired or {}, 'imdb': imdb if imdb is not None else f'tt{tmdb_id:07d}'}

    def get(self, path):
        self.calls.append(path)
        route, _, query = path.partition('?')
        q = dict(urllib.parse.parse_qsl(query))
        parts = route.strip('/').split('/')
        if route.startswith(('/movie/popular', '/tv/popular', '/discover/')):
            for piece, ids in self.lists.items():
                if piece in path:
                    pool = self.films if route.startswith(('/movie', '/discover/movie')) else self.shows
                    return 200, {'results': [self._entry(pool[i]) for i in ids]}
            return 200, {'results': []}
        if parts[0] == 'search':
            return 200, {'results': [self._entry(f) for f in self.films.values() if f['title'] == q['query']]}
        if parts[0] == 'find':
            imdb = parts[1]
            return 200, {'movie_results': [self._entry(f) for f in self.films.values() if f['imdb'] == imdb],
                         'tv_results': [self._entry(s) for s in self.shows.values() if s['imdb'] == imdb]}
        what, tmdb_id = parts[0], int(parts[1])
        item = (self.films if what == 'movie' else self.shows).get(tmdb_id)
        if item is None:
            return 404, {}
        if parts[2:] == ['external_ids']:
            return 200, {'imdb_id': item['imdb'] or None}
        if len(parts) == 2:
            return 200, {'seasons': [{'season_number': n, 'episode_count': c, 'air_date': d}
                                     for n, (c, d) in item['seasons'].items()]}
        season, episode = int(parts[3]), int(parts[5])
        count, first = item['seasons'].get(season, (0, None))
        if episode > count:
            return 404, {}
        return 200, {'name': f'Episode {episode}', 'air_date': item['aired'].get((season, episode), first)}

    @staticmethod
    def _entry(item):
        return {k: v for k, v in item.items() if k not in ('imdb', 'seasons', 'aired')}

    def http(self, url, headers):
        """The draw's HTTP: the TMDB path of the URL, with the key it carries checked and taken off."""
        assert url.startswith(draw.pool.TMDB), url
        path, _, query = url[len(draw.pool.TMDB):].partition('?')
        params = urllib.parse.parse_qsl(query)
        assert ('api_key', KEY) in params, url
        rest = urllib.parse.urlencode([p for p in params if p[0] != 'api_key'])
        status, data = self.get(path + ('?' + rest if rest else ''))
        return status, json.dumps(data).encode()


def world():
    """A TMDB with titles of every kind."""
    t = FakeTmdb()
    for n in range(1, 6):
        t.film(100 + n, f'Popular Film {n}', 2025)
    t.lists['/movie/popular'] = [101, 102, 103, 104, 105]
    t.show(201, 'Popular Show', {1: (8, '2024-01-01'), 2: (8, '2025-01-01')})
    t.show(202, 'Another Show', {1: (6, '2023-01-01')})
    t.lists['/tv/popular'] = [201, 202]
    t.show(401, 'Some Anime', {1: (12, '2020-04-01')})
    t.lists['with_genres=16'] = [401]  # before the foreign list: the anime and daily lists name a language too
    t.show(501, 'Late Talk', {1: (150, '2015-01-05'), 11: (100, '2025-09-01')})
    t.lists['with_genres=10767'] = [501]
    t.film(301, 'Amélie', 2001, original="Le Fabuleux Destin d'Amélie Poulain")
    t.film(302, 'Same Name', 2010)  # its English title is its original one: not a foreign title
    t.lists['with_original_language='] = [301, 302]
    t.film(601, 'Halloween', 2018)
    t.film(602, 'Halloween', 1978)
    t.film(603, 'Only Once', 2015)  # no other film has its name: not a remake
    t.lists['sort_by=vote_count.desc&page='] = [601, 603]
    t.film(701, 'Old Film', 1971)
    t.lists['primary_release_date.lte'] = [701]
    t.lists['vote_count.lte=200&page'] = [701]
    return t


def run_draw(t, ledger=(), kinds=None, seed=1):
    return draw.draw(t.get, list(ledger), kinds or {}, random.Random(seed), TODAY)


class DrawTest(unittest.TestCase):
    def test_a_draw_of_n_titles_by_kind_gives_titles_of_those_kinds_in_order(self):
        got = run_draw(world(), kinds={'popular-film': 3, 'popular-episode': 2})
        self.assertEqual([g[3] for g in got], ['popular-film'] * 3 + ['popular-episode'] * 2)
        self.assertEqual([g[0] for g in got], ['movie'] * 3 + ['series'] * 2)
        self.assertEqual(len({draw.base_id(g[1]) for g in got}), 5)  # never one title (or one show) twice
        film = got[0]
        self.assertRegex(film[1], r'^tt0000\d{3}$')
        self.assertRegex(film[2], r'^Popular Film \d$')

    def test_an_episode_is_an_aired_episode_with_the_show_s_id_its_season_and_episode(self):
        got = run_draw(world(), kinds={'anime': 1})
        self.assertEqual(got[0][0], 'series')
        show, season, episode = got[0][1].split(':')
        self.assertEqual((show, season), ('tt0000401', '1'))
        self.assertTrue(1 <= int(episode) <= 12)
        self.assertEqual(got[0][2], f'Some Anime S01E{int(episode):02d}')

    def test_titles_in_the_ledger_are_never_drawn_and_a_played_show_takes_none_of_its_episodes(self):
        t = world()
        ledger = [{'id': f'tt{n:07d}'} for n in (101, 102, 103, 104)] + [{'id': 'tt0000201:1:3'}]
        got = run_draw(t, ledger, {'popular-film': 1, 'popular-episode': 1})
        self.assertEqual(got[0][1], 'tt0000105')
        self.assertTrue(got[1][1].startswith('tt0000202:'))

    def test_a_kind_that_runs_out_of_new_titles_is_refused_by_name(self):
        t = world()
        with self.assertRaises(draw.Refused) as e:
            run_draw(t, kinds={'popular-episode': 3})  # two shows only
        self.assertEqual(str(e.exception), f'TMDB gave no new popular-episode title in {draw.TRIES} pages: '
                                           'nothing was drawn.')

    def test_a_replacement_is_one_more_title_of_its_kind_not_already_drawn(self):
        t = world()
        first = run_draw(t, kinds={'popular-film': 1})
        ledger = [{'id': first[0][1]}]
        again = run_draw(t, ledger, {'popular-film': 1}, seed=1)
        self.assertEqual(len(again), 1)
        self.assertNotEqual(again[0][1], first[0][1])

    def test_a_foreign_title_has_an_english_title_that_is_not_its_original_one(self):
        for seed in range(5):
            got = run_draw(world(), kinds={'foreign': 1}, seed=seed)
            self.assertEqual(got[0][1:], ['tt0000301', 'Amélie', 'foreign'])

    def test_a_remake_title_shares_its_name_with_a_film_of_another_year(self):
        for seed in range(5):
            got = run_draw(world(), kinds={'remake': 1}, seed=seed)
            self.assertEqual(got[0][1:], ['tt0000601', 'Halloween', 'remake'])

    def test_a_daily_show_episode_comes_from_its_latest_season(self):
        got = run_draw(world(), kinds={'daily': 1})
        self.assertTrue(got[0][1].startswith('tt0000501:11:'), got[0][1])

    def test_a_rare_kind_draws_from_older_or_little_known_titles(self):
        got = run_draw(world(), kinds={'rare-film': 1})
        self.assertEqual(got[0][1:], ['tt0000701', 'Old Film', 'rare-film'])

    def test_an_episode_not_aired_yet_and_a_season_not_started_are_never_drawn(self):
        t = FakeTmdb()
        t.show(1, 'New Show', {1: (3, '2026-11-01'), 2: (5, '2027-02-01')},
               aired={(1, 2): '2026-12-01', (1, 3): '2026-12-08'})
        t.lists['/tv/popular'] = [1]
        for seed in range(5):
            self.assertEqual(run_draw(t, kinds={'popular-episode': 1}, seed=seed)[0][1], 'tt0000001:1:1')

    def test_a_film_not_released_yet_is_never_drawn(self):
        t = FakeTmdb()
        t.film(1, 'Coming Soon', 2027)
        t.film(2, 'No Date', 2020)
        t.films[2]['release_date'] = ''
        t.film(3, 'Out Now', 2026)
        t.lists['/movie/popular'] = [1, 2, 3]
        for seed in range(5):
            self.assertEqual(run_draw(t, kinds={'popular-film': 1}, seed=seed)[0][1], 'tt0000003')

    def test_a_title_without_an_imdb_id_or_whose_id_does_not_check_is_skipped(self):
        t = FakeTmdb()
        t.film(1, 'No Imdb', 2020, imdb='')
        t.film(2, 'Bad Label', 2020, imdb='tt0000009')
        t.film(9, 'Someone Else', 2020, imdb='tt0000009')  # TMDB's find gives this film for tt0000009 first
        t.film(3, 'Good', 2020)
        t.films = {k: t.films[k] for k in (9, 1, 2, 3)}
        t.lists['/movie/popular'] = [1, 2, 3]
        for seed in range(5):
            self.assertEqual(run_draw(t, kinds={'popular-film': 1}, seed=seed)[0][1], 'tt0000003')

    def test_the_id_check_is_check_ids_own_and_repeats_no_call(self):
        t = world()
        run_draw(t, kinds={'popular-film': 1})
        self.assertTrue(any(c.startswith('/find/') for c in t.calls))
        self.assertEqual(len(t.calls), len(set(t.calls)))

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(draw.Refused) as e:
            run_draw(world(), kinds={'cartoon': 1})
        self.assertIn("There is no kind 'cartoon'", str(e.exception))


class KindsTest(unittest.TestCase):
    def test_kinds_and_counts_in_the_order_given(self):
        self.assertEqual(draw.parse_kinds('popular-film=3, anime=1,popular-film=1'),
                         {'popular-film': 4, 'anime': 1})

    def test_a_part_without_a_count_is_refused(self):
        for text in ('anime', 'anime=0', 'anime=x'):
            with self.assertRaises(draw.Refused):
                draw.parse_kinds(text)

    def test_every_kind_the_spec_names_is_there(self):
        self.assertEqual(set(draw.KINDS), {'popular-film', 'popular-episode', 'rare-film', 'rare-episode',
                                           'foreign', 'anime', 'remake', 'daily'})


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        d = self.dir.name
        self.test_dir, self.ledger, self.out = os.path.join(d, 'test'), os.path.join(d, 'runs', 'ledger.json'), \
            os.path.join(d, 'titles.json')
        os.makedirs(os.path.join(self.test_dir, 'config'))
        with open(os.path.join(self.test_dir, 'config', 'config.json'), 'w') as f:
            json.dump({'searchConfig': {'tmdbApiKey': KEY}}, f)

    def titles(self, t, kinds='popular-film=2,anime=1', check='quick 1', seed=1):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = draw.main(['titles', '--check', check, '--kinds', kinds, '--out', self.out, '--ledger', self.ledger,
                              '--test-dir', self.test_dir], http=t.http, rng=random.Random(seed), now=NOW)
        return code, out.getvalue()

    def test_a_draw_writes_the_title_list_and_adds_the_titles_to_the_ledger(self):
        code, said = self.titles(world())
        self.assertEqual(code, 0, said)
        with open(self.out) as f:
            listed = json.load(f)
        self.assertEqual([x[3] for x in listed], ['popular-film', 'popular-film', 'anime'])
        ledger = draw.read_ledger(self.ledger)
        self.assertEqual([e['id'] for e in ledger], [x[1] for x in listed])
        self.assertEqual({(e['check'], e['when']) for e in ledger}, {('quick 1', '2026-11-24T12:00:00+00:00')})
        lines = said.splitlines()
        self.assertEqual(len(lines), 5)
        self.assertTrue(lines[0].startswith('popular-film: Popular Film '))
        self.assertEqual(lines[-1], 'done in 0 s')
        self.assertNotIn(KEY, said)

    def test_the_next_draw_never_takes_a_title_the_ledger_has(self):
        t = world()
        self.titles(t, kinds='popular-film=3')
        code, said = self.titles(t, kinds='popular-film=2', check='quick 2')
        self.assertEqual(code, 0, said)
        ids = [e['id'] for e in draw.read_ledger(self.ledger)]
        self.assertEqual(sorted(ids), [f'tt{n:07d}' for n in range(101, 106)])
        code, said = self.titles(t, kinds='popular-film=1', check='quick 3')
        self.assertEqual(code, 1)
        self.assertIn('TMDB gave no new popular-film title', said)

    def test_a_refused_draw_changes_neither_the_ledger_nor_the_title_list(self):
        code, said = self.titles(world(), kinds='popular-film=1,popular-episode=5')
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(self.ledger))
        self.assertFalse(os.path.exists(self.out))

    def test_without_a_key_nothing_is_drawn(self):
        os.remove(os.path.join(self.test_dir, 'config', 'config.json'))
        code, said = self.titles(world())
        self.assertEqual(code, 1)
        self.assertIn('There is no TMDB key', said)

    def test_a_list_that_cannot_be_written_leaves_the_titles_spent(self):
        self.out = os.path.join(self.dir.name, 'no-such-folder', 'titles.json')
        code, said = self.titles(world())
        self.assertEqual(code, 1)
        self.assertIn('those titles are spent', said)
        self.assertEqual(len(draw.read_ledger(self.ledger)), 3)

    def test_seed_adds_the_replayed_recording_s_played_titles_once(self):
        pool_file = os.path.join(self.dir.name, 'pool.json')
        with open(pool_file, 'w') as f:
            json.dump({'titles': [{'type': 'movie', 'id': 'tt0071360', 'label': 'The Conversation', 'used_by': 'T2'},
                                  {'type': 'movie', 'id': 'tt0000777', 'label': 'Unused'}]}, f)
        for expect in (len(common.TITLES) + 1, 0):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                draw.main(['seed', '--ledger', self.ledger, '--pool', pool_file], now=NOW)
            self.assertIn(f'{expect} titles the replayed recording played were added', out.getvalue())
        ids = {e['id'] for e in draw.read_ledger(self.ledger)}
        self.assertIn('tt0071360', ids)
        self.assertNotIn('tt0000777', ids)
        self.assertTrue({t[1] for t in common.TITLES} <= ids)


if __name__ == '__main__':
    unittest.main()
