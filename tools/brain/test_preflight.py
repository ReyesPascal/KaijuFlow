"""Tests for the preflight of brainrun.py (spec #72, ticket #74): one test per check, each asserting the exit code and the sentence.

Runs the real reader on fixture test copies in a temporary folder; only the Docker/git/port questions are faked.
The tests of ticket #113 (which commits ask for a new image) put those git questions to the real git, in a small temporary repository.
    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import re
import subprocess
import unittest

import brainreport as br
import brainrun
import testbed
from test_settings import ALTMOUNT_FIXTURES, SECRET, addon_stremio, make_copies, rules, tempdir

COMMIT = 'a' * 40
OLDER = 'b' * 40


class FakeWorld(brainrun.RealIO):
    """RealIO reading the fixture folder, with the questions that need Docker, git or a port answered by hand.

    `changed` is what its repository knows: {an earlier commit: whether a build input changed between it and `head`}. Asked
    about any other commit it has no answer, as git has none for a commit the repository does not have.
    """

    def __init__(self, cfg, label=COMMIT, head=COMMIT, dirty=False, free=True, changed=None):
        super().__init__(cfg)
        self.label, self.head, self.dirty, self.free, self.changed = label, head, dirty, free, dict(changed or {})
        self.repo = None  # no real repository behind this world
        self.rebuilt = []

    def git_info(self):
        return self.head, self.dirty

    def build_inputs_changed(self, since):
        return self.changed.get(since)

    def image_label(self):
        return self.label

    def rebuild_image(self, commit):
        self.rebuilt.append(commit)
        self.label = commit

    def port_free(self, port):
        return self.free


class RepoWorld(FakeWorld):
    """FakeWorld whose git questions go to the real git in a small repository of its own, so only the image is answered by hand."""

    def __init__(self, cfg, repo, label):
        super().__init__(cfg, label=label)
        self.repo = repo

    git_info = brainrun.RealIO.git_info
    build_inputs_changed = brainrun.RealIO.build_inputs_changed


def git(repo, *args):
    return subprocess.check_output(['git', '-C', repo, '-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
                                    '-c', 'commit.gpgsign=false', *args], text=True, stderr=subprocess.STDOUT).strip()


def put(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def commit(repo, files):
    """Commits {path: text} in the repository and returns the new commit."""
    for rel, text in files.items():
        put(repo, rel, text)
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'change ' + ', '.join(sorted(files)))
    return git(repo, 'rev-parse', 'HEAD')


def make_repo(case):
    """A git repository with one commit that holds something of everything: code that goes into the image, and files that do not."""
    repo = os.path.join(tempdir(case), 'repo')
    os.makedirs(repo)
    git(repo, 'init', '-q')
    first = commit(repo, {'src/server.ts': 'one', 'ui/src/App.tsx': 'one', 'ui/package.json': '{}', 'package.json': '{}',
                          'package-lock.json': '{}', 'tsconfig.json': '{}', 'tsconfig.test.json': '{}', 'Dockerfile': 'FROM scratch',
                          '.dockerignore': 'dist/', 'scripts/docker-entrypoint.sh': 'one', 'scripts/docker-build.sh': 'one',
                          'docs/note.md': 'one', 'README.md': 'one', 'tools/brain/brainrun.py': 'one', 'tests/a.test.ts': 'one'})
    return repo, first


def write_expected(td, entries=None):
    """Writes the expected settings file of a fixture folder (by default: both copies hold rules()) and returns its path."""
    path = os.path.join(os.path.dirname(td), 'expected-settings.json')
    with open(path, 'w') as f:
        json.dump({'expected': [{'copies': ['kaijuflow', 'uu'], 'settings': rules()}] if entries is None else entries}, f)
    return path


def make_cfg(td, **kw):
    cfg = dict(test_dir=td, store=os.path.join(os.path.dirname(td), 'store'), listname='l', limit=100, standin_port=1340,
               rebuild_image=False, expected_settings=write_expected(td))
    cfg.update(kw)
    return cfg


def record(cfg, counts=None, state='complete', why=None):
    os.makedirs(os.path.join(cfg['store'], cfg['listname']), exist_ok=True)
    if state:
        with open(os.path.join(cfg['store'], cfg['listname'], brainrun.RECORDING_FILE), 'w') as f:
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
        code = brainrun.preflight_command(mode, cfg, world)
    return code, out.getvalue()


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.td = make_copies(self)
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
            self.assertIn('connection caps, sort and filter settings and port all check out', text)

    def test_image_from_an_earlier_commit_stops_when_a_build_input_changed_since(self):
        self.assert_stops('record', self.world(label=OLDER, changed={OLDER: True}),
                          'built from commit bbbbbbb', 'has changed since then', 'aaaaaaa', '--rebuild-image')

    def test_image_from_a_commit_the_repository_does_not_have_stops(self):
        self.assert_stops('record', self.world(label=OLDER), 'built from commit bbbbbbb, which this repository does not have',
                          'aaaaaaa', '--rebuild-image')

    def test_image_without_label_stops(self):
        self.assert_stops('record', self.world(label=None), 'does not say which commit', '--rebuild-image')

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

    def test_key_file_sentence_says_how_to_fix_it_in_plain_words(self):
        os.chmod(os.path.join(self.td, 'indexers.json'), 0o644)
        _code, text = run_command('record', self.cfg, self.world())
        path = os.path.join(self.td, 'indexers.json')
        self.assertIn(f'make the key file readable only by you (run: chmod 600 {path})', text)

    def test_the_indexer_stand_in_is_explained_once_by_that_name(self):
        td = make_copies(self, url=lambda s: 'https://real.example/api?x=1')
        self.cfg = make_cfg(td)
        _code, text = run_command('record', self.cfg, self.world())
        self.assertIn('indexer stand-in (the local program that replays recorded indexer answers', text)
        self.assertEqual(text.count('local program that replays'), 1)
        self.assertNotIn('the stand-in', text.replace('the indexer stand-in', ''))

    def test_key_file_readable_by_others_stops_record(self):
        os.chmod(os.path.join(self.td, 'indexers.json'), 0o644)
        self.assert_stops('record', self.world(), 'key file', 'only by you', 'chmod 600')

    def test_key_file_with_other_indexers_stops_record(self):
        td = make_copies(self, key_slugs=('ninjacentral', 'althub'))
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
        self.cfg = make_cfg(make_copies(self, addon_off=('drunkenslug',)))
        self.assert_stops('record', self.world(), 'AltMount direct', 'drunkenslug')

    def test_indexer_address_must_be_the_standins(self):
        td = make_copies(self, url=lambda s: 'https://api.real-indexer.example/api' if s == 'ninjacentral' else
                         'http://host.docker.internal:1340/%s/api' % s)
        self.cfg = make_cfg(td)
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 1)
        self.assertIn('NinjaCentral', text)
        self.assertIn('not the indexer stand-in', text)
        self.assertNotIn('real-indexer.example/api?', text)
        self.assertNotIn(SECRET, text)

    def test_an_address_with_a_key_in_it_is_never_printed(self):
        td = make_copies(self, url=lambda s: 'https://real.example/api?apikey=' + SECRET)
        self.cfg = make_cfg(td)
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 1)
        self.assertNotIn(SECRET, text)

    def test_caps_over_the_provider_limit_stop(self):
        td = make_copies(self, caps=(12, 12, 50, 50, 50))
        self.cfg = make_cfg(td)
        self.assert_stops('record', self.world(), '174', 'limit of 100')

    def test_caps_exactly_at_the_limit_pass(self):
        td = make_copies(self, caps=(12, 13, 25, 25, 25))
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

    def test_a_recording_that_stopped_early_says_so_and_gives_the_record_command(self):
        record(self.cfg, state='stopped', why='drunkenslug said its limit was reached')
        self.cfg['topup_command'] = 'python3 -I tools/brain/brainrun.py record --name n --store S --list l'
        self.assert_stops('run', self.world(), 'stopped early', 'drunkenslug said its limit was reached', '2026-11-10',
                          'python3 -I tools/brain/brainrun.py record --name n --store S --list l')

    def test_an_incomplete_recording_stops_a_run_and_says_why_with_the_record_command(self):
        record(self.cfg, state='incomplete', why='the proof replay missed 2 requests (AltMount addon asked fake t=search&q=tt1)')
        self.cfg['topup_command'] = 'python3 -I tools/brain/brainrun.py record --name n --store S --list l'
        self.assert_stops('run', self.world(), 'incomplete', 'missed 2 requests', 'AltMount addon asked',
                          'python3 -I tools/brain/brainrun.py record --name n --store S --list l')

    def test_a_recording_without_a_state_does_not_pass_a_run(self):
        record(self.cfg, state=None)
        self.assert_stops('run', self.world(), 'record command')

    def test_the_state_is_not_checked_for_a_record(self):
        record(self.cfg, state='stopped', why='x')
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 0, text)

    def test_problems_come_back_as_a_list_for_the_record_command(self):
        record(self.cfg)
        self.assertEqual(brainrun.preflight('run', self.cfg, self.world()), [])
        self.assertEqual(len(brainrun.preflight('run', self.cfg, self.world(free=False))), 1)

    def test_mode_must_be_record_or_run(self):
        with self.assertRaises(ValueError):
            brainrun.preflight('smoke', self.cfg, self.world())

    # ---- the sort and filter settings of each copy against the expected settings file (ticket #109)
    def test_a_copy_whose_size_cap_differs_from_the_expected_file_stops(self):
        self.cfg = make_cfg(make_copies(self, kf_rules=rules(films=9000)))
        for mode in ('record', 'run'):
            record(self.cfg)
            self.assert_stops(mode, self.world(), 'KaijuFlow has movieFilters.maxFileSize set to 9000',
                              'the expected settings file', 'says 3000')

    def test_every_differing_setting_gets_its_own_sentence_and_the_fix_is_explained_once(self):
        theirs = rules(episodes=50)
        theirs['tvFilters']['rules']['rankedRegexPatterns'][0]['mode'] = 'rank'
        self.cfg = make_cfg(make_copies(self, kf_rules=rules(films=9000), uu_rules=theirs))
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 1, text)
        self.assertEqual(text.splitlines(), [
            'KaijuFlow has movieFilters.maxFileSize set to 9000, but the expected settings file '
            f"({self.cfg['expected_settings']}) says 3000: change the test copy's config, or the file if the copy's value is the intended one.",
            'Usenet Ultimate has tvFilters.maxFileSize set to 50, but the expected settings file says 1000.',
            'Usenet Ultimate has tvFilters.rules.rankedRegexPatterns[No disc images].mode set to "rank", '
            'but the expected settings file says "drop".'])

    def test_a_copy_without_any_sort_and_filter_rules_stops_with_one_sentence_per_missing_section(self):
        # the state found in the retro of the 2026-11-13 baseline: the copies had no filters, movieFilters or tvFilters
        self.cfg = make_cfg(make_copies(self, uu_rules={}))
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 1, text)
        self.assertEqual([line.split(', but')[0] for line in text.splitlines()],
                         ['Usenet Ultimate has no movieFilters setting', 'Usenet Ultimate has no tvFilters setting'])
        self.assertTrue(text.splitlines()[1].endswith(', but the expected settings file has one.'), text)

    def test_a_missing_rule_and_a_rule_of_the_copys_own_get_one_sentence_each(self):
        theirs = rules()
        theirs['movieFilters']['rules']['rankedRegexPatterns'] = [dict(theirs['movieFilters']['rules']['rankedRegexPatterns'][0], name='Mine')]
        theirs['tvFilters']['minFileSize'] = 5
        del theirs['tvFilters']['enabledSorts']['language']
        self.cfg = make_cfg(make_copies(self, kf_rules=theirs))
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 1, text)
        self.assertEqual([line.split(': change')[0].replace(f" ({self.cfg['expected_settings']})", '').rstrip('.') for line in text.splitlines()], [
            'KaijuFlow has no movieFilters.rules.rankedRegexPatterns[No disc images] setting, but the expected settings file has one',
            'KaijuFlow has a movieFilters.rules.rankedRegexPatterns[Mine] setting that the expected settings file does not have',
            'KaijuFlow has no tvFilters.enabledSorts.language setting, but the expected settings file has one',
            'KaijuFlow has a tvFilters.minFileSize setting that the expected settings file does not have'])

    def test_an_expected_settings_file_that_cannot_be_used_stops_with_one_sentence(self):
        write_expected(self.td, entries=[{'copies': ['kaijuflow', 'live'], 'settings': rules()}])
        self.assert_stops('record', self.world(), 'The expected settings file cannot be used (expected-settings.json, entry 1: '
                          '"live" is not a test copy (kaijuflow, uu, nzbdav, altmount-addon, altmount-kf)): fix the file.')
        os.remove(self.cfg['expected_settings'])
        self.assert_stops('record', self.world(), 'The expected settings file cannot be used (expected-settings.json cannot be read: '
                          'FileNotFoundError): fix the file.')

    def test_an_order_that_differs_is_one_setting_and_one_sentence(self):
        theirs = rules()
        theirs['movieFilters']['sortOrder'] = ['quality', 'language', 'size']  # two entries swapped
        theirs['tvFilters']['sortOrder'] = ['quality', 'size']  # one entry short
        self.cfg = make_cfg(make_copies(self, kf_rules=theirs))
        code, text = run_command('record', self.cfg, self.world())
        self.assertEqual(code, 1, text)
        self.assertEqual([line.split(': change')[0].replace(f" ({self.cfg['expected_settings']})", '').rstrip('.') for line in text.splitlines()], [
            'KaijuFlow has movieFilters.sortOrder entry 2 set to "language", but the expected settings file says "size" '
            '(the first entry that differs)',
            'KaijuFlow has no tvFilters.sortOrder entry 3, but the expected settings file says "language"'])


class SettingDifferencesTest(unittest.TestCase):
    """Ticket #109: the comparison with the expected settings on its own, plain data in and sentences out."""

    EXPECTED = [{'copies': ['kaijuflow', 'uu'], 'settings': {'movieFilters': {'maxFileSize': 30, 'sortOrder': ['a', 'b'], 'none': []}}},
                {'copies': ['altmount-kf'], 'settings': {'import.max_processor_workers': '2'}}]

    def settings(self, **changes):
        """What the settings reader gives for copies that match EXPECTED, then changed: settings(kaijuflow={name: value})."""
        rules_ = {'movieFilters.maxFileSize': 30, 'movieFilters.sortOrder[0]': 'a', 'movieFilters.sortOrder[1]': 'b',
                  'movieFilters.none': '[]', 'cacheTTL': 9000, 'healthChecks.maxConnections': 12}
        got = {'kaijuflow': dict(rules_), 'uu': dict(rules_), 'nzbdav': {'usenet.max-download-connections': '25'},
               'altmount-addon': {'import.max_processor_workers': '8'}, 'altmount-kf': {'import.max_processor_workers': '2'}}
        for side, change in changes.items():
            got[side.replace('_', '-')].update(change)
        return got

    def test_copies_that_match_give_no_sentence(self):
        self.assertEqual(brainrun.setting_differences(self.EXPECTED, self.settings()), [])

    def test_only_the_named_settings_of_the_named_copies_are_compared(self):
        got = self.settings(kaijuflow={'cacheTTL': 1, 'tvFilters.maxFileSize': 5}, nzbdav={'x': 1}, altmount_addon={'import.max_processor_workers': '1'})
        self.assertEqual(brainrun.setting_differences(self.EXPECTED, got), [])

    def test_a_setting_can_be_named_by_its_dotted_name_for_any_copy(self):
        got = self.settings(altmount_kf={'import.max_processor_workers': '4'})
        self.assertEqual(brainrun.setting_differences(self.EXPECTED, got, 'F'), [
            'AltMount KaijuFlow has import.max_processor_workers set to "4", but the expected settings file (F) says "2": '
            "change the test copy's config, or the file if the copy's value is the intended one."])

    def test_an_entry_too_many_in_an_order_and_an_order_that_should_be_empty(self):
        got = self.settings(uu={'movieFilters.sortOrder[2]': 'c', 'movieFilters.none[0]': 'x'})
        del got['uu']['movieFilters.none']  # the reader writes an empty list as '[]', a filled one entry by entry
        self.assertEqual(brainrun.setting_differences(self.EXPECTED, got)[1:], [
            'Usenet Ultimate has movieFilters.none entry 1 set to "x", but the expected settings file has no entry 1.'])
        self.assertIn('Usenet Ultimate has movieFilters.sortOrder entry 3 set to "c", but the expected settings file '
                      'has no entry 3: change', brainrun.setting_differences(self.EXPECTED, got)[0])

    def test_a_copy_whose_config_cannot_be_read_is_left_to_the_checks_that_say_so(self):
        got = self.settings()
        got['kaijuflow'] = {'(file missing)': 'config/config.json'}  # what the settings reader gives for a missing config
        self.assertEqual(brainrun.setting_differences(self.EXPECTED, got), [])


