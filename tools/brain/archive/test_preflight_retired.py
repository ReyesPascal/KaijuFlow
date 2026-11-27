"""The archived tests of test_preflight.py (ADR 0010, #273): the run and record preflights, their recording checks, the
run's addresses, and a run stopped by its preflight.
"""
import unittest

import test_preflight
from test_preflight import *  # noqa: F401,F403  (the live file's helpers)
import contextlib
import io
import json
import os
import brainrun  # noqa: F401
import retired_run
import testbed  # noqa: F401
from run_fixtures import run_folder  # noqa: F401
from test_settings import SECRET, make_copies, tempdir  # noqa: F401


def record(cfg, counts=None, state='complete', why=None):
    os.makedirs(os.path.join(cfg['store'], cfg['listname']), exist_ok=True)
    if state:
        with open(os.path.join(cfg['store'], cfg['listname'], retired_run.RECORDING_FILE), 'w') as f:
            json.dump({'state': state, 'why': why, 'when': '2026-11-10T09:00:00Z', 'errors': 0}, f)
    for slug, n in (counts or {'ninjacentral': 2, 'drunkenslug': 1}).items():
        d = os.path.join(cfg['store'], cfg['listname'], slug)
        os.makedirs(d, exist_ok=True)
        for i in range(n):
            with open(os.path.join(d, 'k%d.body' % i), 'w') as f:
                f.write('x')
            with open(os.path.join(d, 'k%d.body.meta.json' % i), 'w') as f:
                f.write('{}')


def run_command(mode, cfg, world):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = retired_run.preflight_command(mode, cfg, world)
    return code, out.getvalue()


class FakeWorld(test_preflight.FakeWorld, retired_run.RetiredIO):
    """The live preflight's fake world with the recording's parts (RetiredIO)."""


