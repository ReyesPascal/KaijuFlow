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
        self.assertEqual(testbed.outside_named(br.flatten(data), names), testbed.outside_named(br.flatten(json.loads(self.before)), names))
        self.assertEqual(data['indexers'][0]['apiKey'], SECRET)  # the real values are written back, not the reader's ***
        uu = json.loads(read(os.path.join(self.td, 'uu/config/config.json')))
        self.assertEqual(uu['movieFilters']['maxFileSize'], 3000)  # only the named copy


    def test_a_missing_rule_and_an_extra_setting_are_named_once_each(self):
        mine = rules()
        mine['tvFilters']['rules']['rankedRegexPatterns'] = []
        mine['tvFilters']['minFileSize'] = 5
        td = make_copies(self, kf_rules=mine)
        code, text = apply(td, 'kaijuflow', write_expected(self, [{'copies': ['kaijuflow'], 'settings': rules()}]))
        self.assertEqual(code, 0, text)
        self.assertEqual(text.splitlines()[1:], [
            'KaijuFlow: tvFilters.rules: added',  # an empty list is no rule at all, as the preflight names it
            'KaijuFlow: tvFilters.minFileSize: removed (was 5)',
            'KaijuFlow: 2 settings changed in config/config.json.'])

    def test_applied_twice_the_second_time_says_nothing_changed_and_writes_nothing(self):
        apply(self.td, 'kaijuflow', self.expected)
        once = read(self.path)
        code, text = apply(self.td, 'kaijuflow', self.expected)
        self.assertEqual((code, text), (0, 'KaijuFlow: nothing changed; config/config.json already holds the expected settings.\n'))
        self.assertEqual(read(self.path), once)
        self.assertEqual(len(os.listdir(os.path.join(self.td, 'backups'))), 1)

    def test_a_copy_the_file_names_no_settings_for_is_refused(self):
        code, text = apply(self.td, 'altmount-kf', self.expected)
        self.assertEqual((code, text), (1, 'Nothing applied: the expected settings file holds no settings for AltMount KaijuFlow.\n'))
        code, text = apply(self.td, 'nzbdav', self.expected)
        self.assertEqual(code, 1)
        self.assertIn('nzbdav is not a test copy with a config file', text)
        self.assertFalse(os.path.exists(os.path.join(self.td, 'backups')))


class ApplyCommittedFileTest(unittest.TestCase):
    """The committed expected settings file, read as it is (so a change to it, such as AltMount direct's formats, is picked up)."""

    def setUp(self):
        self.td = make_copies(self, addon_lines=addon_stremio('stremio-as-found.yaml'))
        self.yaml = os.path.join(self.td, 'altmount-addon/config/config.yaml')

    def test_altmount_direct_as_captured_gets_its_three_settings_and_nothing_else(self):
        before = read(self.yaml)
        code, text = apply(self.td, 'altmount-addon')
        self.assertEqual(code, 0, text)
        backups = os.listdir(os.path.join(self.td, 'backups'))
        self.assertEqual(read(os.path.join(self.td, 'backups', backups[0])), before)
        self.assertEqual(text.splitlines()[1:], [
            'AltMount direct: stremio.max_fallback_releases: "2" -> "0"',
            'AltMount direct: stremio.include_library_streams: "null" -> "false"',
            'AltMount direct: stremio.scoring.custom_formats: added',
            'AltMount direct: 3 settings changed in altmount-addon/config/config.yaml.'])
        names = list(brainrun.load_expected_settings()[1]['settings'])
        self.assertEqual(testbed.outside_named(br.flatten_yaml(read(self.yaml)), names), testbed.outside_named(br.flatten_yaml(before), names))
        self.assertEqual(read(self.yaml).count('api_key: ' + SECRET), before.count('api_key: ' + SECRET))
        self.assertNotIn(SECRET, text)
        self.assertEqual(apply(self.td, 'altmount-addon')[1],
                         'AltMount direct: nothing changed; altmount-addon/config/config.yaml already holds the expected settings.\n')

    def test_after_applying_to_every_copy_the_preflight_finds_no_difference(self):
        cfg = make_cfg(self.td, expected_settings=None)
        code, text = run_command('record', cfg, FakeWorld(cfg))
        self.assertEqual(code, 1, text)
        self.assertIn('the expected settings file', text)
        for copy in ('kaijuflow', 'uu', 'altmount-addon'):
            code, out = apply(self.td, copy)
            self.assertEqual(code, 0, out)
            self.assertNotIn(SECRET, out)
        code, text = run_command('record', cfg, FakeWorld(cfg))
        self.assertEqual(code, 0, text)
        self.assertEqual(testbed.settings_report(self.td)['caps']['altmount-addon'], 25)  # the rest of the copy still reads


if __name__ == '__main__':
    unittest.main()