class ExpectedSettingsFileTest(unittest.TestCase):
    """Ticket #109: the expected settings file itself, the committed one and one that cannot be used."""

    def load(self, content):
        path = os.path.join(tempdir(self), 'expected-settings.json')
        with open(path, 'w') as f:
            f.write(content if isinstance(content, str) else json.dumps(content))
        return brainrun.load_expected_settings(path)

    def refused(self, content):
        with self.assertRaises(ValueError) as caught:
            self.load(content)
        return str(caught.exception)

    def test_a_usable_file_gives_its_entries(self):
        entries = [{'copies': ['kaijuflow', 'uu'], 'settings': rules()}]
        self.assertEqual(self.load({'about': 'x', 'expected': entries}), entries)

    def test_a_file_that_cannot_be_used_says_why_in_plain_words(self):
        self.assertEqual(self.refused('{not json'), 'expected-settings.json cannot be read: JSONDecodeError')
        self.assertEqual(self.refused({'copies': []}), 'expected-settings.json cannot be read: it has no "expected" list')
        self.assertEqual(self.refused({'expected': [{'copies': ['kaijuflow', 'live'], 'settings': {'a': 1}}]}),
                         'expected-settings.json, entry 1: "live" is not a test copy (kaijuflow, uu, nzbdav, altmount-addon, altmount-kf)')
        self.assertEqual(self.refused({'expected': [{'copies': ['uu'], 'settings': {'a': 1}}, {'copies': ['uu'], 'settings': {}}]}),
                         'expected-settings.json, entry 2: it names no settings')
        self.assertEqual(self.refused({'expected': [{'copies': [], 'settings': {'a': 1}}]}),
                         'expected-settings.json, entry 1: it names no copies')
        with self.assertRaises(ValueError) as caught:
            brainrun.load_expected_settings(os.path.join(tempdir(self), 'none.json'))
        self.assertEqual(str(caught.exception), 'none.json cannot be read: FileNotFoundError')

    def test_a_key_a_login_or_a_password_is_refused_and_not_repeated(self):
        why = self.refused({'expected': [{'copies': ['kaijuflow'], 'settings': {
            'movieFilters': {'maxFileSize': 1}, 'healthChecks': {'providers': [{'name': 'p', 'password': SECRET}]}}}]})
        self.assertEqual(why, 'expected-settings.json, entry 1: healthChecks.providers[p].password is a key, a login or a password, '
                              'which does not belong in this file')
        self.assertIn('altmountApiKey', self.refused({'expected': [{'copies': ['kaijuflow'], 'settings': {'altmountApiKey': SECRET}}]}))
        self.assertNotIn(SECRET, why)

    # ---- the committed file: the standard rules the owner defined in issue #109 on 2026-11-13
    DROP = r'\bCOMPLETE[. _-](UHD[. _-])?BLU-?RAY\b|\bBDMV\b|\b(UHD|BD)[. _-]?ISO\b|\bBD(25|50|66|100)\b'

    def committed(self):
        entries = brainrun.load_expected_settings()
        self.assertEqual([e['copies'] for e in entries], [['kaijuflow', 'uu'], ['altmount-addon']])  # NzbDAV has no such rules
        return entries[0]['settings']

    def test_the_committed_file_holds_altmount_directs_like_for_like_settings(self):
        entry = brainrun.load_expected_settings()[1]['settings']
        self.assertEqual((entry['stremio.max_fallback_releases'], entry['stremio.include_library_streams']), (0, False))  # one try
        formats = entry['stremio.scoring.custom_formats']
        self.assertEqual([(f['name'], f['score']) for f in formats],
                         [('2160p', 400), ('1080p', 300), ('720p', 200), ('4K words beside 1080p or 720p', -400),
                          ('No disc images', -10000)])  # 4K first; -1500 or below drops
        self.assertEqual(formats[-1]['pattern'], '(?i)' + self.DROP)  # the same rule as KaijuFlow's and Usenet Ultimate's
        self.assertEqual(self.committed()['movieFilters']['rules']['rankedRegexPatterns'][0]['pattern'], self.DROP)
        titles = {'Film.2010.2160p.UHD.BluRay.REMUX': '2160p', 'Film.2010.UHD.BluRay': '2160p', 'Film.2010.1080p.WEB-DL': '1080p',
                  'Film 2010 1080i HDTV': '1080p', 'Show.S01E02.720p.WEB': '720p', 'Film.2010.COMPLETE.UHD.BLURAY': 'No disc images',
                  'Film.2010.BDMV': 'No disc images', 'Film.2010.DVDRip': None}
        for title, want in titles.items():  # on ASCII titles Python's re and Go's RE2 read these patterns alike
            hit = [f['name'] for f in formats if re.search(f['pattern'], title)]
            self.assertEqual(hit[-1:] if want == 'No disc images' else hit, [want] if want else [], title)

    def test_altmount_directs_formats_score_test_1s_releases_by_their_stated_resolution(self):
        # AltMount v0.4.0 adds the score of every enabled format a title matches (internal/stremio/scorer.go,
        # EvaluateRelease), so "1080p UHD" took 2160p's 400 and 1080p's 300 and beat real 4K in Test 1 (#154).
        formats = brainrun.load_expected_settings()[1]['settings']['stremio.scoring.custom_formats']
        score = {'2160p': 400, '1080p': 300, '720p': 200, None: 0}
        for title, want in {  # top picks of Test 1 (2026-11-15T115540Z-baseline), and the names around them
                'Inception 2010 PROPER 1080p UHD BluRay DD+5.1 x264-LoRD': '1080p',
                'Interstellar 2014 UHD BluRay 1080p DDP 5 1 DoVi HDR10 x265-SM737': '1080p',
                'Oppenheimer 2023 REPACK IMAX 1080p UHD BluRay DoVi HDR10 DD 5 1 x265': '1080p',
                'The Matrix 1999 4K Remaster 1080p BluRay DTS x264-Geek': '1080p',
                'Dune 2021 1080p UHD BluRay x265 HDR DD 5 1-Pahe in': '1080p',
                'Pulp.Fiction.1994.PROPER.UHD.BluRay.1080p.DDP.5.1.DoVi.HDR10.x265-S': '1080p',
                'Chernobyl.2019.S01E02.1080p.UHD.BDRip.DV.HDR.DDP5.1.x265.Vialle': '1080p',
                'Breaking.Bad.S01E01.POLISH.2160p.WEB.H265-FLAME': '2160p',
                'Inception.2010.2160p.UHD.Bluray.x265.HDR10.DTS-HDMA.5.1-4K4U': '2160p',
                'Dune.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HDR.AV1-CoSMiCSuRFeR': '2160p',
                'Film.2010.UHD.BluRay.x265': '2160p', 'Show.S01E02.720p.UHD.WEB': '720p', 'Film.2010.DVDRip': None}.items():
            self.assertEqual(br.resolution(title), want, title)  # what KaijuFlow's like-for-like check states for it
            got = sum(f['score'] for f in formats if f['enabled'] and re.search(f['pattern'], title))
            self.assertEqual(got, score[want], title)

    def test_the_committed_file_holds_the_standard_rules_for_kaijuflow_and_usenet_ultimate(self):
        rules_ = self.committed()
        self.assertEqual(sorted(rules_), ['movieFilters', 'tvFilters'])
        films, episodes = rules_['movieFilters'], rules_['tvFilters']
        self.assertEqual((films['maxFileSize'], episodes['maxFileSize']), (32212254720, 10737418240))  # 30 GB and 10 GB
        for section in (films, episodes):
            self.assertEqual(section['rules'], {'rankedRegexPatterns': [dict(
                section['rules']['rankedRegexPatterns'][0], name='No disc images', pattern=self.DROP, flags='i', mode='drop', enabled=True)]})
            self.assertEqual(section['sortOrder'][:5], ['regexScore', 'quality', 'videoTag', 'seScore', 'size'])  # KaijuFlow's default order
            self.assertEqual(section['resolutionPriority'][0], '4k')
        self.assertEqual(dict(films, maxFileSize=0), dict(episodes, maxFileSize=0))  # the size cap is the only difference

    def test_the_committed_file_holds_no_host_address_login_or_key(self):
        with open(brainrun.EXPECTED_SETTINGS_FILE) as f:
            text = f.read()
        for pattern in (r'://', r'@', r'\b\d{1,3}(\.\d{1,3}){3}\b', r'(?i)"[^"]*(host|url|address|server|user|login|pass|key|token|secret)[^"]*"\s*:'):
            self.assertIsNone(re.search(pattern, text), pattern)

    def test_the_committed_file_is_the_one_the_preflight_uses_unless_another_is_named(self):
        cfg = make_cfg(make_copies(self, kf_rules=self.committed(), uu_rules=self.committed()), expected_settings=None)
        code, text = run_command('record', cfg, FakeWorld(cfg))
        self.assertEqual(code, 0, text)
        cfg = make_cfg(make_copies(self, kf_rules=self.committed(), uu_rules={}), expected_settings=None)
        code, text = run_command('record', cfg, FakeWorld(cfg))
        self.assertEqual(code, 1, text)
        self.assertIn('Usenet Ultimate has no movieFilters setting, but the expected settings file (tools/brain/expected-settings.json) has one', text)

    # ---- AltMount direct, through the settings reader and the preflight (#142)
    def test_altmount_direct_as_captured_before_like_for_like_differs_in_three_settings(self):
        with open(os.path.join(ALTMOUNT_FIXTURES, 'stremio-as-found.yaml')) as f:
            found = br.flatten_yaml(f.read())
        self.assertEqual(brainrun.setting_differences(brainrun.load_expected_settings(), {'altmount-addon': found}), [
            'AltMount direct has stremio.max_fallback_releases set to "2", but the expected settings file says "0": '
            "change the test copy's config, or the file if the copy's value is the intended one.",
            'AltMount direct has stremio.include_library_streams set to "null", but the expected settings file says "false".',
            'AltMount direct has no stremio.scoring.custom_formats setting, but the expected settings file has one.'])
        with open(os.path.join(ALTMOUNT_FIXTURES, 'stremio-like-for-like.yaml')) as f:
            applied = br.flatten_yaml(f.read())
        self.assertEqual(brainrun.setting_differences(brainrun.load_expected_settings(), {'altmount-addon': applied}), [])

    def addon_preflight(self, lines):
        cfg = make_cfg(make_copies(self, kf_rules=self.committed(), uu_rules=self.committed(), addon_lines=lines), expected_settings=None)
        return run_command('record', cfg, FakeWorld(cfg))

    def test_altmount_direct_with_a_fallback_or_without_the_custom_formats_stops_with_one_sentence_each(self):
        lines = addon_stremio()
        fallback = [x.replace('max_fallback_releases: 0', 'max_fallback_releases: 2') for x in lines]
        start = lines.index('        custom_formats:')
        end = next(i for i in range(start + 1, len(lines)) if not lines[i].startswith('            '))
        no_formats = lines[:start] + ['        custom_formats: []'] + lines[end:]
        for changed, sentence in (
                (fallback, 'AltMount direct has stremio.max_fallback_releases set to "2", but the expected settings file '
                           '(tools/brain/expected-settings.json) says "0"'),
                (no_formats, 'AltMount direct has no stremio.scoring.custom_formats setting, but the expected settings file '
                             '(tools/brain/expected-settings.json) has one')):
            code, text = self.addon_preflight(changed)
            self.assertEqual(code, 1, text)
            self.assertEqual([x.split(': change')[0] for x in text.splitlines() if x.strip()], [sentence])
        code, text = self.addon_preflight(lines)
        self.assertEqual(code, 0, text)


