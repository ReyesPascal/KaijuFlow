"""Tests for guard.py, the project's PreToolUse hook (#161): fed command strings and tool inputs, no real file is read.

Each test runs with HOME set to a temporary folder and the test folder (`common.DEFAULT_TEST_DIR`) inside it, so the
refusals are tried on paths that hold nothing.

    python3 -I -m unittest discover -s tools/brain -p 'test_guard.py'
"""
import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

import common
import guard

HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOADS = os.path.join(HERE, 'fixtures', '2026-11-15-hook-payloads')
READ_SETTINGS = 'python3 -I tools/brain/testbed.py read-settings'


def captured(tool):
    """The PreToolUse JSON Claude Code sent for one harmless call of `tool` (scrubbed; see the fixture's README)."""
    with open(os.path.join(PAYLOADS, tool.lower() + '.json')) as f:
        return json.load(f)


def run_hook(payload):
    """guard.main() fed `payload` as Claude Code feeds it: (exit code, stderr)."""
    err = io.StringIO()
    with unittest.mock.patch('sys.stdin', io.StringIO(json.dumps(payload))), contextlib.redirect_stderr(err):
        return guard.main(), err.getvalue()


class GuardCase(unittest.TestCase):
    """A temporary home with the test folder at its default place (`~/kaijuflow-test`), TEST_DIR unset."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix='guard-home-')
        self.addCleanup(shutil.rmtree, self.home, True)
        self.td = os.path.join(self.home, 'kaijuflow-test')
        env = unittest.mock.patch.dict(os.environ, {'HOME': self.home})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('TEST_DIR', None)
        default = unittest.mock.patch.object(common, 'DEFAULT_TEST_DIR', self.td)
        default.start()
        self.addCleanup(default.stop)

    def bash(self, command):
        return guard.refusal('Bash', {'command': command})


class CapturedPayloadTest(GuardCase):
    """The hook on the JSON Claude Code really sends (review rule 2), not on invented calls."""

    def test_the_captured_calls_pass(self):
        for tool in ('Bash', 'Read', 'Grep'):
            self.assertEqual(run_hook(captured(tool)), (0, ''), tool)

    def test_the_same_calls_aimed_at_the_test_folder_are_refused(self):
        for tool, field, value in (('Bash', 'command', 'cat ~/kaijuflow-test/indexers.json'),
                                   ('Read', 'file_path', f'{self.td}/uu/config/config.json'),
                                   ('Grep', 'path', self.td), ('Grep', 'path', self.home)):
            payload = copy.deepcopy(captured(tool))
            payload['tool_input'][field] = value
            code, err = run_hook(payload)
            self.assertEqual(code, 2, (tool, value))
            self.assertIn('read-settings', err)

    def test_the_hook_as_settings_run_it(self):
        """`python3 -I guard.py`, as `.claude/settings.json` runs it, on the captured JSON."""
        refused = copy.deepcopy(captured('Bash'))
        refused['tool_input']['command'] = 'cat indexers.json'
        refused['cwd'] = self.td
        for payload, code in ((captured('Bash'), 0), (captured('Grep'), 0), (refused, 2)):
            done = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'guard.py')], input=json.dumps(payload),
                                  capture_output=True, text=True, env={**os.environ}, timeout=30)
            self.assertEqual(done.returncode, code, (payload['tool_input'], done.stderr))

    def test_a_relative_path_is_judged_from_the_calls_cwd(self):
        for cwd, code in ((self.td, 2), (os.path.join(self.td, 'uu'), 2), (os.path.join(self.td, 'store'), 0),
                          (captured('Bash')['cwd'], 0)):
            payload = copy.deepcopy(captured('Bash'))
            payload['tool_input']['command'] = 'cat config/config.json'
            payload['cwd'] = cwd
            self.assertEqual(run_hook(payload)[0], code, cwd)


class TestFolderTest(GuardCase):
    def test_the_test_folder_is_commons_default(self):
        elsewhere = os.path.join(self.home, 'elsewhere')
        with unittest.mock.patch.object(common, 'DEFAULT_TEST_DIR', elsewhere):
            self.assertIsNotNone(self.bash(f'cat {elsewhere}/limits.json'))
            self.assertIsNotNone(guard.refusal('Read', {'file_path': f'{elsewhere}/indexers.json'}))
            self.assertIsNotNone(self.bash('cat ~/elsewhere/uu/notes.txt'))
            self.assertIsNone(self.bash('cat ~/kaijuflow-test/uu/notes.txt'))

    def test_the_test_dir_follows_the_env(self):
        with unittest.mock.patch.dict(os.environ, {'TEST_DIR': '/tmp/fake-td'}):
            self.assertIsNotNone(self.bash('cat /tmp/fake-td/indexers.json'))
            self.assertIsNotNone(self.bash('cat /tmp/fake-td/uu/config/config.json'))


class SecretCommandTest(GuardCase):
    def test_refuses_direct_reads_of_key_files(self):
        for cmd in (f'cat {self.td}/indexers.json', 'cat ~/kaijuflow-test/indexers.json', 'jq . ~/kaijuflow-test/limits.json',
                    'grep apikey $HOME/kaijuflow-test/indexers.json', 'head ~/kaijuflow-test/provider.json',
                    'cat ~/kaijuflow-test/admin-login.json', 'cat ~/kaijuflow-test/nzbdav-secrets.json',
                    'cat ~/kaijuflow-test/metadata-keys.json', 'cat "$TEST_DIR/indexers.json"', 'cat ${TEST_DIR}/.env',
                    'cd ~/kaijuflow-test && cat indexers.json'):
            self.assertIn('read-settings', self.bash(cmd) or '', cmd)

    def test_refuses_direct_reads_of_a_test_copys_config(self):
        for cmd in ('cat ~/kaijuflow-test/config/config.json', 'cat ~/kaijuflow-test/uu/config/config.json',
                    'grep -r key ~/kaijuflow-test/altmount-addon/config', 'cat ~/kaijuflow-test/altmount-kf/config/config.yaml',
                    "python3 -c \"print(open('/home/brain/kaijuflow-test/config/config.json').read())\"",
                    'sqlite3 ~/kaijuflow-test/nzbdav/config/db.sqlite .dump',
                    'ls ~/kaijuflow-test/templates/config && cat ~/kaijuflow-test/templates/config/config.json'):
            self.assertIn('read-settings', self.bash(cmd) or '', cmd)

    def test_allows_the_brain_tools(self):
        for cmd in ('python3 -I tools/brain/brainrun.py preflight --for record --store ~/kaijuflow-test/store --list x',
                    'python3 -I tools/brain/brainrun.py run --name a --store ~/kaijuflow-test/store --list x | tail -3',
                    READ_SETTINGS, READ_SETTINGS + ' uu', 'python3 -I tools/brain/testbed.py settings',
                    'python3 -I tools/brain/testbed.py reset kaijuflow', 'tools/brain/backup.sh',
                    'python3 -I tools/brain/brainrun.py usage', 'ls ~/kaijuflow-test', 'ls ~/kaijuflow-test/store'):
            self.assertIsNone(self.bash(cmd), cmd)

    def test_allows_unrelated_commands(self):
        for cmd in ('git status', 'npm run check:brain', 'cat tools/brain/expected-settings.json', 'cat tools/brain/limits.example.json',
                    'grep -rn limits tools/brain', 'gh issue view 161 --json number,title,body,labels,comments', 'ls /tmp'):
            self.assertIsNone(self.bash(cmd), cmd)

    def test_refuses_reads_inside_a_container(self):
        for cmd in ('docker exec kaijuflow-test-uu-1 cat /config/config.json', 'docker exec -it uu sh -c "cat /config/config.json"',
                    'docker compose -p kaijuflow-test exec nzbdav sqlite3 /config/db.sqlite .dump',
                    'docker exec altmount-kf grep -r key /config', 'docker cp kaijuflow-test-uu-1:/config/config.json /tmp/x',
                    'podman exec uu cat /app/indexers.json', 'sudo docker exec uu cat /config/config.json'):
            self.assertIn('read-settings', self.bash(cmd) or '', cmd)

    def test_refuses_a_search_from_a_folder_holding_the_test_folder(self):
        for cmd in ('grep -r apikey ~', f'grep -rn apikey {self.home}', 'rg apikey $HOME', 'find ~ -name indexers.json',
                    'find / -name limits.json', 'cat $(find ~ -name indexers.json)', 'cd ~ && grep -r apikey .',
                    'cd && cat kaijuflow-test/indexers.json', 'cd ~ && cat kaijuflow-test/uu/config/config.json',
                    'cd ~/kaijuflow-test; cd uu; cat config/config.json', 'cd ~/kaijuflow-test && grep -r key .'):
            self.assertIn('read-settings', self.bash(cmd) or '', cmd)

    def test_allows_commands_that_only_mention_a_key_file_or_config_folder(self):
        for cmd in ('grep limits.json tools/brain/docs/formats.md', 'grep -rn uu/config tools/brain',
                    "grep -n 'indexers.json\\|db.sqlite' tools/brain/RUNBOOK.md", 'git log --oneline -- tools/brain/limits.example.json',
                    'git commit -m "guard: refuse cat limits.json in nzbdav/config"', 'ls ~', 'cd ~ && ls', 'du -sh ~',
                    'git branch -a | cut -d / -f 2', "python3 - <<'EOF'\nratio = a / b\nEOF", 'echo a / b', 'docker ps', 'docker exec kaijuflow-test-uu-1 ls /data',
                    'docker compose -f tools/brain/compose.test.yaml ps', 'cd ~/kaijuflow-test/store && ls'):
            self.assertIsNone(self.bash(cmd), cmd)

    def test_a_brain_tool_does_not_excuse_a_chained_read(self):
        self.assertIsNotNone(self.bash(f'{READ_SETTINGS} && cat ~/kaijuflow-test/indexers.json'))
        self.assertIsNotNone(self.bash(f'{READ_SETTINGS}; jq . ~/kaijuflow-test/limits.json'))
        self.assertIsNotNone(self.bash('echo $(cat ~/kaijuflow-test/indexers.json)'))


class ToolInputTest(GuardCase):
    def test_refuses_read_and_grep_on_key_files_and_config_folders(self):
        td = self.td
        for tool, field, value in (('Read', 'file_path', f'{td}/indexers.json'), ('Read', 'file_path', f'{td}/config/config.json'),
                                   ('Read', 'file_path', f'{td}/altmount-addon/config/config.yaml'),
                                   ('Read', 'file_path', '~/kaijuflow-test/limits.json'),
                                   ('Grep', 'path', f'{td}/uu/config'), ('Grep', 'path', td), ('Grep', 'path', f'{td}/indexers.json'),
                                   ('Grep', 'glob', f'{td}/**/config.json'), ('Read', 'file_path', f'{td}/../kaijuflow-test/indexers.json'),
                                   ('Grep', 'path', self.home), ('Grep', 'path', '~'), ('Grep', 'path', '/'),
                                   ('Grep', 'path', os.path.dirname(self.home))):
            self.assertIn('read-settings', guard.refusal(tool, {field: value, 'pattern': 'x'}) or '', (tool, value))

    def test_allows_other_paths(self):
        for tool, field, value in (('Read', 'file_path', '/repo/tools/brain/frontier.py'), ('Grep', 'path', '/repo/tools/brain'),
                                   ('Read', 'file_path', f'{self.td}/store/x/RECORDING.json'), ('Grep', 'path', None),
                                   ('Grep', 'path', os.path.join(self.home, 'code')), ('Read', 'file_path', f'{self.home}/.bashrc')):
            self.assertIsNone(guard.refusal(tool, {field: value, 'pattern': 'x'}), (tool, value))

    def test_other_tools_pass(self):
        self.assertIsNone(guard.refusal('Edit', {'file_path': f'{self.td}/indexers.json'}))


class GhTest(GuardCase):
    def test_refuses_each_failing_call_and_names_the_working_one(self):
        cases = {
            'gh issue view 161 --comments': 'gh issue view 161 --json number,title,body,labels,comments',
            'gh issue view --comments 7': 'gh issue view 7 --json number,title,body,labels,comments',
            'gh issue view 161 -c': 'gh issue view 161 --json number,title,body,labels,comments',
            'gh issue view 218': 'gh issue view 218 --json number,title,body,labels,comments',
            'cd x && gh issue view 219 -R o/r': 'gh issue view 219 --json number,title,body,labels,comments',
            'gh pr checks 230 --json name,bucket': 'python3 -I tools/brain/prwatch.py 230',
            's=$(gh pr checks 230 --json name,bucket 2>/dev/null)': 'python3 -I tools/brain/prwatch.py 230',
            'gh pr edit 5 --body-file b.md': 'gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -F body=@<file>',
            'gh pr edit 5 --add-label x': 'gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -F body=@<file>',
            'gh issue create --title t --body b --parent 159':
                'gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<db id>',
            'cd x && gh issue create --parent=159 --title t':
                'gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<db id>',
        }
        for cmd, working in cases.items():
            self.assertIn(working, self.bash(cmd) or '', cmd)

    def test_allows_working_gh_calls(self):
        for cmd in ('gh issue view 161 --json number,title,body,labels,comments', 'gh issue create --title t --body "mentions --parent"',
                    'gh issue comment 161 --body "gh pr edit fails"', 'gh pr view 5', 'gh pr checks 230', 'gh pr checks 230 --watch', 'gh api -X PATCH repos/{owner}/{repo}/pulls/5 -F body=@b.md',
                    'gh issue list --state open', 'gh issue view 218 --json title,body -q .body', 'gh issue view 9 --web', 'git commit -m "gh issue view 1 --comments"'):
            self.assertIsNone(self.bash(cmd), cmd)


class HookTest(GuardCase):
    """The entry point Claude Code runs: the PreToolUse JSON on stdin, exit 2 and the sentence on stderr to refuse."""

    def test_unreadable_input_does_not_block(self):
        with unittest.mock.patch('sys.stdin', io.StringIO('not json')):
            self.assertEqual(guard.main(), 0)

    def test_the_project_settings_wire_it_to_bash_read_and_grep(self):
        with open(os.path.join(HERE, '..', '..', '.claude', 'settings.json')) as f:
            hooks = json.load(f)['hooks']['PreToolUse']
        self.assertEqual(sorted(h['matcher'] for h in hooks), ['Bash', 'Grep', 'Read'])
        for h in hooks:
            self.assertEqual(h['hooks'][0]['command'], 'python3 -I "$CLAUDE_PROJECT_DIR"/tools/brain/guard.py')


if __name__ == '__main__':
    unittest.main()
