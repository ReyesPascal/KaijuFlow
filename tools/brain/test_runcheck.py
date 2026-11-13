"""Tests for runcheck.py (can a finished run serve as a baseline?). No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import runcheck


@contextlib.contextmanager
def tempdir():
    d = tempfile.mkdtemp()
    try:
        yield d
    finally:
        shutil.rmtree(d, True)


FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-usable')


def copy_run(tmp):
    dest = os.path.join(tmp, 'run')
    shutil.copytree(FIXTURE, dest)
    return dest


def edit(run, name, fn):
    path = os.path.join(run, name)
    with open(path) as f:
        data = json.load(f)
    fn(data)
    with open(path, 'w') as f:
        json.dump(data, f)


def run_check(run, store=False):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = runcheck.check_command(run, store=store)
    return code, out.getvalue()


def visit_of(raw, side, phase, title=None):
    return [x for x in raw['visits'] if x['side'] == side and x['phase'] == phase and (title is None or x['title'] == title)][0]


class CheckTests(unittest.TestCase):
    def test_usable_run_exits_zero(self):
        with tempdir() as tmp:
            code, out = run_check(copy_run(tmp))
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith('Usable as a baseline'))
        self.assertIn('Top picks played, KaijuFlow: cold 2 of 2, warm 2 of 2.', out)
        self.assertIn('Missed requests: none.', out)
        self.assertIn('Sides with no import time: none.', out)
        self.assertIn('Failures: none.', out)

    def test_missed_request_exits_nonzero_and_names_it(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'raw.json', lambda raw: visit_of(raw, 'kaijuflow', 'warm', 'Beta').update(misses=['ninjacentral search abc']))
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertTrue(out.startswith('Not usable as a baseline: 1 requests missed the recording in 1 visits.'), out)
        self.assertIn('KaijuFlow warm 1: 1', out)
        self.assertIn('Missed in warm rounds (side, title, round): KaijuFlow Beta (1).', out)

    def test_absent_planned_side_exits_nonzero(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'meta.json', lambda m: m['sides'].append('uu'))
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertIn('planned side absent: Usenet Ultimate', out.splitlines()[0])

    def test_null_run_exits_nonzero(self):
        with tempdir() as tmp:
            run = copy_run(tmp)

            def null(m):
                m['status'] = 'null'
                m['null'] = {'indexer': 'ninjacentral', 'time': '2026-01-01T00:01:00Z', 'where': 'search'}
            edit(run, 'meta.json', null)
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertIn('the run is null (ninjacentral said its limit was reached', out.splitlines()[0])

    def test_failed_run_exits_nonzero(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'meta.json', lambda m: m.update(status='failed', error='RuntimeError: boom'))
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertIn('the run did not finish (RuntimeError: boom)', out)

    def test_stopped_run_exits_nonzero(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'meta.json', lambda m: m.update(status='stopped', stopped={
                'time': '2026-01-01T00:03:00.000Z', 'plays_done': 5, 'plays_planned': 8, 'during': None}))
            code, out = run_check(run)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], 'Not usable as a baseline: the run was stopped by hand at 2026-01-01T00:03:00.000Z: '
                                              '5 of 8 plays had finished, and it stopped between two plays.')

    def test_unreadable_folder_exits_nonzero(self):
        with tempdir() as tmp:
            code, out = run_check(os.path.join(tmp, 'nothing'))
        self.assertNotEqual(code, 0)
        self.assertIn('meta.json is missing', out)

    def test_failure_cause_and_step_gap_are_listed(self):
        with tempdir() as tmp:
            run = copy_run(tmp)

            def bad(raw):
                visit_of(raw, 'altmount-addon', 'cold').update(ok=False, note='HTTP 503')
                visit_of(raw, 'kaijuflow', 'cold').update(start_s=4.0)
            edit(run, 'raw.json', bad)
            code, out = run_check(run)
        self.assertEqual(code, 0)  # a failed play alone does not stop a baseline; only misses, an absent side or a null run do
        self.assertIn("- AltMount's own addon, cold 1, Alpha: HTTP 503", out)
        self.assertIn('KaijuFlow, cold 1, Alpha (', out)

    def test_side_without_import_time_is_named(self):
        with tempdir() as tmp:
            run = copy_run(tmp)

            def strip(raw):
                for v in raw['visits']:
                    if v['side'] == 'altmount-addon':
                        v['imports'] = []
            edit(run, 'raw.json', strip)
            _, out = run_check(run)
        self.assertIn("Sides with no import time: AltMount's own addon.", out)

    def test_store_writes_check_file(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            _, out = run_check(run, store=True)
            with open(os.path.join(run, runcheck.CHECK_FILE)) as f:
                self.assertEqual(f.read(), out)


if __name__ == '__main__':
    unittest.main()
