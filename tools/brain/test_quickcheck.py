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

import brainreport as br
import brainrun
import quickcheck as qc
import testbed
from test_preflight import FakeWorld, make_cfg, run_command
from test_settings import SECRET, make_copies, tempdir

HERE = os.path.dirname(os.path.abspath(__file__))
UTC = datetime.timezone.utc


def names():
    """The captured release names (fixtures/2026-11-24-release-names/), by a short key."""
    with open(os.path.join(HERE, 'fixtures', '2026-11-24-release-names', 'names.txt')) as f:
        lines = f.read().splitlines()
    keys = ['inside out 2', 'pushing daisies e09', 'avatar', 'spider-verse', 'hitcher', '7th time loop', 'space 1999 e04',
            'pushing daisies pack', 'avatar german', 'misanthrope e02']
    return dict(zip(keys, lines))


def read(*parts):
    with open(os.path.join(*parts)) as f:
        return f.read()


def step_lines(name):
    """KaijuFlow's step lines of one captured Best press (fixtures/2026-11-23-step-lines/)."""
    with open(os.path.join(HERE, 'fixtures', '2026-11-23-step-lines', name)) as f:
        return br.parse_step_lines(f.read())


FILM = ['movie', 'tt1000010', 'KaijuFlow PlayTime', 'popular-film', '2026-03-01']


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
        ok, why = self.ok('inside out 2', ['movie', 'tt2096673', 'Inside Out', 'popular-film', '2015-06-17'])
        self.assertEqual((ok, why), (False, 'its year is 2024, not 2015'))  # the sequel is the wrong film

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

    def test_other_episode_markers(self):
        title = ['series', 'tt1:3:7', 'Some Show S03E07', 'popular-episode', '2024-05-01']
        for release, right in (('Some.Show.3x07.720p.HDTV', True), ('Some.Show.S03E06-E08.1080p.WEB', True),
                               ('Some.Show.S03E06E07.1080p', True), ('Some.Show.S01-S04.COMPLETE.1080p', True),
                               ('Some.Show.Season.3.1080p', True), ('Some.Show.1080p.WEB', False)):
            self.assertEqual(qc.right_title(release, title)[0], right, release)

    def test_a_daily_show_is_known_by_its_air_date(self):
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

    def test_original_and_alternative_names_from_the_imdb_id(self):
        asked = []

        def get(path):
            asked.append(path)
            if path.startswith('/find/tt0499549'):
                return 200, {'movie_results': [{'id': 19995, 'title': 'Avatar', 'original_title': 'Avatar'}], 'tv_results': []}
            if path == '/movie/19995/alternative_titles':
                return 200, {'titles': [{'title': 'Avatar: Aufbruch nach Pandora'}, {'title': 'Avatar'}]}
            return 404, None
        self.assertEqual(qc.tmdb_names(get, FILM[:1] + ['tt0499549'] + FILM[2:]), ['Avatar', 'Avatar: Aufbruch nach Pandora'])
        self.assertEqual(asked, ['/find/tt0499549?external_source=imdb_id', '/movie/19995/alternative_titles'])

    def test_an_episode_is_looked_up_by_its_show_and_unknown_gives_none(self):
        def get(path):
            if path.startswith('/find/tt0925266'):
                return 200, {'movie_results': [], 'tv_results': [{'id': 1, 'name': 'Pushing Daisies', 'original_name': 'Pushing Daisies'}]}
            if path == '/tv/1/alternative_titles':
                return 200, {'results': [{'title': 'Pushing Up Daisies'}]}
            return 200, {'movie_results': [], 'tv_results': []}
        self.assertEqual(qc.tmdb_names(get, ['series', 'tt0925266:1:9', 'Pushing Daisies S01E09', 'rare-episode', '2008-12-03']),
                         ['Pushing Daisies', 'Pushing Up Daisies'])
        self.assertEqual(qc.tmdb_names(get, ['movie', 'tt9', 'X', 'popular-film', '2000-01-01']), [])


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
        o = qc.judge(visit(steps=step_lines('kaijuflow-head-start-refused-first.txt')))
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
        self.assertIn('its year is 2024, not 2015', o['why'])

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
        empty = qc.judge(visit(sources=0, best=False))
        self.assertEqual((empty['outcome'], empty['why']), ('nothing to play', 'the list held no Source'))
        dead = [{'step': 'play_check', 'title': f'Rel.{i}.2026', 'ok': False, 'status': 'blocked'} for i in range(3)]
        o = qc.judge(visit(sources=3, plays=False, steps=dead))
        self.assertEqual((o['outcome'], o['why']), ('nothing to play', 'every Source KaijuFlow looked at failed its check (3 of 3)'))
        o = qc.judge(visit(sources=5, plays=False, steps=dead))  # two Sources never reached: not shown that none would play
        self.assertEqual((o['outcome'], o['why']), ('fail', 'no video (failure video), and only 3 of 5 Sources were checked'))

    def test_a_list_that_did_not_come_or_has_no_best_entry_is_a_fail(self):
        o = qc.judge(visit(status=None, sources=0, best=False, note='timed out'))
        self.assertEqual((o['outcome'], o['why']), ('fail', "KaijuFlow's list did not come: timed out"))
        o = qc.judge(visit(best=False))
        self.assertEqual((o['outcome'], o['why']), ('fail', 'the list had no Best entry to press'))

    def test_visit_steps_keep_the_visits_own_play_lines(self):
        steps = step_lines('kaijuflow-best-dead-first.txt')
        kept = qc.visit_steps(steps + [{'step': 'played', 'ref': 'tt999', 'title': 'Other', 't': '2026-11-23T20:35:13.000Z'}],
                              'tt1000010', '2026-11-23T20:35:11.000Z')
        self.assertEqual([s['step'] for s in kept], ['play_check', 'play_check', 'play_check', 'played'])
        self.assertEqual(qc.visit_steps(steps, 'tt1000010', '2026-11-23T20:36:00.000Z'), [])  # lines before the visit


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


