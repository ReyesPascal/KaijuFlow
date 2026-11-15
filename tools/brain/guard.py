"""The project's PreToolUse hook (#161): keeps secrets out of a session and stops `gh` calls that fail on this machine.

Claude Code runs it (`.claude/settings.json`, on Bash, Read and Grep) with the tool call as JSON on stdin. It exits 2
with one sentence on stderr to refuse the call, 0 to allow it.

Refused: a shell command, Read or Grep that would show the test folder's key files (`indexers.json`, `limits.json`,
`provider.json`, `*-secrets.json`, `metadata-keys.json`, `admin-login.json`, `db.sqlite`) or a test copy's config folder.
Allowed: the brain tools (`tools/brain/*.py|sh`, `npm run check:brain`: runs, preflights, applying expected settings
and `testbed.py read-settings`, the settings with secrets as ***), the test folder's `store/` and `backups/`, and every
unrelated command. A command line is cut at `;`, `&&`, `||`, `|`, `$(` and backticks; each piece is judged alone, so a
brain tool does not excuse a read chained after it.
Also refused, with the call that works: `gh issue view <n> --comments`, `gh pr edit`, `gh issue create --parent` (gh 2.46).

    python3 -I -m unittest discover -s tools/brain -p 'test_guard.py'
"""
import json
import os
import re
import shlex
import sys

HOME_TEST = r'(?:~|\$HOME|\$\{HOME\}|/home/[^/\s]+)/kaijuflow-test'
KEY_FILE = re.compile(r'(?<![\w.-])(?:indexers|limits|provider|metadata-keys|admin-login|[\w-]*-secrets)\.json\b|(?<![\w.-])db\.sqlite\b')
COPY_CONFIG = re.compile(r'(?<![\w.-])(?:uu|nzbdav|altmount-addon|altmount-kf)/config\b')
BRAIN_TOOL = re.compile(r'^(?:python3?\s+(?:-I\s+)?)?(?:\./)?tools/brain/[\w.-]+\.(?:py|sh)(?:\s|$)|^npm run check:brain\b')
CUT = re.compile(r'&&|\|\||[;|\n`]|\$\(')
OPEN_FOLDER = {'ls', 'cd', 'du', 'df', 'stat', 'mkdir'}  # commands that name the test folder without reading a file in it
SAFE_SUBFOLDERS = ('store', 'backups')

SETTINGS_HINT = ('use `python3 -I tools/brain/testbed.py read-settings [side]`, which prints every test copy\'s settings '
                 'with secrets as ***; runs and preflights go through tools/brain/brainrun.py')
REFUSE_SECRET = f"That would show a test key file or a test copy's config (secrets): {SETTINGS_HINT}."
GH_VIEW = 'gh issue view {n} --json number,title,body,labels,comments'
GH_PR = 'gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -F body=@<file>'
GH_PARENT = ('create the issue without --parent, then `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues '
             '-F sub_issue_id=<db id>`')


def test_dirs():
    dirs = {os.path.realpath(os.path.expanduser('~/kaijuflow-test'))}
    if os.environ.get('TEST_DIR'):
        dirs.add(os.path.realpath(os.environ['TEST_DIR']))
    return dirs


def _mentions_secret(segment):
    folders = re.compile('|'.join([HOME_TEST, r'\$\{?TEST_DIR\}?'] + [re.escape(d) for d in test_dirs()]))
    words = segment.split()
    for m in folders.finditer(segment):
        tail = segment[m.end():]
        if tail.startswith('/'):
            name = re.match(r'/([^/\s"\']*)', tail).group(1)
            if name not in SAFE_SUBFOLDERS:
                return True
        elif not words or words[0] not in OPEN_FOLDER:  # the folder itself, e.g. `grep -r x ~/kaijuflow-test`
            return True
    return bool(KEY_FILE.search(segment) or COPY_CONFIG.search(segment))


def _gh(segment):
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()
    if len(tokens) < 3 or tokens[0] != 'gh':
        return None
    rest = tokens[1:]
    if rest[:2] == ['issue', 'view'] and any(t in ('--comments', '-c') for t in rest):
        number = next((t for t in rest[2:] if re.fullmatch(r'\d+', t)), '<n>')
        return f'`gh issue view --comments` fails here (Projects classic GraphQL error); use `{GH_VIEW.format(n=number)}`.'
    if rest[:2] == ['pr', 'edit']:
        return f'`gh pr edit` fails here (Projects classic GraphQL error); use `{GH_PR}`.'
    if rest[:2] == ['issue', 'create'] and any(t == '--parent' or t.startswith('--parent=') for t in rest):
        return f'gh 2.46 has no `--parent`; {GH_PARENT}.'
    return None


def check_command(command):
    for segment in (s.strip() for s in CUT.split(command)):
        if not segment:
            continue
        hit = _gh(segment)
        if hit:
            return hit
        if not BRAIN_TOOL.match(segment) and _mentions_secret(segment):
            return REFUSE_SECRET
    return None


def _protected_path(value):
    if not value:
        return False
    head = re.split(r'[*?\[{]', os.path.expandvars(os.path.expanduser(value)), maxsplit=1)[0]
    path = os.path.realpath(os.path.normpath(head)) if head else ''
    for d in test_dirs():
        if path == d:
            return True
        if path.startswith(d + os.sep):
            return path[len(d) + 1:].split(os.sep)[0] not in SAFE_SUBFOLDERS
    return False


def refusal(tool, tool_input):
    """The sentence that refuses this tool call, or None when it may go ahead."""
    if tool == 'Bash':
        return check_command(tool_input.get('command') or '')
    if tool in ('Read', 'Grep') and any(_protected_path(tool_input.get(k)) for k in ('file_path', 'path', 'glob')):
        return REFUSE_SECRET
    return None


def main():
    try:
        call = json.load(sys.stdin)
        message = refusal(call.get('tool_name'), call.get('tool_input') or {})
    except (ValueError, AttributeError):
        return 0
    if message:
        print(message, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