class PreflightTest(test_preflight.PreflightTest):
    def world(self, **kw):
        return FakeWorld(self.cfg, **kw)

    def assert_stops(self, mode, world, *fragments):
        code, text = run_command(mode, self.cfg, world)
        self.assertEqual(code, 1, text)
        for f in fragments:
            self.assertIn(f, text)
        self.assertNotIn(SECRET, text)
        self.assertEqual(len([line for line in text.splitlines() if line.strip()]), 1, text)  # one sentence per failure here

    def copies(self, **kw):
        """Another fixture test folder in place of setUp's (make_copies' options), with a recording for a run."""
        super().copies(**kw)
        record(self.cfg)

    def ran(self, name, started, misses, recording='l', visits=None, **meta):
        """A run folder in the runs root: its meta.json as a run writes it, and with `visits` its raw.json."""
        self.cfg['runs_root'] = os.path.join(os.path.dirname(self.td), 'runs')
        run_folder(self.cfg['runs_root'], name, {'name': name, 'status': 'ok', 'started': started, 'recording': recording,
                                                 'standin_misses': misses, **meta}, visits)

    def test_correct_setup_passes_in_record_and_in_run(self):
        record(self.cfg)
        for mode in ('record', 'run'):
            code, text = run_command(mode, self.cfg, self.world())
            self.assertEqual(code, 0, text)
            self.assertIn('Setup is right', text)
            self.assertIn('connection caps, sort and filter settings', text)

    def test_a_run_that_passes_names_the_machine_checks_too(self):
        record(self.cfg)
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 0, text)
        self.assertIn('the machine is plugged in and idle (1-minute load below 1.00), HOST_IP and altmountUrl are its addresses, '
                      'news.newshosting.com resolves outside 10.x and the recording is complete', text)
        self.assertIn('CPU probe: 950 ms (governor powersave, energy preference performance).', text)
        code, text = run_command('record', self.cfg, self.world())
        self.assertIn('the machine is plugged in, HOST_IP and altmountUrl are its addresses, news.newshosting.com resolves outside 10.x.', text)
        self.assertNotIn('idle', text)
        self.assertNotIn('CPU probe', text)

    def test_a_machine_on_battery_stops_a_run_and_a_record(self):
        record(self.cfg)
        for mode in ('record', 'run'):
            self.assert_stops(mode, self.world(power='battery'), 'The machine runs on battery', 'plug it in')

    def test_a_run_preflight_keeps_the_machine_it_judged_with_the_cpu_probe_taken_after_the_load_check(self):
        record(self.cfg)
        world, seen = self.world(probe=1234), {}
        self.assertEqual(retired_run.preflight('run', self.cfg, world, seen), [])
        self.assertEqual(seen, {'load': 0.3, 'machine': {'power': 'ac', 'governor': 'powersave', 'energy_preference': 'performance',
                                                         'cpu_probe_ms': 1234}})
        self.assertEqual(world.asked, ['load', 'probe'])

    def test_a_record_preflight_takes_no_cpu_probe(self):
        world = self.world()
        code, text = run_command('record', self.cfg, world)
        self.assertEqual((code, world.asked), (0, []), text)

    def test_a_busy_machine_stops_a_run(self):
        record(self.cfg)
        for load in (1.0, 2.37):
            world = self.world(load=load)
            self.assert_stops('run', world, f'load average is {load:.2f}, at or above 1.00', 'idle')
            self.assertEqual(world.slept, [])  # no image build: judged at once

    def test_a_machine_just_under_the_load_limit_passes_a_run(self):
        record(self.cfg)
        code, text = run_command('run', self.cfg, self.world(load=0.99))
        self.assertEqual(code, 0, text)

    def test_the_load_is_not_checked_for_a_record(self):
        code, text = run_command('record', self.cfg, self.world(load=3.0))
        self.assertEqual(code, 0, text)

    def test_after_its_image_build_a_run_preflight_waits_for_the_load_to_settle(self):
        record(self.cfg)
        self.cfg['rebuild_image'] = True
        world, seen = self.world(label=OLDER, load=[6.2, 3.1, 1.4, 0.8, 0.5]), {}
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(retired_run.preflight('run', self.cfg, world, seen), [])
        self.assertEqual((world.rebuilt, world.slept), ([COMMIT], [10, 10, 10]))
        self.assertEqual(seen['load'], 0.8)
        self.assertEqual(world.asked[-2:], ['load', 'probe'])  # the probe runs once the build's load has settled
        self.assertIn('Waiting up to 3 minutes', out.getvalue())

    def test_a_load_that_does_not_settle_3_minutes_after_the_image_build_stops_a_run(self):
        record(self.cfg)
        self.cfg['rebuild_image'] = True
        world = self.world(label=OLDER, load=2.5)
        code, text = run_command('run', self.cfg, world)
        self.assertEqual(code, 1, text)
        self.assertIn('load average is 2.50 3 minutes after the image build, at or above 1.00', text)
        self.assertEqual(sum(world.slept), 180)

    def test_a_run_preflight_hands_back_the_load_it_judged(self):
        record(self.cfg)
        seen = {}
        self.assertEqual(retired_run.preflight('run', self.cfg, self.world(load=[0.42, 1.7]), seen), [])
        self.assertEqual(seen['load'], 0.42)
        seen = {}
        retired_run.preflight('record', self.cfg, self.world(), seen)
        self.assertEqual(seen, {})

    def test_a_host_ip_the_machine_does_not_have_stops_a_run_and_a_record(self):
        self.copies(host_ip='192.0.2.99')
        for mode in ('run', 'record'):
            self.assert_stops(mode, self.world(), 'HOST_IP', '192.0.2.99', os.path.join(self.td, '.env'),
                              'not an address this machine has', HOST_IP)

    def test_an_altmount_url_on_an_address_the_machine_does_not_have_stops_a_run_and_a_record(self):
        self.copies(altmount_url='http://192.0.2.99:8087')
        for mode in ('run', 'record'):
            self.assert_stops(mode, self.world(), 'altmountUrl', '192.0.2.99', 'not an address this machine has', HOST_IP)

    def test_a_missing_host_ip_or_altmount_url_stops_a_run(self):
        self.copies(host_ip=None)
        self.assert_stops('run', self.world(), 'no HOST_IP', os.path.join(self.td, '.env'))
        self.copies(altmount_url=None)
        self.assert_stops('run', self.world(), 'no altmountUrl')

    def test_a_sinkholed_newshosting_dns_stops_a_run_and_a_record(self):
        record(self.cfg)
        for mode in ('run', 'record'):
            world = self.world(dns=('10.10.10.1',))
            self.assert_stops(mode, world, 'news.newshosting.com', '192.168.4.1', '10.10.10.1', 'sinkhole')
            self.assertEqual(world.asked_dns, [('news.newshosting.com', '192.168.4.1')])

    def test_one_10_x_address_among_good_ones_stops_a_run(self):
        record(self.cfg)
        self.assert_stops('run', self.world(dns=('85.12.62.251', '10.0.0.7')), '10.0.0.7')

    def test_no_dns_answer_stops_a_run(self):
        record(self.cfg)
        self.assert_stops('run', self.world(dns=()), 'The router (192.168.4.1) gives no address for news.newshosting.com')

    def test_key_file_missing_stops_record(self):
        os.remove(os.path.join(self.td, 'indexers.json'))
        self.assert_stops('record', self.world(), 'key file', 'missing')

    def test_key_file_readable_by_others_stops_record(self):
        os.chmod(os.path.join(self.td, 'indexers.json'), 0o644)
        self.assert_stops('record', self.world(), 'key file', 'only by you', 'chmod 600')

    def test_key_file_with_other_indexers_stops_record(self):
        td = make_copies(self, key_slugs=('ninjacentral', 'althub'))
        self.cfg = make_cfg(td)
        self.assert_stops('record', self.world(), 'althub', 'drunkenslug')

    def test_key_file_is_not_checked_in_run_mode(self):
        os.remove(os.path.join(self.td, 'indexers.json'))
        record(self.cfg)
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_missing_recording_stops_run_but_not_record(self):
        self.assert_stops('run', self.world(), 'recording', 'record command')
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_recording_must_hold_an_answer_for_every_enabled_indexer(self):
        record(self.cfg, {'ninjacentral': 3})
        self.assert_stops('run', self.world(), 'drunkenslug')

    def test_a_recording_that_stopped_early_says_so_and_gives_the_record_command(self):
        record(self.cfg, state='stopped', why='drunkenslug said its limit was reached')
        self.cfg['topup_command'] = 'python3 -I tools/brain/brainrun.py record --name n --store S --list l'
        self.assert_stops('run', self.world(), 'stopped early', 'drunkenslug said its limit was reached', '2026-11-10',
                          'python3 -I tools/brain/brainrun.py record --name n --store S --list l')

    def test_an_incomplete_recording_stops_a_run_and_says_why_with_the_record_command(self):
        record(self.cfg, state='incomplete', why='the proof replay missed 2 requests (KaijuFlow asked fake t=search&q=tt1)')
        self.cfg['topup_command'] = 'python3 -I tools/brain/brainrun.py record --name n --store S --list l'
        self.assert_stops('run', self.world(), 'incomplete', 'missed 2 requests', 'KaijuFlow asked',
                          'python3 -I tools/brain/brainrun.py record --name n --store S --list l')

    def test_a_last_run_whose_only_misses_are_releases_never_played_passes_a_run(self):
        record(self.cfg)
        walk = ['ninjacentral nzb 1a2b3c4d5e6f Witcher.2160p-HONE'] * 162
        self.ran('2026-11-11T100000Z-baseline', '2026-11-11T10:00:00Z', 162,
                 visits=[{'ok': True, 'played_source': 'Witcher.2160p-HHWEB', 'misses': walk}])
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_a_last_run_that_missed_a_search_still_stops_a_run(self):
        record(self.cfg)
        self.ran('2026-11-11T100000Z-baseline', '2026-11-11T10:00:00Z', 2,
                 visits=[{'ok': True, 'played_source': 'X', 'misses': ['ninjacentral api t=search&q=x', 'ninjacentral nzb ab Y']}])
        self.assert_stops('run', self.world(), 'missed 1 requests')

    def test_a_recording_the_last_run_missed_stops_a_run_with_the_record_command(self):
        record(self.cfg)  # recorded 2026-11-10T09:00:00Z
        self.ran('2026-11-11T100000Z-baseline', '2026-11-11T10:00:00Z', 1840)
        self.cfg['topup_command'] = 'python3 -I tools/brain/brainrun.py record --name n --store S --list l'
        self.assert_stops('run', self.world(), 'The last run on', '2026-11-11T100000Z-baseline', 'missed 1840 requests',
                          'python3 -I tools/brain/brainrun.py record --name n --store S --list l')

    def test_a_stopped_run_since_the_top_up_that_missed_still_blocks_the_recording(self):
        """#241: the preflight asks its own question, not the Previous run's: a stopped or short run counts too."""
        for name, meta in (('stopped', {'status': 'stopped', 'stopped': {'signal': 'SIGINT', 'plays_done': 3}}),
                           ('short', {'short': 'KaijuFlow, 1 round, 2 titles'})):
            with self.subTest(name):
                record(self.cfg)  # the top-up, 2026-11-10T09:00:00Z
                self.ran('2026-11-11T090000Z-baseline', '2026-11-11T09:00:00Z', 0)  # a finished run that missed nothing
                self.ran(f'2026-11-11T100000Z-{name}', '2026-11-11T10:00:00Z', 1,
                         visits=[{'ok': False, 'played_source': None, 'misses': ['ninjacentral api t=search&q=x']}], **meta)
                self.assert_stops('run', self.world(), 'The last run on', f'2026-11-11T100000Z-{name}', 'missed 1 requests')
                shutil.rmtree(self.cfg['runs_root'])

    def test_a_run_marked_never_compared_with_does_not_block_the_recording(self):
        """#265: a run made with the wrong titles is marked never compared with; its misses are not the recording's."""
        record(self.cfg)
        self.ran('2026-11-11T090000Z-baseline', '2026-11-11T09:00:00Z', 0)
        self.ran('2026-11-11T100000Z-wrong-titles', '2026-11-11T10:00:00Z', 34, never_compared=True,
                 visits=[{'ok': False, 'played_source': None, 'misses': ['ninjacentral api t=search&q=x']}])
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_a_record_after_the_run_that_missed_passes_a_run(self):
        self.ran('2026-11-09T100000Z-baseline', '2026-11-09T10:00:00Z', 1840)
        record(self.cfg)  # the top-up, 2026-11-10T09:00:00Z
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_only_the_newest_run_on_the_same_recording_counts(self):
        record(self.cfg)
        self.ran('2026-11-11T100000Z-a', '2026-11-11T10:00:00Z', 12)
        self.ran('2026-11-12T100000Z-b', '2026-11-12T10:00:00Z', 0)
        self.ran('2026-11-13T100000Z-other', '2026-11-13T10:00:00Z', 99, recording='another-list')
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_a_recording_without_a_state_does_not_pass_a_run(self):
        record(self.cfg, state=None)
        self.assert_stops('run', self.world(), 'record command')

    def test_the_state_is_not_checked_for_a_record(self):
        record(self.cfg, state='stopped', why='x')
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_problems_come_back_as_a_list_for_the_record_command(self):
        record(self.cfg)
        self.assertEqual(retired_run.preflight('run', self.cfg, self.world()), [])
        self.assertEqual(len(retired_run.preflight('run', self.cfg, self.world(free=False))), 1)

    def test_mode_must_be_record_or_run(self):
        with self.assertRaises(ValueError):
            retired_run.preflight('smoke', self.cfg, self.world())