# --------------------------------------------------------------------------- the check's run, in a fake world

T0 = datetime.datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
DRAWN = [['movie', 'tt0000001', 'First Film', 'popular-film', '2020-05-01'],
         ['movie', 'tt0000002', 'Second Film', 'popular-film', '2018-02-02'],
         ['movie', 'tt0000003', 'Old Film', 'rare-film', '1984-01-01'],
         ['series', 'tt0000004:1:2', 'New Show S01E02', 'popular-episode', '2025-01-08'],
         ['series', 'tt0000005:2:1', 'Old Show S02E01', 'rare-episode', '2001-09-01']]
BEST = {'name': 'KaijuFlow', 'title': 'KaijuFlow ▶ Best', 'url': 'http://localhost:1338/u/play/stream/ultimate-fallback?x=1'}


class CheckWorld:
    """The real world as a quick check meets it, faked: a clock that moves only while something takes time, the draw, the
    reset, the stand-in, KaijuFlow's list and the press of Best (through brainrun.check_visit_answer, as RealIO does), and
    the two containers' logs. `plays` maps a title's id to what its press gives: a release name (video, a `played` line),
    None (no video, every Source's check failed), or 'limit' (KaijuFlow's log says the indexer's limit was reached).
    A stopped container answers no list (status None), as a stopped copy refuses the connection."""

    def __init__(self, plays=None, problems=(), drawn=DRAWN):
        self.clock, self.calls, self.problems, self.drawn = T0, [], list(problems), [list(t) for t in drawn]
        # by default each press plays the right release: a film's name and year, an episode's show and episode
        self.plays = {t[1]: t[2].replace(' ', '.') + ('.' + t[4][:4] if t[0] == 'movie' else '') + '.1080p.WEB' for t in drawn}
        self.plays.update(plays or {})
        self.log, self.up, self.store, self.marker_ = [], True, None, None

    def takes(self, s):
        self.clock += datetime.timedelta(seconds=s)

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

    def draw_titles(self, check, kinds):
        self.calls.append(('draw', check.split(' ')[0], dict(kinds)))
        return [list(t) for t in self.drawn]

    def reset(self, sides, log=print):
        self.calls.append(('reset', tuple(sides)))
        self.takes(20)

    def open_check_store(self, run_dir):
        self.store = os.path.join(run_dir + '-store')
        self.calls.append(('open-store',))

    def close_check_store(self):
        self.calls.append(('close-store',))

    def start_standin(self, logpath, mode='replay', wait=True):
        self.calls.append(('standin', mode))
        world = self

        class Handle:
            def stop(self):
                world.calls.append(('standin-stop',))
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
        body = json.dumps({'streams': [BEST, {'name': 'KaijuFlow', 'title': 'A'}, {'name': 'KaijuFlow', 'title': 'B'}]}).encode()
        got = (200, {}, body, {'ready': 2.0, 'total': 2.0})
        release = self.plays.get(vid)

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

    def title_names(self, title):
        return []


def check_cfg(case):
    root = tempdir(case)
    return dict(name='quick-check', runs_root=root, test_dir=os.path.join(root, 'td'), indexers=['ninjacentral'], browse_pause=5,
                settle=3, ledger=os.path.join(root, 'titles-played.json'), user_id='u')


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
        self.assertEqual(world.calls[:5], [('preflight', 'check'), ('draw', 'quick', qc.KINDS), ('reset', tuple(brainrun.ALL_TESTBED)),
                                           ('open-store',), ('standin', 'record')])
        self.assertEqual([c[1] for c in world.calls if c[0] == 'visit'], [t[1] for t in DRAWN])  # each title once
        self.assertEqual(world.calls[-3:], [('standin-stop',), ('stop-all',), ('close-store',)])
        self.assertEqual(sum(qc.KINDS.values()), 5)
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


# --------------------------------------------------------------------------- the preflight of a check, on fixture test copies

