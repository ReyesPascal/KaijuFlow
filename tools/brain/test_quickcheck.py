"""Tests for the quick check (#270, spec #268): the right-title match, one visit's outcome, the verdict and report.md, the
check's run through brainrun.quick_check_all (a fake world: HTTP, the indexer stand-in, Docker and the clock), its
preflight on fixture test copies, and the expected settings' `indexers[*]` rule.
    python3 -I -m unittest discover -s tools/brain -p 'test_quickcheck.py'
"""
import contextlib
import datetime
import io
import json
import os
import unittest

from unittest import mock

import brainreport as br
import brainrun
import common
import draw
import fixing
import pool
import quickcheck as qc
import testbed
from test_preflight import FakeWorld, make_cfg, run_command
from test_settings import SECRET, make_copies, put_limits, tempdir

HERE = os.path.dirname(os.path.abspath(__file__))
UTC = datetime.timezone.utc


def names():
    """The captured release names (fixtures/2026-11-24-release-names/), by a short key."""
    with open(os.path.join(HERE, 'fixtures', '2026-11-24-release-names', 'names.txt')) as f:
        lines = f.read().splitlines()
    keys = ['inside out 2', 'pushing daisies e09', 'avatar', 'spider-verse', 'hitcher', '7th time loop', 'space 1999 e04',
            'pushing daisies pack', 'avatar german', 'misanthrope e02', 'chernobyl 1x02', 'chernobyl s01.e02', 'got 2011 s02e03',
            'breaking bad 1x01', 'squid game challenge', 'witcher blood origin', 'guardians imax', 'thief german', 'witcher sonarr',
            'reacher tv', 'inception cobol job', 'oppenheimer real story', 'avatar pandoras box', 'deadpool german', 'witcher us',
            'utopia uk', 'utopia au pack', 'got complete', 'akira special edition']
    return dict(zip(keys, lines))


def shared_release_names():
    """The shared release-name table (tests/fixtures/release-names/table.tsv, #282): one dict per row."""
    head, *lines = read(HERE, '..', '..', 'tests', 'fixtures', 'release-names', 'table.tsv').rstrip('\n').split('\n')
    return [dict(zip(head.split('\t'), line.split('\t'))) for line in lines]


def read(*parts):
    with open(os.path.join(*parts)) as f:
        return f.read()


def step_lines_of(folder, name):
    """KaijuFlow's step lines in one captured log (fixtures/<folder>/<name>)."""
    with open(os.path.join(HERE, 'fixtures', folder, name)) as f:
        return br.parse_step_lines(f.read())


def step_lines(name):
    """KaijuFlow's step lines of one captured Best press (fixtures/2026-11-23-step-lines/)."""
    return step_lines_of('2026-11-23-step-lines', name)


def parity_film(tag):
    """The title a captured Best press played (its releases are `KaijuFlow.PlayTime.<tag>.2026...`)."""
    return ['movie', 'tt1000010', f'KaijuFlow PlayTime {tag}', 'popular-film', '2026-03-01']


FILM = parity_film('log-ok')