class DocsOnlyCommitTest(unittest.TestCase):
    """Ticket #113: the image is compared with the code that goes into it, asked of the real git in a small repository."""

    def setUp(self):
        self.cfg = make_cfg(make_copies(self))
        record(self.cfg)
        self.repo, self.built_from = make_repo(self)

    def world(self):
        return RepoWorld(self.cfg, self.repo, label=self.built_from)

    def test_a_commit_that_touches_only_docs_or_a_markdown_file_needs_no_rebuild(self):
        commit(self.repo, {'docs/note.md': 'two', 'README.md': 'two'})
        w = self.world()
        code, text = run_command('run', self.cfg, w)
        self.assertEqual(code, 0, text)
        self.assertIn('Setup is right', text)
        self.assertEqual(w.rebuilt, [])

    def test_a_commit_that_touches_src_stops_and_asks_for_a_rebuild(self):
        head = commit(self.repo, {'src/server.ts': 'two'})
        code, text = run_command('run', self.cfg, self.world())
        self.assertEqual(code, 1, text)
        self.assertIn(f'built from commit {self.built_from[:7]}', text)
        self.assertIn(f'the code that goes into the image has changed since then (the repository is at {head[:7]})', text)
        self.assertIn('--rebuild-image', text)
        self.assertEqual(len(text.strip().splitlines()), 1, text)

    def test_the_rebuild_option_leaves_an_image_alone_that_still_holds_the_code(self):
        commit(self.repo, {'docs/note.md': 'two'})
        self.cfg['rebuild_image'] = True
        w = self.world()
        code, text = run_command('run', self.cfg, w)
        self.assertEqual((code, w.rebuilt, w.label), (0, [], self.built_from), text)

    def test_the_rebuild_option_builds_from_the_new_commit_after_a_change_to_src(self):
        head = commit(self.repo, {'src/server.ts': 'two'})
        self.cfg['rebuild_image'] = True
        w = self.world()
        code, text = run_command('run', self.cfg, w)
        self.assertEqual((code, w.rebuilt, w.label), (0, [head], head), text)

    def test_an_image_from_a_commit_the_repository_does_not_have_stops(self):
        code, text = run_command('run', self.cfg, RepoWorld(self.cfg, self.repo, label=OLDER))
        self.assertEqual(code, 1, text)
        self.assertIn('built from commit bbbbbbb, which this repository does not have', text)

    def test_a_label_that_is_not_a_commit_id_is_never_handed_to_git(self):
        def run(argv, **kw):
            self.fail('git was asked about ' + argv[-1])

        for label in ('--output=/tmp/x', 'latest', 'HEAD', '', None):
            self.assertIsNone(brainrun.build_inputs_changed(self.repo, label, run=run))


