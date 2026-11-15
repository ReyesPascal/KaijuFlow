"""The frontier: the tickets that can start now, read from the tracker.

    python3 -I tools/brain/frontier.py [parent]

Prints the open sub-issues of the parent (default #58, the map) that have no open blocker and no assignee,
in the parent's sub-issue order, one line each: number, labels (ready-for-agent or ready-for-human), title.
When none qualifies it prints one line saying so. Exits 0; 1 when gh fails (message on stderr).
The frontier query is in docs/agents/issue-tracker.md; `issue_dependencies_summary.blocked_by` counts open blockers only.
"""
import json
import subprocess
import sys

REPO = 'ReyesPascal/KaijuFlow'
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


def main(argv, gh=gh):
    parent = int(argv[0]) if argv else DEFAULT_PARENT
    try:
        issues = json.loads(gh(['api', f'repos/{REPO}/issues/{parent}/sub_issues?per_page=100']))
    except GhError as e:
        print(f'Cannot read the sub-issues of #{parent}: {e}', file=sys.stderr)
        return 1
    ready = [i for i in issues if i['state'] == 'open' and not i['issue_dependencies_summary']['blocked_by']
             and not i['assignees']]
    for i in ready:
        labels = ', '.join(lb['name'] for lb in i['labels'])
        print(f"#{i['number']} [{labels}] {i['title']}")
    if not ready:
        print(f'Nothing can start: #{parent} has no open sub-issue without a blocker or an assignee.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