class RightTitleTest(unittest.TestCase):
    """quickcheck.right_title on release names NinjaCentral really sent."""

    def setUp(self):
        self.n = names()

    def ok(self, release, title, other=()):
        return qc.right_title(self.n[release], title, other)

    def test_a_film_with_its_name_and_year_is_right(self):
        self.assertEqual(self.ok('avatar', ['movie', 'tt0499549', 'Avatar', 'popular-film', '2009-12-15']), (True, ''))
        self.assertEqual(self.ok('spider-verse', ['movie', 'tt9362722', 'Spider-Man: Across the Spider-Verse', 'popular-film',
                                                  '2023-05-31']), (True, ''))
        self.assertEqual(self.ok('hitcher', ['movie', 'tt0091209', 'The Hitcher', 'rare-film', '1986-02-21']), (True, ''))

    def test_a_year_one_off_is_right_but_further_is_the_wrong_film(self):
        self.assertTrue(self.ok('avatar', ['movie', 'tt0499549', 'Avatar', 'popular-film', '2010-01-01'])[0])
        self.assertEqual(self.ok('avatar', ['movie', 'tt0499549', 'Avatar', 'popular-film', '2012-05-01']),
                         (False, 'its year is 2009, not 2012'))

    def test_a_number_between_a_films_name_and_its_year_is_another_film(self):
        ok, why = self.ok('inside out 2', ['movie', 'tt2096673', 'Inside Out', 'popular-film', '2015-06-17'])
        self.assertEqual((ok, why), (False, 'the name "Inside Out" is not followed by a year (2015 wanted)'))  # the sequel

    def test_editions_languages_and_video_tags_may_stand_between_a_films_name_and_its_year(self):
        self.assertEqual(self.ok('guardians imax', ['movie', 'tt6791350', 'Guardians of the Galaxy Vol. 3', 'popular-film',
                                                    '2023-05-03']), (True, ''))  # IMAX and 1080p before the year
        self.assertEqual(self.ok('deadpool german', ['movie', 'tt6263850', 'Deadpool & Wolverine', 'popular-film', '2024-07-24']),
                         (True, ''))
        self.assertEqual(self.ok('akira special edition', ['movie', 'tt0094625', 'Akira', 'anime', '1988-07-16']), (True, ''))

    def test_every_allowed_tag_was_seen_in_a_real_release_of_the_right_film(self):
        rows = [line.split('\t') for line in read(HERE, 'fixtures', '2026-11-24-release-names', 'film-tags.tsv').splitlines()]
        seen = set()
        for label, year, other, release in rows:
            title = ['movie', 'tt1', label, 'popular-film', f'{year}-06-01']
            self.assertEqual(qc.right_title(release, title, [other] if other else []), (True, ''), release)
            rel = qc.words(release)
            for n in [other or label]:  # the name it fits through
                for j in qc._after(rel, qc.words(n)):
                    seen |= set(rel[j:next((k for k in range(j, len(rel)) if qc._year(rel[k])), j)])
        self.assertEqual(seen - {'1080p', '2160p', '720p', '4k'}, qc.FILM_TAGS)

    def test_a_longer_film_around_the_name_is_another_film(self):
        for key, label, date in (('inception cobol job', 'Inception', '2010-07-15'), ('oppenheimer real story', 'Oppenheimer', '2023-07-19'),
                                 ('avatar pandoras box', 'Avatar', '2009-12-15')):
            ok, why = self.ok(key, ['movie', 'tt1', label, 'popular-film', date])
            self.assertEqual((ok, why), (False, f'the name "{label}" is not followed by a year ({date[:4]} wanted)'), key)

    def test_a_title_in_another_language_fits_through_another_name_of_it(self):
        title = ['movie', 'tt0499549', 'Avatar', 'popular-film', '2009-12-15']
        self.assertEqual(self.ok('avatar german', title), (False, 'the name "Avatar" is not followed by a year (2009 wanted)'))
        self.assertEqual(self.ok('avatar german', title, ['Avatar: Aufbruch nach Pandora']), (True, ''))
        thief = ['movie', 'tt0083190', 'Thief', 'rare-film', '1981-03-27']
        self.assertFalse(self.ok('thief german', thief)[0])
        self.assertEqual(self.ok('thief german', thief, ['Der Einzelgänger']), (True, ''))  # released as Einzelgaenger
        ok, why = self.ok('spider-verse', ['movie', 'tt0145487', 'Spider-Man', 'popular-film', '2002-05-01'])
        self.assertFalse(ok)

    def test_a_longer_show_around_the_name_is_another_show(self):
        ok, why = self.ok('squid game challenge', ['series', 'tt10919420:1:1', 'Squid Game S01E01', 'popular-episode', '2021-09-17'])
        self.assertEqual((ok, why), (False, 'the name "Squid Game" is not followed by a season or episode'))
        self.assertFalse(self.ok('witcher blood origin', ['series', 'tt5180504:1:1', 'The Witcher S01E01', 'popular-episode',
                                                          '2019-12-20'])[0])

    def test_a_show_tag_year_or_tvdb_number_may_stand_before_the_episode(self):
        witcher = ['series', 'tt5180504:1:1', 'The Witcher S01E01', 'popular-episode', '2019-12-20']
        self.assertEqual(self.ok('witcher sonarr', witcher), (True, ''))  # The Witcher (2019) (362696) - S01E01
        self.assertEqual(self.ok('reacher tv', ['series', 'tt9288030:1:1', 'Reacher S01E01', 'popular-episode', '2022-02-04']),
                         (True, ''))
        self.assertEqual(self.ok('witcher us', witcher), (True, ''))
        utopia = ['series', 'tt2384811:1:1', 'Utopia S01E01', 'popular-episode', '2013-01-15']
        self.assertEqual(self.ok('utopia uk', utopia), (True, ''))
        self.assertEqual(self.ok('utopia au pack', utopia), (True, ''))
        self.assertEqual(self.ok('got complete', ['series', 'tt0944947:2:3', 'Game of Thrones S02E03', 'popular-episode',
                                                  '2012-04-15']), (True, ''))

    def test_a_release_without_the_name_is_the_wrong_title(self):
        ok, why = self.ok('hitcher', ['movie', 'tt0499549', 'Avatar', 'popular-film', '2009-12-15'])
        self.assertEqual((ok, why), (False, 'the name "Avatar" is not in it'))

    def test_another_name_of_the_title_counts(self):
        title = ['movie', 'tt0499549', 'Avatar: Aufbruch nach Pandora', 'foreign', '2009-12-15']
        self.assertFalse(self.ok('avatar', title)[0])
        self.assertEqual(self.ok('avatar', title, ['Avatar']), (True, ''))

    def test_an_episode_needs_its_show_and_its_episode(self):
        self.assertEqual(self.ok('pushing daisies e09', ['series', 'tt0925266:1:9', 'Pushing Daisies S01E09', 'rare-episode',
                                                         '2008-12-03']), (True, ''))
        ok, why = self.ok('pushing daisies e09', ['series', 'tt0925266:1:8', 'Pushing Daisies S01E08', 'rare-episode', '2008-11-26'])
        self.assertEqual((ok, why), (False, 'it is S01E09, not S01E08'))
        self.assertTrue(self.ok('misanthrope e02', ['series', 'tt1:1:2', 'A Misanthrope Teaches a Class for Demi-Humans S01E02',
                                                    'anime', '2025-01-13'])[0])

    def test_a_show_whose_name_holds_a_year(self):
        self.assertEqual(self.ok('space 1999 e04', ['series', 'tt0072564:1:4', 'Space: 1999 S01E04', 'rare-episode', '1975-09-25']),
                         (True, ''))

    def test_a_season_pack_of_the_right_season_is_right_and_of_another_is_wrong(self):
        self.assertTrue(self.ok('pushing daisies pack', ['series', 'tt0925266:1:3', 'Pushing Daisies S01E03', 'rare-episode',
                                                         '2007-10-17'])[0])
        ok, why = self.ok('pushing daisies pack', ['series', 'tt0925266:2:3', 'Pushing Daisies S02E03', 'rare-episode', '2008-10-15'])
        self.assertEqual((ok, why), (False, 'it is a pack of season 1, not season 2'))

    def test_other_episode_markers_as_released(self):
        chernobyl = ['series', 'tt7366338:1:2', 'Chernobyl S01E02', 'popular-episode', '2019-05-13']
        self.assertEqual(self.ok('chernobyl 1x02', chernobyl), (True, ''))
        self.assertEqual(self.ok('chernobyl s01.e02', chernobyl), (True, ''))
        self.assertEqual(self.ok('chernobyl s01.e02', chernobyl[:1] + ['tt7366338:1:5', 'Chernobyl S01E05'] + chernobyl[3:]),
                         (False, 'it is S01E02, not S01E05'))  # S01.E02 is an episode, not a pack of season 1
        self.assertEqual(self.ok('got 2011 s02e03', ['series', 'tt0944947:2:3', 'Game of Thrones S02E03', 'popular-episode',
                                                     '2012-04-15']), (True, ''))  # a year between the name and the episode
        self.assertEqual(self.ok('breaking bad 1x01', ['series', 'tt0903747:1:1', 'Breaking Bad S01E01', 'popular-episode',
                                                       '2008-01-20']), (True, ''))
        self.assertEqual(self.ok('7th time loop', ['series', 'tt1:1:1', '7th Time Loop: The Villainess Enjoys a Carefree Life '
                                                   'Married to Her Worst Enemy! S01E01', 'anime', '2024-01-07']),
                         (False, 'the name "7th Time Loop: The Villainess Enjoys a Carefree Life Married to Her Worst Enemy!" is not in it'))
        self.assertTrue(self.ok('7th time loop', ['series', 'tt1:1:1', '7th Time Loop S01E01', 'anime', '2024-01-07'])[0])

    def test_every_row_of_the_shared_release_name_table_gets_its_strict_answer(self):
        """The table KaijuFlow's Search Flow tests read too (tests/unit/search-flow.test.ts), so the two copies of the
        rule give the same answers: `strict` is `pass` or the why."""
        rows = shared_release_names()
        self.assertGreaterEqual(len(rows), 60)
        for row in rows:
            title = [row['type'], 'tt1', row['label'], 'shared-table', row['date']]
            ok, why = qc.right_title(row['release'], title, row['other'].split('|') if row['other'] else [])
            self.assertEqual('pass' if ok else why, row['strict'], f"{row['release']} as {row['label']}")

    def test_episode_markers_no_recording_holds(self):
        """Invented names: no release in the recordings uses these markers."""
        title = ['series', 'tt1:3:7', 'Some Show S03E07', 'popular-episode', '2024-05-01']
        for release, right in (('Some.Show.S03E06-E08.1080p.WEB', True), ('Some.Show.S03E06E07.1080p', True),
                               ('Some.Show.S01-S04.COMPLETE.1080p', True), ('Some.Show.Season.3.1080p', True),
                               ('Some.Show.1080p.WEB', False)):
            self.assertEqual(qc.right_title(release, title)[0], right, release)

    def test_a_daily_show_is_known_by_its_air_date(self):
        """Invented names: no daily show is in the recordings."""
        title = ['series', 'tt3697842:2026:45', 'Late Night Talk S2026E45', 'daily', '2026-11-20']
        self.assertTrue(qc.right_title('Late.Night.Talk.2026.11.20.Guest.Name.1080p.WEB.h264', title)[0])
        self.assertFalse(qc.right_title('Late.Night.Talk.2026.11.19.Guest.Name.1080p.WEB.h264', title)[0])


class TmdbNamesTest(unittest.TestCase):
    def test_a_films_other_names_from_tmdbs_real_answers(self):
        answers = json.loads(read(HERE, 'fixtures', '2026-11-24-release-names', 'tmdb-amelie.json'))
        found = qc.tmdb_names(lambda path: tuple(answers.get(path, [404, None])), ['movie', 'tt0211915', 'Amélie', 'foreign', '2001-04-25'])
        self.assertEqual(found[:2], ['Amélie', "Le Fabuleux Destin d'Amélie Poulain"])
        self.assertIn('The Fabulous Destiny of Amelie Poulain', found)
        release = 'Le.Fabuleux.Destin.dAmelie.Poulain.2001.1080p.BluRay.x264-GRP'  # the French name, its apostrophe dropped
        title = ['movie', 'tt0211915', 'Amélie', 'foreign', '2001-04-25']
        self.assertEqual(qc.right_title(release, title), (False, 'the name "Amélie" is not in it'))
        self.assertEqual(qc.right_title(release, title, found), (True, ''))

    def test_an_episode_is_looked_up_by_its_show_in_tmdbs_real_answers(self):
        answers = json.loads(read(HERE, 'fixtures', '2026-11-24-release-names', 'tmdb-breaking-bad.json'))
        asked = []

        def get(path):
            asked.append(path)
            return tuple(answers.get(path, [404, None]))
        found = qc.tmdb_names(get, ['series', 'tt0903747:1:1', 'Breaking Bad S01E01', 'popular-episode', '2008-01-20'])
        self.assertEqual(found[0], 'Breaking Bad')
        self.assertIn('Breaking Bad: A Química do Mal', found)
        self.assertEqual(asked, ['/find/tt0903747?external_source=imdb_id', '/tv/1396/alternative_titles'])

    def test_a_title_tmdb_does_not_know_has_no_other_names(self):
        self.assertEqual(qc.tmdb_names(lambda path: (200, {'movie_results': [], 'tv_results': []}),
                                       ['movie', 'tt9', 'X', 'popular-film', '2000-01-01']), [])

    def test_a_tmdb_that_does_not_answer_raises_so_the_fail_says_so(self):
        for status in (429, 500):
            with self.assertRaisesRegex(pool.TmdbError, f'TMDB answered HTTP {status}'):
                qc.tmdb_names(lambda path: (status, None), ['movie', 'tt9', 'X', 'popular-film', '2000-01-01'])


