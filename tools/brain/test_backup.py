"""Tests for backup.sh (#114, #312): it backs up the check folders of ~/kaijuflow-notes to its private repo, with no
recording store, and never touches a recording.
    python3 -I -m unittest discover -s tools/brain -p 'test_backup.py'
"""
import json
import os
import subprocess
import unittest

from test_settings import tempdir

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup.sh')
SECRET = 'sk-0123456789abcdef'


GIT_ID = {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}


def git(cwd, *args):
    # Its own identity: CI's runner has no git user, so a commit here would exit 128.
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **GIT_ID)).stdout


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.home = tempdir(self)
        self.origin = os.path.join(self.home, 'origin.git')
        self.notes = os.path.join(self.home, 'kaijuflow-notes')
        subprocess.run(['git', 'init', '-q', '--bare', self.origin], check=True)
        subprocess.run(['git', 'clone', '-q', self.origin, self.notes], check=True, capture_output=True)
        self.env = dict(os.environ, HOME=self.home, KF_NOTES=self.notes, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t', GIT_CONFIG_GLOBAL=os.devnull)
        self.env.pop('KF_STORE', None)
        self.write('brain-runs/2026-11-24T122253Z-quick-check/report.md', 'Fail: 1 of 5 titles failed.\n')
        self.write('recordings/kf-265/RECORDING.json', '{"old": true}\n')  # an old copy: the lead deletes it, not backup.sh
        git(self.notes, 'add', '-A')
        git(self.notes, 'commit', '-qm', 'start')
        git(self.notes, 'push', '-q', 'origin', 'HEAD')
        test_dir = os.path.join(self.home, 'kaijuflow-test')
        os.makedirs(test_dir)
        with open(os.path.join(test_dir, 'indexers.json'), 'w') as f:
            json.dump({'indexers': {'ninjacentral': {'name': 'NinjaCentral', 'apikey': SECRET}}}, f)

    def write(self, rel, text):
        path = os.path.join(self.notes, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)

    def backup(self, **env):
        return subprocess.run(['bash', SCRIPT], env=dict(self.env, **env), capture_output=True, text=True, timeout=60)

    def pushed(self, rel):
        return git(self.origin, 'show', f'HEAD:{rel}')

    def test_a_new_check_folder_is_pushed_with_no_store_and_the_recordings_untouched(self):
        self.write('brain-runs/2026-11-25T100000Z-quick-check/report.md', 'Pass: 0 fails in 5 titles.\n')
        r = self.backup()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.pushed('brain-runs/2026-11-25T100000Z-quick-check/report.md'), 'Pass: 0 fails in 5 titles.\n')
        self.assertEqual(self.pushed('recordings/kf-265/RECORDING.json'), '{"old": true}\n')
        with open(os.path.join(self.notes, 'recordings', 'kf-265', 'RECORDING.json')) as f:
            self.assertEqual(f.read(), '{"old": true}\n')

    def test_a_store_folder_is_never_mirrored(self):
        store = os.path.join(self.home, 'kaijuflow-test', 'store')
        os.makedirs(os.path.join(store, 'kf-189'))
        with open(os.path.join(store, 'kf-189', 'RECORDING.json'), 'w') as f:
            f.write('{}\n')
        r = self.backup(KF_STORE=store)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.listdir(os.path.join(self.notes, 'recordings')), ['kf-265'])

    def test_a_key_files_value_in_a_check_folder_stops_the_backup(self):
        self.write('brain-runs/2026-11-25T100000Z-quick-check/logs/standin.log', f'GET /api?apikey={SECRET}\n')
        r = self.backup()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('A value from indexers.json is in', r.stdout + r.stderr)
        self.assertNotIn('2026-11-25T100000Z-quick-check', git(self.origin, 'log', '--stat', 'HEAD'))


if __name__ == '__main__':
    unittest.main()
