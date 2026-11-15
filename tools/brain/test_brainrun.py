"""Tests for brainrun.py (the one command: sides x cold/warm x 2, run records, cap rule). Fakes only: no Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import datetime
import http.server
import io as io_module
import json
import os
import signal
import socket
import sqlite3
import time
import unittest
import urllib.request
from unittest import mock

import brainreport as br
import brainrun
import common
import indexer_standin
import runcheck
import test_indexer_standin as fakes
import test_preflight
from test_settings import tempdir

SECRET = 'TOPSECRET-123'
UTC = datetime.timezone.utc


def read(path):
    with open(path) as f:
        return f.read()


def refused_get():
    """What common.get() gives for an address nothing listens on: a test copy that is stopped."""
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    return common.get(f'http://127.0.0.1:{port}/stream/movie/tt1.json', timeout=5, limit=0)


class Copies:
    """Which test copies are up, the way Docker would have it: a reset starts a copy, the one-page switch and the config
    restore stop KaijuFlow's, stop_all stops every one. A visit to a side whose copy is down fails as a real one does."""

    def __init__(self, up=()):
        self.up = set(up)

    def is_up(self, side):
        return brainrun.SIDE_SERVICE[side] in self.up

    def down_answer(self, tries):
        return brainrun.visit_answer(refused_get(), tries)


class FakeIO(Copies):
    """Stands in for Docker, the stand-in and the sides. Records every call in order.

    Its clock is a clock: reading it does not move it. It moves only while something takes time, by the seconds below:
    a pause takes what it was asked for, a reset, a visit, starting the stand-in and stopping the copies take what they
    take in this world. So a time the runner reports can be worked out by hand from what the run did."""

    STANDIN_START_S, RESET_S, STOP_ALL_S = 2, 20, 5
    LIST_S, START_S, SEEKS_S = 2.0, 1.5, 0.5  # a visit whose top pick plays takes the three together: 4 s
    FAILED_PLAY_S = 10.0                      # a top pick that fails gives up after this long: the visit takes 12 s

    def __init__(self, limit_at_visit=None, marker=None, commit='c1', settings=None, fail_http_for=None, up=()):
        Copies.__init__(self, up)
        self.calls, self.clock, self.visits = [], datetime.datetime(2026, 11, 10, 18, 0, 0, tzinfo=UTC), 0
        self.limit_at_visit, self._marker, self.commit = limit_at_visit, marker, commit
        self.settings = settings or {'kaijuflow': {'healthChecks.sampleCount': 3, 'altmountApiKey': '***'}, 'uu': {}}
        self.fail_http_for = fail_http_for
        self.patched = False
        self.working = 0
        self.standin_log = []
        self.lines_per_visit = {}  # visit number -> lines the stand-in writes during that visit
        self.max_working = 0
        self.history = []  # the test NzbDAV's history slots; a Usenet Ultimate visit adds one job

    def nzbdav_history(self):
        self.calls.append(('history',))
        return {'history': {'slots': list(self.history), 'noofslots': len(self.history)}, 'status': True, 'error': None}

    def takes(self, seconds):
        self.clock += datetime.timedelta(seconds=seconds)

    def now(self):
        return self.clock

    def sleep(self, s):
        self.calls.append(('sleep', s))
        self.takes(s)

    def git_info(self):
        return 'repo-head', False

    def image_label(self):
        return self.commit

    def preflight(self, mode):
        self.calls_preflight = getattr(self, 'calls_preflight', []) + [mode]
        return list(getattr(self, 'problems', []))

    def snapshot(self):
        return json.loads(json.dumps(self.settings))

    def marker(self):
        return self._marker

    def shelve_marker(self):
        self.calls.append(('shelve-marker',))
        self._marker = None

    def setting_conflicts(self):
        return list(getattr(self, 'conflicts', []))

    def start_standin(self, logpath, mode='replay', wait=True):
        self.calls.append(('standin-start', mode, wait))
        self.takes(self.STANDIN_START_S)
        self.standin_log =['HIT ninjacentral api t=search wait_ms=0', 'MISS drunkenslug api t=search']
        with open(logpath, 'w') as f:
            f.write('\n'.join(self.standin_log) + '\n')
        io = self

        class H:
            def stop(self):
                io.calls.append(('standin-stop',))
        return H()

    def standin_line_count(self):
        return len(self.standin_log)

    def standin_lines(self):
        return list(self.standin_log)

    def reset(self, sides, log=print):
        self.calls.append(('reset', tuple(sides)))
        for side in sides:  # the two lines testbed.reset logs per test copy, the copies sharing the reset's time
            log(f'reset {side}: restored from template')
            self.takes(self.RESET_S / len(sides))
            log(f'reset {side}: up')
        self.up |= set(sides)

    def stop_all(self):
        self.calls.append(('stop-all',))
        self.takes(self.STOP_ALL_S)
        self.up.clear()

    def apply_one_page(self):
        self.patched = True
        self.up.discard('kaijuflow')  # the real one stops the copy to change its config
        self.calls.append(('patch-one-page',))
        return {'kaijuflow-1page': {'indexers[NinjaCentral].pagination': False}}

    def restore_config(self):
        self.patched = False
        self.up.discard('kaijuflow')
        self.calls.append(('restore-config',))

    ADDRESSES = {'kaijuflow-test': '10.0.0.2', 'uu-test': '10.0.0.3', 'altmount-addon-test': '10.0.0.4'}
    SIDE_IP = {'kaijuflow': '10.0.0.2', 'kaijuflow-1page': '10.0.0.2', 'uu': '10.0.0.3', 'altmount-addon': '10.0.0.4'}

    def addresses(self):
        self.calls.append(('addresses',))
        return dict(self.ADDRESSES)

    def visit_http(self, side, kind, vid, tries):
        self.visits += 1
        self.calls.append(('visit', side, vid))
        if not self.is_up(side):
            return self.down_answer(tries)
        t = int(self.clock.timestamp() * 1000) + 300  # a moment after the visit began
        self.standin_log += [f'{x} from={self.SIDE_IP[side]} t={t}' for x in self.lines_per_visit.get(self.visits, [])]
        ok = side != self.fail_http_for
        self.takes(self.LIST_S + (self.START_S + self.SEEKS_S if ok else self.FAILED_PLAY_S))
        if side == 'uu':
            self.history.insert(0, {'nzo_id': f'n{self.visits}', 'nzb_name': 'R', 'status': 'Completed', 'download_time': 4})
        return dict(list_status=200, list_s=self.LIST_S, sources=5, first_try_plays=ok, start_s=self.START_S if ok else None,
                    note=None if ok else 'failure video', seeks={'50': 0.2, '90': 0.3}, tries=[{'plays': ok}])

    def logs(self, container, since):
        t = self.clock.strftime('%Y-%m-%dT%H:%M:%S.000000000Z')
        text = ''
        if container == 'kaijuflow-test':
            ts = self.clock.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            text = (f'{t} [KF-STEP] {{"step":"nzb_fetch","source":"S","ms":100,"ok":true,"t":"{ts}","title":"R"}}\n'
                    f'{t} apikey=' + SECRET + ' fetching\n')
        if container == 'uu-test':
            text = f'{t} uu line apikey=' + SECRET + '\n'
        if self.limit_at_visit and self.visits == self.limit_at_visit and container != 'kaijuflow-test':
            text += f'{t} DrunkenSlug: API limit reached. Retry in 30 minutes\n'
        return text


def make_cfg(tmp, **kw):
    cfg = dict(name='trial', runs_root=os.path.join(tmp, 'runs'), store=os.path.join(tmp, 'store'), listname='l',
               test_dir=os.path.join(tmp, 'kaijuflow-test'), user_id='U', download_key='DK', one_page=False,
               titles=[('movie', 'tt1', 'Matrix'), ('series', 'tt2:1:1', 'Show S01E01')], tries=1, settle=0,
               indexers=['ninjacentral', 'drunkenslug'])
    cfg.update(kw)
    return cfg


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempdir(self)

    def test_full_run_layout_and_phases(self):
        io = FakeIO()
        run = brainrun.run_all(make_cfg(self.tmp), io)
        self.assertEqual(run['status'], 'ok')
        root = os.path.join(self.tmp, 'runs')
        folders = [d for d in os.listdir(root) if d != 'INDEX.md']
        self.assertEqual(len(folders), 1)
        d = os.path.join(root, folders[0])
        for f in ('settings.json', 'meta.json', 'raw.json', 'report.md', 'logs'):
            self.assertTrue(os.path.exists(os.path.join(d, f)), f)
        # 4 phases x 2 titles x 3 sides
        self.assertEqual(len(run['visits']), 4 * 2 * 3)
        self.assertEqual([(v['phase'], v['round']) for v in run['visits'][::6]],
                         [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)])
        # cold = reset of every test copy before the cold phases only; warm = no reset
        resets = [c for c in io.calls if c[0] == 'reset']
        self.assertEqual(len(resets), 2)
        self.assertEqual(set(resets[0][1]), {'nzbdav', 'altmount-addon', 'altmount-kf', 'uu', 'kaijuflow'})
        kinds = [c[0] for c in io.calls]
        self.assertLess(kinds.index('standin-start'), kinds.index('reset'))
        self.assertEqual(kinds[-2:], ['standin-stop', 'stop-all'])
        # INDEX.md row and report
        idx = read(os.path.join(root, 'INDEX.md'))
        self.assertIn(folders[0], idx)
        self.assertIn('first one', idx)
        self.assertTrue(read(os.path.join(d, 'report.md')).split('\n')[0].startswith('Across 2 titles'))
        self.assertIn('MISS', read(os.path.join(d, 'logs', 'standin.log')))
        self.assertEqual(run['standin_misses'], 1)

    def test_uu_import_is_nzbdav_job_time_and_uu_log_is_kept_scrubbed(self):
        run = brainrun.run_all(make_cfg(self.tmp), FakeIO())
        uu = [v for v in run['visits'] if v['side'] == 'uu']
        self.assertTrue(all([i['seconds'] for i in v['imports']] == [4.0] for v in uu))
        self.assertTrue(all(v['imports'] == [] for v in run['visits'] if v['side'] != 'uu'))
        log = read(os.path.join(run['dir'], 'logs', 'uu-test.log'))
        self.assertIn('uu line', log)
        self.assertNotIn(SECRET, log)

    def test_run_record_commit_comes_from_the_image_label_after_a_preflight(self):
        io = FakeIO(commit='c-from-label')
        run = brainrun.run_all(make_cfg(self.tmp), io)
        self.assertEqual(run['commit'], 'c-from-label')
        self.assertEqual(json.loads(read(os.path.join(run['dir'], 'meta.json')))['commit'], 'c-from-label')
        self.assertEqual(io.calls_preflight, ['run'])

    def test_run_record_also_keeps_the_repository_commit_as_head(self):
        run = brainrun.run_all(make_cfg(self.tmp), FakeIO(commit='c-from-label'))
        meta = json.loads(read(os.path.join(run['dir'], 'meta.json')))
        self.assertEqual((meta['commit'], meta['head']), ('c-from-label', 'repo-head'))

    def test_sides_exactly_the_named_ones(self):
        run = brainrun.run_all(make_cfg(self.tmp), FakeIO())
        self.assertEqual({v['side'] for v in run['visits']}, {'kaijuflow', 'uu', 'altmount-addon'})

    def test_rotation_and_no_two_sides_at_once(self):
        io = FakeIO()
        brainrun.run_all(make_cfg(self.tmp), io)
        visits = [c for c in io.calls if c[0] == 'visit']
        # first title: kaijuflow first, second title: next side first
        self.assertNotEqual(visits[0][1], visits[3][1])

    def test_secrets_not_in_run_folder(self):
        brainrun.run_all(make_cfg(self.tmp), FakeIO())
        for dirpath, _, files in os.walk(os.path.join(self.tmp, 'runs')):
            for f in files:
                self.assertNotIn(SECRET, read(os.path.join(dirpath, f)), f)

    def test_second_run_new_folder_diff_and_nothing_overwritten(self):
        brainrun.run_all(make_cfg(self.tmp, name='one'), FakeIO())
        root = os.path.join(self.tmp, 'runs')
        first_idx = read(os.path.join(root, 'INDEX.md'))
        io2 = FakeIO(commit='c2', settings={'kaijuflow': {'healthChecks.sampleCount': 5, 'altmountApiKey': '***'}, 'uu': {}})
        io2.clock += datetime.timedelta(minutes=5)
        run2 = brainrun.run_all(make_cfg(self.tmp, name='two'), io2)
        idx = read(os.path.join(root, 'INDEX.md'))
        self.assertTrue(idx.startswith(first_idx))
        self.assertEqual(len([d for d in os.listdir(root) if d != 'INDEX.md']), 2)
        self.assertIn('kaijuflow healthChecks.sampleCount: 3 -> 5', ' '.join(run2['changes']))
        self.assertIn('KaijuFlow code: c1 -> c2', ' '.join(run2['changes']))
        self.assertIn('healthChecks.sampleCount: 3 -> 5', idx)
        rep = read(os.path.join(root, os.path.basename(run2['dir']), 'report.md'))
        self.assertIn('healthChecks.sampleCount: 3 -> 5', rep.split('Steps every side shares')[0])

    def test_cap_rule_aborts_and_records_null(self):
        io = FakeIO(limit_at_visit=3)
        run = brainrun.run_all(make_cfg(self.tmp), io)
        self.assertEqual(run['status'], 'null')
        self.assertEqual(run['null']['indexer'], 'drunkenslug')
        self.assertEqual(io.visits, 3)  # stopped at once
        self.assertEqual([c[0] for c in io.calls][-2:], ['standin-stop', 'stop-all'])
        root = os.path.join(self.tmp, 'runs')
        idx = read(os.path.join(root, 'INDEX.md'))
        self.assertIn('NULL', idx)
        self.assertIn('drunkenslug', idx)
        d = run['dir']
        rep = read(os.path.join(d, 'report.md'))
        self.assertNotIn('median', rep.lower())
        self.assertEqual(json.load(open(os.path.join(d, 'meta.json')))['status'], 'null')

    def test_null_run_is_not_the_previous_run(self):
        brainrun.run_all(make_cfg(self.tmp, name='ok1'), FakeIO())
        brainrun.run_all(make_cfg(self.tmp, name='bad'), FakeIO(limit_at_visit=1))
        prev = br.previous_run(os.path.join(self.tmp, 'runs'), exclude='zzz')
        self.assertEqual(prev['status'], 'ok')

    def test_standin_marker_aborts_run(self):
        marker = {'indexer': 'altHUB', 'time': '2026-11-10T18:30:00Z'}  # newer than the run's start (18:00): written during it
        io = FakeIO(marker=marker)
        run = brainrun.run_all(make_cfg(self.tmp), io)
        self.assertEqual(run['status'], 'null')
        self.assertEqual(run['null']['indexer'], 'altHUB')
        self.assertEqual(io.visits, 0)
        self.assertIn('altHUB', read(os.path.join(self.tmp, 'runs', 'INDEX.md')))

    def test_a_marker_older_than_the_run_does_not_block_it(self):
        io = FakeIO(marker={'indexer': 'altHUB', 'time': '2026-11-10T09:00:00Z'})  # left by an earlier command; replay never asks an indexer
        run = brainrun.run_all(make_cfg(self.tmp), io)
        self.assertEqual(run['status'], 'ok')
        self.assertEqual(io.visits, 4 * 2 * 3)

    def test_addresses_are_read_after_each_reset_and_kept_in_the_meta(self):
        io = FakeIO()
        run = brainrun.run_all(make_cfg(self.tmp), io)
        kinds = [c[0] for c in io.calls]
        for i, k in enumerate(kinds):
            if k == 'reset':
                self.assertEqual(kinds[i + 1], 'addresses')  # containers get their address when they start
        meta = json.loads(read(os.path.join(run['dir'], 'meta.json')))
        self.assertEqual(meta['addresses'], {'kaijuflow-test': ['10.0.0.2'], 'uu-test': ['10.0.0.3'], 'altmount-addon-test': ['10.0.0.4']})

    def test_one_page_side_runs_after_main_pass_and_config_restored(self):
        io = FakeIO()
        run = brainrun.run_all(make_cfg(self.tmp, one_page=True), io)
        sides = {v['side'] for v in run['visits']}
        self.assertEqual(sides, {'kaijuflow', 'uu', 'altmount-addon', 'kaijuflow-1page'})
        self.assertFalse(io.patched)
        kinds = [c[0] for c in io.calls]
        self.assertLess(kinds.index('patch-one-page'), kinds.index('restore-config'))
        later = [c for c in io.calls[kinds.index('patch-one-page'):] if c[0] == 'visit']
        self.assertEqual({c[1] for c in later}, {'kaijuflow-1page'})
        self.assertEqual(run['facts']['one-page side'], 'yes')

    def test_failure_is_split_in_report(self):
        run = brainrun.run_all(make_cfg(self.tmp), FakeIO(fail_http_for='uu'))
        self.assertTrue(all(not v['ok'] for v in run['visits'] if v['side'] == 'uu'))
        self.assertTrue(all(br.classify_failure(v) == 'failure_video' for v in run['visits'] if v['side'] == 'uu'))

    def test_error_leaves_a_failed_record_and_still_stops_everything(self):
        io = FakeIO()
        io.visit_http = lambda *a: (_ for _ in ()).throw(RuntimeError('boom'))
        with self.assertRaises(RuntimeError):
            brainrun.run_all(make_cfg(self.tmp), io)
        self.assertEqual([c[0] for c in io.calls][-2:], ['standin-stop', 'stop-all'])
        self.assertIn('failed', read(os.path.join(self.tmp, 'runs', 'INDEX.md')))
        self.assertIsNone(br.previous_run(os.path.join(self.tmp, 'runs')))