def visit(title=FILM, steps=(), sources=3, best=True, plays=True, first_byte=4.0, list_s=2.0, status=200, note=None):
    play = {'plays': plays, 'first_byte_s': first_byte, 'note': None if plays else 'failure video'} if best else None
    return {'title': list(title), 'list_status': status, 'list_s': list_s, 'sources': sources, 'best': best, 'play': play,
            'steps': list(steps), 'note': note}


class JudgeTest(unittest.TestCase):
    """quickcheck.judge on the step lines KaijuFlow really writes (the captured Best presses)."""

    def test_best_plays_the_first_healthy_source_and_the_dead_one_is_no_fallback(self):
        o = qc.judge(visit(steps=step_lines('kaijuflow-best-dead-first.txt')))
        self.assertEqual((o['outcome'], o['release'], o['fallbacks'], o['check_misses'], o['title_to_video'], o['slow']),
                         ('played', 'KaijuFlow.PlayTime.log-ok.2026.2160p.WEB-DL.H265-GRP', 0, [], 6.0, False))
        self.assertEqual([(c['release'].split('.')[2], c['status']) for c in o['checked']],
                         [('log-ok', 'verified'), ('log-dead', 'blocked'), ('log-backup', 'verified')])

    def test_a_source_altmount_refused_after_its_check_is_a_check_miss_and_a_fallback_that_ended_in_video(self):
        o = qc.judge(visit(title=parity_film('hsr-ok'), steps=step_lines('kaijuflow-head-start-refused-first.txt')))
        self.assertEqual((o['outcome'], o['fallbacks'], o['video']), ('played', 1, True))
        self.assertEqual(o['check_misses'], [{'release': 'KaijuFlow.PlayTime.hsr-refused.2026.2160p.WEB-DL.H265-GRP',
                                              'reason': 'AltMount could not process the Source: {"error":"NZB processing failed"}'}])

    def test_no_video_after_a_source_passed_its_check_is_a_fail_with_one_check_miss_per_release(self):
        o = qc.judge(visit(sources=1, plays=False, steps=step_lines('kaijuflow-best-first-byte-failed.txt')))
        self.assertEqual(o['outcome'], 'fail')
        self.assertEqual(o['why'], 'no video (failure video); AltMount refused KaijuFlow.PlayTime.fbf-400.2026.2160p.WEB-DL.H265-GRP: '
                                   'First byte failed (status 400); the Source is kept')
        self.assertEqual((o['fallbacks'], len(o['check_misses'])), (1, 1))  # the Head start and the press both tried it

    def test_the_wrong_title_is_a_fail_even_with_video(self):
        title = ['movie', 'tt2096673', 'Inside Out', 'popular-film', '2015-06-17']
        steps = [{'step': 'played', 'title': names()['inside out 2'], 't': '2026-11-24T10:00:05.000Z'}]
        o = qc.judge(visit(title=title, steps=steps), names=lambda: ['Alles steht Kopf'])
        self.assertEqual(o['outcome'], 'fail')
        self.assertIn('the wrong title played: Inside.Out.2.2024', o['why'])
        self.assertIn('is not followed by a year (2015 wanted)', o['why'])

    def test_a_wrong_title_after_60_s_is_a_fail_not_a_slow_play(self):
        title = ['movie', 'tt2096673', 'Inside Out', 'popular-film', '2015-06-17']
        steps = [{'step': 'played', 'title': names()['inside out 2']}]
        o = qc.judge(visit(title=title, steps=steps, first_byte=75.0), names=lambda: [])
        self.assertEqual((o['outcome'], o['slow']), ('fail', False))

    def test_tmdb_that_cannot_be_read_is_named_in_the_fail(self):
        title = ['movie', 'tt0499549', 'Avatar: Aufbruch nach Pandora', 'foreign', '2009-12-15']
        o = qc.judge(visit(title=title, steps=[{'step': 'played', 'title': names()['avatar']}]), names=lambda: None)
        self.assertEqual(o['outcome'], 'fail')
        self.assertIn("TMDB's other names of the title could not be read", o['why'])

    def test_other_names_are_asked_for_only_when_the_name_is_missing(self):
        asked = []
        title = ['movie', 'tt0499549', 'Avatar: Aufbruch nach Pandora', 'foreign', '2009-12-15']
        steps = [{'step': 'played', 'title': names()['avatar']}]
        o = qc.judge(visit(title=title, steps=steps), names=lambda: asked.append(1) or ['Avatar'])
        self.assertEqual((o['outcome'], asked), ('played', [1]))
        qc.judge(visit(steps=step_lines('kaijuflow-best-dead-first.txt')), names=lambda: asked.append(2) or [])
        self.assertEqual(asked, [1])

    def test_video_without_a_played_line_cannot_be_told_right_and_is_a_fail(self):
        o = qc.judge(visit(steps=[]))
        self.assertEqual(o['outcome'], 'fail')
        self.assertIn('names no release played', o['why'])

    def test_video_after_60_s_is_a_slow_play_not_a_fail(self):
        o = qc.judge(visit(first_byte=61.5, steps=step_lines('kaijuflow-best-dead-first.txt')))
        self.assertEqual((o['outcome'], o['slow'], o['title_to_video']), ('played', True, 63.5))
        self.assertFalse(qc.judge(visit(first_byte=60.0, steps=step_lines('kaijuflow-best-dead-first.txt')))['slow'])

    def test_nothing_to_play_needs_every_source_said_no(self):
        counted = qc.judge(visit(sources=0, best=False, steps=[{'step': 'list_filter', 'results': 12, 'kept': 0}]))
        self.assertEqual((counted['outcome'], counted['why']),
                         ('nothing to play', "the list held no Source: KaijuFlow's search kept 12 Sources and its filters kept none"))
        dead = [{'step': 'play_check', 'title': f'Rel.{i}.2026', 'ok': False, 'status': 'blocked'} for i in range(3)]
        o = qc.judge(visit(sources=3, plays=False, steps=dead))
        self.assertEqual((o['outcome'], o['why']), ('nothing to play', 'every Source KaijuFlow looked at failed its check (3 of 3)'))
        o = qc.judge(visit(sources=5, plays=False, steps=dead))  # two Sources never reached: not shown that none would play
        self.assertEqual((o['outcome'], o['why']), ('fail', 'no video (failure video), and only 3 of 5 Sources were checked'))

    def test_an_empty_list_is_a_fail_when_it_is_not_shown_that_nothing_would_play(self):
        lines = step_lines_of('2026-11-24-step-lines', 'kaijuflow-indexer-down-empty-list.txt')  # NinjaCentral did not answer
        kept = qc.visit_steps(lines, 'tt1375666', '2026-11-24T06:00:46.348Z')
        self.assertEqual([s['step'] for s in kept], ['indexer_page', 'list_filter'])
        o = qc.judge(visit(title=['movie', 'tt1375666', 'Inception', 'popular-film', '2010-07-15'], sources=0, best=False, steps=kept))
        self.assertEqual((o['outcome'], o['why']), ('fail', 'the list held no Source, and NinjaCentral did not answer its search (page 1)'))
        answered = [dict(kept[0], ok=True), kept[1]]
        o = qc.judge(visit(sources=0, best=False, steps=answered))
        self.assertEqual((o['outcome'], o['why']),
                         ('nothing to play', "the list held no Source: KaijuFlow's search kept 0 Sources and its filters kept none"))
        o = qc.judge(visit(sources=0, best=False))  # no list_filter line: the list's handler failed
        self.assertEqual(o['outcome'], 'fail')
        self.assertIn('no list_filter line', o['why'])

    def test_a_list_that_did_not_come_or_has_no_best_entry_is_a_fail(self):
        o = qc.judge(visit(status=None, sources=0, best=False, note='timed out'))
        self.assertEqual((o['outcome'], o['why']), ('fail', "KaijuFlow's list did not come: timed out"))
        o = qc.judge(visit(best=False))
        self.assertEqual((o['outcome'], o['why']), ('fail', 'the list had no Best entry to press'))

    def test_visit_steps_keep_the_visits_own_play_lines(self):
        steps = step_lines('kaijuflow-best-dead-first.txt')
        kept = qc.visit_steps(steps + [{'step': 'played', 'ref': 'tt999', 'title': 'Other', 't': '2026-11-23T20:35:13.000Z'}],
                              'tt1000010', '2026-11-23T20:35:11.000Z')
        self.assertEqual([s['step'] for s in kept], ['indexer_page', 'play_check', 'play_check', 'play_check', 'played'])
        self.assertEqual(qc.visit_steps(steps, 'tt1000010', '2026-11-23T20:36:00.000Z'), [])  # lines before the visit
        at_start = [{'step': 'played', 'ref': 'tt1000010', 'title': 'A', 't': '2026-11-23T20:35:11.000Z'}]
        self.assertEqual(len(qc.visit_steps(at_start, 'tt1000010', '2026-11-23T20:35:11Z')), 1)  # times as times, not text


