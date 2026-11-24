"""The project's PreToolUse hook (#161): keeps secrets out of a session and stops `gh` calls that fail on this machine.

Claude Code runs it (`.claude/settings.json`, on Bash, Read and Grep) with the tool call as JSON on stdin (captured
samples: `fixtures/2026-11-15-hook-payloads/`). It exits 2 with one sentence on stderr to refuse the call, 0 to allow it.

Refused: a shell command, Read or Grep that reaches into the test folder (`common.DEFAULT_TEST_DIR`, and TEST_DIR when
set) outside `store/` and `backups/`, where the key files (`indexers.json`, `limits.json`, ...) and the test copies'
config folders live; a search from a folder holding it (`grep -r x ~`, `find / -name ...`, a Grep on `~`); and a
`docker`/`podman` `exec` or `cp` that names `/config` or a key file, in any container. A relative path is judged from
the call's `cwd` and the `cd`s before it on the line. Merely naming a key file or `uu/config` is allowed
(`grep limits.json tools/brain/docs/formats.md`), and so are `ls`, `cd`, `du`, `df`, `stat`, `mkdir` on the test
folder or a folder holding it.
One narrow exception (#280): AltMount's failed NZBs, `altmount-kf/config/.nzbs/failed/**/<name>.nzb` (and `ls`/`stat` of
that folder), may be read, as the given path and with links resolved; the rest of that config folder stays refused.
Allowed: the brain tools (`tools/brain/*.py|sh`, `npm run check:brain`: runs, preflights, applying expected settings
and `testbed.py read-settings`, the settings with secrets as ***) and every unrelated command. A command line is cut at
`;`, `&&`, `||`, `|`, `$(` and backticks; each piece is judged alone, so a brain tool does not excuse a read chained
after it.
Known limits (a guardrail against slips, not a sandbox): paths built at run time (`$(...)` output, globs over the
folder's name, symlinks inside the repo), `pushd`/subshell `cd`s, another program's own working folder (`git -C`,
`docker exec -w /config`).
Also refused, with the call that works: `gh issue view <n>` without `--json` or with `--comments`, `gh pr checks --json`, `gh pr edit`, `gh issue create --parent` (gh 2.46).

    python3 -I -m unittest discover -s tools/brain -p 'test_guard.py'
"""
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import common  # noqa: E402

HOME_SPELLINGS = r'(?:~|\$HOME|\$\{HOME\}|/home/[^/\s]+)'
KEY_FILE = r'(?<![\w.-])(?:indexers|limits|provider|metadata-keys|admin-login|[\w-]*-secrets)\.json\b|(?<![\w.-])db\.sqlite\b'
CONTAINER_SECRET = re.compile(KEY_FILE + r'|(?<![\w.-])/config\b')
BRAIN_TOOL = re.compile(r'^(?:python3?\s+(?:-I\s+)?)?(?:\./)?tools/brain/[\w.-]+\.(?:py|sh)(?:\s|$)|^npm run check:brain\b')
CUT = re.compile(r'&&|\|\||[;|\n`]|\$\(')
REDIRECT = re.compile(r'^\d*[<>]+&?')
OPEN_FOLDER = {'ls', 'cd', 'du', 'df', 'stat', 'mkdir'}  # commands that name a folder without reading a file in it
SEARCH = {'find', 'grep', 'egrep', 'fgrep', 'rg', 'ag', 'ack', 'tree', 'tar', 'zip', 'rsync', 'cp'}  # a bare `/` counts for these only
SAFE_SUBFOLDERS = ('store', 'backups')
# The one narrow exception inside a test copy's config folder (#280, spec #279): the NZBs AltMount moves there when an
# import fails (`/config/.nzbs/failed/<category>/<release>.nzb` in its container), kept as evidence. They hold no key.
FAILED_NZBS = ('altmount-kf', 'config', '.nzbs', 'failed')