def printed(fn, *args):
    """(what fn returned, the lines it printed)."""
    out = io_module.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(*args)
    return result, out.getvalue().splitlines()


def play_lines(lines):
    """The lines a play printed, without the ones a reset printed."""
    return [x for x in lines if ' reset ' not in x]


class WallClockTest(unittest.TestCase):
    """The run says where its wall-clock time went (#112). Every figure below is worked out by hand from FakeIO's world:
    the stand-in starts in 2 s, a reset takes 20 s, a visit whose top pick plays 4 s (list 2.0, start 1.5, seek checks 0.5),
    one whose top pick fails 12 s, stopping the copies 5 s; the pause after a play is the run's `settle`."""

    def setUp(self):
        self.tmp = tempdir(self)

    def test_every_play_line_starts_with_the_utc_time_and_how_many_plays_are_done(self):
        run, lines = printed(brainrun.run_all, make_cfg(self.tmp, settle=3), FakeIO())
        plays = play_lines(lines)
        # started 18:00:00, stand-in up at :02, reset done at :22, the first visit ends at :26
        self.assertEqual(plays[0], '18:00:26 [1/24] kaijuflow cold 1 Matrix: plays list 2.0 s start 1.5 s')
        self.assertEqual(plays[1], '18:00:33 [2/24] uu cold 1 Matrix: plays list 2.0 s start 1.5 s')  # 3 s pause, 4 s visit
        # 24 plays of 7 s and a second reset of 20 s after the first twelve; the last pause is still to come
        self.assertEqual(plays[-1], '18:03:27 [24/24] kaijuflow warm 2 Show S01E01: plays list 2.0 s start 1.5 s')
        self.assertEqual(len(plays), 24)

    def test_the_count_runs_on_into_the_one_page_side(self):
        run, lines = printed(brainrun.run_all, make_cfg(self.tmp, one_page=True), FakeIO())
        plays = play_lines(lines)
        self.assertEqual(plays[23].split()[1], '[24/32]')
        self.assertEqual(' '.join(plays[24].split()[1:6]), '[25/32] kaijuflow-1page cold 1 Matrix:')
        self.assertEqual(plays[-1].split()[1], '[32/32]')

    def test_the_lines_of_a_reset_start_the_same_way_so_the_last_line_of_the_log_always_says_how_far_the_run_is(self):
        run, lines = printed(brainrun.run_all, make_cfg(self.tmp, one_page=True, settle=3), FakeIO())
        # the first reset: five test copies, 4 s each, from 18:00:02
        self.assertEqual(lines[:3], ['18:00:02 [0/32] reset nzbdav: restored from template', '18:00:06 [0/32] reset nzbdav: up',
                                     '18:00:06 [0/32] reset altmount-addon: restored from template'])
        self.assertEqual(lines[9], '18:00:22 [0/32] reset kaijuflow: up')
        # the second one comes after the twelfth play and its pause
        at = lines.index('18:01:43 [12/32] kaijuflow warm 1 Show S01E01: plays list 2.0 s start 1.5 s')
        self.assertEqual((lines[at + 1], lines[at + 10]), ('18:01:46 [12/32] reset nzbdav: restored from template',
                                                           '18:02:06 [12/32] reset kaijuflow: up'))
        # the switch to one page resets KaijuFlow and its AltMount, 10 s each, from 18:03:30
        at = lines.index('18:03:27 [24/32] kaijuflow warm 2 Show S01E01: plays list 2.0 s start 1.5 s')
        self.assertEqual(lines[at + 1:at + 5], [
            '18:03:30 [24/32] reset kaijuflow: restored from template', '18:03:40 [24/32] reset kaijuflow: up',
            '18:03:40 [24/32] reset altmount-kf: restored from template', '18:03:50 [24/32] reset altmount-kf: up'])
        for n, line in enumerate(lines):  # no line of the run without the time and the count
            time_, count, _ = line.split(' ', 2)
            datetime.datetime.strptime(time_, '%H:%M:%S')
            self.assertEqual((count[0], count[-4:]), ('[', '/32]'), line)
            self.assertLessEqual(int(count[1:-4]), 32)

    def run_with_one_page(self, io=None, settle=3):
        run, _ = printed(brainrun.run_all, make_cfg(self.tmp, one_page=True, settle=settle), io or FakeIO())
        return run, json.loads(read(os.path.join(run['dir'], 'meta.json')))

    def time_section(self, run):
        """The report's section "Where the time went": (its sentence, {part: seconds} of its first table, its other lines)."""
        text = read(os.path.join(run['dir'], 'report.md')).split('## Where the time went\n\n')[1].split('\n## ')[0]
        lines = text.split('\n')
        table = [x for x in lines[2:lines.index('', 2)]]
        self.assertEqual(table[:2], ['| Part | Seconds | Minutes |', '|---|---|---|'])
        return lines[0], {row.split(' | ')[0][2:]: float(row.split(' | ')[1]) for row in table[2:]}, lines

    def test_the_report_says_where_the_time_went_and_the_parts_add_up_to_the_whole_run(self):
        # Usenet Ultimate's top picks fail (12 s a visit), pauses of 2 s. A round of the main sides: 4 plays of 4 s, 2 failed
        # ones of 12 s, 6 pauses = 52 s; of the one-page side: 2 plays, 2 pauses = 12 s. Main sides 2 x 20 + 4 x 52 = 248 s,
        # one-page side 2 x 20 + 4 x 12 = 88 s, 2 s for the stand-in before them, 5 s to stop the copies after: 343 s.
        run, meta = self.run_with_one_page(FakeIO(fail_http_for='uu'), settle=2)
        sentence, parts, lines = self.time_section(run)
        self.assertEqual(sentence, 'The whole run took 5.7 minutes (343.0 s), from 18:00:00 to 18:05:43 UTC: '
                                   'the main sides 4.1 minutes (248.0 s), the one-page side 1.5 minutes (88.0 s).')
        self.assertEqual(parts, {
            'Measured list and start time': 84.0,  # 24 top picks played: 2.0 s list + 1.5 s start each
            'Pauses (`--settle`)': 64.0,           # 32 plays, 2 s after each
            'Failed plays': 96.0,                  # 8 visits of 12 s
            'Resets': 80.0,                        # 4 of 20 s
            'Everything else': 19.0,               # 24 seek checks of 0.5 s, 2 s stand-in start, 5 s to stop the copies
            'The whole run': 343.0})
        whole = parts.pop('The whole run')
        self.assertLessEqual(abs(sum(parts.values()) - whole), 1.0)
        self.assertEqual(meta['timing']['parts'], {'measured_s': 84.0, 'pauses_s': 64.0, 'failed_s': 96.0, 'resets_s': 80.0,
                                                   'other_s': 19.0})
        self.assertEqual((meta['timing']['seconds'], meta['timing']['settle_s']), (343.0, 2))

    def test_no_part_of_the_time_is_counted_twice(self):
        """Held against the clock, not against the remainder: every play and every pause lies inside a round, the rounds and
        the resets lie inside the run. So the parts made of plays and pauses never exceed the rounds' own time, and the
        measured parts never exceed the whole run, so "Everything else" is never below 0. A part counted twice breaks it."""
        for kw in ({}, {'fail_http_for': 'uu'}):
            with self.subTest(**kw):
                run, meta = self.run_with_one_page(FakeIO(**kw), settle=2)
                timing, parts = meta['timing'], meta['timing']['parts']
                in_rounds = sum(r['seconds'] for r in timing['rounds'])
                in_resets = sum(r['seconds'] for r in timing['resets'])
                self.assertLessEqual(parts['measured_s'] + parts['failed_s'] + parts['pauses_s'], in_rounds)
                self.assertLessEqual(in_rounds + in_resets, timing['seconds'])
                self.assertLessEqual(sum(parts[k] for k in ('measured_s', 'pauses_s', 'failed_s', 'resets_s')), timing['seconds'])
                self.assertGreaterEqual(parts['other_s'], 0)

    def test_every_visit_keeps_its_wall_clock_time_and_a_failed_plays_time_is_in_the_per_title_table(self):
        run, _ = printed(brainrun.run_all, make_cfg(self.tmp), FakeIO(fail_http_for='uu'))
        raw = json.loads(read(os.path.join(run['dir'], 'raw.json')))['visits']
        took = {(br.parse_ts(v['t_end']) - br.parse_ts(v['t_start'])).total_seconds() for v in raw if v['side'] == 'uu'}
        self.assertEqual(took, {12.0})
        self.assertEqual({br.visit_wall_s(v) for v in raw if v['side'] != 'uu'}, {4.0})
        rows = read(os.path.join(run['dir'], 'report.md')).split('## Per title\n\n')[1].split('\n\n')[0].split('\n')[2:]
        failed = [r for r in rows if '| Usenet Ultimate |' in r]
        self.assertEqual(len(failed), 8)
        self.assertTrue(all('failure video: failure video (the whole visit took 12.0 s)' in r for r in failed), failed[0])
        self.assertFalse(any('took' in r for r in rows if r not in failed))

    def test_the_report_lists_each_round_with_its_reset(self):
        run, meta = self.run_with_one_page(FakeIO(fail_http_for='uu'), settle=2)
        _, _, lines = self.time_section(run)
        at = lines.index('| Pass | Round | Started (UTC) | Reset before it (s) | Plays | Round (s) | Round (minutes) |')
        self.assertEqual(lines[at + 2:at + 10], [
            '| Main sides | Cold 1 | 18:00:22 | 20.0 | 6 | 52.0 | 0.9 |',
            '| Main sides | Warm 1 | 18:01:14 | - | 6 | 52.0 | 0.9 |',
            '| Main sides | Cold 2 | 18:02:26 | 20.0 | 6 | 52.0 | 0.9 |',
            '| Main sides | Warm 2 | 18:03:18 | - | 6 | 52.0 | 0.9 |',
            '| One-page side | Cold 1 | 18:04:30 | 20.0 | 2 | 12.0 | 0.2 |',
            '| One-page side | Warm 1 | 18:04:42 | - | 2 | 12.0 | 0.2 |',
            '| One-page side | Cold 2 | 18:05:14 | 20.0 | 2 | 12.0 | 0.2 |',
            '| One-page side | Warm 2 | 18:05:26 | - | 2 | 12.0 | 0.2 |'])

    def test_the_meta_holds_the_time_of_the_whole_run_of_each_pass_each_round_and_each_reset(self):
        run, meta = self.run_with_one_page()
        timing = meta['timing']
        # 2 s stand-in + main sides 208 s + one-page side 96 s + 5 s to stop the copies
        self.assertEqual((meta['started'], meta['finished'], timing['seconds']),
                         ('2026-11-10T18:00:00.000Z', '2026-11-10T18:05:11.000Z', 311.0))
        self.assertEqual(timing['passes'], [
            {'name': 'main sides', 'sides': ['kaijuflow', 'uu', 'altmount-addon'],
             'start': '2026-11-10T18:00:02.000Z', 'end': '2026-11-10T18:03:30.000Z', 'seconds': 208.0},
            {'name': 'one-page side', 'sides': ['kaijuflow-1page'],
             'start': '2026-11-10T18:03:30.000Z', 'end': '2026-11-10T18:05:06.000Z', 'seconds': 96.0}])
        # a round of the main sides: 6 plays of 4 s, each followed by a 3 s pause; of the one-page side: 2 plays
        self.assertEqual([(r['pass'], r['phase'], r['round'], r['start'][11:19], r['end'][11:19], r['seconds'], r['plays'], r['pause_s'])
                          for r in timing['rounds']], [
            ('main sides', 'cold', 1, '18:00:22', '18:01:04', 42.0, 6, 18.0),
            ('main sides', 'warm', 1, '18:01:04', '18:01:46', 42.0, 6, 18.0),
            ('main sides', 'cold', 2, '18:02:06', '18:02:48', 42.0, 6, 18.0),
            ('main sides', 'warm', 2, '18:02:48', '18:03:30', 42.0, 6, 18.0),
            ('one-page side', 'cold', 1, '18:03:50', '18:04:04', 14.0, 2, 6.0),
            ('one-page side', 'warm', 1, '18:04:04', '18:04:18', 14.0, 2, 6.0),
            ('one-page side', 'cold', 2, '18:04:38', '18:04:52', 14.0, 2, 6.0),
            ('one-page side', 'warm', 2, '18:04:52', '18:05:06', 14.0, 2, 6.0)])
        # one reset before every cold round; the one-page side's first is the switch to one page, which resets too
        self.assertEqual([(r['pass'], r['phase'], r['round'], r['start'][11:19], r['seconds']) for r in timing['resets']], [
            ('main sides', 'cold', 1, '18:00:02', 20.0), ('main sides', 'cold', 2, '18:01:46', 20.0),
            ('one-page side', 'cold', 1, '18:03:30', 20.0), ('one-page side', 'cold', 2, '18:04:18', 20.0)])


