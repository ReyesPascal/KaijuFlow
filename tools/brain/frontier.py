"""The frontier: the tickets that can start now, read from the tracker.

    python3 -I tools/brain/frontier.py [parent]

Prints the open sub-issues of the parent (default #183, the map) that have no open blocker and no assignee,
in the parent's sub-issue order, one line each: number, all its labels (e.g. `[bug, ready-for-agent]`), title; a
`ready-for-human` ticket gets one more line (run in this session by the runbook, the owner's go per live step, never a
parallel build). Issues labelled `spec` are maps, not tickets: left out, and one warning on stderr names any open one that
carries a triage label.
When none qualifies it prints one line saying so. An open sub-issue whose body repeats its blockers (a "Blocked by"
heading or line) gets a warning on stderr: the tracker's blocked-by links are the only source. Exits 0; 1 when gh fails or prints something that is not JSON;
2 when the parent is not an issue number. Every failure is one line on stderr.
The repo is the clone's own: gh fills `{owner}/{repo}` from the current directory's git remote.
The frontier query is in docs/agents/issue-tracker.md; `issue_dependencies_summary.blocked_by` counts open blockers only.
"""
import json
import re
import subprocess
import sys

DEFAULT_PARENT = 183  # the map (spec #183 since 2026-11-20; #159 before, #58 before that)
# One page is the whole list: GitHub allows at most 100 sub-issues per parent.
BLOCKED_BY_IN_BODY = re.compile(r'^\s*(#+\s*Blocked by\s*$|Blocked by\s*:)', re.IGNORECASE | re.MULTILINE)
TRIAGE_LABELS = ('needs-triage', 'needs-info', 'ready-for-agent', 'ready-for-human', 'wontfix')
HUMAN_LINE = ("  Run in this session by the runbook (tools/brain/RUNBOOK.md); the owner's go for each live step; "
              'never a parallel build.')


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


def is_spec(issue):
    return any(lb['name'] == 'spec' for lb in issue['labels'])


def repeats_blockers(issue):
    """An open sub-issue whose body lists blockers that the tracker's links already hold (and that go stale)."""
    return issue['state'] == 'open' and bool(BLOCKED_BY_IN_BODY.search(issue.get('body') or ''))


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
    ready = [i for i in issues if can_start(i) and not is_spec(i)]
    for i in ready:
        names = [lb['name'] for lb in i['labels']]
        print(f"#{i['number']} [{', '.join(names)}] {i['title']}")
        if 'ready-for-human' in names:
            print(HUMAN_LINE)
    if not ready:
        print(f'Nothing can start: #{parent} has no open sub-issue without a blocker or an assignee.')
    labelled = [i['number'] for i in issues if i['state'] == 'open' and is_spec(i)
                and any(lb['name'] in TRIAGE_LABELS for lb in i['labels'])]
    if labelled:
        print(f"Warning: spec issues {', '.join('#%d' % n for n in labelled)} carry a triage label "
              '(docs/agents/triage-labels.md); a spec is a map, not a ticket: remove the label.', file=sys.stderr)
    for i in issues:
        if repeats_blockers(i):
            print(f'Warning: #{i["number"]}\'s body has a "Blocked by" section. The tracker\'s blocked-by links are the '
                  'only source (docs/agents/issue-tracker.md); remove the section.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