def check_record(**kw):
    return {'status': 'ok', 'folder': '2026-11-25T100000Z-quick-check', 'started': '2026-11-25T10:00:00.000Z', 'commit': 'abc1234def',
            'titles': [FILM] * 5, **kw}


def outcome(label='A Film', outcome='played', **kw):
    base = {'label': label, 'id': 'tt1', 'kind': 'popular-film', 'sources': 3, 'outcome': outcome, 'why': '', 'release': f'{label}.2026',
            'video': outcome == 'played', 'checked': [], 'fallbacks': 0, 'check_misses': [], 'start_s': 3.0, 'title_to_video': 5.0,
            'slow': False}
    return {**base, **kw}


class ReportTest(unittest.TestCase):
    def test_a_check_with_no_fail_passes_and_says_fallbacks_were_not_tested(self):
        outcomes = [outcome('A', title_to_video=4.0), outcome('B', title_to_video=6.0), outcome('C', title_to_video=5.0),
                    outcome('D', 'nothing to play', why='the list held no Source', video=False, title_to_video=None),
                    outcome('E', title_to_video=9.0, slow=True, start_s=70.0)]
        check = check_record()
        self.assertEqual(qc.verdict(check, outcomes), 'pass')
        text = qc.render_report(check, outcomes)
        lines = text.splitlines()
        self.assertEqual(lines[:3], ['# Quick check 2026-11-25T10:00:00.000Z', '', 'Pass: 0 fails in 5 titles.'])
        self.assertIn('- E: video 70.00 s after the press.', text)
        self.assertIn('Fallbacks not tested this time: no play fell back.', text)
        self.assertIn('- D: the list held no Source.', text)
        self.assertIn('5.50 s (median of 4 plays with the right video', text)
        self.assertNotIn('Tickets to file', text)
        self.assertNotIn('previous', text.lower())

    def test_a_fail_fails_the_check_and_each_fail_and_check_miss_gets_a_ticket_text(self):
        miss = {'release': 'Rel.Refused.2026', 'reason': 'NZB processing failed'}
        outcomes = [outcome('A'), outcome('B', 'fail', why='no video (failure video)', video=False, title_to_video=None,
                                          checked=[{'release': 'Rel.B.2026', 'ok': True, 'status': 'verified'}]),
                    outcome('C', fallbacks=1, check_misses=[miss])]
        check = check_record()
        self.assertEqual(qc.verdict(check, outcomes), 'fail')
        text = qc.render_report(check, outcomes)
        self.assertTrue(text.splitlines()[2].startswith('Fail: 1 of 3 titles failed (B).'), text)
        self.assertIn('## Fails\n\n- B: no video (failure video).', text)
        self.assertIn('- C: Rel.Refused.2026: NZB processing failed.', text)
        self.assertIn('1 fallback in 1 title; 1 of them ended in video.\n- C: 1 fallback, ended in video.', text)
        self.assertIn('### Quick check fail: B', text)
        self.assertIn('### Check miss: Rel.Refused.2026', text)
        self.assertIn('checked: Rel.B.2026 (verified)', text)
        self.assertIn('Quick check `2026-11-25T100000Z-quick-check` (commit abc1234', text)

    def test_a_check_the_cap_rule_stopped_has_no_verdict(self):
        check = check_record(status='null', null={'indexer': 'ninjacentral', 'time': '2026-11-25T10:03:00Z', 'where': 'x'})
        self.assertIsNone(qc.verdict(check, [outcome('B', 'fail')]))
        self.assertEqual(qc.headline(check, []), 'No verdict: ninjacentral said its limit was reached at 2026-11-25T10:03:00Z, so the '
                                                 'check stopped (the cap rule).')



def table_release(release):
    """The row of the shared release-name table for this release name."""
    return next(r for r in shared_release_names() if r['release'] == release)


class AllowedWordTest(unittest.TestCase):
    """A maybe that played the right title offers its odd word as a new allowed word, with that release as proof (#286,
    spec #279 story 72). The right title is told by the video file KaijuFlow played (its played line's `video`, dev switch
    on) when the release name does not show it. Real release names from the shared table."""

    PULP = ['movie', 'tt0110912', 'Pulp Fiction', 'popular-film', '1994-09-10']
    PULP_CE = 'Pulp.Fiction.CE.1994.INTERNAL.DVDRip.XviD-SChiZO'  # `CE` between the name and the year: a maybe

    def played(self, release, video=None, **kw):
        line = {'step': 'played', 'title': release, 'source': 'NinjaCentral', 't': '2026-11-25T10:00:05.000Z', **kw}
        return [{**line, 'video': video} if video else line]

    def test_a_maybe_whose_video_file_fits_played_the_right_title_and_offers_its_odd_word_with_the_release(self):
        self.assertEqual(table_release(self.PULP_CE)['right'], 'yes')
        video = 'Pulp.Fiction.1994.INTERNAL.DVDRip.XviD-SChiZO.avi'
        o = qc.judge(visit(title=self.PULP, steps=self.played(self.PULP_CE, video, flow='sure', proof='nzb video')), names=lambda: [])
        self.assertEqual((o['outcome'], o['why']), ('played', ''))
        self.assertEqual(o['allowed_word'], {'word': 'ce', 'where': 'between the name and the year', 'release': self.PULP_CE,
                                             'video': video, 'proof': 'nzb video'})

    def test_without_a_video_file_that_fits_the_maybe_is_the_wrong_title_and_offers_nothing(self):
        o = qc.judge(visit(title=self.PULP, steps=self.played(self.PULP_CE)), names=lambda: [])
        self.assertEqual(o['outcome'], 'fail')
        self.assertIn('the wrong title played: Pulp.Fiction.CE.1994', o['why'])
        self.assertIsNone(o['allowed_word'])
        other = qc.judge(visit(title=self.PULP, steps=self.played(self.PULP_CE, 'Jackie.Brown.1997.DVDRip.avi')), names=lambda: [])
        self.assertEqual((other['outcome'], other['allowed_word']), ('fail', None))

    def test_a_right_release_with_more_than_one_odd_word_offers_none(self):
        thief = 'Thief.Der.Einzelgaenger.1981.Directors.Cut.German.DL.1080p.BluRay.x264-CONTRiBUTiON'  # another name, not a tag
        title = ['movie', 'tt0083190', 'Thief', 'rare-film', '1981-03-27']
        o = qc.judge(visit(title=title, steps=self.played(thief, 'Thief.1981.German.DL.1080p.BluRay.x264-CONTRiBUTiON.mkv')),
                     names=lambda: [])
        self.assertEqual((o['outcome'], o['allowed_word']), ('played', None))

    def test_a_release_the_strict_rule_passes_offers_nothing(self):
        o = qc.judge(visit(steps=step_lines('kaijuflow-best-dead-first.txt')))
        self.assertIsNone(o['allowed_word'])

    def test_the_offered_word_is_in_the_checks_report_with_its_release(self):
        offer = {'word': 'ce', 'where': 'between the name and the year', 'release': self.PULP_CE,
                 'video': 'Pulp.Fiction.1994.INTERNAL.DVDRip.XviD-SChiZO.avi', 'proof': 'nzb video'}
        text = qc.render_report(check_record(), [outcome('Pulp Fiction', release=self.PULP_CE, allowed_word=offer), outcome('B')])
        self.assertIn('## Allowed words offered\n\n'
                      '- `ce` (between the name and the year), offered by Pulp Fiction: Pulp.Fiction.CE.1994.INTERNAL.DVDRip.XviD-SChiZO '
                      'played the right title (its video file Pulp.Fiction.1994.INTERNAL.DVDRip.XviD-SChiZO.avi fits; KaijuFlow made it '
                      'sure by: nzb video). Added through normal review: the tag lists of both copies of the strict rule '
                      '(tools/brain/quickcheck.py, src/parsers/searchFlow.ts) and a row in tests/fixtures/release-names/table.tsv.', text)
        none = qc.render_report(check_record(), [outcome('A'), outcome('B')])
        self.assertIn('## Allowed words offered\n\nNone.', none)