class BuildInputsTest(unittest.TestCase):
    def test_what_counts_as_a_change_to_the_code_in_the_image(self):
        repo, before = make_repo(self)
        cases = [('src/server.ts', True), ('src/deep/new.ts', True), ('ui/src/App.tsx', True), ('ui/package.json', True),
                 ('package.json', True), ('package-lock.json', True), ('tsconfig.json', True), ('Dockerfile', True),
                 ('.dockerignore', True), ('.gitattributes', True), ('scripts/docker-entrypoint.sh', True),
                 ('docs/note.md', False), ('README.md', False), ('docs/src/note.md', False), ('tools/brain/brainrun.py', False),
                 ('tests/a.test.ts', False), ('tsconfig.test.json', False), ('scripts/docker-build.sh', False)]
        for path, expected in cases:
            after = commit(repo, {path: 'changed'})
            self.assertIs(brainrun.build_inputs_changed(repo, before), expected, path)
            before = after

    def test_a_change_that_was_taken_back_leaves_the_image_current(self):
        repo, before = make_repo(self)
        commit(repo, {'src/server.ts': 'two'})
        commit(repo, {'src/server.ts': 'one', 'docs/note.md': 'two'})
        self.assertIs(brainrun.build_inputs_changed(repo, before), False)

    def test_a_removed_source_file_is_a_change(self):
        repo, before = make_repo(self)
        git(repo, 'rm', '-q', 'ui/src/App.tsx')
        git(repo, 'commit', '-q', '-m', 'remove')
        self.assertIs(brainrun.build_inputs_changed(repo, before), True)

    def test_the_build_inputs_are_what_the_dockerfile_copies_into_the_image(self):
        with open(os.path.join(brainrun.REPO, 'Dockerfile')) as f:
            copies = [line.split()[1:-1] for line in f if line.startswith('COPY ') and '--from=' not in line]
        copied = {src.rstrip('*').rstrip('/') for sources in copies for src in sources}
        self.assertIn('src', copied)  # the Dockerfile was read
        inputs = set(brainrun.BUILD_INPUTS)
        not_covered = sorted(c for c in copied if not any(c == i or c.startswith(i + '/') for i in inputs))
        self.assertEqual(not_covered, [], 'the Dockerfile copies these, but BUILD_INPUTS does not name them')
        not_copied = sorted(i for i in inputs - {'Dockerfile', '.dockerignore', '.gitattributes'}
                            if not any(c == i or c.startswith(i + '/') for c in copied))
        self.assertEqual(not_copied, [], 'BUILD_INPUTS names these, but the Dockerfile does not copy them')

    def test_the_image_state_is_decided_from_the_label_the_commit_and_git(self):
        def never(commit):
            self.fail('git is not asked when the commits are the same or there is no label')

        self.assertEqual(brainrun.image_state(None, COMMIT, never), 'missing')
        self.assertEqual(brainrun.image_state(COMMIT, COMMIT, never), 'current')
        self.assertEqual(brainrun.image_state(OLDER, COMMIT, {OLDER: False}.get), 'current')
        self.assertEqual(brainrun.image_state(OLDER, COMMIT, {OLDER: True}.get), 'stale')
        self.assertEqual(brainrun.image_state(OLDER, COMMIT, {}.get), 'unknown')


