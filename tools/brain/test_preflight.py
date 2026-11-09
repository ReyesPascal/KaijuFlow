"""Tests for the preflight of brainrun.py (spec #72, ticket #74): one test per check, each asserting the exit code and the sentence.

Runs the real reader on fixture test copies in a temporary folder; only the Docker/git/port questions are faked.
    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

import brainrun
from test_settings import SECRET, make_copies

COMMIT = 'a' * 40


class FakeWorld(brainrun.RealIO):
    """RealIO reading the fixture folder, with the questions that need Docker, git or a port answered by hand."""

    def __init__(self, cfg, label=COMMIT, repo=COMMIT, dirty=False, free=True):
        super().__init__(cfg)
        self.label, self.repo, self.dirty, self.free = label, repo, dirty, free
        self.rebuilt = []

    def git_info(self):
        return self.repo, self.dirty

    def image_label(self):
        return self.label

    def rebuild_image(self, commit):
        self.rebuilt.append(commit)
        self.label = commit

    def port_free(self, port):
        return self.free


def make_cfg(td, **kw):
    cfg = dict(test_dir=td, store=os.path.join(os.path.dirname(td), 'store'), listname='l', limit=100, standin_port=1340,
               rebuild_image=False)
    cfg.update(kw)
    return cfg


def record(cfg, counts=None):
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
        code = brainrun.preflight_command(mode, cfg, world)
    return code, out.getvalue()


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.td = make_copies()
        self.cfg = make_cfg(self.td)

    def world(self, **kw):
        return FakeWorld(self.cfg, **kw)

    def assert_stops(self, mode, world, *fragments):
        code, text = run_command(mode, self.cfg, world)
        self.assertEqual(code, 1, text)
        for f in fragments:
            self.assertIn(f, text)
        self.assertNotIn(SECRET, text)
        self.assertEqual(len([line for line in text.splitlines() if line.strip()]), 1, text)  # one sentence per failure here

    def test_correct_setup_passes_in_record_and_in_run(self):
        record(self.cfg)
        for mode in ('record', 'run'):
            code, text = run_command(mode, self.cfg, self.world())
            self.assertEqual(code, 0, text)
            self.assertIn('Setup is right', text)

    def test_image_label_must_equal_the_repository_commit(self):
        self.assert_stops('record', self.world(label='b' * 40), 'built from commit bbbbbbb', 'aaaaaaa', '--rebuild-image')

    def test_image_without_label_stops(self):
        self.assert_stops('record', self.world(label=None), 'no commit label', '--rebuild-image')

    def test_dirty_tree_stops(self):
        self.assert_stops('record', self.world(dirty=True), 'uncommitted changes')

    def test_rebuild_option_builds_with_the_commit_then_passes(self):
        self.cfg['rebuild_image'] = True
        w = self.world(label='b' * 40)
        code, text = run_command('record', self.cfg, w)
        self.assertEqual((code, w.rebuilt), (0, [COMMIT]), text)

    def test_rebuild_option_does_not_build_for_a_dirty_tree(self):
        self.cfg['rebuild_image'] = True
        w = self.world(label='b' * 40, dirty=True)
        self.assert_stops('record', w, 'uncommitted changes')
        self.assertEqual(w.rebuilt, [])

    def test_key_file_missing_stops_record(self):
        os.remove(os.path.join(self.td, 'indexers.json'))
        self.assert_stops('record', self.world(), 'key file', 'missing')

    def test_key_file_readable_by_others_stops_record(self):
        os.chmod(os.path.join(self.td, 'indexers.json'), 0o644)
        self.assert_stops('record', self.world(), 'key file', 'only by you', 'chmod 600')

    def test_key_file_with_other_indexers_stops_record(self):
        td = make_copies(key_slugs=('ninjacentral', 'althub'))
        self.cfg = make_cfg(td)
        self.assert_stops('record', self.world(), 'althub', 'drunkenslug')

    def test_key_file_extra_per_indexer_setting_is_tolerated(self):
        with open(os.path.join(self.td, 'indexers.json'), 'w') as f:
            json.dump({'indexers': {'ninjacentral': {'url': 'u', 'apikey': SECRET},
                                    'drunkenslug': {'url': 'u', 'apikey': SECRET, 'drop_params': ['o']}}}, f)
        os.chmod(os.path.join(self.td, 'indexers.json'), 0o600)
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_key_file_is_not_checked_in_run_mode(self):
        os.remove(os.path.join(self.td, 'indexers.json'))
        record(self.cfg)
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_copies_must_agree_on_enabled_indexers(self):
        # AltMount's addon copy has DrunkenSlug switched off; the key file and the other copies use it
        self.cfg = make_cfg(make_copies(addon_off=('drunkenslug',)))
        self.assert_stops('record', self.world(), 'AltMount addon', 'drunkenslug')

    def test_indexer_address_must_be_the_standins(self):
        td = make_copies(url=lambda s: 'https://api.real-indexer.example/api' if s == 'ninjacentral' else
                         'http://host.docker.internal:1340/%s/api' % s)
        self.cfg = make_cfg(td)
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 1)
        self.assertIn('NinjaCentral', text)
        self.assertIn('not the stand-in', text)
        self.assertNotIn('real-indexer.example/api?', text)
        self.assertNotIn(SECRET, text)

    def test_an_address_with_a_key_in_it_is_never_printed(self):
        td = make_copies(url=lambda s: 'https://real.example/api?apikey=' + SECRET)
        self.cfg = make_cfg(td)
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 1)
        self.assertNotIn(SECRET, text)

    def test_caps_over_the_provider_limit_stop(self):
        td = make_copies(caps=(12, 12, 50, 50, 50))
        self.cfg = make_cfg(td)
        self.assert_stops('record', self.world(), '174', 'limit of 100')

    def test_caps_exactly_at_the_limit_pass(self):
        td = make_copies(caps=(12, 13, 25, 25, 25))
        self.cfg = make_cfg(td)
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_limit_is_settable(self):
        self.cfg['limit'] = 90
        self.assert_stops('record', self.world(), '99', 'limit of 90')

    def test_port_in_use_stops(self):
        self.assert_stops('record', self.world(free=False), 'port 1340', 'in use')

    def test_missing_recording_stops_run_but_not_record(self):
        self.assert_stops('run', self.world(), 'recording', 'record command')
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_recording_must_hold_an_answer_for_every_enabled_indexer(self):
        record(self.cfg, {'ninjacentral': 3})
        self.assert_stops('run', self.world(), 'drunkenslug')

    def test_problems_come_back_as_a_list_for_the_record_command(self):
        record(self.cfg)
        self.assertEqual(brainrun.preflight('run', self.cfg, self.world()), [])
        self.assertEqual(len(brainrun.preflight('run', self.cfg, self.world(free=False))), 1)

    def test_mode_must_be_record_or_run(self):
        with self.assertRaises(ValueError):
            brainrun.preflight('smoke', self.cfg, self.world())


class FirstInARunTest(unittest.TestCase):
    def test_a_failing_preflight_stops_a_run_before_anything_starts(self):
        from test_brainrun import FakeIO, make_cfg as run_cfg
        tmp = tempfile.mkdtemp()
        fake = FakeIO()
        fake.problems = ['Port 1340 is in use.']
        with self.assertRaises(brainrun.PreflightFailed):
            brainrun.run_all(run_cfg(tmp), fake)
        self.assertEqual(fake.calls, [])
        self.assertEqual(fake.calls_preflight, ['run'])
        self.assertFalse(os.path.exists(os.path.join(tmp, 'runs')))


if __name__ == '__main__':
    unittest.main()