class PickIO(FakeIO):
    """FakeIO whose sides list one named Source on top, kept in the visit the way common.play_stream keeps it."""

    def __init__(self, text, size, **kw):
        FakeIO.__init__(self, **kw)
        self.text, self.size = text, size

    def visit_http(self, side, kind, vid, tries):
        out = FakeIO.visit_http(self, side, kind, vid, tries)
        for t in out.get('tries', [])[:1]:
            t.update(title=self.text, size=self.size if t['plays'] else common.FAILURE_SIZE)
        return out


class TopPickRunTest(unittest.TestCase):
    """Ticket #109: the run's report names every top pick, and says which ones changed since the last run."""

    def test_the_report_names_the_top_picks_and_lists_the_ones_that_changed_since_the_last_run(self):
        tmp = tempdir(self)
        brainrun.run_all(make_cfg(tmp, name='one'), PickIO('4K REMUX Matrix 💾 95.01 GB FGT', 85436578297))
        io2 = PickIO('4K WEB-DL Matrix 💾 21.9 GB NEW', 22300000000)
        io2.clock += datetime.timedelta(minutes=5)
        run2 = brainrun.run_all(make_cfg(tmp, name='two'), io2)
        rep = read(os.path.join(run2['dir'], 'report.md'))
        changed = rep.split('## What changed since the last run')[1].split('##')[0]
        for side in ('KaijuFlow', 'Usenet Ultimate', "AltMount's own addon"):
            self.assertIn(f'- Top pick changed: {side}, Matrix (Cold 1, Warm 1, Cold 2, Warm 2): 4K REMUX Matrix 💾 95.01 GB FGT, 85.4 GB '
                          '-> 4K WEB-DL Matrix 💾 21.9 GB NEW, 22.3 GB', changed)
        self.assertEqual(changed.count('Top pick changed'), 2 * 3)  # two titles on three sides
        self.assertIn('| Matrix | KaijuFlow | Cold 1 | 4K WEB-DL Matrix 💾 21.9 GB NEW | 22.3 GB | 5 |', rep.split('## Per title')[1])
        self.assertIn('Top pick changed: KaijuFlow, Matrix', read(os.path.join(tmp, 'runs', 'INDEX.md')))
        # the same top picks again: nothing to list
        io3 = PickIO('4K WEB-DL Matrix 💾 21.9 GB NEW', 22300000000)
        io3.clock += datetime.timedelta(minutes=10)
        run3 = brainrun.run_all(make_cfg(tmp, name='three'), io3)
        self.assertNotIn('Top pick changed', read(os.path.join(run3['dir'], 'report.md')))


def interrupt_at(io, n):
    """Ctrl-C during the n-th visit: the visit raises KeyboardInterrupt, as the real one does inside its HTTP read."""
    inner = io.visit_http

    def visit(side, kind, vid, tries):
        if io.visits == n - 1:
            io.visits += 1
            raise KeyboardInterrupt
        return inner(side, kind, vid, tries)
    io.visit_http = visit
    return io


def terminate_at(io, n):
    """SIGTERM during the n-th visit, sent to this process as `timeout` sends it; the visit waits for it to land."""
    inner = io.visit_http

    def visit(side, kind, vid, tries):
        if io.visits == n - 1:
            io.visits += 1
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(5)  # cut short by the signal
        return inner(side, kind, vid, tries)
    io.visit_http = visit
    return io


def ctrl_c_again_in_the_ending(io):
    """The owner presses Ctrl-C again while the command finishes its record: once as the test copies are stopped (the
    cleanup), once as the clock is next read after that (the writing of the record). Real signals, so that a command
    that ignores them is seen to ignore them."""
    stop_all, now, pressed = io.stop_all, io.now, []

    def press():
        pressed.append(1)
        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(0.2)  # a Ctrl-C that is not ignored cuts this short

    def stop_all_and_press():
        press()
        stop_all()

    def now_and_press():
        if len(pressed) == 1:
            press()
        return now()
    io.stop_all, io.now = stop_all_and_press, now_and_press
    return io, pressed


class SignalGuard(unittest.TestCase):
    """A SIGTERM that no handler of brainrun catches fails the test instead of ending the test process; SIGINT gets
    Python's own handler back after every test."""

    def setUp(self):
        self.tmp = tempdir(self)

        def unhandled(signum, frame):
            raise RuntimeError('SIGTERM reached the test: brainrun has no handler for it')
        self.unhandled = unhandled
        self.addCleanup(signal.signal, signal.SIGTERM, signal.signal(signal.SIGTERM, unhandled))
        self.addCleanup(signal.signal, signal.SIGINT, signal.default_int_handler)

    def command(self, argv, io_for, titles=None):
        """brainrun.main with the world of `io_for(cfg)`, on the test's titles or the `titles` given: (exit code, printed
        lines, the run folder or record folder)."""
        cfg = make_cfg(self.tmp)
        titles_file = os.path.join(self.tmp, 'titles.json')
        with open(titles_file, 'w') as f:
            json.dump(titles or cfg['titles'], f)
        out = io_module.StringIO()
        with mock.patch.object(brainrun, 'RealIO', io_for), contextlib.redirect_stdout(out):
            code = brainrun.main(argv + ['--name', 'trial', '--store', cfg['store'], '--list', 'l', '--runs-root',
                                         cfg['runs_root'], '--test-dir', cfg['test_dir'], '--titles-file', titles_file])
        folder = os.path.join(cfg['runs_root'], [d for d in os.listdir(cfg['runs_root']) if d != 'INDEX.md'][0])
        return code, out.getvalue().splitlines(), folder


TAGGED = [['movie', 'tt1', 'Matrix', 'easy'], ['series', 'tt2:1:1', 'Show S01E01', 'hard']]  # #165's tagged title list


class TaggedListTest(SignalGuard):
    """#167: a speed test's tagged title list ([type, id, label, list]) goes through run and record, and each title's list
    lands in the run folder."""

    def test_a_run_on_a_tagged_list_keeps_each_titles_list_in_meta_and_raw(self):
        code, _, folder = self.command(['run'], lambda cfg: CleanIO(), titles=TAGGED)
        self.assertEqual(code, 0)
        meta = json.loads(read(os.path.join(folder, 'meta.json')))
        self.assertEqual(meta['lists'], {'Matrix': 'easy', 'Show S01E01': 'hard'})
        self.assertEqual(meta['titles'], ['Matrix', 'Show S01E01'])
        visits = json.loads(read(os.path.join(folder, 'raw.json')))['visits']
        self.assertEqual({(v['title'], v['list']) for v in visits}, {('Matrix', 'easy'), ('Show S01E01', 'hard')})
        self.assertIn('## Fails and title to video per list', read(os.path.join(folder, 'report.md')))

    def test_a_tagged_list_is_a_speed_tests_whole_list_not_a_short_run(self):
        code, lines, folder = self.command(['run'], lambda cfg: CleanIO(), titles=TAGGED)
        self.assertIsNone(json.loads(read(os.path.join(folder, 'meta.json')))['short'])
        self.assertTrue(runcheck.check_run(folder)[0], lines)

    def test_a_run_without_tags_keeps_no_list(self):
        code, _, folder = self.command(['run'], lambda cfg: CleanIO())
        self.assertNotIn('lists', json.loads(read(os.path.join(folder, 'meta.json'))))
        self.assertFalse(any('list' in v for v in json.loads(read(os.path.join(folder, 'raw.json')))['visits']))
        self.assertNotIn('per list', read(os.path.join(folder, 'report.md')))


class SigtermTest(SignalGuard):
    """`timeout` ends a command with SIGTERM: a run or a record ended that way is stopped, like one stopped with Ctrl-C."""

    def test_a_run_ended_by_sigterm_is_stopped_and_keeps_its_record(self):
        code, lines, folder = self.command(['run'], lambda cfg: terminate_at(FakeIO(), 5))
        self.assertEqual(code, 130)
        meta = json.loads(read(os.path.join(folder, 'meta.json')))
        self.assertEqual((meta['status'], meta['stopped']['signal'], meta['stopped']['plays_done']), ('stopped', 'SIGTERM', 4))
        self.assertEqual(len(json.loads(read(os.path.join(folder, 'raw.json')))['visits']), 4)
        self.assertIn('This run was stopped by SIGTERM at ', read(os.path.join(folder, 'report.md')))  # after the short-run line: the test's titles are a subset
        self.assertIn('| trial | stopped', read(os.path.join(os.path.dirname(folder), 'INDEX.md')))  # the test's titles are a subset: also short
        self.assertTrue(lines[lines.index(f'stopped: {folder}') + 1].startswith(
            'Not usable as a baseline: the run was stopped by SIGTERM at '), lines)
        self.assertIs(signal.getsignal(signal.SIGTERM), self.unhandled)  # the command's handler is gone again

    def test_a_record_ended_by_sigterm_is_stopped_and_keeps_what_was_stored(self):
        fake = fakes.serve(http.server.ThreadingHTTPServer(('127.0.0.1', 0), fakes.FakeIndexer))
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        fakes.FakeIndexer.hits, fakes.FakeIndexer.limit, fakes.FakeIndexer.force_status = 0, False, None
        url = f'http://127.0.0.1:{fake.server_port}'
        os.makedirs(make_cfg(self.tmp)['store'])
        code, lines, folder = self.command(['record'], lambda cfg: terminate_at(RecordIO(cfg, url), 3))
        self.assertEqual(code, 130)
        self.assertTrue(lines[-1].startswith('The recording was stopped by SIGTERM at '), lines[-1])
        meta = json.loads(read(os.path.join(folder, 'meta.json')))
        self.assertEqual((meta['status'], meta['stopped']['signal']), ('stopped', 'SIGTERM'))
        with open(os.path.join(make_cfg(self.tmp)['store'], 'l', 'RECORDING.json')) as f:
            self.assertEqual(json.load(f)['state'], 'stopped')
        self.assertIs(signal.getsignal(signal.SIGTERM), self.unhandled)


class SecondStopTest(SignalGuard):
    """Ctrl-C again while a stopped command finishes its record: one line says it is finishing, and the record is written."""

    def test_a_second_ctrl_c_while_the_run_finishes_its_record_is_ignored(self):
        io, pressed = ctrl_c_again_in_the_ending(interrupt_at(FakeIO(), 5))
        try:
            run, lines = printed(brainrun.run_all, make_cfg(self.tmp), io)
        except KeyboardInterrupt:
            self.fail('the second Ctrl-C escaped run_all')
        self.assertEqual(len(pressed), 2)
        self.assertIn('Stopped by Ctrl-C (SIGINT): the run is finishing its record (report.md, raw.json, meta.json and the '
                      'INDEX.md row); a second Ctrl-C is ignored until it is written.', lines)
        self.assertEqual([c[0] for c in io.calls][-3:], ['restore-config', 'standin-stop', 'stop-all'])  # the cleanup's order
        for name in ('report.md', 'raw.json', 'meta.json'):
            self.assertTrue(os.path.exists(os.path.join(run['dir'], name)), name)
        self.assertEqual(json.loads(read(os.path.join(run['dir'], 'meta.json')))['status'], 'stopped')
        self.assertIn(os.path.basename(run['dir']), read(os.path.join(self.tmp, 'runs', 'INDEX.md')))
        self.assertIs(signal.getsignal(signal.SIGINT), signal.default_int_handler)  # Ctrl-C works again afterwards

    def test_a_second_ctrl_c_while_the_record_finishes_is_ignored(self):
        fake = fakes.serve(http.server.ThreadingHTTPServer(('127.0.0.1', 0), fakes.FakeIndexer))
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        fakes.FakeIndexer.hits, fakes.FakeIndexer.limit, fakes.FakeIndexer.force_status = 0, False, None
        cfg = make_cfg(self.tmp)
        os.makedirs(cfg['store'])
        io, pressed = ctrl_c_again_in_the_ending(interrupt_at(RecordIO(cfg, f'http://127.0.0.1:{fake.server_port}'), 3))
        try:
            rec, lines = printed(brainrun.record_all, cfg, io)
        except KeyboardInterrupt:
            self.fail('the second Ctrl-C escaped record_all')
        self.assertEqual(len(pressed), 2)
        self.assertIn('Stopped by Ctrl-C (SIGINT): the record command is finishing its record (RECORDING.json, meta.json and '
                      'the INDEX.md row); a second Ctrl-C is ignored until it is written.', lines)
        self.assertEqual([c[0] for c in io.calls][-4:], ['standin-stop', 'restore-config', 'reset', 'stop-all'])
        self.assertEqual(json.loads(read(os.path.join(rec['dir'], 'meta.json')))['status'], 'stopped')
        self.assertIn(os.path.basename(rec['dir']), read(os.path.join(self.tmp, 'runs', 'INDEX.md')))


