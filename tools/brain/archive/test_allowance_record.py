"""The archived tests of test_allowance.py (ADR 0010, #273): the record preflight's allowance table and warnings.
"""
import unittest

import test_allowance
from test_allowance import *  # noqa: F401,F403  (the live file's helpers)
import retired_run  # noqa: F401
from test_preflight import FakeWorld, make_cfg  # noqa: F401
from test_preflight_retired import record, run_command  # noqa: F401
from test_settings import make_copies  # noqa: F401


class AllowanceTest(test_allowance.AllowanceTest):
    def test_last_complete_recording_of_the_same_list_only(self):
        record_folder(self.runs, '1-record', 'l', [api('RECORD', hours_ago(9))] * 2)
        record_folder(self.runs, '2-record', 'l', [api('RECORD', hours_ago(8))] * 5, status='null')  # stopped early
        record_folder(self.runs, '3-record', 'other', [api('RECORD', hours_ago(7))] * 7)
        name, counts = retired_run.last_complete_recording(self.runs, 'l')
        self.assertEqual(name, '1-record')
        self.assertEqual(counts, {'ninjacentral': {'search': 2, 'download': 0}})
        self.assertIsNone(retired_run.last_complete_recording(self.runs, 'none'))

    def test_record_preflight_shows_table_and_last_count_and_warns_when_short(self):
        limits_file(self.limits)
        record_folder(self.runs, '1-record', 'l', [api('RECORD', hours_ago(30))] * 2100)
        text = '\n'.join(retired_run.record_preflight_lines(self.cfg, NOW))
        self.assertIn('searches       0    2000    2000', text)
        self.assertIn('sent 2100 requests', text)
        self.assertIn('Warning: ninjacentral has 2000 searches left but the last full recording needed 2100', text)

    def test_record_preflight_has_no_warning_when_it_fits(self):
        limits_file(self.limits)
        record_folder(self.runs, '1-record', 'l', [api('RECORD', hours_ago(30))] * 10)
        text = '\n'.join(retired_run.record_preflight_lines(self.cfg, NOW))
        self.assertIn('sent 10 requests', text)
        self.assertNotIn('Warning', text)

    def test_record_preflight_without_limits_file_or_earlier_recording_says_so(self):
        text = '\n'.join(retired_run.record_preflight_lines(self.cfg, NOW))
        self.assertIn('no key file', text)
        self.assertIn('no earlier complete recording', text)

    def test_preflight_for_record_warns_but_does_not_block(self):
        copies = make_copies(self)
        cfg = make_cfg(copies, runs_root=self.runs)
        record(cfg)
        limits_file(os.path.join(copies, 'indexers.json'), search=1)
        record_folder(self.runs, '1-record', 'l', [api('RECORD', hours_ago(30))] * 50)
        code, text = run_command('record', cfg, FakeWorld(cfg))
        self.assertEqual(code, 0, text)
        self.assertIn('Warning: ninjacentral', text)
        self.assertIn('sent 50 requests', text)
        self.assertIn('Setup is right for a record', text)


MOVED = [('AllowanceTest', 'test_last_complete_recording_of_the_same_list_only'), ('AllowanceTest', 'test_record_preflight_shows_table_and_last_count_and_warns_when_short'), ('AllowanceTest', 'test_record_preflight_has_no_warning_when_it_fits'), ('AllowanceTest', 'test_record_preflight_without_limits_file_or_earlier_recording_says_so'), ('AllowanceTest', 'test_preflight_for_record_warns_but_does_not_block')]


def load_tests(loader, tests, pattern):
    """Only the archived tests, not the live ones the classes inherit."""
    suite = unittest.TestSuite(globals()[c](n) for c, n in MOVED)
    suite.addTests(t for t in tests if not any(isinstance(x, tuple(globals()[c] for c, _ in MOVED)) for x in _flat(t)))
    return suite


def _flat(t):
    return [t] if isinstance(t, unittest.TestCase) else [x for s in t for x in _flat(s)]


if __name__ == '__main__':
    unittest.main()
