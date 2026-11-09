"""Tests for brainrun.py (the one command: sides x cold/warm x 2, run records, cap rule). Fakes only: no Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import datetime
import json
import os
import sqlite3
import tempfile
import unittest

import brainreport as br
import brainrun

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
        self.max_working = 0

    def now(self):
        self.clock += datetime.timedelta(seconds=1)
        return self.clock

    def sleep(self, s):
        self.calls.append(('sleep', s))

    def git_info(self):
        return self.commit, False

    def snapshot(self):
        return json.loads(json.dumps(self.settings))

    def marker(self):
        return self._marker

    def start_standin(self, logpath):
        self.calls.append(('standin-start',))
        with open(logpath, 'w') as f:
            f.write('HIT ninjacentral api t=search\nMISS drunkenslug api t=search\n')
        io = self

        class H:
            def stop(self):
                io.calls.append(('standin-stop',))
        return H()

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

    def visit_http(self, side, kind, vid, tries):
        self.visits += 1
        self.calls.append(('visit', side, vid))
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
        marker = {'indexer': 'altHUB', 'time': '2026-11-10T09:00:00Z'}
        io = FakeIO(marker=marker)
        run = brainrun.run_all(make_cfg(self.tmp), io)
        self.assertEqual(run['status'], 'null')
        self.assertEqual(run['null']['indexer'], 'altHUB')
        self.assertEqual(io.visits, 0)
        self.assertIn('altHUB', read(os.path.join(self.tmp, 'runs', 'INDEX.md')))

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
        self.assertIn('kaijuflow-1page', run['settings'])

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
