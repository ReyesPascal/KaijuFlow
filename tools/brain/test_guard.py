"""Tests for guard.py, the project's PreToolUse hook (#161): fed command strings and tool inputs, no real file is read.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import io
import json
import os
import unittest
import unittest.mock

import guard

TD = os.path.expanduser('~/kaijuflow-test')
READ_SETTINGS = 'python3 -I tools/brain/testbed.py read-settings'


def bash(command):
    return guard.refusal('Bash', {'command': command})


class SecretCommandTest(unittest.TestCase):
    def test_refuses_direct_reads_of_key_files(self):
        for cmd in (f'cat {TD}/indexers.json', 'cat ~/kaijuflow-test/indexers.json', 'jq . ~/kaijuflow-test/limits.json',
                    'grep apikey $HOME/kaijuflow-test/indexers.json', 'head ~/kaijuflow-test/provider.json',
                    'cat ~/kaijuflow-test/admin-login.json', 'cat ~/kaijuflow-test/nzbdav-secrets.json',
                    'cat ~/kaijuflow-test/metadata-keys.json', 'cat "$TEST_DIR/indexers.json"', 'cat ${TEST_DIR}/.env',
                    'cd ~/kaijuflow-test && cat indexers.json'):
            self.assertIn('read-settings', bash(cmd) or '', cmd)

    def test_refuses_direct_reads_of_a_test_copys_config(self):
        for cmd in ('cat ~/kaijuflow-test/config/config.json', 'cat ~/kaijuflow-test/uu/config/config.json',
                    'grep -r key ~/kaijuflow-test/altmount-addon/config', 'cat ~/kaijuflow-test/altmount-kf/config/config.yaml',
                    "python3 -c \"print(open('/home/brain/kaijuflow-test/config/config.json').read())\"",
                    'sqlite3 ~/kaijuflow-test/nzbdav/config/db.sqlite .dump', 'ls ~/kaijuflow-test/templates/config && cat ~/kaijuflow-test/templates/config/config.json'):
            self.assertIn('read-settings', bash(cmd) or '', cmd)

    def test_allows_the_brain_tools(self):
        for cmd in ('python3 -I tools/brain/brainrun.py preflight --for record --store ~/kaijuflow-test/store --list x',
                    'python3 -I tools/brain/brainrun.py run --name a --store ~/kaijuflow-test/store --list x | tail -3',
                    READ_SETTINGS, READ_SETTINGS + ' uu', 'python3 -I tools/brain/testbed.py settings',
                    'python3 -I tools/brain/testbed.py reset kaijuflow', 'tools/brain/backup.sh',
                    'python3 -I tools/brain/brainrun.py usage', 'ls ~/kaijuflow-test', 'ls ~/kaijuflow-test/store'):
            self.assertIsNone(bash(cmd), cmd)

    def test_allows_unrelated_commands(self):
        for cmd in ('git status', 'npm run check:brain', 'cat tools/brain/expected-settings.json', 'cat tools/brain/limits.example.json',
                    'grep -rn limits tools/brain', 'gh issue view 161 --json number,title,body,labels,comments', 'ls /tmp'):
            self.assertIsNone(bash(cmd), cmd)

    def test_a_brain_tool_does_not_excuse_a_chained_read(self):
        self.assertIsNotNone(bash(f'{READ_SETTINGS} && cat ~/kaijuflow-test/indexers.json'))
        self.assertIsNotNone(bash(f'{READ_SETTINGS}; jq . ~/kaijuflow-test/limits.json'))
        self.assertIsNotNone(bash('echo $(cat ~/kaijuflow-test/indexers.json)'))

    def test_the_test_dir_follows_the_env(self):
        with unittest.mock.patch.dict(os.environ, {'TEST_DIR': '/tmp/fake-td'}):
            self.assertIsNotNone(bash('cat /tmp/fake-td/indexers.json'))
            self.assertIsNotNone(bash('cat /tmp/fake-td/uu/config/config.json'))


class ToolInputTest(unittest.TestCase):
    def test_refuses_read_and_grep_on_key_files_and_config_folders(self):
        for tool, field, value in (('Read', 'file_path', f'{TD}/indexers.json'), ('Read', 'file_path', f'{TD}/config/config.json'),
                                   ('Read', 'file_path', f'{TD}/altmount-addon/config/config.yaml'),
                                   ('Read', 'file_path', '~/kaijuflow-test/limits.json'),
                                   ('Grep', 'path', f'{TD}/uu/config'), ('Grep', 'path', TD), ('Grep', 'path', f'{TD}/indexers.json'),
                                   ('Grep', 'glob', f'{TD}/**/config.json'), ('Read', 'file_path', f'{TD}/../kaijuflow-test/indexers.json')):
            self.assertIn('read-settings', guard.refusal(tool, {field: value, 'pattern': 'x'}) or '', (tool, value))

    def test_allows_other_paths(self):
        for tool, field, value in (('Read', 'file_path', '/repo/tools/brain/frontier.py'), ('Grep', 'path', '/repo/tools/brain'),
                                   ('Read', 'file_path', f'{TD}/store/x/RECORDING.json'), ('Grep', 'path', None)):
            self.assertIsNone(guard.refusal(tool, {field: value, 'pattern': 'x'}), (tool, value))

    def test_other_tools_pass(self):
        self.assertIsNone(guard.refusal('Edit', {'file_path': f'{TD}/indexers.json'}))


class GhTest(unittest.TestCase):
    def test_refuses_each_failing_call_and_names_the_working_one(self):
        cases = {
            'gh issue view 161 --comments': 'gh issue view 161 --json number,title,body,labels,comments',
            'gh issue view --comments 7': 'gh issue view 7 --json number,title,body,labels,comments',
            'gh issue view 161 -c': 'gh issue view 161 --json number,title,body,labels,comments',
            'gh pr edit 5 --body-file b.md': 'gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -F body=@<file>',
            'gh pr edit 5 --add-label x': 'gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -F body=@<file>',
            'gh issue create --title t --body b --parent 159':
                'gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<db id>',
            'cd x && gh issue create --parent=159 --title t':
                'gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<db id>',
        }
        for cmd, working in cases.items():
            self.assertIn(working, bash(cmd) or '', cmd)

    def test_allows_working_gh_calls(self):
        for cmd in ('gh issue view 161 --json number,title,body,labels,comments', 'gh issue create --title t --body "mentions --parent"',
                    'gh issue comment 161 --body "gh pr edit fails"', 'gh pr view 5', 'gh api -X PATCH repos/{owner}/{repo}/pulls/5 -F body=@b.md',
                    'gh issue list --state open', 'git commit -m "gh issue view 1 --comments"'):
            self.assertIsNone(bash(cmd), cmd)


class HookTest(unittest.TestCase):
    """The entry point Claude Code runs: the PreToolUse JSON on stdin, exit 2 and the sentence on stderr to refuse."""

    def run_hook(self, payload):
        err = io.StringIO()
        with unittest.mock.patch('sys.stdin', io.StringIO(json.dumps(payload))), unittest.mock.patch('sys.stderr', err):
            return guard.main(), err.getvalue()

    def test_refuses_with_exit_2_and_the_sentence_on_stderr(self):
        code, err = self.run_hook({'tool_name': 'Bash', 'tool_input': {'command': 'cat ~/kaijuflow-test/indexers.json'}})
        self.assertEqual(code, 2)
        self.assertIn('read-settings', err)

    def test_allows_with_exit_0_and_no_output(self):
        self.assertEqual(self.run_hook({'tool_name': 'Bash', 'tool_input': {'command': 'git status'}}), (0, ''))

    def test_unreadable_input_does_not_block(self):
        with unittest.mock.patch('sys.stdin', io.StringIO('not json')):
            self.assertEqual(guard.main(), 0)

    def test_the_project_settings_wire_it_to_bash_read_and_grep(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.claude', 'settings.json')
        with open(path) as f:
            hooks = json.load(f)['hooks']['PreToolUse']
        self.assertEqual(sorted(h['matcher'] for h in hooks), ['Bash', 'Grep', 'Read'])
        for h in hooks:
            self.assertEqual(h['hooks'][0]['command'], 'python3 -I "$CLAUDE_PROJECT_DIR"/tools/brain/guard.py')


if __name__ == '__main__':
    unittest.main()