class BuildImageTest(unittest.TestCase):
    def test_the_image_is_built_from_an_archive_of_the_commit_not_from_the_working_folder(self):
        calls = []

        class Out:
            def close(self):
                calls.append(('closed',))

        class Archive:
            stdout = Out()

            def wait(self):
                calls.append(('waited',))

        def popen(argv, **kw):
            calls.append(('popen', argv, kw))
            return Archive()

        def run(argv, **kw):
            calls.append(('run', argv, kw))

        brainrun.build_image(COMMIT, '/repo', popen=popen, run=run)
        (_, archive_argv, _), (_, build_argv, build_kw) = calls[0], calls[1]
        self.assertEqual(archive_argv, ['git', '-C', '/repo', 'archive', 'HEAD'])
        self.assertEqual(build_argv, ['docker', 'build', '--label', f'kaijuflow.commit={COMMIT}', '-t', 'kaijuflow:test', '-'])
        self.assertIs(build_kw['stdin'], Archive.stdout)  # the archive is the build context
        self.assertNotIn('/repo', build_argv)  # no folder is handed to docker, so nothing untracked can get in


class AddressesTest(unittest.TestCase):
    def test_addresses_are_read_with_docker_inspect_for_test_containers_only(self):
        asked = []

        class R:
            def __init__(self, out, code=0):
                self.stdout, self.returncode = out, code

        def run(argv, **kw):
            asked.append(argv)
            return R({'kaijuflow-test': '172.20.0.5\n', 'uu-test': '172.20.0.6\n'}.get(argv[-1], ''), 0 if argv[-1] != 'altmount-addon-test' else 1)

        got = brainrun.read_addresses(run=run)
        self.assertEqual(got, {'kaijuflow-test': '172.20.0.5', 'uu-test': '172.20.0.6'})  # one container not up: left out
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
            brainrun.run_all(run_cfg(tmp), fake)
        self.assertEqual(fake.calls, [])
        self.assertEqual(fake.calls_preflight, ['run'])
        self.assertFalse(os.path.exists(os.path.join(tmp, 'runs')))


if __name__ == '__main__':
    unittest.main()