# --------------------------------------------------------------------------- the check's run, in a fake world

T0 = datetime.datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
DRAWN = [['movie', 'tt0000001', 'First Film', 'popular-film', '2020-05-01'],
         ['movie', 'tt0000002', 'Second Film', 'popular-film', '2018-02-02'],
         ['movie', 'tt0000003', 'Old Film', 'rare-film', '1984-01-01'],
         ['series', 'tt0000004:1:2', 'New Show S01E02', 'popular-episode', '2025-01-08'],
         ['series', 'tt0000005:2:1', 'Old Show S02E01', 'rare-episode', '2001-09-01']]
BEST = {'name': 'KaijuFlow', 'title': 'KaijuFlow ▶ Best', 'url': 'http://localhost:1338/u/play/stream/ultimate-fallback?x=1'}


ALTMOUNT = {'image': 'ghcr.io/kipsilabs/altmount:v0.4.0', 'id': 'sha256:5e1f'}  # AltMount's test copy (#287)


class CheckWorld:
    """The real world as a quick check meets it, faked: a clock that moves only while something takes time, the draw, the
    reset, the stand-in, KaijuFlow's list and the press of Best (through brainrun.check_visit_answer, as RealIO does), and
    the two containers' logs. `plays` maps a title's id to what its press gives: a release name (video, a `played` line),
    None (no video, every Source's check failed), or 'limit' (KaijuFlow's log says the indexer's limit was reached).
    A stopped container answers no list (status None), as a stopped copy refuses the connection."""

    def __init__(self, plays=None, problems=(), drawn=DRAWN, refuse_draw=None, other_names=None):
        self.clock, self.calls, self.problems, self.drawn = T0, [], list(problems), [list(t) for t in drawn]
        # by default each press plays the right release: a film's name and year, an episode's show and episode
        self.plays = {t[1]: t[2].replace(' ', '.') + ('.' + t[4][:4] if t[0] == 'movie' else '') + '.1080p.WEB' for t in drawn}
        self.plays.update(plays or {})
        self.log, self.up, self.store, self.marker_ = [], True, None, None
        self.refuse_draw, self.other_names, self.marker_on_stop = refuse_draw, other_names or {}, None

    def takes(self, s):
        self.clock += datetime.timedelta(seconds=s)

    def usenet(self):  # this world has no news server: the live Clues' connection is refused (#284)
        raise OSError('no news server in this world')

    def start_diagnosing_agent(self, cases, ids, run_dir):  # the agent a check starts on its unproved failures (#287)
        self.calls.append(('diagnosing agent', list(ids)))
        return 'herdr agent diag-test'

    def alert(self, line):
        self.calls.append(('alert', line))

    def tracker(self):  # the issue tracker a check files its fix tickets with (#288): none open, each filing noted
        world = self

        class Tracker:
            def find(self, text):
                return None

            def file(self, title, body):
                world.calls.append(('file ticket', title))
                return '#401', None
        return Tracker()

    def now(self):
        return self.clock

    def sleep(self, s):
        self.calls.append(('sleep', s))
        self.takes(s)

    def preflight(self, mode, seen=None):
        self.calls.append(('preflight', mode))
        if seen is not None:
            seen.update(load=0.2, machine={'power': 'ac', 'cpu_probe_ms': 900})
        return list(self.problems)

    def snapshot(self):
        return {'kaijuflow': {'ultimateFallback.whenToResolve': 'on-results', 'altmountApiKey': '***'}}

    def git_info(self):
        return 'head1', False

    def image_label(self):
        return 'img1'

    def altmount_image(self):
        return dict(ALTMOUNT)

    def draw_titles(self, check, kinds):
        self.calls.append(('draw', check.split(' ')[0], dict(kinds)))
        if self.refuse_draw:  # as draw.draw refuses a kind TMDB has no new title of
            raise self.refuse_draw
        return [list(t) for t in self.drawn]

    def reset(self, sides, log=print):
        self.calls.append(('reset', tuple(sides)))
        self.takes(20)

    def open_check_store(self, run_dir):
        self.store = os.path.join(run_dir + '-store')
        self.calls.append(('open-store',))

    def close_check_store(self):
        self.calls.append(('close-store',))
        self.store = None
        self.marker_ = None  # the marker goes with the store

    def start_standin(self, logpath, mode='replay', wait=True):
        if self.store is None:  # the real stand-in has no store to record into
            raise RuntimeError('indexer stand-in did not start')
        self.calls.append(('standin', mode))
        world = self

        class Handle:
            def stop(self):
                world.calls.append(('standin-stop',))
                if world.marker_on_stop:  # a late request hit the limit before the stand-in stopped
                    world.marker_ = world.marker_on_stop
        return Handle()

    def marker(self):
        return self.marker_

    def stop_all(self):
        self.calls.append(('stop-all',))
        self.up = False

    def check_visit(self, kind, vid, pause_s):
        self.calls.append(('visit', vid))
        t_list = br.iso(self.clock)
        if not self.up:
            return brainrun.check_visit_answer((None, {'error': 'connection refused'}, b'', {'ready': 0.0}), None)
        self.takes(2.0)
        release = self.plays.get(vid)
        if release == 'indexer down':  # as KaijuFlow logs a search the indexer did not answer, and the empty list after it
            for line in ({'step': 'indexer_page', 'source': 'NinjaCentral', 'ok': False, 'page': 1},
                         {'step': 'list_filter', 'ok': True, 'results': 0, 'kept': 0}):
                self.log.append(f'{t_list} [KF-STEP] ' + json.dumps({**line, 'ms': 1, 'ref': vid, 't': t_list}))
            return brainrun.check_visit_answer((200, {}, b'{"streams": []}', {'ready': 2.0, 'total': 2.0}), None, pause_s, self.sleep)
        body = json.dumps({'streams': [BEST, {'name': 'KaijuFlow', 'title': 'A'}, {'name': 'KaijuFlow', 'title': 'B'}]}).encode()
        got = (200, {}, body, {'ready': 2.0, 'total': 2.0})

        def press(stream):
            self.takes(3.0)
            t = br.iso(self.clock)
            if release == 'limit':
                self.log.append(f'{t} Failed to download NZB from ninjacentral: 429 Too Many Requests')
                return {'plays': False, 'first_byte_s': 3.0, 'note': 'failure video'}
            if release is None:
                for rel in ('A', 'B'):
                    self.log.append(f'{t} [KF-STEP] ' + json.dumps({'step': 'play_check', 'ref': vid, 'title': rel, 'ok': False,
                                                                    'status': 'blocked', 't': t}))
                return {'plays': False, 'first_byte_s': 3.0, 'note': 'failure video'}
            self.log.append(f'{t} [KF-STEP] ' + json.dumps({'step': 'play_check', 'ref': vid, 'title': release, 'ok': True,
                                                            'status': 'verified', 't': t_list}))
            self.log.append(f'{t} [KF-STEP] ' + json.dumps({'step': 'played', 'title': release, 't': t}))
            return {'plays': True, 'first_byte_s': 3.0, 'note': None}
        return brainrun.check_visit_answer(got, press, pause_s, self.sleep)

    def logs(self, container, since):
        if container not in testbed.TEST_CONTAINERS:
            raise ValueError('not a test container: ' + container)
        return '\n'.join(line for line in self.log if line[:24] >= since[:24]) if container == brainrun.KF_CONTAINER else ''

    def secret_values(self):
        return []

    def check_answers(self):  # the check's store holds no answer here (FailedPlayWorld, test_evidence.py, fills one)
        return None

    def standin_lines(self):
        return []

    def altmount_file(self, path):
        return None

    def title_names(self, title):
        if title[1] in self.other_names and self.other_names[title[1]] is None:
            raise pool.TmdbError('TMDB answered HTTP 503 to /find/' + title[1])  # as quickcheck.tmdb_names does
        return list(self.other_names.get(title[1], []))