class MachineWiringTest(test_preflight.MachineWiringTest):
    class World(test_preflight.MachineWiringTest.World, retired_run.RetiredIO):
        pass

    def setUp(self):
        super().setUp()
        record(self.cfg)

    def preflight(self, mode, load):  # the retired preflights, by mode
        with mock.patch.object(subprocess, 'run', self.run_), mock.patch.object(os, 'getloadavg', lambda: (load, 0.2, 0.1)):
            return run_command(mode, self.cfg, self.World(self.cfg, allowance=PLENTY))

    def test_a_run_reads_the_load_the_addresses_and_the_dns_from_the_machine(self):
        code, text = self.preflight('run', 0.31)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.asked, ['ip', 'dig'])
        code, text = self.preflight('run', 1.52)
        self.assertEqual(code, 1, text)
        self.assertIn('load average is 1.52', text)

    def test_a_record_reads_the_addresses_and_the_dns_but_not_the_load(self):
        code, text = self.preflight('record', 4.0)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.asked, ['ip', 'dig'])


class PowerWiringTest(test_preflight.PowerWiringTest):
    class World(test_preflight.PowerWiringTest.World, retired_run.RetiredIO):
        pass

    def setUp(self):
        super().setUp()
        record(self.cfg)

    def preflight(self, mode, supplies, seen=None):  # the retired preflights, by mode
        with mock.patch.object(brainrun, 'POWER_SUPPLY_ROOT', supplies), \
                mock.patch.object(brainrun, 'CPUFREQ_ROOT', os.path.join(POWER, 'cpufreq')), \
                mock.patch.object(brainrun, 'PROBE_ROUNDS', 1000):
            return retired_run.preflight(mode, self.cfg, self.World(self.cfg, allowance=PLENTY), seen)

    def test_on_battery_a_run_and_a_record_stop(self):
        for mode in ('record', 'run'):
            problems = self.preflight(mode, power_tree(self, mains_online='0'))
            self.assertEqual(len(problems), 1, problems)
            self.assertIn('The machine runs on battery', problems[0])

    def test_plugged_in_or_without_a_mains_supply_a_run_passes_and_keeps_the_machine(self):
        for supplies in (os.path.join(POWER, 'power_supply'), power_tree(self, mains=False)):
            seen = {}
            self.assertEqual(self.preflight('run', supplies, seen), [])
            machine = seen['machine']
            self.assertEqual({k: v for k, v in machine.items() if k != 'cpu_probe_ms'},
                             {'power': 'ac', 'governor': 'powersave', 'energy_preference': 'performance'})
            self.assertIsInstance(machine['cpu_probe_ms'], int)


