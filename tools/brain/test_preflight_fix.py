"""Tests for the preflight's fixes (#303): every refusal names the command that fixes it, and `--fix` runs the safe ones
(the expected settings, the image rebuild, the key file's mode, the indexer command) on the fixture test folder, then runs
the preflight again; power, the machine's addresses, DNS and the allowance are never touched.

    python3 -I -m unittest discover -s tools/brain -p 'test_preflight_fix.py'
"""
import contextlib
import io
import json
import os
import stat
import unittest
from unittest import mock

import brainrun
from test_preflight import COMMIT, OLDER, FakeWorld, make_cfg, record, run_command
from test_settings import SECRET, make_copies, put_limits, rules, tempdir

ADD = 'python3 -I tools/brain/testbed.py indexer add'


class Fixing(FakeWorld):
    """FakeWorld whose test copies can be stopped (the fixes stop them before writing a config)."""

    def __init__(self, cfg, **kw):
        super().__init__(cfg, **kw)
        self.stopped = 0

    def stop_all(self):
        self.stopped += 1


def config(td):
    with open(os.path.join(td, 'config', 'config.json')) as f:
        return json.load(f)


def switched_on(td):
    return sorted(e['name'] for e in config(td)['indexers'] if e['enabled'])


class EveryRefusalNamesItsFixTest(unittest.TestCase):
    def stops(self, mode, cfg, world, *fix):
        code, text = run_command(mode, cfg, world)
        self.assertEqual(code, 1, text)
        for f in fix:
            self.assertIn(f, text)
        self.assertNotIn(SECRET, text)
        return text

    def setUp(self):
        self.td = make_copies(self)
        self.cfg = make_cfg(self.td, runs_root=tempdir(self))
        record(self.cfg)

    def test_the_machine_and_the_repository(self):
        self.stops('run', self.cfg, Fixing(self.cfg, dirty=True), 'git commit')
        self.stops('run', self.cfg, Fixing(self.cfg, label=OLDER, changed={OLDER: True}), '--rebuild-image', '--fix')
        self.stops('run', self.cfg, Fixing(self.cfg, free=False), "ss -ltnp 'sport = :1340'")
        self.stops('run', self.cfg, Fixing(self.cfg, load=2.5), 'uptime')
        self.stops('run', self.cfg, Fixing(self.cfg, machine=('127.0.0.1', '192.0.2.99')), 'testbed.py up')
        self.stops('run', self.cfg, Fixing(self.cfg, dns=('10.0.0.1',)), 'dig +short news.newshosting.com @192.168.4.1')
        self.stops('run', self.cfg, Fixing(self.cfg, power='battery'), 'plug it in')

    def test_the_key_file(self):
        path = os.path.join(self.td, 'indexers.json')
        os.chmod(path, 0o644)
        self.stops('record', self.cfg, Fixing(self.cfg), f'chmod 600 {path}', '--fix')
        os.remove(path)
        self.stops('record', self.cfg, Fixing(self.cfg), f'{ADD} <slug> --stash <entry>')
        with open(path, 'w') as f:
            f.write('{}')
        os.chmod(path, 0o600)
        self.stops('record', self.cfg, Fixing(self.cfg), f'{ADD} <slug> --stash <entry>')

    def test_the_indexers_switched_on(self):
        cfg = make_cfg(make_copies(self, enabled=('ninjacentral',), disabled=('drunkenslug', 'althub'),
                                   key_slugs=('ninjacentral', 'drunkenslug')))
        self.stops('record', cfg, Fixing(cfg), 'python3 -I tools/brain/testbed.py indexer on drunkenslug', '--fix')
        cfg = make_cfg(make_copies(self, enabled=('ninjacentral', 'althub'), disabled=('drunkenslug',),
                                   key_slugs=('ninjacentral',)))
        self.stops('record', cfg, Fixing(cfg), f'{ADD} althub --stash <entry>')

    def test_the_settings_of_the_test_copies(self):
        cfg = make_cfg(make_copies(self, kf_rules=rules(films=4000)))
        self.stops('record', cfg, Fixing(cfg), 'python3 -I tools/brain/testbed.py apply kaijuflow', '--fix')
        cfg = make_cfg(make_copies(self, caps=(12, 100)))
        self.stops('record', cfg, Fixing(cfg), 'python3 -I tools/brain/testbed.py settings')
        cfg = make_cfg(make_copies(self, url=lambda s: 'https://real.example/api'))
        self.stops('record', cfg, Fixing(cfg), "KaijuFlow's indexer settings")

    def test_the_allowance(self):
        put_limits(os.path.join(self.td, 'indexers.json'), {'ninjacentral': (2000, 450), 'drunkenslug': (10, 100)})
        self.stops('check', self.cfg, Fixing(self.cfg), 'brainrun.py usage')


