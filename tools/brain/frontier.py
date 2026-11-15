"""The frontier: the tickets that can start now, read from the tracker.

    python3 -I tools/brain/frontier.py [parent]

Prints the open sub-issues of the parent (default #58, the map) that have no open blocker and no assignee,
in the parent's sub-issue order, one line each: number, all its labels (e.g. `[bug, ready-for-agent]`), title.
When none qualifies it prints one line saying so. Exits 0; 1 when gh fails or prints something that is not JSON;
2 when the parent is not an issue number. Every failure is one line on stderr.
The repo is the clone's own: gh fills `{owner}/{repo}` from the current directory's git remote.
The frontier query is in docs/agents/issue-tracker.md; `issue_dependencies_summary.blocked_by` counts open blockers only.
"""
import json
import subprocess
import sys

DEFAULT_PARENT = 58  # the map
# One page is the whole list: GitHub allows at most 100 sub-issues per parent.


class GhError(Exception):
    pass


def gh(args):
    """stdout of `gh <args>`; GhError with gh's message when it fails."""
    try:
        done = subprocess.run(['gh', *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GhError(str(e)) from e
    if done.returncode:
        raise GhError((done.stderr or done.stdout).strip() or f'gh exited {done.returncode}')
    return done.stdout


def can_start(issue):
    """The frontier rule: open, no open blocker, no assignee."""
    return issue['state'] == 'open' and not issue['issue_dependencies_summary']['blocked_by'] and not issue['assignees']


def main(argv, run_gh=gh):
    try:
        parent = int(argv[0]) if argv else DEFAULT_PARENT
    except ValueError:
        print(f'Usage: frontier.py [parent]: the parent is an issue number, not {argv[0]!r}.', file=sys.stderr)
        return 2
    try:
        issues = json.loads(run_gh(['api', f'repos/{{owner}}/{{repo}}/issues/{parent}/sub_issues?per_page=100']))
    except GhError as e:
        print(f'Cannot read the sub-issues of #{parent}: {e}', file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f'Cannot read the sub-issues of #{parent}: gh did not print JSON ({e}).', file=sys.stderr)
        return 1
    ready = [i for i in issues if can_start(i)]
    for i in ready:
        labels = ', '.join(lb['name'] for lb in i['labels'])
        print(f"#{i['number']} [{labels}] {i['title']}")
    if not ready:
        print(f'Nothing can start: #{parent} has no open sub-issue without a blocker or an assignee.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