class CheckPreflightTest(unittest.TestCase):
    def setUp(self):
        self.td = make_copies(self)
        self.root = tempdir(self)
        self.cfg = make_cfg(self.td, runs_root=self.root)
        self.limits({'ninjacentral': (2000, 450), 'drunkenslug': (1000, 300)})

    def limits(self, entries):
        with open(os.path.join(self.td, 'limits.json'), 'w') as f:
            json.dump({'indexers': {slug: {'search_per_day': s, 'download_per_day': d, 'reset': 'rolling-24h'}
                                    for slug, (s, d) in entries.items()}}, f)

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
        self.used(450 - 149)  # 149 downloads left; 5 titles may need 150
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertEqual(code, 1, text)
        self.assertIn('ninjacentral has 149 downloads left today, and the check may need 150', text)

    def test_a_missing_limits_file_or_entry_refuses_a_check(self):
        self.limits({'ninjacentral': (2000, 450)})
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertIn('The limits file has no entry for drunkenslug', text)
        os.remove(os.path.join(self.td, 'limits.json'))
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg))
        self.assertEqual(code, 1)
        self.assertIn('There is no limits file yet', text)


class SearchMethodRuleTest(unittest.TestCase):
    """The expected settings' rule for every indexer (`indexers[*]`): Ultimate Text Search, the shipped default (#270)."""

    def test_the_committed_file_holds_ultimate_text_search_and_on_search(self):
        wanted = {}
        for entry in brainrun.load_expected_settings():
            wanted.update(entry['settings'])
        self.assertEqual(wanted['ultimateFallback.whenToResolve'], 'on-results')  # "On Search" in the settings UI
        for kind in ('movie', 'tv', 'animeMovie', 'animeTv'):
            self.assertEqual(wanted[f'indexers[*].{kind}SearchMethod'], ['text'])

    def test_an_indexer_on_another_search_method_is_named(self):
        expected = [{'copies': ['kaijuflow'], 'settings': {'indexers[*].movieSearchMethod': ['text']}}]
        have = {'kaijuflow': {'indexers[NinjaCentral].name': 'NinjaCentral', 'indexers[NinjaCentral].movieSearchMethod[0]': 'text',
                              'indexers[altHUB].name': 'altHUB', 'indexers[altHUB].movieSearchMethod[0]': 'imdb'}}
        self.assertEqual(brainrun.setting_differences(expected, have), [
            'KaijuFlow has indexers[altHUB].movieSearchMethod entry 1 set to "imdb", but the expected settings file says "text" '
            "(the first entry that differs): change the test copy's config, or the file if the copy's value is the intended one."])
        have['kaijuflow']['indexers[altHUB].movieSearchMethod[0]'] = 'text'
        self.assertEqual(brainrun.setting_differences(expected, have), [])

    def test_the_preflight_refuses_a_copy_whose_indexers_lack_the_search_method(self):
        td = make_copies(self)
        cfg = make_cfg(td)
        path = os.path.join(td, 'config', 'config.json')
        with open(path) as f:
            config = json.load(f)
        del config['indexers'][0]['tvSearchMethod']
        with open(path, 'w') as f:
            json.dump(config, f)
        path = os.path.join(os.path.dirname(td), 'expected-settings.json')
        with open(cfg['expected_settings']) as f:
            data = json.load(f)
        data['expected'].append({'copies': ['kaijuflow'], 'settings': {'indexers[*].tvSearchMethod': ['text']}})
        with open(path, 'w') as f:
            json.dump(data, f)
        problems = brainrun.preflight('record', cfg, FakeWorld(cfg))
        self.assertEqual([p.split(',')[0] for p in problems if 'SearchMethod' in p], ['KaijuFlow has no indexers[NinjaCentral].tvSearchMethod setting'])

    def test_apply_writes_the_method_into_every_indexer(self):
        td = make_copies(self)
        path = os.path.join(td, 'config', 'config.json')
        with open(path) as f:
            config = json.load(f)
        for ix in config['indexers']:
            ix.update(tvSearchMethod=['imdb'], movieSearchMethod=['imdb'])
        with open(path, 'w') as f:
            json.dump(config, f)
        expected = os.path.join(os.path.dirname(td), 'e.json')
        with open(expected, 'w') as f:
            json.dump({'expected': [{'copies': ['kaijuflow'], 'settings': {'indexers[*].tvSearchMethod': ['text']}}]}, f)
        lines = testbed.apply_expected(td, 'kaijuflow', expected, stamp='20261125T100000Z')
        self.assertIn('KaijuFlow: 3 settings changed in config/config.json.', lines)
        with open(os.path.join(td, 'config', 'config.json')) as f:
            config = json.load(f)
        self.assertEqual([ix['tvSearchMethod'] for ix in config['indexers']], [['text']] * 3)
        self.assertEqual([ix['movieSearchMethod'] for ix in config['indexers']], [['imdb']] * 3)  # nothing else touched
        self.assertEqual(testbed.apply_expected(td, 'kaijuflow', expected), [
            'KaijuFlow: nothing changed; config/config.json already holds the expected settings.'])


if __name__ == '__main__':
    unittest.main()