class FixTest(unittest.TestCase):
    def setUp(self):
        self.root = tempdir(self)

    def broken(self, **kw):
        """A test folder with every safe problem: the key file open to others, KaijuFlow's size cap not the expected one,
        DrunkenSlug switched on in the key file but off in KaijuFlow; and an image built before the code changed."""
        td = make_copies(self, kf_rules=rules(films=4000), key_mode=0o644, enabled=('ninjacentral',),
                         disabled=('drunkenslug', 'althub'), key_slugs=('ninjacentral', 'drunkenslug'))
        cfg = make_cfg(td, runs_root=self.root, fix=True)
        put_limits(os.path.join(td, 'indexers.json'), {'ninjacentral': (2000, 450), 'drunkenslug': (1000, 100)})
        os.chmod(os.path.join(td, 'indexers.json'), 0o644)
        return td, cfg, Fixing(cfg, label=OLDER, changed={OLDER: True}, **kw)

    def test_fix_runs_the_safe_fixes_then_passes(self):
        td, cfg, world = self.broken()
        code, text = run_command('check', cfg, world)
        self.assertEqual(code, 0, text)
        self.assertIn('Setup is right for a check', text)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(td, 'indexers.json')).st_mode), 0o600)
        self.assertEqual(config(td)['movieFilters']['maxFileSize'], 3000)
        self.assertEqual(switched_on(td), ['DrunkenSlug', 'NinjaCentral'])
        self.assertEqual(world.rebuilt, [COMMIT])
        self.assertGreaterEqual(world.stopped, 1)  # the test copies stopped before a config was written
        self.assertIn('Fixing:', text)
        self.assertNotIn(SECRET, text)
        self.assertTrue(os.listdir(os.path.join(td, 'backups')))  # each changed file backed up first

    def test_fix_leaves_power_addresses_dns_and_the_port_alone_and_names_them(self):
        td, cfg, world = self.broken(power='battery', machine=('127.0.0.1', '192.0.2.99'), dns=('10.0.0.1',), free=False)
        code, text = run_command('check', cfg, world)
        self.assertEqual(code, 1, text)
        self.assertEqual(switched_on(td), ['DrunkenSlug', 'NinjaCentral'])  # the safe ones were still fixed
        for left in ('runs on battery', 'HOST_IP', 'sinkhole', 'port 1340'):
            self.assertIn(left, text)
        for fixed in ('can be read by others', 'switches on', 'maxFileSize', 'has changed since then'):
            self.assertNotIn(fixed, text.split('Fixing:')[-1].split('\n', 1)[-1])
        with open(os.path.join(td, '.env')) as f:
            self.assertIn('HOST_IP=192.0.2.10', f.read())

    def test_fix_never_touches_the_allowance(self):
        td, cfg, world = self.broken()
        put_limits(os.path.join(td, 'indexers.json'), {'ninjacentral': (2000, 450), 'drunkenslug': (10, 100)})
        with open(os.path.join(td, 'indexers.json')) as f:
            before = json.load(f)['indexers']['drunkenslug']['search_per_day']
        code, text = run_command('check', cfg, world)
        self.assertEqual(code, 1, text)
        self.assertIn('drunkenslug has 10 searches left today', text)
        with open(os.path.join(td, 'indexers.json')) as f:
            self.assertEqual(json.load(f)['indexers']['drunkenslug']['search_per_day'], before)

    def test_without_fix_nothing_is_written(self):
        td, cfg, world = self.broken()
        cfg['fix'] = False
        code, text = run_command('check', cfg, world)
        self.assertEqual(code, 1, text)
        self.assertEqual(switched_on(td), ['NinjaCentral'])
        self.assertEqual((world.rebuilt, world.stopped), ([], 0))
        self.assertFalse(os.path.exists(os.path.join(td, 'backups')))

    def test_an_indexer_off_in_the_key_file_is_switched_off_in_kaijuflow(self):
        td = make_copies(self)
        path = os.path.join(td, 'indexers.json')
        with open(path) as f:
            data = json.load(f)
        data['indexers']['drunkenslug']['enabled'] = False
        with open(path, 'w') as f:
            json.dump(data, f)
        cfg = make_cfg(td, fix=True)
        code, text = run_command('record', cfg, Fixing(cfg))
        self.assertEqual(code, 0, text)
        self.assertEqual(switched_on(td), ['NinjaCentral'])

    def test_a_check_started_with_fix_fixes_before_it_draws(self):
        # play_check asks io.preflight: the same path as the preflight command
        td, cfg, world = self.broken()
        seen = {}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(world.preflight('check', seen), [])
        self.assertIn('load', seen)
        self.assertEqual(switched_on(td), ['DrunkenSlug', 'NinjaCentral'])

    def test_the_commands_take_fix_and_standing_go(self):
        for argv, want in ((['preflight', '--for', 'check', '--fix'], {'fix': True, 'standing_go': False, 'full_check': False}),
                           (['preflight', '--for', 'check', '--full', '--standing-go'], {'fix': False, 'standing_go': True, 'full_check': True})):
            got = []
            with mock.patch.object(brainrun, 'preflight_command', side_effect=lambda m, c, i: got.append(c) or 0), \
                    contextlib.redirect_stdout(io.StringIO()):
                brainrun.main(argv + ['--test-dir', make_copies(self), '--runs-root', self.root])
            self.assertEqual({k: got[0].get(k) for k in want}, want)
        got = []
        with mock.patch.object(brainrun, 'quick_check_command', side_effect=lambda c, i: got.append(c) or 0):
            brainrun.main(['check', '--quick', '--fix', '--test-dir', make_copies(self), '--runs-root', self.root])
        self.assertEqual((got[0]['fix'], got[0].get('full_check')), (True, False))


if __name__ == '__main__':
    unittest.main()
