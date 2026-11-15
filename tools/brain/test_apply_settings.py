"""Tests for `testbed.py apply <copy>` (ticket #163): the expected settings written into one test copy's config.

Fixture test copies in a temporary folder with a planted fake key; nothing real is read or written.
    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import unittest

import brainreport as br
import brainrun
import testbed
from test_preflight import FakeWorld, make_cfg, run_command
from test_settings import SECRET, addon_stremio, make_copies, rules, tempdir

STAMP = '20261115T120000Z'


def apply(td, copy, expected=None):
    """Runs the command as the owner would, with TEST_DIR pointing at the fixture folder; returns (exit code, output)."""
    out = io.StringIO()
    old = os.environ.get('TEST_DIR')
    os.environ['TEST_DIR'] = td
    try:
        with contextlib.redirect_stdout(out):
            code = testbed.main(['testbed.py', 'apply', copy] + (['--expected', expected] if expected else []))
    finally:
        if old is None:
            del os.environ['TEST_DIR']
        else:
            os.environ['TEST_DIR'] = old
    return code, out.getvalue()


def read(path):
    with open(path) as f:
        return f.read()


def write_expected(case, entries):
    path = os.path.join(tempdir(case), 'expected-settings.json')
    with open(path, 'w') as f:
        json.dump({'expected': entries}, f)
    return path


def outside(flat, names):
    """The settings of a flat map that are not at or below one of `names`."""
    return {k: v for k, v in flat.items() if not any(k == n or k.startswith((n + '.', n + '[')) for n in names)}


class ApplyJsonCopyTest(unittest.TestCase):
    def setUp(self):
        self.td = make_copies(self)
        self.path = os.path.join(self.td, 'config/config.json')
        self.before = read(self.path)
        want = rules()
        want['movieFilters']['maxFileSize'] = 9000
        want['movieFilters']['sortOrder'] = ['size', 'quality', 'language']
        want['tvFilters']['enabledSorts']['language'] = True
        self.expected = write_expected(self, [{'copies': ['kaijuflow', 'uu'], 'settings': want}])

    def test_the_copy_is_backed_up_the_values_written_and_the_changes_printed_one_by_one(self):
        code, text = apply(self.td, 'kaijuflow', self.expected)
        self.assertEqual(code, 0, text)
        backups = os.listdir(os.path.join(self.td, 'backups'))
        self.assertEqual(len(backups), 1, backups)
        self.assertEqual(read(os.path.join(self.td, 'backups', backups[0])), self.before)  # the copy as it was
        self.assertTrue(backups[0].startswith('kaijuflow-') and backups[0].endswith('-config.json'), backups)
        lines = text.splitlines()
        self.assertEqual(lines[0], f'KaijuFlow: config/config.json backed up to backups/{backups[0]}.')
        self.assertEqual(lines[1:-1], [
            'KaijuFlow: movieFilters.sortOrder: ["quality", "size", "language"] -> ["size", "quality", "language"]',
            'KaijuFlow: movieFilters.maxFileSize: 3000 -> 9000',
            'KaijuFlow: tvFilters.enabledSorts.language: false -> true'])
        self.assertEqual(lines[-1], 'KaijuFlow: 3 settings changed in config/config.json.')
        self.assertNotIn(SECRET, text)

    def test_every_other_setting_is_left_as_it_was_and_the_keys_stay_in_the_file(self):
        apply(self.td, 'kaijuflow', self.expected)
        data = json.loads(read(self.path))
        self.assertEqual(data['movieFilters']['maxFileSize'], 9000)
        names = ['movieFilters', 'tvFilters']
        self.assertEqual(outside(br.flatten(data), names), outside(br.flatten(json.loads(self.before)), names))
        self.assertEqual(data['indexers'][0]['apiKey'], SECRET)  # the real values are written back, not the reader's ***
        uu = json.loads(read(os.path.join(self.td, 'uu/config/config.json')))
        self.assertEqual(uu['movieFilters']['maxFileSize'], 3000)  # only the named copy


if __name__ == '__main__':
    unittest.main()
