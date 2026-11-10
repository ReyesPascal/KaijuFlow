"""Tests for brainrun.py (the one command: sides x cold/warm x 2, run records, cap rule). Fakes only: no Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import datetime
import http.server
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.request

import brainreport as br
import brainrun
import indexer_standin
import test_indexer_standin as fakes
import test_preflight

SECRET = 'TOPSECRET-123'
UTC = datetime.timezone.utc


def read(path):
    with open(path) as f:
        return f.read()


class FakeIO:
    """Stands in for Docker, the stand-in and the sides. Records every call in order."""

    def __init__(self, limit_at_visit=None, marker=None, commit='c1', settings=None, fail_http_for=None):
        self.calls, self.clock, self.visits = [], datetime.datetime(2026, 11, 10, 18, 0, 0, tzinfo=UTC), 0
        self.limit_at_visit, self._marker, self.commit = limit_at_visit, marker, commit
        self.settings = settings or {'kaijuflow': {'healthChecks.sampleCount': 3, 'altmountApiKey': '***'}, 'uu': {}}
        self.fail_http_for = fail_http_for
        self.patched = False
        self.working = 0
        self.standin_log = []
        self.lines_per_visit = {}  # visit number -> lines the stand-in writes during that visit
        self.max_working = 0

    def now(self):
        self.clock += datetime.timedelta(seconds=1)
        return self.clock

    def sleep(self, s):
        self.calls.append(('sleep', s))

    def git_info(self):
        return 'repo-head-must-not-be-recorded', False

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

    def reset(self, sides):
        self.calls.append(('reset', tuple(sides)))

    def stop_all(self):
        self.calls.append(('stop-all',))

    def apply_one_page(self):
        self.patched = True
        self.calls.append(('patch-one-page',))
        return {'kaijuflow-1page': {'indexers[NinjaCentral].pagination': False}}

    def restore_config(self):
        self.patched = False
        self.calls.append(('restore-config',))

    ADDRESSES = {'kaijuflow-test': '10.0.0.2', 'uu-test': '10.0.0.3', 'altmount-addon-test': '10.0.0.4'}
    SIDE_IP = {'kaijuflow': '10.0.0.2', 'kaijuflow-1page': '10.0.0.2', 'uu': '10.0.0.3', 'altmount-addon': '10.0.0.4'}

    def addresses(self):
        self.calls.append(('addresses',))
        return dict(self.ADDRESSES)

    def visit_http(self, side, kind, vid, tries):
        self.visits += 1
        self.calls.append(('visit', side, vid))
        t = int(self.clock.timestamp() * 1000) + 300  # a moment after the visit began
        self.standin_log += [f'{x} from={self.SIDE_IP[side]} t={t}' for x in self.lines_per_visit.get(self.visits, [])]
        ok = side != self.fail_http_for
        return dict(list_status=200, list_s=2.0, sources=5, first_try_plays=ok, start_s=1.5 if ok else None,
                    note=None if ok else 'failure video', seeks={'50': 0.2, '90': 0.3}, tries=[{'plays': ok}])

    def logs(self, container, since):
        t = self.clock.strftime('%Y-%m-%dT%H:%M:%S.000000000Z')
        text = ''
        if container == 'kaijuflow-test':
            ts = self.clock.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            text = (f'{t} [KF-STEP] {{"step":"nzb_fetch","source":"S","ms":100,"ok":true,"t":"{ts}","title":"R"}}\n'
                    f'{t} apikey=' + SECRET + ' fetching\n')
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
        self.tmp = tempfile.mkdtemp()

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

    def test_run_record_commit_comes_from_the_image_label_after_a_preflight(self):
        io = FakeIO(commit='c-from-label')
        run = brainrun.run_all(make_cfg(self.tmp), io)
        self.assertEqual(run['commit'], 'c-from-label')
        self.assertEqual(json.loads(read(os.path.join(run['dir'], 'meta.json')))['commit'], 'c-from-label')
        self.assertEqual(io.calls_preflight, ['run'])

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


class WaitSwitchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

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
        tmp = tempfile.mkdtemp()
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
        tmp = tempfile.mkdtemp()
        io = FakeIO()
        io.ADDRESSES = {}  # docker inspect gave nothing
        io.lines_per_visit = {2: ['MISS drunkenslug api t=search&offset=100'], 3: ['MISS drunkenslug api t=search&offset=200']}
        run = brainrun.run_all(make_cfg(tmp), io)
        self.assertEqual(run['standin_unmatched'], 2)
        self.assertEqual(run['visits'][1]['misses'], ['drunkenslug api t=search&offset=100'])
        self.assertIn('matched by time', read(os.path.join(run['dir'], 'report.md')))
        self.assertEqual(json.loads(read(os.path.join(run['dir'], 'meta.json')))['standin_unmatched'], 2)

    def test_a_failed_top_pick_with_an_unrelated_miss_keeps_its_cause(self):
        tmp = tempfile.mkdtemp()
        io = FakeIO(fail_http_for='uu')
        io.lines_per_visit = {2: ['MISS drunkenslug api t=search&offset=100']}  # the list was not empty (5 Sources)
        run = brainrun.run_all(make_cfg(tmp), io)
        self.assertEqual(br.classify_failure(run['visits'][1]), 'failure_video')
        self.assertEqual(run['visits'][1]['misses'], ['drunkenslug api t=search&offset=100'])


class RecordIO(FakeIO):
    """FakeIO whose stand-in is the real one in record mode on loopback, in front of a fake indexer; the 'sides' ask it
    for different requests, the way the three sides do. Everything else (containers, resets) is the fake's."""

    def __init__(self, cfg, fake_url, limit_from_visit=None, drop=None):
        super().__init__()
        self.cfg, self.fake_url, self.limit_from_visit, self.drop = cfg, fake_url, limit_from_visit, drop or []
        self.port, self.server, self.recording_dir = None, None, cfg['store']

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
        conf = self.conf()
        self.server = fakes.serve(indexer_standin.make_server(conf, self.cfg['store'], mode, self.cfg['listname'], port=0, bind='127.0.0.1'))
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
        if self.limit_from_visit and self.visits >= self.limit_from_visit:
            fakes.FakeIndexer.limit = True
        base = f'http://127.0.0.1:{self.port}/fake/api'
        asks = {'kaijuflow': [f'?t=search&q={vid}&offset=0', f'?t=search&q={vid}&offset=3'],
                'uu': [f'?t=search&q={vid}&cat=uu'], 'altmount-addon': [f'?t=search&q={vid}&o=json']}[side]
        for a in asks:
            try:
                urllib.request.urlopen(f'{base}{a}&apikey=dummy', timeout=10).read()
            except OSError:
                pass
        return dict(sources=3, first_try_plays=True)


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
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
        self.assertEqual(len(self.stored()), 8)  # 2 titles x (2 KaijuFlow pages + 1 UU + 1 addon JSON), all different
        self.assertEqual(fakes.FakeIndexer.hits, 8)
        self.assertEqual(rec['new_answers'], 8)
        before = self.stored()
        io2, rec2 = self.record()
        self.assertEqual(fakes.FakeIndexer.hits, 8)  # zero requests to the fake indexer: a top-up of nothing
        self.assertEqual(self.stored(), before)
        self.assertEqual((rec2['new_answers'], rec2['stored_answers']), (0, 8))
        self.assertEqual(rec2['visits'], 6)  # 3 sides x 2 titles, once

    def test_test_copies_are_reset_before_and_after_and_stopped(self):
        io, _ = self.record()
        kinds = [c[0] for c in io.calls]
        self.assertEqual(kinds[0], 'preflight')
        self.assertEqual(io.calls[0], ('preflight', 'record'))
        resets = [i for i, k in enumerate(kinds) if k == 'reset']
        self.assertEqual(len(resets), 2)
        self.assertLess(resets[0], kinds.index('standin-start'))
        self.assertGreater(resets[1], kinds.index('standin-stop'))
        self.assertEqual(kinds[-1], 'stop-all')
        self.assertEqual(set(io.calls[resets[0]][1]), {'nzbdav', 'altmount-addon', 'altmount-kf', 'uu', 'kaijuflow'})
        self.assertIn(('standin-start', 'record', True), io.calls)
        self.assertEqual(len([c for c in io.calls if c[0] == 'visit']), 6)  # once per side and title, no rounds

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
        self.assertLess(len(kept), 8)
        idx = read(os.path.join(self.tmp, 'runs', 'INDEX.md'))
        self.assertIn('NULL', idx)
        self.assertIn('fake', idx)
        self.assertIn('record', idx)
        kinds = [c[0] for c in io.calls]
        self.assertEqual(kinds[-4:], ['standin-stop', 'restore-config', 'reset', 'stop-all'])
        self.assertEqual(json.load(open(os.path.join(rec['dir'], 'meta.json')))['status'], 'null')

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
        self.assertEqual(len(self.stored()), 8)
        self.assertTrue(set(kept) <= set(self.stored()))
        self.assertEqual(fakes.FakeIndexer.hits - hits, 8 - len(kept))  # only what was missing is asked

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
        self.assertEqual((rec2['errors'], len(self.stored())), (0, 8))
        self.assertEqual(self.state()['errors'], 0)
        self.assertNotIn('were errors', brainrun.record_summary(rec2))

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
        td = test_preflight.make_copies()
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
        tmp = tempfile.mkdtemp()
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
        t = tempfile.mkdtemp()
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


if __name__ == '__main__':
    unittest.main()