class InterruptedRunTest(unittest.TestCase):
    """A run stopped by hand (#110) keeps the plays it finished and ends the normal way."""

    def setUp(self):
        self.tmp = tempdir(self)

    def stopped_run(self, n=5, **kw):
        io = interrupt_at(FakeIO(), n)
        try:
            return io, brainrun.run_all(make_cfg(self.tmp, **kw), io)
        except KeyboardInterrupt:
            self.fail('the interrupt escaped run_all')

    def test_an_interrupt_during_a_visit_keeps_every_earlier_visit_and_records_the_run_as_stopped(self):
        io, run = self.stopped_run(5)  # 3 sides x 2 titles x 4 rounds = 24 plays planned
        d = run['dir']
        raw = json.loads(read(os.path.join(d, 'raw.json')))
        self.assertEqual(raw['status'], 'stopped')
        self.assertEqual([(v['side'], v['phase'], v['round'], v['title']) for v in raw['visits']],
                         [('kaijuflow', 'cold', 1, 'Matrix'), ('uu', 'cold', 1, 'Matrix'),
                          ('altmount-addon', 'cold', 1, 'Matrix'), ('uu', 'cold', 1, 'Show S01E01')])
        meta = json.loads(read(os.path.join(d, 'meta.json')))
        self.assertEqual(meta['status'], 'stopped')
        self.assertEqual(meta['stopped'], {
            'time': '2026-11-10T18:00:38.000Z', 'plays_done': 4, 'plays_planned': 24,  # 2 s stand-in, 20 s reset, 4 visits of 4 s
            'signal': 'SIGINT', 'stage': 'the pass of the main sides',
            'during': {'side': 'altmount-addon', 'phase': 'cold', 'round': 1, 'title': 'Show S01E01'}})
        rows = [x for x in read(os.path.join(self.tmp, 'runs', 'INDEX.md')).splitlines() if os.path.basename(d) in x]
        self.assertEqual(len(rows), 1)
        self.assertIn('| trial | stopped |', rows[0])
        self.assertIn('4 of 24 plays', rows[0])

    def test_the_cleanup_still_runs_after_an_interrupt(self):
        io, run = self.stopped_run(5, one_page=True)
        self.assertEqual(io.visits, 5)  # stopped at once
        self.assertEqual([c[0] for c in io.calls][-3:], ['restore-config', 'standin-stop', 'stop-all'])
        self.assertEqual(io.up, set())

    def test_the_report_opens_by_saying_the_run_was_stopped_and_is_made_from_the_finished_plays(self):
        io, run = self.stopped_run(5)
        rep = read(os.path.join(run['dir'], 'report.md'))
        self.assertEqual(rep.split('\n')[0],
                         "This run was stopped by Ctrl-C (SIGINT) at 2026-11-10T18:00:38.000Z in the pass of the main sides: "
                         "4 of 24 plays had finished, and it stopped "
                         "during the next one (AltMount's own addon, cold 1, Show S01E01). The tables below are made from the "
                         "finished plays alone, so the run is not a baseline.")
        self.assertNotIn('each round done twice', rep)
        self.assertIn('| Usenet Ultimate | Cold 1 | 2 of 2 |', rep)  # the failures table: both of its finished plays played
        self.assertIn('| KaijuFlow | Cold 1 | 1 of 1 |', rep)  # the round was cut short: one of its two titles
        self.assertNotIn('| Warm 1 |', rep)  # no row for a round that never began

    def time_table(self, run, head):
        """The rows of one table of the report's section "Where the time went", found by its header line."""
        lines = read(os.path.join(run['dir'], 'report.md')).split('## Where the time went\n\n')[1].split('\n')
        at = lines.index(head)
        return lines[at + 2:lines.index('', at)]

    def test_a_stopped_run_still_says_where_its_time_went(self):
        # stand-in 2 s, reset 20 s, four plays of 4 s with a 3 s pause after each, stopped as the fifth began, 5 s to stop the copies
        io, run = self.stopped_run(5, settle=3)
        meta = json.loads(read(os.path.join(run['dir'], 'meta.json')))
        timing = meta['timing']
        self.assertEqual((meta['stopped']['time'], meta['finished'], timing['seconds']),
                         ('2026-11-10T18:00:50.000Z', '2026-11-10T18:00:55.000Z', 55.0))
        self.assertEqual(timing['parts'], {'measured_s': 14.0, 'pauses_s': 12.0, 'failed_s': 0.0, 'resets_s': 20.0, 'other_s': 9.0})
        self.assertEqual(timing['passes'], [{'name': 'main sides', 'sides': ['kaijuflow', 'uu', 'altmount-addon'],
                                             'start': '2026-11-10T18:00:02.000Z', 'end': '2026-11-10T18:00:50.000Z', 'seconds': 48.0}])
        self.assertEqual(timing['rounds'], [{'pass': 'main sides', 'phase': 'cold', 'round': 1, 'plays': 4, 'pause_s': 12.0,
                                             'start': '2026-11-10T18:00:22.000Z', 'end': '2026-11-10T18:00:50.000Z', 'seconds': 28.0}])
        self.assertEqual(self.time_table(run, '| Part | Seconds | Minutes |'), [
            '| Measured list and start time | 14.0 | 0.2 |', '| Pauses (`--settle`) | 12.0 | 0.2 |', '| Failed plays | 0.0 | 0.0 |',
            '| Resets | 20.0 | 0.3 |', '| Everything else | 9.0 | 0.1 |', '| The whole run | 55.0 | 0.9 |'])
        self.assertEqual(self.time_table(run, '| Pass | Round | Started (UTC) | Reset before it (s) | Plays | Round (s) | Round (minutes) |'),
                         ['| Main sides | Cold 1 | 18:00:22 | 20.0 | 4 | 28.0 | 0.5 |'])

    def test_a_run_stopped_during_a_reset_keeps_the_time_that_reset_had_taken(self):
        io = FakeIO()
        reset = io.reset

        def hanging_second_reset(sides, log=print):
            if [c[0] for c in io.calls].count('reset') == 1:
                io.calls.append(('reset', tuple(sides)))
                io.takes(7)  # Ctrl-C seven seconds into it
                raise KeyboardInterrupt
            reset(sides, log)
        io.reset = hanging_second_reset
        run = brainrun.run_all(make_cfg(self.tmp), io)  # no pauses: 2 s stand-in, 20 s reset, two rounds of 6 plays of 4 s
        self.assertEqual((run['status'], run['stopped']['time'], run['stopped']['during']), ('stopped', '2026-11-10T18:01:17.000Z', None))
        timing = json.loads(read(os.path.join(run['dir'], 'meta.json')))['timing']
        self.assertEqual([(r['phase'], r['round'], r['seconds']) for r in timing['resets']], [('cold', 1, 20.0), ('cold', 2, 7.0)])
        self.assertEqual(timing['parts'], {'measured_s': 42.0, 'pauses_s': 0.0, 'failed_s': 0.0, 'resets_s': 27.0, 'other_s': 13.0})
        self.assertEqual(timing['seconds'], 82.0)
        self.assertEqual(self.time_table(run, '| Pass | Round | Started (UTC) | Reset before it (s) | Plays | Round (s) | Round (minutes) |'), [
            '| Main sides | Cold 1 | 18:00:22 | 20.0 | 6 | 24.0 | 0.4 |',
            '| Main sides | Warm 1 | 18:00:46 | - | 6 | 24.0 | 0.4 |',
            '| Main sides | Cold 2 | - | 7.0 | 0 | - | - |'])  # the round never began

    def test_a_pause_cut_short_counts_for_as_long_as_it_lasted(self):
        io = FakeIO()
        sleep = io.sleep

        def second_pause_cut_short(s):
            if [c[0] for c in io.calls].count('sleep') == 1:
                io.calls.append(('sleep', s))
                io.takes(1)  # Ctrl-C one second into a pause of three
                raise KeyboardInterrupt
            sleep(s)
        io.sleep = second_pause_cut_short
        run = brainrun.run_all(make_cfg(self.tmp, settle=3), io)
        timing = json.loads(read(os.path.join(run['dir'], 'meta.json')))['timing']
        self.assertEqual((run['status'], timing['rounds'][0]['plays'], timing['rounds'][0]['pause_s']), ('stopped', 2, 4.0))
        # 2 s stand-in, 20 s reset, two plays of 4 s, pauses of 3 s and 1 s, 5 s to stop the copies
        self.assertEqual((timing['seconds'], timing['parts']), (39.0, {
            'measured_s': 7.0, 'pauses_s': 4.0, 'failed_s': 0.0, 'resets_s': 20.0, 'other_s': 8.0}))

    def test_a_null_run_that_made_no_play_still_has_its_time_in_the_meta(self):
        run = brainrun.run_all(make_cfg(self.tmp), FakeIO(marker={'indexer': 'altHUB', 'time': '2026-11-10T18:30:00Z'}))
        timing = json.loads(read(os.path.join(run['dir'], 'meta.json')))['timing']
        self.assertEqual(run['status'], 'null')
        self.assertEqual((timing['seconds'], timing['passes'], timing['rounds'], timing['resets']), (5.0, [], [], []))  # 5 s to stop the copies
        self.assertEqual(timing['parts'], {'measured_s': 0.0, 'pauses_s': 0.0, 'failed_s': 0.0, 'resets_s': 0.0, 'other_s': 5.0})

    def test_an_interrupt_between_two_plays_names_no_play(self):
        io = FakeIO()
        sleeps = []

        def sleep(s):
            sleeps.append(s)
            if len(sleeps) == 2:
                raise KeyboardInterrupt
        io.sleep = sleep
        run = brainrun.run_all(make_cfg(self.tmp), io)
        self.assertEqual((run['status'], len(run['visits'])), ('stopped', 2))
        self.assertIsNone(run['stopped']['during'])
        self.assertIn('2 of 24 plays had finished, and it stopped between two plays.',
                      read(os.path.join(run['dir'], 'report.md')).split('\n')[0])

    def test_a_stopped_run_judges_no_target_in_its_report_or_its_check(self):
        io, run = self.stopped_run(5)
        targets = read(os.path.join(run['dir'], 'report.md')).split('## Targets\n\n')[1].split('\n## ')[0]
        self.assertEqual(targets.strip(), 'Not judged: the run was stopped before its last play, and the targets are '
                                          'judged on a finished run alone.')
        out = io_module.StringIO()
        with contextlib.redirect_stdout(out):
            runcheck.check_command(run['dir'])
        self.assertEqual([x for x in out.getvalue().splitlines() if x.startswith('Target')], [
            'Targets: not judged: the run was stopped before its last play, and the targets are judged on a finished run alone.'])

    def test_a_stopped_run_is_not_the_previous_run(self):
        self.stopped_run(5)
        self.assertIsNone(br.previous_run(os.path.join(self.tmp, 'runs')))

    def test_check_says_a_stopped_run_is_not_usable_as_a_baseline(self):
        io, run = self.stopped_run(5)
        out = io_module.StringIO()
        with contextlib.redirect_stdout(out):
            code = runcheck.check_command(run['dir'])
        self.assertEqual(code, 1)
        first = out.getvalue().splitlines()[0]  # the fake stand-in's one miss is a second reason, after this one
        self.assertTrue(first.startswith(
            "Not usable as a baseline: the run was stopped by Ctrl-C (SIGINT) at 2026-11-10T18:00:38.000Z in the pass of the "
            "main sides: 4 of 24 plays had finished, and it stopped during the next one (AltMount's own addon, cold 1, "
            "Show S01E01)"), first)

    def test_the_run_command_ends_a_stopped_run_with_the_check_and_exit_code_130(self):
        cfg = make_cfg(self.tmp)
        titles = os.path.join(self.tmp, 'titles.json')
        with open(titles, 'w') as f:
            json.dump(cfg['titles'], f)
        out = io_module.StringIO()
        with mock.patch.object(brainrun, 'RealIO', lambda cfg: interrupt_at(FakeIO(), 5)), contextlib.redirect_stdout(out):
            code = brainrun.main(['run', '--name', 'trial', '--store', cfg['store'], '--list', 'l', '--runs-root', cfg['runs_root'],
                                  '--test-dir', cfg['test_dir'], '--titles-file', titles])
        self.assertEqual(code, 130)
        lines = out.getvalue().splitlines()
        folder = os.path.join(cfg['runs_root'], [d for d in os.listdir(cfg['runs_root']) if d != 'INDEX.md'][0])
        self.assertIn(f'stopped: {folder}', lines)
        first = lines[lines.index(f'stopped: {folder}') + 1]
        self.assertEqual(read(os.path.join(folder, 'CHECK.txt')).splitlines()[0], first)
        self.assertFalse(lines[-1].startswith('done in'))  # that line is the mark of a finished run
        self.assertTrue(first.startswith(  # the command's own --settle: a 3 s pause after each of the four plays
            "Not usable as a baseline: the run was stopped by Ctrl-C (SIGINT) at 2026-11-10T18:00:50.000Z in the pass of the "
            "main sides: 4 of 24 plays had finished, and it stopped during the next one (AltMount's own addon, cold 1, "
            "Show S01E01)"), first)


class WaitSwitchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempdir(self)

    def test_wait_is_on_by_default_and_the_record_says_so(self):
        io = FakeIO()
        run = brainrun.run_all(make_cfg(self.tmp), io)
        self.assertIn(('standin-start', 'replay', True), io.calls)
        facts = {'stand-in replay wait': 'on', 'one-page side': 'no'}
        self.assertEqual(run['facts'], facts)
        self.assertEqual(json.loads(read(os.path.join(run['dir'], 'meta.json')))['facts'], facts)
        # run-level facts are not part of the settings snapshot (which equals the settings reader's output)
        self.assertNotIn('stand-in', run['settings'])
        self.assertNotIn('stand-in', json.loads(read(os.path.join(run['dir'], 'settings.json'))))

    def test_the_one_page_side_is_a_fact_not_a_setting(self):
        run = brainrun.run_all(make_cfg(self.tmp, one_page=True), FakeIO())
        self.assertEqual(run['facts']['one-page side'], 'yes')
        self.assertNotIn('kaijuflow-1page', run['settings'])

    def test_no_wait_switch_reaches_the_stand_in_and_shows_in_what_changed(self):
        brainrun.run_all(make_cfg(self.tmp, name='with'), FakeIO())
        io = FakeIO()
        io.clock += datetime.timedelta(minutes=5)
        run = brainrun.run_all(make_cfg(self.tmp, name='without', wait=False), io)
        self.assertIn(('standin-start', 'replay', False), io.calls)
        self.assertIn('stand-in replay wait: on -> off', ' '.join(run['changes']))

    def test_cli_switch(self):
        self.assertTrue(brainrun.build_parser().parse_args(['run', '--no-wait']).no_wait)
        self.assertFalse(brainrun.build_parser().parse_args(['run']).no_wait)


class MissMatchingTest(unittest.TestCase):
    """The stand-in's lines carry no side or title: they are matched to the visit that was running."""

    def test_misses_and_indexer_time_land_on_the_visit(self):
        tmp = tempdir(self)
        io = FakeIO()
        io.lines_per_visit = {2: ['HIT ninjacentral api t=search wait_ms=200', 'MISS drunkenslug api t=search&offset=100'],
                              5: ['HIT drunkenslug api t=search wait_ms=250']}
        run = brainrun.run_all(make_cfg(tmp, topup_command='python3 -I tools/brain/brainrun.py record --name t --store S --list l'), io)
        by_n = run['visits']
        self.assertEqual(by_n[1]['misses'], ['drunkenslug api t=search&offset=100'])  # the 2nd visit
        self.assertEqual(by_n[1]['indexer_s'], 0.2)
        self.assertEqual(run['standin_unmatched'], 0)
        self.assertEqual(by_n[4]['indexer_s'], 0.25)
        self.assertEqual(by_n[0]['misses'], [])
        rep = read(os.path.join(run['dir'], 'report.md'))
        self.assertIn('## Not recorded', rep)
        self.assertIn('brainrun.py record --name t --store S --list l', rep)
        raw = json.loads(read(os.path.join(run['dir'], 'raw.json')))['visits'][1]
        self.assertEqual(raw['misses'], ['drunkenslug api t=search&offset=100'])


    def test_lines_from_an_unknown_address_are_matched_by_time_and_counted(self):
        tmp = tempdir(self)
        io = FakeIO()
        io.ADDRESSES = {}  # docker inspect gave nothing
        io.lines_per_visit = {2: ['MISS drunkenslug api t=search&offset=100'], 3: ['MISS drunkenslug api t=search&offset=200']}
        run = brainrun.run_all(make_cfg(tmp), io)
        self.assertEqual(run['standin_unmatched'], 2)
        self.assertEqual(run['visits'][1]['misses'], ['drunkenslug api t=search&offset=100'])
        self.assertIn('matched by time', read(os.path.join(run['dir'], 'report.md')))
        self.assertEqual(json.loads(read(os.path.join(run['dir'], 'meta.json')))['standin_unmatched'], 2)

    def test_a_failed_top_pick_with_an_unrelated_miss_keeps_its_cause(self):
        tmp = tempdir(self)
        io = FakeIO(fail_http_for='uu')
        io.lines_per_visit = {2: ['MISS drunkenslug api t=search&offset=100']}  # the list was not empty (5 Sources)
        run = brainrun.run_all(make_cfg(tmp), io)
        self.assertEqual(br.classify_failure(run['visits'][1]), 'failure_video')
        self.assertEqual(run['visits'][1]['misses'], ['drunkenslug api t=search&offset=100'])


class SmokeTest(unittest.TestCase):
    def test_each_side_reports_which_address_it_came_from_and_whether_inspect_agrees(self):
        lines = ['MISS ninja api q=x&t=search from=172.20.0.5 t=1', 'MISS ninja api q=y&t=search from=172.20.0.5 t=2']
        r = brainrun.smoke_side_result(lines, '172.20.0.5')
        self.assertEqual((r['standin_requests'], r['came_from'], r['matched']), (2, ['172.20.0.5'], True))
        self.assertFalse(brainrun.smoke_side_result(lines, '172.20.0.9')['matched'])
        self.assertFalse(brainrun.smoke_side_result(lines, None)['matched'])
        self.assertFalse(brainrun.smoke_side_result([], '172.20.0.5')['matched'])

    def test_verdict_in_one_plain_sentence(self):
        def res(*ips):
            return {f's{i}': brainrun.smoke_side_result([f'MISS n api t=search from={ip} t=1'], ip) for i, ip in enumerate(ips)}
        self.assertIn('own address', brainrun.smoke_verdict(res('1.1.1.1', '1.1.1.2', '1.1.1.3')))
        self.assertIn('do not all arrive', brainrun.smoke_verdict(res('1.1.1.1', '1.1.1.1')))  # same address twice
        self.assertIn('No side reached', brainrun.smoke_verdict({'a': brainrun.smoke_side_result([], 'x')}))


class SmokeWorldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempdir(self)

    def smoke(self, one_page):
        io = FakeIO(up=brainrun.ALL_TESTBED)  # the owner started the test copies
        io.lines_per_visit = {n: ['MISS ninjacentral api t=search'] for n in range(1, 5)}
        res = brainrun.smoke(make_cfg(self.tmp, one_page=one_page, store=os.path.join(self.tmp, 'empty')), io)
        return io, res

    def test_the_smoke_check_visits_every_planned_side_the_one_page_side_included(self):
        io, res = self.smoke(one_page=True)
        self.assertEqual(list(res), ['kaijuflow', 'uu', 'altmount-addon', 'kaijuflow-1page'])
        self.assertTrue(all(r['http'] == 200 and r['standin_requests'] == 1 for r in res.values()), res)
        self.assertIn('own address', brainrun.smoke_verdict(res))  # the one-page side may share KaijuFlow's address
        self.assertFalse(io.patched)
        kinds = [c[0] for c in io.calls]
        self.assertEqual(kinds[-2:], ['restore-config', 'standin-stop'])

    def test_without_the_one_page_side_the_smoke_check_tries_the_three_main_sides(self):
        io, res = self.smoke(one_page=False)
        self.assertEqual(list(res), ['kaijuflow', 'uu', 'altmount-addon'])
        self.assertNotIn('patch-one-page', [c[0] for c in io.calls])

    def test_a_visit_to_a_stopped_test_copy_fails_as_the_real_one_does(self):
        io = FakeIO(up=['uu', 'nzbdav'])
        down = io.visit_http('kaijuflow', 'movie', 'tt1', 1)
        self.assertEqual(down, brainrun.visit_answer(refused_get(), 1) | {'list_s': down['list_s']})
        self.assertEqual((down['list_status'], down['sources'], down['first_try_plays']), (None, 0, False))
        self.assertIn('refused', down['note'])
        self.assertEqual(io.visit_http('uu', 'movie', 'tt1', 1)['list_status'], 200)

    def test_the_one_page_switch_brings_kaijuflow_up_again(self):
        io = FakeIO(up=brainrun.ALL_TESTBED)
        brainrun.switch_to_one_page(io)
        self.assertTrue(io.patched)
        self.assertTrue(io.is_up('kaijuflow-1page'))
        self.assertEqual(io.visit_http('kaijuflow-1page', 'movie', 'tt1', 1)['list_status'], 200)