def check_cfg(case):
    root = tempdir(case)
    return dict(name='quick-check', runs_root=root, test_dir=os.path.join(root, 'td'), indexers=['ninjacentral'], browse_pause=5,
                settle=3, ledger=os.path.join(root, 'titles-played.json'), user_id='u', cases=os.path.join(tempdir(case), 'cases'))


def run_check(cfg, world):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = brainrun.quick_check_command(cfg, world)
    return code, out.getvalue()


class QuickCheckRunTest(unittest.TestCase):
    def test_a_check_draws_five_titles_resets_plays_each_live_once_and_passes(self):
        cfg, world = check_cfg(self), CheckWorld()
        code, out = run_check(cfg, world)
        self.assertEqual(code, 0, out)
        self.assertIn('Pass: 0 fails in 5 titles.', out)
        self.assertEqual(world.calls[:5], [('preflight', 'check'), ('draw', 'quick', qc.QUICK_KINDS), ('reset', tuple(brainrun.ALL_TESTBED)),
                                           ('open-store',), ('standin', 'record')])
        self.assertEqual([c[1] for c in world.calls if c[0] == 'visit'], [t[1] for t in DRAWN])  # each title once
        self.assertEqual(world.calls[-3:], [('standin-stop',), ('stop-all',), ('close-store',)])
        self.assertEqual(sum(qc.QUICK_KINDS.values()), 5)
        folder = os.path.join(cfg['runs_root'], '2026-11-25T100000Z-quick-check')
        meta = json.loads(read(os.path.join(folder, 'meta.json')))
        self.assertEqual((meta['kind'], meta['verdict'], meta['status'], meta['commit'], meta['start_load']),
                         ('quick check', 'pass', 'ok', 'img1', 0.2))
        self.assertNotIn('recording', meta)  # never a previous run of anything
        self.assertEqual(json.loads(read(os.path.join(folder, 'titles.json'))), DRAWN)
        raw = json.loads(read(os.path.join(folder, 'raw.json')))
        self.assertEqual([o['outcome'] for o in raw['outcomes']], ['played'] * 5)
        self.assertEqual(raw['visits'][0]['browse_pause_s'], 5)
        report = read(os.path.join(folder, 'report.md'))
        self.assertIn('5.00 s (median of 5 plays', report)  # the list's 2 s and the press's 3 s, the 5 s Browse pause left out
        index = read(os.path.join(cfg['runs_root'], 'INDEX.md'))
        self.assertIn('| quick-check | pass |', index)

    def test_the_wrong_title_played_fails_the_check_and_nothing_to_play_does_not(self):
        cfg, world = check_cfg(self), CheckWorld(plays={'tt0000002': 'Wrong.Film.1999.1080p', 'tt0000003': None})
        code, out = run_check(cfg, world)
        self.assertEqual(code, brainrun.EXIT_FAILS, out)
        self.assertIn('Fail: 1 of 5 titles failed (Second Film).', out)
        report = read(os.path.join(cfg['runs_root'], '2026-11-25T100000Z-quick-check', 'report.md'))
        self.assertIn('- Old Film: every Source KaijuFlow looked at failed its check (2 of 2).\n  - A: blocked\n  - B: blocked', report)
        self.assertIn('### Quick check fail: Second Film', report)
        self.assertIn('| quick-check | FAIL |', read(os.path.join(cfg['runs_root'], 'INDEX.md')))

    def test_the_first_limit_reached_stops_the_check_with_no_verdict(self):
        world = CheckWorld()
        world.plays['tt0000002'] = 'limit'
        cfg = check_cfg(self)
        code, out = run_check(cfg, world)
        self.assertEqual(code, brainrun.EXIT_NO_VERDICT, out)
        self.assertIn('No verdict: ninjacentral said its limit was reached', out)
        self.assertEqual([c[1] for c in world.calls if c[0] == 'visit'], ['tt0000001', 'tt0000002'])
        self.assertEqual(world.calls[-3:], [('standin-stop',), ('stop-all',), ('close-store',)])
        index = read(os.path.join(cfg['runs_root'], 'INDEX.md'))
        self.assertIn('| quick-check | NULL |', index)

    def test_a_limit_after_the_last_title_still_gives_no_verdict(self):
        world = CheckWorld()
        world.marker_on_stop = {'indexer': 'ninjacentral', 'time': '2026-11-25T10:02:00Z'}
        code, out = run_check(check_cfg(self), world)
        self.assertEqual(code, brainrun.EXIT_NO_VERDICT, out)
        self.assertIn('No verdict: ninjacentral said its limit was reached at 2026-11-25T10:02:00Z', out)

    def test_the_play_the_limit_cut_is_not_judged(self):
        world = CheckWorld()
        world.plays['tt0000002'] = 'limit'
        cfg = check_cfg(self)
        run_check(cfg, world)
        folder = os.path.join(cfg['runs_root'], '2026-11-25T100000Z-quick-check')
        raw = json.loads(read(folder, 'raw.json'))
        self.assertEqual([v['id'] for v in raw['visits']], ['tt0000001', 'tt0000002'])
        self.assertTrue(raw['visits'][1]['cut_by_limit'])
        self.assertEqual([o['id'] for o in raw['outcomes']], ['tt0000001'])
        report = read(folder, 'report.md')
        self.assertNotIn('## Fails', report)
        self.assertNotIn('Tickets to file', report)
        self.assertIn('Played 2 of 5 titles; 1 cut by the limit, not judged.', report)

    def test_a_foreign_name_reaches_the_judge_through_tmdbs_names(self):
        drawn = [list(t) for t in DRAWN]
        drawn[0] = ['movie', 'tt0211915', 'Amélie', 'foreign', '2001-04-25']
        world = CheckWorld(drawn=drawn, plays={'tt0211915': 'Le.Fabuleux.Destin.dAmelie.Poulain.2001.1080p.BluRay'},
                           other_names={'tt0211915': ["Le Fabuleux Destin d'Amélie Poulain"]})
        code, out = run_check(check_cfg(self), world)
        self.assertEqual(code, 0, out)
        world = CheckWorld(drawn=drawn, plays={'tt0211915': 'Le.Fabuleux.Destin.dAmelie.Poulain.2001.1080p.BluRay'},
                           other_names={'tt0211915': None})  # TMDB down: a fail that says so
        cfg = check_cfg(self)
        code, out = run_check(cfg, world)
        self.assertEqual(code, brainrun.EXIT_FAILS, out)
        report = read(cfg['runs_root'], '2026-11-25T100000Z-quick-check', 'report.md')
        self.assertIn("TMDB's other names of the title could not be read", report)

    def test_a_refused_draw_ends_the_check_with_its_sentence_not_a_traceback(self):
        cfg = check_cfg(self)
        world = CheckWorld(refuse_draw=draw.Refused('TMDB gave no new rare-film title in 8 pages: nothing was drawn.'))
        code, out = run_check(cfg, world)
        self.assertEqual(code, 1, out)
        self.assertIn('No verdict: the check failed: TMDB gave no new rare-film title in 8 pages', out)
        self.assertNotIn(('reset', tuple(brainrun.ALL_TESTBED)), world.calls)
        self.assertIn('| quick-check | failed |', read(cfg['runs_root'], 'INDEX.md'))

    def test_an_indexer_that_does_not_answer_fails_the_check(self):
        world = CheckWorld()
        world.plays['tt0000003'] = 'indexer down'
        cfg = check_cfg(self)
        code, out = run_check(cfg, world)
        self.assertEqual(code, brainrun.EXIT_FAILS, out)
        report = read(cfg['runs_root'], '2026-11-25T100000Z-quick-check', 'report.md')
        self.assertIn('the list held no Source, and NinjaCentral did not answer its search (page 1)', report)

    def test_tmdb_failing_the_draw_ends_the_check_with_its_sentence(self):
        cfg = check_cfg(self)
        code, out = run_check(cfg, CheckWorld(refuse_draw=pool.TmdbError('TMDB refused the key of KaijuFlow\'s test copy (HTTP 401), so no ID can be checked.')))
        self.assertEqual(code, 1, out)
        self.assertIn('No verdict: the check failed: TMDB refused the key', out)
        self.assertNotIn('Traceback', out)

    def test_a_stand_in_marker_stops_the_check_too(self):
        world = CheckWorld()
        original = world.check_visit

        def visit_then_mark(kind, vid, pause_s):
            got = original(kind, vid, pause_s)
            world.marker_ = {'indexer': 'ninjacentral', 'time': br.iso(world.clock)}
            return got
        world.check_visit = visit_then_mark
        code, out = run_check(check_cfg(self), world)
        self.assertEqual(code, brainrun.EXIT_NO_VERDICT, out)
        self.assertEqual(len([c for c in world.calls if c[0] == 'visit']), 1)

    def test_a_refused_preflight_draws_nothing_and_writes_no_folder(self):
        cfg, world = check_cfg(self), CheckWorld(problems=['The machine is busy.'])
        code, out = run_check(cfg, world)
        self.assertEqual((code, out), (1, 'The machine is busy.\n'))
        self.assertEqual(world.calls, [('preflight', 'check')])
        self.assertFalse(os.path.exists(os.path.join(cfg['runs_root'], 'INDEX.md')))

    def test_a_stop_keeps_the_titles_played_and_gives_no_verdict(self):
        world = CheckWorld()
        original = world.check_visit
        n = []

        def stop_on_third(kind, vid, pause_s):
            n.append(vid)
            if len(n) == 3:
                raise KeyboardInterrupt
            return original(kind, vid, pause_s)
        world.check_visit = stop_on_third
        cfg = check_cfg(self)
        code, out = run_check(cfg, world)
        self.assertEqual(code, brainrun.EXIT_INTERRUPTED, out)
        self.assertIn('No verdict: the check was stopped', out)
        self.assertIn('2 of 5 plays had finished, and it stopped during the next one (KaijuFlow, cold, Old Film)', out)
        raw = json.loads(read(os.path.join(cfg['runs_root'], '2026-11-25T100000Z-quick-check', 'raw.json')))
        self.assertEqual(len(raw['outcomes']), 2)