SETTINGS_HINT = ('use `python3 -I tools/brain/testbed.py read-settings [side]`, which prints every test copy\'s settings '
                 'with secrets as ***; runs and preflights go through tools/brain/brainrun.py')
REFUSE_SECRET = f"That would show a test key file or a test copy's config (secrets): {SETTINGS_HINT}."
GH_VIEW = 'gh issue view {n} --json number,title,body,labels,comments'
GH_PR = 'gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -F body=@<file>'
GH_PARENT = ('create the issue without --parent, then `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues '
             '-F sub_issue_id=<db id>`')


def test_dirs():
    """The test folder (`common.DEFAULT_TEST_DIR`, and TEST_DIR when set), as given and with links resolved."""
    given = [common.DEFAULT_TEST_DIR] + ([os.environ['TEST_DIR']] if os.environ.get('TEST_DIR') else [])
    return {f(os.path.expanduser(d)) for d in given for f in (os.path.normpath, os.path.realpath)}


def _resolve(value, cwd):
    return os.path.normpath(os.path.join(cwd, os.path.expandvars(os.path.expanduser(value))))


def failed_nzb(rel, folder_ok=False):
    """Whether `rel`, a path inside the test folder, is one of AltMount's failed NZBs (#280): a `.nzb` file under
    FAILED_NZBS, or, when `folder_ok` (a command that only names a folder: ls, stat), that folder or one under it."""
    parts = os.path.normpath(rel).split(os.sep)
    if tuple(parts[:len(FAILED_NZBS)]) != FAILED_NZBS or '..' in parts:
        return False
    return (len(parts) > len(FAILED_NZBS) and parts[-1].endswith('.nzb')) or folder_ok


def _place(path, folder_ok=False):
    """'secret' (inside the test folder, outside store/ and backups/ and not one of AltMount's failed NZBs), 'folder' (the
    test folder or one holding it) or None. The path as given and with links resolved must both pass."""
    places = set()
    for p in {path, os.path.realpath(path)}:
        for d in test_dirs():
            if p.startswith(d + os.sep):
                rel = p[len(d) + 1:]
                if rel.split(os.sep)[0] not in SAFE_SUBFOLDERS and not failed_nzb(rel, folder_ok):
                    places.add('secret')
                break
            if p == d or d.startswith(p.rstrip(os.sep) + os.sep):
                places.add('folder')
                break
    return 'secret' if 'secret' in places else ('folder' if places else None)


def _names_test_folder(segment, command):
    """The test folder spelled out in the text (also inside quotes and code), e.g. `~/kaijuflow-test/uu` or `$TEST_DIR`."""
    home = os.path.normpath(os.path.expanduser('~'))
    spellings = [r'\$\{?TEST_DIR\}?']
    for d in test_dirs():
        spellings.append(re.escape(d))
        if d.startswith(home + os.sep):
            spellings.append(HOME_SPELLINGS + re.escape(d[len(home):]))
    for m in re.finditer('(?:' + '|'.join(spellings) + r')(?![\w.-])', segment):
        tail = segment[m.end():]
        if tail.startswith('/'):
            if failed_nzb(re.match(r'/([^\s"\';|&<>]*)', tail).group(1), command in OPEN_FOLDER):
                continue  # one of AltMount's failed NZBs, still judged with its links resolved (_reaches_test_folder)
            if re.match(r'/([^/\s"\']*)', tail).group(1) not in SAFE_SUBFOLDERS:
                return True
        elif command not in OPEN_FOLDER:  # the folder itself, e.g. `grep -r x ~/kaijuflow-test`
            return True
    return False