class RecordIO(FakeIO):
    """FakeIO whose stand-in is the real one in record mode on loopback, in front of a fake indexer; the 'sides' ask it
    for different requests, the way the three sides do. Everything else (containers, resets) is the fake's."""

    def __init__(self, cfg, fake_url, limit_from_visit=None, drop=None, proof_asks_more=False):
        super().__init__()
        self.proof_asks_more, self.mode = proof_asks_more, None
        self.cfg, self.fake_url, self.limit_from_visit, self.drop = cfg, fake_url, limit_from_visit, drop or []
        self.port, self.server, self.recording_dir = None, None, cfg['store']
        self.up = set()
        self.seen = set()  # (side, title) already visited: the next visit is a warm one

    def preflight(self, mode):
        self.calls.append(('preflight', mode))
        return list(getattr(self, 'problems', []))

    def marker(self):
        try:
            with open(os.path.join(self.cfg['store'], 'LIMIT_REACHED.json')) as f:
                return json.load(f)
        except OSError:
            return None

    def shelve_marker(self):
        self.calls.append(('shelve-marker',))
        return brainrun.shelve_marker(self.cfg['store'])

    def conf(self):
        return {'indexers': {'fake': {'url': self.fake_url, 'apikey': fakes.REAL_KEY, 'drop_params': self.drop}}}

    def setting_conflicts(self):
        return indexer_standin.setting_conflicts(self.conf(), self.cfg['store'], self.cfg['listname'])

    def start_standin(self, logpath, mode='replay', wait=True):
        self.calls.append(('standin-start', mode, wait))
        self.takes(self.STANDIN_START_S)
        self.mode = mode
        self.seen = set()  # a new pass starts cold again
        conf = self.conf()
        self.server = fakes.serve(indexer_standin.make_server(conf, self.cfg['store'], mode, self.cfg['listname'], port=0, bind='127.0.0.1', wait=wait))
        self.port = self.server.server_port
        io = self

        class H:
            def stop(self):
                io.calls.append(('standin-stop',))
                io.standin_log = list(io.server.state.log_lines)
                io.server.shutdown()
                io.server.server_close()
                with open(logpath, 'w') as f:
                    f.write('\n'.join(io.standin_log) + '\n')
        return H()

    def standin_line_count(self):
        return len(self.server.state.log_lines)

    def standin_lines(self):
        return list(self.server.state.log_lines)

    def visit_http(self, side, kind, vid, tries):
        self.visits += 1
        self.calls.append(('visit', side, vid))
        if not self.is_up(side):
            return self.down_answer(tries)
        self.takes(self.LIST_S + self.START_S + self.SEEKS_S)
        if self.limit_from_visit and self.visits >= self.limit_from_visit:
            fakes.FakeIndexer.limit = True
        base = f'http://127.0.0.1:{self.port}/fake/api'
        asks = {'kaijuflow': [f'?t=search&q={vid}&offset=0', f'?t=search&q={vid}&cat=2000'],  # two searches (a later page is empty, #142)
                'kaijuflow-1page': [f'?t=search&q={vid}&offset=0&limit=100'],
                'uu': [f'?t=search&q={vid}&cat=uu'], 'altmount-addon': [f'?t=search&q={vid}&o=json']}[side]
        if (side, vid) in self.seen:  # what only a warm visit asks: a health-check replacement, the addon's second search
            asks = asks + {'kaijuflow': [f'?t=search&q={vid}-replacement'],
                           'altmount-addon': [f'?t=search&q={vid}&o=json&again=1']}.get(side, [])
        if self.mode == 'replay' and self.proof_asks_more and side == 'altmount-addon' and (side, vid) in self.seen:
            asks = asks + [f'?t=search&q={vid}&o=json&never-recorded=1']  # a warm-only ask nobody stored
        self.seen.add((side, vid))
        for a in asks:
            try:
                urllib.request.urlopen(f'{base}{a}&apikey=dummy', timeout=10).read()
            except OSError:
                pass
        return dict(sources=3, first_try_plays=True)


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempdir(self)
        fakes.FakeIndexer.hits, fakes.FakeIndexer.limit, fakes.FakeIndexer.error_body = 0, False, None
        fakes.FakeIndexer.delay, fakes.FakeIndexer.seen, fakes.FakeIndexer.force_status = 0.0, [], None
        self.fake = fakes.serve(http.server.ThreadingHTTPServer(('127.0.0.1', 0), fakes.FakeIndexer))
        self.addCleanup(self.fake.server_close)
        self.addCleanup(self.fake.shutdown)
        self.url = f'http://127.0.0.1:{self.fake.server_port}'
        self.cfg = make_cfg(self.tmp)
        os.makedirs(self.cfg['store'])

    def stored(self):
        d = os.path.join(self.cfg['store'], self.cfg['listname'], 'fake')
        return sorted(f for f in os.listdir(d) if f.endswith('.body')) if os.path.isdir(d) else []

    def record(self, **kw):
        io = RecordIO(self.cfg, self.url, **kw)
        return io, brainrun.record_all(self.cfg, io)

    def test_every_sides_requests_are_stored_and_a_second_record_asks_the_indexer_for_nothing(self):
        io, rec = self.record()
        self.assertEqual(rec['status'], 'recorded')
        # 2 titles x (2 KaijuFlow searches + 1 UU + 1 addon JSON) cold, + 2 titles x (1 replacement + 1 addon search) warm
        self.assertEqual(len(self.stored()), 12)
        self.assertEqual(fakes.FakeIndexer.hits, 12)
        self.assertEqual(rec['new_answers'], 12)
        before = self.stored()
        io2, rec2 = self.record()
        self.assertEqual(fakes.FakeIndexer.hits, 12)  # zero requests to the fake indexer: a top-up of nothing
        self.assertEqual(self.stored(), before)
        self.assertEqual((rec2['new_answers'], rec2['stored_answers']), (0, 20))  # both rounds served from the store (8 cold + 12 warm)
        self.assertEqual(rec2['visits'], 12)  # 3 sides x 2 titles x 2 rounds

    def test_a_record_with_the_one_page_side_stores_that_sides_answers(self):
        self.cfg['one_page'] = True
        io, rec = self.record()
        self.assertEqual(rec['status'], 'recorded')
        self.assertEqual(rec['listed'], {'kaijuflow': 2, 'uu': 2, 'altmount-addon': 2, 'kaijuflow-1page': 2})
        self.assertEqual(len(self.stored()), 14)  # the 12 of the main sides + one page per title from the one-page side
        self.assertNotIn('listed no Sources', brainrun.record_summary(rec))
        self.assertFalse(os.path.exists(os.path.join(self.cfg['test_dir'], 'config', 'config.json.pre-brainrun')))
        kinds = [c[0] for c in io.calls]
        self.assertLess(kinds.index('patch-one-page'), kinds.index('restore-config'))

    def test_the_record_summary_names_a_side_that_listed_nothing(self):
        rec = {'new_answers': 4, 'stored_answers': 0, 'errors': 0, 'titles': ['A', 'B'],
               'listed': {'kaijuflow': 2, 'kaijuflow-1page': 0}}
        self.assertIn('KaijuFlow, one page per indexer listed no Sources for 2 of 2 titles.', brainrun.record_summary(rec))

    def test_every_play_line_of_a_record_starts_with_the_utc_time_and_a_count_and_the_proof_says_it_is_the_proof(self):
        self.cfg['one_page'] = True
        io = RecordIO(self.cfg, self.url)
        rec, lines = printed(brainrun.record_all, self.cfg, io)
        plays = play_lines(lines)
        self.assertEqual(len(plays), 32)  # 4 sides x 2 titles x 2 rounds, in the record pass and again in the proof
        # started 18:00:00, reset done at :20, stand-in up at :22, a visit takes 4 s
        self.assertEqual(plays[0], '18:00:26 [1/16] kaijuflow cold Matrix: 3 Sources, top pick plays')
        self.assertEqual(plays[11], '18:01:10 [12/16] kaijuflow warm Show S01E01: 3 Sources, top pick plays')
        self.assertEqual(plays[12], '18:01:34 [13/16] kaijuflow-1page cold Matrix: 3 Sources, top pick plays')  # after the 20 s switch
        self.assertEqual(plays[15].split()[1], '[16/16]')
        # the proof: reset 20 s, stand-in 2 s, then its own count
        self.assertEqual(plays[16], '18:02:12 [1/16] proof kaijuflow cold Matrix: 3 Sources, top pick plays')
        self.assertEqual(plays[31].split()[1:3], ['[16/16]', 'proof'])
        # the resets' lines start the same way: before the pass, at the switch to one page, before the proof, at the end
        self.assertEqual(lines[0], '18:00:00 [0/16] reset nzbdav: restored from template')
        self.assertEqual(lines[lines.index(plays[11]) + 1], '18:01:10 [12/16] reset kaijuflow: restored from template')
        self.assertEqual(lines[lines.index(plays[15]) + 1], '18:01:46 [0/16] proof reset nzbdav: restored from template')
        self.assertEqual(lines[lines.index(plays[27]) + 1], '18:02:56 [12/16] proof reset kaijuflow: restored from template')
        self.assertEqual(lines[-1], '18:03:52 [16/16] reset kaijuflow: up')
        self.assertTrue(all(x[2] == x[5] == ':' and x[9] == '[' for x in lines), lines)

    def test_test_copies_are_reset_before_and_after_and_stopped(self):
        io, _ = self.record()
        kinds = [c[0] for c in io.calls]
        self.assertEqual(kinds[0], 'preflight')
        self.assertEqual(io.calls[0], ('preflight', 'record'))
        resets = [i for i, k in enumerate(kinds) if k == 'reset']
        self.assertEqual(len(resets), 3)  # before the pass, before the proof, after everything
        self.assertLess(resets[0], kinds.index('standin-start'))
        self.assertGreater(resets[2], max(i for i, k in enumerate(kinds) if k == 'standin-stop'))
        self.assertEqual(kinds[-1], 'stop-all')
        self.assertEqual(set(io.calls[resets[0]][1]), {'nzbdav', 'altmount-addon', 'altmount-kf', 'uu', 'kaijuflow'})
        self.assertIn(('standin-start', 'record', True), io.calls)
        self.assertEqual(len([c for c in io.calls if c[0] == 'visit']), 24)  # per side and title: a cold and a warm visit, then the same in the proof

    def test_a_record_on_a_tagged_list_keeps_each_titles_list_in_its_meta(self):
        self.cfg['titles'] = [tuple(t) for t in TAGGED]
        io, rec = self.record()
        self.assertEqual(rec['status'], 'recorded')
        meta = json.load(open(os.path.join(rec['dir'], 'meta.json')))
        self.assertEqual((meta['titles'], meta['lists']), (['Matrix', 'Show S01E01'], {'Matrix': 'easy', 'Show S01E01': 'hard'}))
        self.assertEqual(len([c for c in io.calls if c[0] == 'visit']), 24)  # every title played, as on a list without tags

    def test_a_record_without_tags_keeps_no_list(self):
        io, rec = self.record()
        self.assertNotIn('lists', json.load(open(os.path.join(rec['dir'], 'meta.json'))))

    def test_nothing_reaches_a_report_and_a_good_record_has_no_index_row(self):
        io, rec = self.record()
        root = os.path.join(self.tmp, 'runs')
        self.assertFalse(os.path.exists(os.path.join(root, 'INDEX.md')))
        d = rec['dir']
        self.assertTrue(os.path.basename(d).endswith('-trial-record'))
        self.assertTrue(os.path.exists(os.path.join(d, 'logs', 'standin.log')))
        self.assertFalse(os.path.exists(os.path.join(d, 'report.md')))
        self.assertIsNone(br.previous_run(root))  # a record is never the previous run of a diff
        self.assertIn('RECORD fake', read(os.path.join(d, 'logs', 'standin.log')))
        self.assertEqual(json.load(open(os.path.join(d, 'meta.json')))['status'], 'recorded')

    def test_limit_answer_aborts_records_null_and_keeps_what_was_stored(self):
        io, rec = self.record(limit_from_visit=3)
        self.assertEqual(rec['status'], 'null')
        self.assertEqual(rec['null']['indexer'], 'fake')
        self.assertEqual(io.visits, 3)  # stopped at once
        kept = self.stored()
        self.assertGreater(len(kept), 0)
        self.assertLess(len(kept), 12)
        idx = read(os.path.join(self.tmp, 'runs', 'INDEX.md'))
        self.assertIn('NULL', idx)
        self.assertIn('fake', idx)
        self.assertIn('record', idx)
        kinds = [c[0] for c in io.calls]
        self.assertEqual(kinds[-4:], ['standin-stop', 'restore-config', 'reset', 'stop-all'])
        self.assertEqual(json.load(open(os.path.join(rec['dir'], 'meta.json')))['status'], 'null')

    # ---- two rounds per record pass (#79)
    def test_a_record_makes_a_cold_and_a_warm_round_on_every_asked_side(self):
        self.cfg['one_page'] = True
        io, rec = self.record()
        self.assertEqual(rec['status'], 'recorded')
        self.assertEqual(rec['rounds'], ['cold', 'warm'])
        visits = [(c[1], c[2]) for c in io.calls if c[0] == 'visit'][:16]  # the record pass; the proof repeats it after
        main, one_page = visits[:12], visits[12:]
        pairs = {(side, vid) for side in brainrun.MAIN_SIDES for vid in ('tt1', 'tt2:1:1')}
        self.assertEqual(set(main[:6]), pairs)  # the cold round: every main side, every title, once
        self.assertEqual(set(main[6:]), pairs)  # then the warm round, the same again
        self.assertEqual(one_page, [('kaijuflow-1page', 'tt1'), ('kaijuflow-1page', 'tt2:1:1')] * 2)
        kinds = [c[0] for c in io.calls]
        visit_at = [i for i, k in enumerate(kinds) if k == 'visit']
        self.assertNotIn('reset', kinds[visit_at[0]:visit_at[11]])  # no reset between the main sides' rounds
        self.assertEqual(rec['listed'], {'kaijuflow': 2, 'uu': 2, 'altmount-addon': 2, 'kaijuflow-1page': 2})
        recorded = [x for x in read(os.path.join(rec['dir'], 'logs', 'standin.log')).splitlines() if x.startswith('RECORD ')]
        self.assertEqual(len([x for x in recorded if 'tt1-replacement' in x or 'again=1' in x]), 3)  # warm-only asks, stored
        self.assertEqual(len(self.stored()), 14)

    def test_a_top_up_makes_both_rounds_and_asks_only_for_what_is_not_stored(self):
        self.record(limit_from_visit=7)  # stops in the warm round
        kept, hits = self.stored(), fakes.FakeIndexer.hits
        fakes.FakeIndexer.limit = False
        io, rec = self.record()
        self.assertEqual(rec['status'], 'recorded')
        self.assertEqual(rec['visits'], 12)  # the top-up makes the cold and the warm round again
        self.assertEqual(len(self.stored()), 12)
        self.assertEqual(fakes.FakeIndexer.hits - hits, 12 - len(kept))  # only the missing answers are asked
        self.assertEqual(rec['new_answers'], 12 - len(kept))

    def test_limit_reached_in_the_warm_round_stops_the_pass_and_the_recording_is_null(self):
        io, rec = self.record(limit_from_visit=7)
        self.assertEqual(rec['status'], 'null')
        self.assertEqual(rec['null']['indexer'], 'fake')
        self.assertEqual(io.visits, 7)  # the first warm visit (a new ask: a replacement); nothing after it
        self.assertGreaterEqual(len(self.stored()), 8)  # the cold round's answers stay
        self.assertLess(len(self.stored()), 12)
        self.assertEqual(self.state()['state'], 'stopped')
        self.assertIn('NULL', read(os.path.join(self.tmp, 'runs', 'INDEX.md')))
        kinds = [c[0] for c in io.calls]
        self.assertEqual(kinds[-4:], ['standin-stop', 'restore-config', 'reset', 'stop-all'])

    # ---- a record pass stopped by hand (#110)
    def stopped_record(self, n):
        io = interrupt_at(RecordIO(self.cfg, self.url), n)
        try:
            return io, brainrun.record_all(self.cfg, io)
        except KeyboardInterrupt:
            self.fail('the interrupt escaped record_all')

    def test_an_interrupt_during_the_record_pass_keeps_what_was_stored_and_records_it_as_stopped(self):
        io, rec = self.stopped_record(3)
        self.assertEqual(rec['status'], 'stopped')
        # 20 s reset, 2 s stand-in, two visits of 4 s
        self.assertEqual((rec['stopped']['time'], rec['stopped']['plays_done']), ('2026-11-10T18:00:30.000Z', 2))
        self.assertEqual(len(self.stored()), 3)  # KaijuFlow's two searches and Usenet Ultimate's one, for the first title
        self.assertEqual(json.loads(read(os.path.join(rec['dir'], 'meta.json')))['status'], 'stopped')
        row = read(os.path.join(self.tmp, 'runs', 'INDEX.md')).splitlines()[-1]
        self.assertIn('| trial (record) | stopped |', row)
        self.assertIn(os.path.basename(rec['dir']), row)
        st = self.state()
        self.assertEqual((st['state'], st['why']), ('stopped', 'the record command was stopped by Ctrl-C (SIGINT) at '
                                                    '2026-11-10T18:00:30.000Z in the record pass: 2 of 12 plays had finished, '
                                                    "and it stopped during the next one (AltMount's own addon, cold, Matrix)"))
        kinds = [c[0] for c in io.calls]
        self.assertEqual(kinds.count('standin-start'), 1)  # no proof of a pass that did not finish
        self.assertEqual(kinds[-4:], ['standin-stop', 'restore-config', 'reset', 'stop-all'])

    def test_an_interrupt_during_the_proof_records_it_as_stopped_and_a_run_refuses_the_recording(self):
        io, rec = self.stopped_record(13)  # the pass makes 12 visits; the 13th is the proof's first
        self.assertEqual((rec['status'], rec['stopped']['stage'], rec['stopped']['plays_done']), ('stopped', 'the proof replay', 0))
        self.assertEqual(len(self.stored()), 12)
        self.assertEqual(self.state()['state'], 'stopped')  # not proven, so not complete: the preflight of a run refuses it
        self.assertEqual([c[0] for c in io.calls][-4:], ['standin-stop', 'restore-config', 'reset', 'stop-all'])
        self.assertEqual(io.up, set())

    def test_an_interrupt_in_the_opening_reset_or_the_stand_ins_start_still_ends_the_normal_way(self):
        for step in ('reset', 'start_standin'):
            with self.subTest(step=step):
                io = RecordIO(self.cfg, self.url)
                real = getattr(io, step)

                def cut_short(*args, _step=step, _real=real, **kw):  # Ctrl-C in the first call only
                    setattr(io, _step, _real)
                    raise KeyboardInterrupt
                setattr(io, step, cut_short)
                try:
                    rec = brainrun.record_all(self.cfg, io)
                except KeyboardInterrupt:
                    self.fail('the interrupt escaped record_all')
                self.assertEqual((rec['status'], rec['stopped']['plays_done'], rec['stopped']['during']), ('stopped', 0, None))
                self.assertEqual(json.loads(read(os.path.join(rec['dir'], 'meta.json')))['status'], 'stopped')
                self.assertTrue(self.state()['why'].endswith('in the record pass: 0 of 12 plays had finished, and it stopped '
                                                             'before its first play'), self.state()['why'])
                self.assertIn(os.path.basename(rec['dir']), read(os.path.join(self.tmp, 'runs', 'INDEX.md')))
                self.assertEqual([c[0] for c in io.calls][-2:], ['reset', 'stop-all'])  # the cleanup still runs
                self.assertEqual(io.up, set())

    def test_check_on_a_stopped_record_folder_says_it_holds_a_recording_and_how_it_stopped(self):
        io, rec = self.stopped_record(3)
        out = io_module.StringIO()
        with contextlib.redirect_stdout(out):
            code = runcheck.check_command(rec['dir'])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue().splitlines()[0],
                         'Not usable as a baseline: the folder holds a recording, not a timed run; the recording was stopped '
                         'by Ctrl-C (SIGINT) at 2026-11-10T18:00:30.000Z in the record pass: 2 of 12 plays had finished, and '
                         "it stopped during the next one (AltMount's own addon, cold, Matrix).")

    def test_a_stopped_record_and_a_stopped_run_say_how_they_stopped_in_one_shape(self):
        io, rec = self.stopped_record(3)
        run = brainrun.run_all(make_cfg(self.tmp), interrupt_at(FakeIO(), 5))
        self.assertEqual(rec['stopped'], {'time': '2026-11-10T18:00:30.000Z', 'signal': 'SIGINT', 'stage': 'the record pass',
                                          'plays_done': 2, 'plays_planned': 12,
                                          'during': {'side': 'altmount-addon', 'phase': 'cold', 'round': None, 'title': 'Matrix'}})
        self.assertEqual(sorted(run['stopped']), sorted(rec['stopped']))

    def test_the_record_command_ends_a_stopped_record_with_one_sentence_and_exit_code_130(self):
        titles = os.path.join(self.tmp, 'titles.json')
        with open(titles, 'w') as f:
            json.dump(self.cfg['titles'], f)
        out = io_module.StringIO()
        with mock.patch.object(brainrun, 'RealIO', lambda cfg: interrupt_at(RecordIO(cfg, self.url), 3)), \
                contextlib.redirect_stdout(out):
            code = brainrun.main(['record', '--name', 'trial', '--store', self.cfg['store'], '--list', 'l', '--runs-root',
                                  self.cfg['runs_root'], '--test-dir', self.cfg['test_dir'], '--titles-file', titles])
        self.assertEqual(code, 130)
        last = out.getvalue().splitlines()[-1]
        self.assertTrue(last.startswith('The recording was stopped by Ctrl-C (SIGINT) at 2026-11-10T18:00:36.000Z in the record '
                                        'pass: 2 of 12 plays had finished, and it stopped during the next one '
                                        "(AltMount's own addon, cold, Matrix). What was stored is kept; "
                                        'run the same command again to top up. Folder: '), last)

    def marker_files(self):
        return sorted(f for f in os.listdir(self.cfg['store']) if f.startswith('LIMIT_REACHED'))

    def test_a_marker_from_an_earlier_command_is_moved_aside_and_the_top_up_goes_on(self):
        self.record(limit_from_visit=3)
        kept, hits = self.stored(), fakes.FakeIndexer.hits
        self.assertEqual(self.marker_files(), ['LIMIT_REACHED.json'])
        fakes.FakeIndexer.limit = False
        io, rec = self.record()  # the marker is still there, the indexer has reset
        self.assertEqual(rec['status'], 'recorded')
        self.assertIn(('shelve-marker',), io.calls)
        files = self.marker_files()
        self.assertEqual(len(files), 1)  # kept, renamed with its time; no live marker left
        self.assertRegex(files[0], r'^LIMIT_REACHED\.\d{8}T\d{6}Z\.json$')
        self.assertEqual(len(self.stored()), 12)
        self.assertTrue(set(kept) <= set(self.stored()))
        self.assertEqual(fakes.FakeIndexer.hits - hits, 12 - len(kept))  # only what was missing is asked

    def test_if_the_limit_still_holds_the_first_answer_writes_a_new_marker_and_aborts(self):
        self.record(limit_from_visit=3)
        hits = fakes.FakeIndexer.hits
        io, rec = self.record()  # limit is still on in the fake indexer
        self.assertEqual(rec['status'], 'null')
        self.assertEqual(fakes.FakeIndexer.hits, hits + 1)
        self.assertIn('LIMIT_REACHED.json', self.marker_files())
        self.assertEqual(len(self.marker_files()), 2)  # the new one and the old one, kept

    # ---- the recording's state, error answers (review fixes 5, 9)
    def state(self):
        with open(os.path.join(self.cfg['store'], self.cfg['listname'], 'RECORDING.json')) as f:
            return json.load(f)

    def test_a_finished_record_writes_state_complete(self):
        io, rec = self.record()
        st = self.state()
        self.assertEqual((st['state'], st['errors']), ('complete', 0))
        self.assertIn('when', st)

    def test_a_stopped_record_writes_state_stopped_with_why_and_when(self):
        self.record(limit_from_visit=3)
        st = self.state()
        self.assertEqual(st['state'], 'stopped')
        self.assertIn('fake', st['why'])
        self.assertIn('limit', st['why'])
        self.assertTrue(st['when'])

    def test_error_answers_are_counted_not_stored_and_a_second_record_tops_them_up(self):
        fakes.FakeIndexer.force_status = 503
        io, rec = self.record()
        self.assertEqual(rec['status'], 'recorded')
        self.assertGreater(rec['errors'], 0)
        self.assertEqual(self.state()['errors'], rec['errors'])
        self.assertEqual(self.stored(), [])
        sentence = brainrun.record_summary(rec)
        self.assertIn(f"{rec['errors']} answers were errors", sentence)
        self.assertIn('run record again', sentence)
        fakes.FakeIndexer.force_status = None
        io2, rec2 = self.record()
        self.assertEqual((rec2['errors'], len(self.stored())), (0, 12))
        self.assertEqual(self.state()['errors'], 0)
        self.assertNotIn('were errors', brainrun.record_summary(rec2))

    # ---- the proof (#80)
    def test_the_proof_marks_a_recording_complete_when_every_answer_is_there(self):
        io, rec = self.record()
        self.assertEqual(rec['misses'], [])
        self.assertEqual(self.state()['state'], 'complete')
        self.assertEqual(self.state()['misses'], [])
        self.assertNotIn('INCOMPLETE', brainrun.record_summary(rec))
        proof = read(os.path.join(rec['dir'], 'logs', 'standin-proof.log'))
        self.assertIn('HIT fake', proof)
        self.assertNotIn('MISS', proof)

    def test_the_proof_marks_a_recording_incomplete_when_a_warm_only_answer_is_missing(self):
        io, rec = self.record(proof_asks_more=True)
        self.assertEqual(rec['status'], 'recorded')
        self.assertEqual({m['side'] for m in rec['misses']}, {'altmount-addon'})
        self.assertEqual(len(rec['misses']), 2)  # one per title
        self.assertTrue(all('never-recorded=1' in m['request'] and m['request'].startswith('fake ') for m in rec['misses']))
        st = self.state()
        self.assertEqual(st['state'], 'incomplete')
        self.assertEqual(st['misses'], rec['misses'])
        self.assertIn('missed 2 requests', st['why'])
        self.assertIn('INCOMPLETE', brainrun.record_summary(rec))
        self.assertIn('MISS fake', read(os.path.join(rec['dir'], 'logs', 'standin-proof.log')))

    def test_the_proof_contacts_no_indexer_and_resets_the_copies_first(self):
        io, rec = self.record(proof_asks_more=True)
        self.assertEqual(fakes.FakeIndexer.hits, 12)  # the record pass's 12; the proof (with misses) added none
        starts = [c for c in io.calls if c[0] == 'standin-start']
        self.assertEqual(starts, [('standin-start', 'record', True), ('standin-start', 'replay', False)])
        kinds = [c[0] for c in io.calls]
        proof_start = kinds.index('standin-start', kinds.index('standin-start') + 1)
        self.assertEqual(kinds[proof_start - 1], 'reset')  # test copies reset right before the proof
        self.assertEqual(len([c for c in io.calls[:proof_start] if c[0] == 'visit']), 12)

    def test_a_record_with_a_limit_runs_no_proof(self):
        io, rec = self.record(limit_from_visit=3)
        self.assertEqual([c for c in io.calls if c[0] == 'standin-start'], [('standin-start', 'record', True)])
        self.assertEqual(self.state()['state'], 'stopped')

    def test_a_proof_covers_the_one_page_side_too(self):
        self.cfg['one_page'] = True
        io, rec = self.record(proof_asks_more=True)
        self.assertEqual({m['side'] for m in rec['misses']}, {'altmount-addon'})
        self.assertEqual(len([c for c in io.calls if c[0] == 'visit' and c[1] == 'kaijuflow-1page']), 8)  # 2 titles x 2 rounds, record and proof

    def test_a_changed_dropped_parameter_setting_stops_the_record_with_one_sentence(self):
        self.record(drop=['o'])
        hits = fakes.FakeIndexer.hits
        with self.assertRaises(brainrun.PreflightFailed) as cm:
            self.record(drop=[])
        self.assertEqual(len(cm.exception.problems), 1)
        self.assertIn('new list name', cm.exception.problems[0])
        self.assertEqual(fakes.FakeIndexer.hits, hits)
        self.record(drop=['o'])  # the same setting goes on

    def test_a_failed_preflight_stops_before_anything_happens(self):
        io = RecordIO(self.cfg, self.url)
        io.problems = ['The test image is old: build it again with --rebuild-image.']
        with self.assertRaises(brainrun.PreflightFailed) as cm:
            brainrun.record_all(self.cfg, io)
        self.assertEqual(cm.exception.problems, io.problems)
        self.assertEqual([c[0] for c in io.calls], ['preflight'])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'runs')))

    def test_a_run_refuses_to_start_without_a_recording(self):
        td = test_preflight.make_copies(self)
        cfg = test_preflight.make_cfg(td, runs_root=os.path.join(self.tmp, 'runs2'), titles=[], name='x', tries=1, settle=0,
                                      indexers=[], one_page=False, user_id='U', download_key='K')
        world = test_preflight.FakeWorld(cfg)
        with self.assertRaises(brainrun.PreflightFailed) as cm:
            brainrun.run_all(cfg, world)
        self.assertIn('no recording', ' '.join(cm.exception.problems))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'runs2')))

    def test_record_command_line(self):
        a = brainrun.build_parser().parse_args(['record', '--name', 'n', '--store', 'S', '--list', 'L', '--key-file', 'K'])
        self.assertEqual(a.cmd, 'record')
        self.assertEqual(brainrun.topup_command(a), 'python3 -I tools/brain/brainrun.py record --name n --store S --list L --key-file K')