class RealPartsTest(unittest.TestCase):
    """The parts of RealIO a check adds, and main's wiring, with only HTTP, TMDB and Docker faked."""

    def setUp(self):
        self.root = tempdir(self)
        self.cfg = dict(test_dir=os.path.join(self.root, 'td'), user_id='u', ledger=os.path.join(self.root, 'titles-played.json'))

    def test_the_draw_writes_the_ledger_before_any_title_is_played(self):
        with mock.patch.object(brainrun.pool, 'tmdb_getter', return_value=lambda path: (200, {})), \
                mock.patch.object(brainrun.draw, 'draw', return_value=[list(t) for t in DRAWN[:2]]) as drew, \
                contextlib.redirect_stdout(io.StringIO()):
            titles = brainrun.RealIO(self.cfg).draw_titles('quick check x', qc.QUICK_KINDS)
        self.assertEqual(titles, DRAWN[:2])
        self.assertEqual(drew.call_args.args[2], qc.QUICK_KINDS)
        self.assertEqual([e['id'] for e in draw.read_ledger(self.cfg['ledger'])], ['tt0000001', 'tt0000002'])

    def test_the_check_store_is_the_test_folders_own_and_goes_after_the_check(self):
        real = brainrun.RealIO(self.cfg)
        real.open_check_store(os.path.join(self.root, '2026-11-25T100000Z-quick-check'))
        store = self.cfg['store']
        self.assertEqual((os.path.dirname(store), self.cfg['listname']), (os.path.join(self.cfg['test_dir'], 'check-answers'), 'check'))
        os.makedirs(os.path.join(store, 'check', 'ninjacentral'))
        real.close_check_store()
        self.assertFalse(os.path.exists(store))
        self.cfg['store'] = os.path.join(self.root, 'not-a-check-store')  # never a store the check did not make
        os.makedirs(self.cfg['store'])
        real.close_check_store()
        self.assertTrue(os.path.isdir(self.cfg['store']))

    def test_a_visit_asks_the_list_then_presses_best_waiting_up_to_300_s(self):
        body = json.dumps({'streams': [BEST, {'name': 'KaijuFlow', 'title': 'A'}]}).encode()
        pressed = []
        with mock.patch.object(common, 'get', return_value=(200, {}, body, {'ready': 1.0, 'total': 1.2})) as get, \
                mock.patch.object(common, 'play_stream', side_effect=lambda st, timeout: pressed.append((st, timeout)) or
                                  {'plays': True, 'first_byte_s': 2.0}):
            real = brainrun.RealIO(self.cfg)
            real.sleep = lambda s: None
            out = real.check_visit('movie', 'tt0000001', 5)
        self.assertEqual(get.call_args.args[0], 'http://localhost:1338/u/stream/movie/tt0000001.json')
        self.assertEqual(pressed, [(BEST, qc.PLAY_TIMEOUT_S)])
        self.assertEqual((out['sources'], out['best'], out['browse_pause_s'], out['list_s']), (1, True, 5, 1.2))

    def test_main_runs_the_quick_check_with_its_name_ledger_and_key_file_indexers(self):
        td = make_copies(self)
        seen = {}

        def fake_check(cfg, world):
            seen.update(cfg)
            return 0
        with mock.patch.object(brainrun, 'quick_check_command', side_effect=fake_check):
            code = brainrun.main(['check', '--quick', '--test-dir', td, '--runs-root', self.root])
        self.assertEqual(code, 0)
        self.assertEqual((seen['name'], seen['ledger'], seen['indexers']),
                         ('quick-check', os.path.join(self.root, 'titles-played.json'), ['drunkenslug', 'ninjacentral']))
        self.assertFalse(seen['tickets_dry_run'])  # a check files its fix tickets (#288) ...
        with mock.patch.object(brainrun, 'quick_check_command', side_effect=fake_check):
            brainrun.main(['check', '--quick', '--test-dir', td, '--runs-root', self.root, '--tickets-dry-run'])
        self.assertTrue(seen['tickets_dry_run'])  # ... unless it is a dry run
        self.assertIsInstance(brainrun.RealIO(self.cfg).tracker(), fixing.GitHub)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            brainrun.main(['check', '--quick', '--run', self.root])