def _words(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _reaches_test_folder(words, cwd):
    """A word that, as a path from `cwd`, lies in the test folder, or is a folder holding it and is searched."""
    command = words[1] if words[:1] == ['sudo'] and len(words) > 1 else (words[0] if words else '')
    for word in words:
        word = REDIRECT.sub('', word)
        if word.startswith('-'):
            word = word.partition('=')[2]  # --file=<path>
        elif re.fullmatch(r'/+', word) and command not in SEARCH:
            continue  # `cut -d /`, `a / b` or a `//` comment line in a heredoc (each heredoc line is judged as a command)
        if not word:
            continue
        place = _place(_resolve(word, cwd), command in OPEN_FOLDER)
        if place == 'secret' or (place == 'folder' and command not in OPEN_FOLDER):
            return True
    return False


def _reads_in_container(words, segment):
    return (bool({'docker', 'podman'} & set(words)) and bool({'exec', 'cp'} & set(words))
            and bool(CONTAINER_SECRET.search(segment)))


def _gh(words):
    if len(words) < 3 or words[0] != 'gh':
        return None
    rest = words[1:]
    if rest[:2] == ['issue', 'view'] and any(t in ('--comments', '-c') for t in rest):
        number = next((t for t in rest[2:] if re.fullmatch(r'\d+', t)), '<n>')
        return f'`gh issue view --comments` fails here (Projects classic GraphQL error); use `{GH_VIEW.format(n=number)}`.'
    if rest[:2] == ['issue', 'view'] and not any(t in ('--json', '--web', '-w') or t.startswith('--json=') for t in rest):
        number = next((t for t in rest[2:] if re.fullmatch(r'\d+', t)), '<n>')
        return f'`gh issue view` without `--json` fails here (Projects classic GraphQL error); use `{GH_VIEW.format(n=number)}`.'
    if rest[:2] == ['pr', 'checks'] and any(t == '--json' or t.startswith('--json=') for t in rest):
        number = next((t for t in rest[2:] if re.fullmatch(r'\d+', t)), '<n>')
        return (f'gh 2.46 has no `gh pr checks --json`, so a watch built on it never fires; use '
                f'`python3 -I tools/brain/prwatch.py {number}` in the background (one line when the PR is ready to merge).')
    if rest[:2] == ['pr', 'edit']:
        return f'`gh pr edit` fails here (Projects classic GraphQL error); use `{GH_PR}`.'
    if rest[:2] == ['issue', 'create'] and any(t == '--parent' or t.startswith('--parent=') for t in rest):
        return f'gh 2.46 has no `--parent`; {GH_PARENT}.'
    return None


def check_command(command, cwd):
    for segment in (s.strip() for s in CUT.split(command)):
        if not segment:
            continue
        words = _words(segment)
        hit = _gh(words)
        if hit:
            return hit
        if BRAIN_TOOL.match(segment):
            continue
        if (_names_test_folder(segment, words[0] if words else '') or _reaches_test_folder(words, cwd)
                or _reads_in_container(words, segment)):
            return REFUSE_SECRET
        if words[:1] == ['cd'] and words[1:2] != ['-']:
            cwd = _resolve(words[1] if len(words) > 1 else '~', cwd)
    return None


def _protected_path(value, cwd):
    if not value:
        return False
    head = re.split(r'[*?\[{]', value, maxsplit=1)[0]
    return _place(_resolve(head, cwd)) is not None


def refusal(tool, tool_input, cwd=None):
    """The sentence that refuses this tool call, or None when it may go ahead. `cwd`: the call's folder (the payload's)."""
    cwd = cwd or os.getcwd()
    if tool == 'Bash':
        return check_command(tool_input.get('command') or '', cwd)
    glob = tool_input.get('glob') or ''
    paths = ([tool_input.get('file_path')] if tool == 'Read'
             else [tool_input.get('path') or cwd] + ([glob] if glob.startswith(('/', '~', '$')) else []))  # else relative to path
    if tool in ('Read', 'Grep') and any(_protected_path(p, cwd) for p in paths):
        return REFUSE_SECRET
    return None


def main():
    try:
        call = json.load(sys.stdin)
        message = refusal(call.get('tool_name'), call.get('tool_input') or {}, call.get('cwd'))
    except (ValueError, AttributeError, TypeError):
        return 0
    if message:
        print(message, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