class FinalStepsTest(unittest.TestCase):
    """Step lines are attributed after the pass, so a late health_batch is kept (#62 review)."""

    class LateIO(FakeIO):
        def logs(self, container, since):
            return ('2026-11-10T18:00:03.000000000Z [KF-STEP] {"step":"indexer_page","source":"N","ms":100,"ok":true,'
                    '"t":"2026-11-10T18:00:03.000Z","ref":"tt1","page":1}\n'
                    '2026-11-10T18:00:45.000000000Z [KF-STEP] {"step":"health_batch","ms":9000,"ok":true,'
                    '"t":"2026-11-10T18:00:45.000Z","ref":"tt1","count":3,"checked":3}\n'
                    '2026-11-10T18:01:10.000000000Z [KF-STEP] {"step":"health_batch","ms":500,"ok":true,'
                    '"t":"2026-11-10T18:01:10.000Z","ref":"tt2","count":1,"checked":1}\n')

    def test_late_health_batch_lands_on_its_own_visit(self):
        visits = [dict(side='kaijuflow', id='tt1', t_start='2026-11-10T18:00:01.000Z', steps=[], tries=[]),
                  dict(side='uu', id='tt1', t_start='2026-11-10T18:00:20.000Z', steps=[], tries=[]),
                  dict(side='kaijuflow', id='tt2', t_start='2026-11-10T18:01:05.000Z', steps=[], tries=[])]
        brainrun.finalize_steps(self.LateIO(), visits)
        self.assertEqual([s['step'] for s in visits[0]['steps']], ['indexer_page', 'health_batch'])
        self.assertEqual(visits[1]['steps'], [])  # a side without KaijuFlow step lines
        self.assertEqual([(s['step'], s['ref']) for s in visits[2]['steps']], [('health_batch', 'tt2')])

    def test_diff_in_a_run_names_null_runs_between(self):
        tmp = tempdir(self)
        brainrun.run_all(make_cfg(tmp, name='ok1'), FakeIO())
        bad = FakeIO(limit_at_visit=1)
        bad.clock += datetime.timedelta(hours=1)
        brainrun.run_all(make_cfg(tmp, name='bad'), bad)
        io = FakeIO()
        io.clock += datetime.timedelta(hours=3)
        run = brainrun.run_all(make_cfg(tmp, name='ok2'), io)
        self.assertIn('1 null run ', ' '.join(run['changes']))
        self.assertIn('Time of day', ' '.join(run['changes']))