class AddressesTest(unittest.TestCase):
    def test_addresses_are_read_with_docker_inspect_for_test_containers_only(self):
        asked = []

        def run(argv, **kw):
            asked.append(argv)
            return R({'kaijuflow-test': '172.20.0.5\n'}.get(argv[-1], ''))

        self.assertEqual(retired_run.read_addresses(run=run), {'kaijuflow-test': '172.20.0.5'})
        self.assertEqual(retired_run.read_addresses(run=lambda argv, **kw: R('', 1)), {})  # a container that is not up: left out
        self.assertTrue(all(a[:2] == ['docker', 'inspect'] for a in asked))
        self.assertTrue(all(a[-1] in testbed.TEST_CONTAINERS for a in asked))
        self.assertTrue(all('kaijuflow-test-net' in a[3] for a in asked))


class FirstInARunTest(unittest.TestCase):
    def test_a_failing_preflight_stops_a_run_before_anything_starts(self):
        from test_brainrun import FakeIO, make_cfg as run_cfg
        tmp = tempdir(self)
        fake = FakeIO()
        fake.problems = ['Port 1340 is in use.']
        with self.assertRaises(brainrun.PreflightFailed):
            retired_run.run_all(run_cfg(tmp), fake)
        self.assertEqual(fake.calls, [])
        self.assertEqual(fake.calls_preflight, ['run'])
        self.assertFalse(os.path.exists(os.path.join(tmp, 'runs')))