# --------------------------------------------------------------------------- the preflight of a check, on fixture test copies

class CheckPreflightTest(unittest.TestCase):
    def setUp(self):
        self.td = make_copies(self)
        self.root = tempdir(self)
        self.cfg = make_cfg(self.td, runs_root=self.root)
        self.limits({'ninjacentral': (2000, 450), 'drunkenslug': (1000, 300)})

    def limits(self, entries):
        put_limits(os.path.join(self.td, 'indexers.json'), entries)

    def used(self, downloads):
        """A record folder whose stand-in log asked the real ninjacentral `downloads` NZBs just now."""
        logs = os.path.join(self.root, '2026-11-25T090000Z-x-record', 'logs')
        os.makedirs(logs)
        t = int(datetime.datetime.now(UTC).timestamp() * 1000)
        with open(os.path.join(logs, 'standin.log'), 'w') as f:
            f.write(''.join(f'RECORD ninjacentral nzb/abc{i} from=1.2.3.4 t={t}\n' for i in range(downloads)))

    def test_a_right_setup_passes_a_check_with_no_recording(self):
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertEqual(code, 0, text)
        self.assertIn("Setup is right for a check", text)
        self.assertIn("idle (1-minute load below 1.00)", text)
        self.assertIn("the indexer allowance holds the check's requests", text)

    def test_a_check_needs_the_key_file_and_an_idle_machine(self):
        os.chmod(os.path.join(self.td, 'indexers.json'), 0o644)
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg, load=2.5))
        self.assertEqual(code, 1, text)
        self.assertIn('can be read by others', text)
        self.assertIn('load average is 2.50', text)
        self.assertNotIn(SECRET, text)

    def test_too_little_allowance_left_refuses_a_check(self):
        self.limits({'ninjacentral': (2000, 450), 'drunkenslug': (1000, 0)})
        self.used(450 - 149)  # 149 downloads left between the two; 5 titles may need 150
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertEqual(code, 1, text)
        self.assertIn('The indexers have 149 downloads left today between them (drunkenslug 0, ninjacentral 149), '
                      'and the check may need 150', text)

    def test_the_walks_grabs_are_shared_so_downloads_count_once_across_the_indexers(self):
        # owner's pick on #286, 2026-11-24: the Walk grabs at most 30 per title in all, from whichever indexer has the
        # Source, so two indexers together must hold the check's downloads; neither needs all of them alone
        self.limits({'ninjacentral': (2000, 450), 'drunkenslug': (1000, 100)})
        self.used(450 - 60)  # ninjacentral 60 left, drunkenslug 100: 160 between them, 150 needed
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertEqual(code, 0, text)

    def test_searches_still_count_per_indexer(self):
        # every title is searched on every indexer, so each needs the check's searches itself
        self.limits({'ninjacentral': (2000, 450), 'drunkenslug': (59, 100)})
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertEqual(code, 1, text)
        self.assertIn('drunkenslug has 59 searches left today, and the check may need 60', text)

    def test_a_drill_down_asks_for_one_titles_allowance(self):
        self.limits({'ninjacentral': (2000, 450), 'drunkenslug': (1000, 0)})
        self.used(450 - 30)  # 30 downloads left: one title may need 30, five 150
        code, text = run_command('check', dict(self.cfg, check_titles=1), FakeWorld(self.cfg))
        self.assertEqual(code, 0, text)
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertIn('The indexers have 30 downloads left today between them (drunkenslug 0, ninjacentral 30), '
                      'and the check may need 150', text)

    def test_an_indexer_without_limits_in_the_key_file_refuses_a_check_and_names_the_command(self):
        make_copies(self, base=os.path.dirname(self.td))  # a key file with no limits in it
        self.limits({'ninjacentral': (2000, 450)})
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertEqual(code, 1, text)
        self.assertIn('The key file has no daily limits for drunkenslug, so its allowance cannot be checked: add them '
                      '(python3 -I tools/brain/testbed.py indexer add drunkenslug --stash <entry> --searches <n> --downloads <n>)', text)
        self.assertNotIn(SECRET, text)

    def test_a_limits_file_beside_the_key_file_is_not_read(self):
        make_copies(self, base=os.path.dirname(self.td))
        with open(os.path.join(self.td, 'limits.json'), 'w') as f:
            json.dump({'indexers': {s: {'search_per_day': 2000, 'download_per_day': 450} for s in ('ninjacentral', 'drunkenslug')}}, f)
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertEqual(code, 1, text)
        self.assertIn('The key file', text)


class IndexerRuleTest(unittest.TestCase):
    """The expected settings' rule for every indexer (`indexers[*]`, #270), tried on a per-indexer setting (`timeout`)."""

    def test_the_committed_file_holds_on_search_and_no_search_method(self):
        wanted = {}
        for entry in brainrun.load_expected_settings():
            wanted.update(entry['settings'])
        self.assertEqual(wanted['ultimateFallback.whenToResolve'], 'on-results')  # "On Search" in the settings UI
        self.assertEqual([k for k in wanted if 'SearchMethod' in k], [])  # Kaiju Search has nothing to set (#285)

    def test_an_indexer_with_another_value_is_named(self):
        expected = [{'copies': ['kaijuflow'], 'settings': {'indexers[*].timeout': 15}}]
        have = {'kaijuflow': {'indexers[NinjaCentral].name': 'NinjaCentral', 'indexers[NinjaCentral].timeout': 15,
                              'indexers[altHUB].name': 'altHUB', 'indexers[altHUB].timeout': 8}}
        self.assertEqual(brainrun.setting_differences(expected, have), [
            'KaijuFlow has indexers[altHUB].timeout set to 8, but the expected settings file says 15'
            ": change the test copy's config, or the file if the copy's value is the intended one."])
        have['kaijuflow']['indexers[altHUB].timeout'] = 15
        self.assertEqual(brainrun.setting_differences(expected, have), [])

    def test_the_preflight_refuses_a_copy_whose_indexers_lack_the_setting(self):
        td = make_copies(self)
        cfg = make_cfg(td)
        path = os.path.join(td, 'config', 'config.json')
        with open(path) as f:
            config = json.load(f)
        del config['indexers'][0]['timeout']
        with open(path, 'w') as f:
            json.dump(config, f)
        path = os.path.join(os.path.dirname(td), 'expected-settings.json')
        with open(cfg['expected_settings']) as f:
            data = json.load(f)
        data['expected'].append({'copies': ['kaijuflow'], 'settings': {'indexers[*].timeout': 15}})
        with open(path, 'w') as f:
            json.dump(data, f)
        problems = brainrun.preflight('record', cfg, FakeWorld(cfg))
        self.assertEqual([p.split(',')[0] for p in problems if '.timeout' in p], ['KaijuFlow has no indexers[NinjaCentral].timeout setting'])

    def test_apply_writes_the_setting_into_every_indexer(self):
        td = make_copies(self)
        path = os.path.join(td, 'config', 'config.json')
        with open(path) as f:
            config = json.load(f)
        for ix in config['indexers']:
            ix.update(timeout=8, maxPages=2)
        with open(path, 'w') as f:
            json.dump(config, f)
        expected = os.path.join(os.path.dirname(td), 'e.json')
        with open(expected, 'w') as f:
            json.dump({'expected': [{'copies': ['kaijuflow'], 'settings': {'indexers[*].timeout': 15}}]}, f)
        lines = testbed.apply_expected(td, 'kaijuflow', expected, stamp='20261125T100000Z')
        self.assertIn('KaijuFlow: 3 settings changed in config/config.json.', lines)
        with open(os.path.join(td, 'config', 'config.json')) as f:
            config = json.load(f)
        self.assertEqual([ix['timeout'] for ix in config['indexers']], [15] * 3)
        self.assertEqual([ix['maxPages'] for ix in config['indexers']], [2] * 3)  # nothing else touched
        self.assertEqual(testbed.apply_expected(td, 'kaijuflow', expected), [
            'KaijuFlow: nothing changed; config/config.json already holds the expected settings.'])


if __name__ == '__main__':
    unittest.main()