class SettingsTest(unittest.TestCase):
    def test_snapshot_has_every_side_and_no_secrets(self):
        t = tempdir(self)
        td = os.path.join(t, 'kaijuflow-test')
        for rel, text in (('config/config.json', json.dumps({'healthChecks': {'sampleCount': 3}, 'altmountApiKey': SECRET,
                                                              'indexers': [{'name': 'N', 'apiKey': SECRET, 'maxPages': 3}]})),
                          ('uu/config/config.json', json.dumps({'healthChecks': {'sampleCount': 3}, 'nzbdavApiKey': SECRET})),
                          ('altmount-addon/config/config.yaml', 'import:\n  max_processor_workers: 2\napi_key: ' + SECRET + '\n'),
                          ('altmount-kf/config/config.yaml', 'import:\n  max_processor_workers: 2\n')):
            p = os.path.join(td, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w') as f:
                f.write(text)
        p = os.path.join(td, 'nzbdav/config/db.sqlite')
        os.makedirs(os.path.dirname(p))
        db = sqlite3.connect(p)
        db.execute('create table ConfigItems (ConfigName text, ConfigValue text)')
        db.execute("insert into ConfigItems values ('api.key', ?)", (SECRET,))
        db.execute("insert into ConfigItems values ('usenet.max-download-connections', '25')")
        db.execute("insert into ConfigItems values ('usenet.providers', ?)", (json.dumps({'Providers': [{'Host': 'h', 'Password': SECRET, 'MaxConnections': 50}]}),))
        db.commit()
        db.close()
        snap = brainrun.snapshot_settings(td)
        self.assertEqual(set(snap), {'kaijuflow', 'uu', 'nzbdav', 'altmount-addon', 'altmount-kf'})
        self.assertNotIn(SECRET, json.dumps(snap))
        self.assertEqual(snap['kaijuflow']['indexers[N].maxPages'], 3)
        self.assertEqual(snap['nzbdav']['usenet.max-download-connections'], '25')
        self.assertEqual(snap['altmount-addon']['import.max_processor_workers'], '2')

    def test_one_page_patch_is_config_only(self):
        cfg = {'indexers': [{'name': 'A', 'pagination': True, 'maxPages': 3}, {'name': 'B', 'pagination': True}],
               'searchConfig': {'seasonPackPagination': True, 'seriesPackPagination': True, 'junkFilter': True}}
        out = brainrun.one_page_config(cfg)
        self.assertTrue(all(i['pagination'] is False for i in out['indexers']))
        self.assertFalse(out['searchConfig']['seasonPackPagination'])
        self.assertFalse(out['searchConfig']['seriesPackPagination'])
        self.assertTrue(out['searchConfig']['junkFilter'])
        self.assertTrue(cfg['indexers'][0]['pagination'])  # input untouched


class CleanIO(FakeIO):
    """A world whose stand-in misses nothing, so its runs can serve as baselines."""

    def start_standin(self, logpath, mode='replay', wait=True):
        handle = super().start_standin(logpath, mode, wait)
        self.standin_log = ['HIT ninjacentral api t=search wait_ms=0']
        with open(logpath, 'w') as f:
            f.write('\n'.join(self.standin_log) + '\n')
        return handle


class ShortRunTest(SignalGuard):
    """#111: `run` can play a part of the plan; such a short run says what it played and is never a baseline."""

    def meta(self, run):
        return json.loads(read(os.path.join(run['dir'], 'meta.json')))

    def played(self, run):
        return sorted({(v['side'], v['phase'], v['round']) for v in json.loads(read(os.path.join(run['dir'], 'raw.json')))['visits']})

    def test_sides_and_rounds_play_only_what_they_name(self):
        io = CleanIO()
        run = brainrun.run_all(make_cfg(self.tmp, sides=['kaijuflow'], rounds=1), io)
        self.assertEqual(self.played(run), [('kaijuflow', 'cold', 1), ('kaijuflow', 'warm', 1)])
        self.assertEqual(len(run['visits']), 4)  # two titles, cold and warm
        self.assertEqual([c for c in io.calls if c[0] == 'reset'], [('reset', tuple(brainrun.ALL_TESTBED))])
        meta = self.meta(run)
        self.assertEqual((meta['sides'], meta['rounds'], meta['titles']), (['kaijuflow'], 1, ['Matrix', 'Show S01E01']))
        self.assertEqual(meta['short'], 'KaijuFlow, 1 round, 2 titles')

    def test_quick_plays_the_same_as_sides_kaijuflow_rounds_1(self):
        def played_by(argv):
            self.tmp = tempdir(self)
            code, _, folder = self.command(argv, lambda cfg: CleanIO())
            self.assertEqual(code, 0)
            raw = json.loads(read(os.path.join(folder, 'raw.json')))['visits']
            return [(v['side'], v['phase'], v['round'], v['title']) for v in raw], json.loads(read(os.path.join(folder, 'meta.json')))
        quick, qmeta = played_by(['run', '--quick'])
        named, nmeta = played_by(['run', '--sides', 'kaijuflow', '--rounds', '1'])
        self.assertEqual(quick, named)
        self.assertEqual(len(quick), 4)
        self.assertEqual((qmeta['sides'], qmeta['rounds'], qmeta['short']), (nmeta['sides'], nmeta['rounds'], nmeta['short']))
        self.assertEqual(qmeta['sides'], ['kaijuflow'])

    def test_the_one_page_side_can_be_played_alone(self):
        io = CleanIO()
        run = brainrun.run_all(make_cfg(self.tmp, sides=['kaijuflow-1page']), io)
        self.assertEqual({v['side'] for v in run['visits']}, {'kaijuflow-1page'})
        self.assertEqual(len(run['visits']), 8)  # two titles, four rounds
        self.assertEqual(self.meta(run)['sides'], ['kaijuflow-1page'])
        self.assertIn(('patch-one-page',), io.calls)
        self.assertNotIn(('reset', tuple(brainrun.ALL_TESTBED)), io.calls)  # no pass of the main sides

    def test_no_selectors_play_the_full_plan_as_before(self):
        run = brainrun.run_all(make_cfg(self.tmp), CleanIO())
        self.assertEqual(len(run['visits']), 24)
        meta = self.meta(run)
        self.assertEqual((meta['sides'], meta['rounds'], meta['short']), (list(brainrun.MAIN_SIDES), 2, None))
        self.assertFalse(read(os.path.join(run['dir'], 'report.md')).startswith('Short run'))
        self.assertIn('| trial | ok |', read(os.path.join(self.tmp, 'runs', 'INDEX.md')))
        self.assertTrue(runcheck.check_run(run['dir'])[0])

    def test_all_four_sides_named_are_the_one_page_run(self):
        run = brainrun.run_all(make_cfg(self.tmp, sides=['kaijuflow-1page', 'uu', 'altmount-addon', 'kaijuflow']), CleanIO())
        self.assertEqual(self.meta(run)['sides'], ['kaijuflow', 'uu', 'altmount-addon', 'kaijuflow-1page'])
        self.assertIsNone(self.meta(run)['short'])

    def test_the_progress_count_is_the_short_runs_own(self):
        _, lines = printed(brainrun.run_all, make_cfg(self.tmp, sides=['kaijuflow'], rounds=1), CleanIO())
        self.assertTrue(all('/4]' in x for x in lines), lines)

    def test_a_short_run_says_so_in_its_report_its_index_row_and_check(self):
        run = brainrun.run_all(make_cfg(self.tmp, sides=['uu', 'altmount-addon'], rounds=1), CleanIO())
        text = 'Usenet Ultimate, AltMount direct, 1 round, 2 titles'
        self.assertEqual(read(os.path.join(run['dir'], 'report.md')).splitlines()[0], f'Short run, not a baseline: {text}.')
        self.assertIn(f'| trial | short: {text} |', read(os.path.join(self.tmp, 'runs', 'INDEX.md')))
        usable, lines = runcheck.check_run(run['dir'])
        self.assertFalse(usable)
        self.assertEqual(lines[0], f'Not usable as a baseline: short run ({text}).')
        self.assertTrue(any(x.startswith('Top picks played, Usenet Ultimate') for x in lines))  # the other lines are still there

    def test_a_titles_subset_is_a_short_run(self):
        run = brainrun.run_all(make_cfg(self.tmp, partial_titles=True), CleanIO())
        self.assertEqual(self.meta(run)['short'], 'KaijuFlow, Usenet Ultimate, AltMount direct, 2 rounds, 2 titles')
        self.assertFalse(runcheck.check_run(run['dir'])[0])

    def test_a_short_run_is_compared_with_the_last_baseline_limited_to_what_it_played(self):
        brainrun.run_all(make_cfg(self.tmp, name='base'), CleanIO(commit='c1'))
        base = sorted(d for d in os.listdir(os.path.join(self.tmp, 'runs')) if d != 'INDEX.md')[0]
        short = brainrun.run_all(make_cfg(self.tmp, name='quick', sides=['kaijuflow'], rounds=1), CleanIO(commit='c2'))
        changes = short['changes']
        self.assertEqual(changes[0], f'Short run: compared with the last baseline, {base}, limited to KaijuFlow, 1 round, 2 titles.')
        self.assertIn('KaijuFlow code: c1 -> c2', changes)
        self.assertFalse([c for c in changes if 'removed' in c], changes)  # the sides it did not play are not "removed"
        # a short run is never the baseline of the next one, nor the previous run of a full one
        short2 = brainrun.run_all(make_cfg(self.tmp, name='quick2', sides=['kaijuflow'], rounds=1), CleanIO(commit='c3'))
        self.assertIn(f'compared with the last baseline, {base},', short2['changes'][0])
        self.assertIn('KaijuFlow code: c1 -> c3', short2['changes'])
        full = brainrun.run_all(make_cfg(self.tmp, name='full'), CleanIO(commit='c4'))
        self.assertIn('KaijuFlow code: c1 -> c4', full['changes'])

    def test_a_run_that_cannot_be_a_baseline_is_not_the_one_a_short_run_is_compared_with(self):
        brainrun.run_all(make_cfg(self.tmp, name='missed'), FakeIO(commit='c1'))  # its stand-in logged a miss
        short = brainrun.run_all(make_cfg(self.tmp, name='quick', sides=['kaijuflow'], rounds=1), CleanIO())
        self.assertEqual(short['changes'], ['No earlier run to compare with: this is the first one.'])

    def bad(self, argv):
        err = io_module.StringIO()
        with mock.patch.object(brainrun, 'RealIO', side_effect=AssertionError('nothing may start')), \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            brainrun.main(argv + ['--name', 't', '--store', self.tmp, '--list', 'l', '--runs-root', os.path.join(self.tmp, 'runs')])
        self.assertEqual(stop.exception.code, 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'runs')))
        message = err.getvalue().strip().splitlines()[-1]
        self.assertEqual(message.count('. '), 0, message)  # one sentence
        return message

    def test_wrong_selector_values_stop_with_one_sentence_before_anything_runs(self):
        self.assertIn('unknown side', self.bad(['run', '--sides', 'kaijuflow,nzbdav']))
        self.assertIn('--rounds', self.bad(['run', '--rounds', '3']))
        self.assertIn('--quick', self.bad(['run', '--quick', '--sides', 'uu']))
        self.assertIn('--quick', self.bad(['run', '--quick', '--rounds', '1']))
        self.assertIn('--one-page', self.bad(['run', '--one-page', '--sides', 'uu']))
        self.assertIn('only for run', self.bad(['record', '--quick']))
        self.assertIn('only for run', self.bad(['smoke', '--rounds', '1']))



class ArchiveTest(unittest.TestCase):
    """#144: a run in the runs root's archive folder is never the baseline nor a comparison."""

    def setUp(self):
        self.tmp = tempdir(self)
        self.root = os.path.join(self.tmp, 'runs')

    def archive_all(self):
        os.makedirs(os.path.join(self.root, br.ARCHIVE), exist_ok=True)
        for d in os.listdir(self.root):
            if d not in (br.ARCHIVE, 'INDEX.md'):
                os.rename(os.path.join(self.root, d), os.path.join(self.root, br.ARCHIVE, d))

    def test_a_run_next_to_an_archive_folder_is_the_first_one(self):
        brainrun.run_all(make_cfg(self.tmp, name='old'), CleanIO(commit='c1'))
        brainrun.run_all(make_cfg(self.tmp, name='old-null'), FakeIO(limit_at_visit=1))
        self.archive_all()
        run = brainrun.run_all(make_cfg(self.tmp, name='baseline'), CleanIO(commit='c2'))
        self.assertEqual(run['changes'], ['No earlier run to compare with: this is the first one.'])
        self.assertIn('No earlier run to compare with: this is the first one.', read(os.path.join(run['dir'], 'report.md')))
        self.assertIsNone(br.previous_run(self.root, exclude=os.path.basename(run['dir'])))
        # the next run is compared with that first one, not with anything archived
        nxt = brainrun.run_all(make_cfg(self.tmp, name='tuning'), CleanIO(commit='c3'))
        self.assertIn('KaijuFlow code: c2 -> c3', nxt['changes'])
        self.assertFalse([c for c in nxt['changes'] if 'null run' in c], nxt['changes'])

    def test_a_short_run_is_never_compared_with_an_archived_baseline(self):
        brainrun.run_all(make_cfg(self.tmp, name='old'), CleanIO())
        self.archive_all()
        short = brainrun.run_all(make_cfg(self.tmp, name='quick', sides=['kaijuflow'], rounds=1), CleanIO())
        self.assertEqual(short['changes'], ['No earlier run to compare with: this is the first one.'])

    def test_the_check_says_an_archived_run_is_not_usable_as_a_baseline(self):
        run = brainrun.run_all(make_cfg(self.tmp, name='old'), CleanIO())
        self.assertTrue(runcheck.check_run(run['dir'])[0])
        self.archive_all()
        usable, lines = runcheck.check_run(os.path.join(self.root, br.ARCHIVE, os.path.basename(run['dir'])))
        self.assertFalse(usable)
        self.assertEqual(lines[0], 'Not usable as a baseline: archived (not like for like): the folder is in the archive.')


class NeverComparedTest(unittest.TestCase):
    """#153: a run marked never compared with (meta.json "never_compared") is kept beside the others but never compared with."""

    def setUp(self):
        self.tmp = tempdir(self)
        self.root = os.path.join(self.tmp, 'runs')

    def mark(self, run_dir, label='Test 1'):
        path = os.path.join(run_dir, 'meta.json')
        meta = json.loads(read(path))
        meta.update(label=label, never_compared=True)
        with open(path, 'w') as f:
            json.dump(meta, f)

    def test_a_run_after_a_marked_run_is_the_first_one(self):
        self.mark(brainrun.run_all(make_cfg(self.tmp, name='baseline'), CleanIO(commit='c1'))['dir'])
        run = brainrun.run_all(make_cfg(self.tmp, name='tuning'), CleanIO(commit='c2'))
        self.assertEqual(run['changes'], ['No earlier run to compare with: this is the first one.'])
        self.assertIn('No earlier run to compare with: this is the first one.', read(os.path.join(run['dir'], 'report.md')))

    def test_a_short_run_is_never_compared_with_a_marked_run(self):
        self.mark(brainrun.run_all(make_cfg(self.tmp, name='baseline'), CleanIO())['dir'])
        short = brainrun.run_all(make_cfg(self.tmp, name='quick', sides=['kaijuflow'], rounds=1), CleanIO())
        self.assertEqual(short['changes'], ['No earlier run to compare with: this is the first one.'])

    def test_the_check_says_a_marked_run_is_not_usable_as_a_baseline(self):
        run = brainrun.run_all(make_cfg(self.tmp, name='baseline'), CleanIO())
        self.mark(run['dir'])
        usable, lines = runcheck.check_run(run['dir'])
        self.assertFalse(usable)
        self.assertEqual(lines[0], 'Not usable as a baseline: marked never compared with (Test 1).')


if __name__ == '__main__':
    unittest.main()
