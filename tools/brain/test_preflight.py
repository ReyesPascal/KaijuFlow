"""Tests for the preflight of brainrun.py (spec #72, ticket #74): one test per check, each asserting the exit code and the sentence.

Runs the real reader on fixture test copies in a temporary folder; only the Docker/git/port questions are faked.
The tests of ticket #113 (which commits ask for a new image) put those git questions to the real git, in a small temporary repository.
    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import subprocess
import unittest

import brainrun
import testbed
from test_settings import SECRET, make_copies, tempdir

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


def make_cfg(td, **kw):
    cfg = dict(test_dir=td, store=os.path.join(os.path.dirname(td), 'store'), listname='l', limit=100, standin_port=1340,
               rebuild_image=False)
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
        self.assert_stops('record', self.world(), 'AltMount addon', 'drunkenslug')

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