MOVED = [('PreflightTest', 'test_correct_setup_passes_in_record_and_in_run'), ('PreflightTest', 'test_a_run_that_passes_names_the_machine_checks_too'), ('PreflightTest', 'test_a_machine_on_battery_stops_a_run_and_a_record'), ('PreflightTest', 'test_a_run_preflight_keeps_the_machine_it_judged_with_the_cpu_probe_taken_after_the_load_check'), ('PreflightTest', 'test_a_record_preflight_takes_no_cpu_probe'), ('PreflightTest', 'test_a_busy_machine_stops_a_run'), ('PreflightTest', 'test_a_machine_just_under_the_load_limit_passes_a_run'), ('PreflightTest', 'test_the_load_is_not_checked_for_a_record'), ('PreflightTest', 'test_after_its_image_build_a_run_preflight_waits_for_the_load_to_settle'), ('PreflightTest', 'test_a_load_that_does_not_settle_3_minutes_after_the_image_build_stops_a_run'), ('PreflightTest', 'test_a_run_preflight_hands_back_the_load_it_judged'), ('PreflightTest', 'test_a_host_ip_the_machine_does_not_have_stops_a_run_and_a_record'), ('PreflightTest', 'test_an_altmount_url_on_an_address_the_machine_does_not_have_stops_a_run_and_a_record'), ('PreflightTest', 'test_a_missing_host_ip_or_altmount_url_stops_a_run'), ('PreflightTest', 'test_a_sinkholed_newshosting_dns_stops_a_run_and_a_record'), ('PreflightTest', 'test_one_10_x_address_among_good_ones_stops_a_run'), ('PreflightTest', 'test_no_dns_answer_stops_a_run'), ('PreflightTest', 'test_key_file_missing_stops_record'), ('PreflightTest', 'test_key_file_readable_by_others_stops_record'), ('PreflightTest', 'test_key_file_with_other_indexers_stops_record'), ('PreflightTest', 'test_key_file_is_not_checked_in_run_mode'), ('PreflightTest', 'test_missing_recording_stops_run_but_not_record'), ('PreflightTest', 'test_recording_must_hold_an_answer_for_every_enabled_indexer'), ('PreflightTest', 'test_a_recording_that_stopped_early_says_so_and_gives_the_record_command'), ('PreflightTest', 'test_an_incomplete_recording_stops_a_run_and_says_why_with_the_record_command'), ('PreflightTest', 'test_a_last_run_whose_only_misses_are_releases_never_played_passes_a_run'), ('PreflightTest', 'test_a_last_run_that_missed_a_search_still_stops_a_run'), ('PreflightTest', 'test_a_recording_the_last_run_missed_stops_a_run_with_the_record_command'), ('PreflightTest', 'test_a_stopped_run_since_the_top_up_that_missed_still_blocks_the_recording'), ('PreflightTest', 'test_a_run_marked_never_compared_with_does_not_block_the_recording'), ('PreflightTest', 'test_a_record_after_the_run_that_missed_passes_a_run'), ('PreflightTest', 'test_only_the_newest_run_on_the_same_recording_counts'), ('PreflightTest', 'test_a_recording_without_a_state_does_not_pass_a_run'), ('PreflightTest', 'test_the_state_is_not_checked_for_a_record'), ('PreflightTest', 'test_problems_come_back_as_a_list_for_the_record_command'), ('PreflightTest', 'test_mode_must_be_record_or_run'), ('MachineWiringTest', 'test_a_run_reads_the_load_the_addresses_and_the_dns_from_the_machine'), ('MachineWiringTest', 'test_a_record_reads_the_addresses_and_the_dns_but_not_the_load'), ('PowerWiringTest', 'test_on_battery_a_run_and_a_record_stop'), ('PowerWiringTest', 'test_plugged_in_or_without_a_mains_supply_a_run_passes_and_keeps_the_machine')]


def load_tests(loader, tests, pattern):
    """Only the archived tests, not the live ones the classes inherit."""
    suite = unittest.TestSuite(globals()[c](n) for c, n in MOVED)
    suite.addTests(t for t in tests if not any(isinstance(x, tuple(globals()[c] for c, _ in MOVED)) for x in _flat(t)))
    return suite


def _flat(t):
    return [t] if isinstance(t, unittest.TestCase) else [x for s in t for x in _flat(s)]


if __name__ == '__main__':
    unittest.main()
