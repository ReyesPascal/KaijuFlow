"""Wait for a pull request's CI and say once whether it is ready to merge (#231).

    python3 -I tools/brain/prwatch.py <pr> [--interval S] [--timeout S]

Run it with the shell's background mode: it prints one line at once (how many checks, how many still running, the head
commit), then exits on the first final state with one line:

    PR #230 GREEN at b025f27              exit 0: every check passed (a draft says "(draft)": not mergeable yet)
    PR #230 RED at b025f27: a4-isolated   exit 1: the checks that failed
    PR #230 TIMEOUT at b025f27: ...       exit 3: still running after --timeout seconds (default 1800)

A new push while it waits starts the count again (one line says so). A gh failure is printed and exits 2, so a broken
watch never looks like "still running". It reads `gh pr view <pr> --json headRefOid,isDraft,statusCheckRollup`, which
gh 2.46 has (`gh pr checks --json` does not: the guard refuses it).
"""
import json
import subprocess
import sys
import time

FIELDS = 'headRefOid,isDraft,statusCheckRollup'
PASSED = ('SUCCESS', 'NEUTRAL', 'SKIPPED')


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


def outcome(check):
    """'running', 'passed' or 'failed' for one entry of statusCheckRollup (a CheckRun or a commit StatusContext)."""
    if check.get('__typename') == 'StatusContext' or 'state' in check and 'conclusion' not in check:
        state = (check.get('state') or '').upper()
        return 'running' if state in ('', 'PENDING', 'EXPECTED') else 'passed' if state == 'SUCCESS' else 'failed'
    if (check.get('status') or '').upper() != 'COMPLETED':
        return 'running'
    return 'passed' if (check.get('conclusion') or '').upper() in PASSED else 'failed'


def name(check):
    return check.get('name') or check.get('context') or '?'


def verdict(answer):
    """('running', n running, n checks) while any check runs or none has started; ('green',) or ('red', [failed names])."""
    checks = answer.get('statusCheckRollup') or []
    if not checks:
        return 'running', 0, 0
    got = [(name(c), outcome(c)) for c in checks]
    running = sum(1 for _, o in got if o == 'running')
    if running:
        return 'running', running, len(got)
    failed = [n for n, o in got if o == 'failed']
    return ('red', failed) if failed else ('green',)


def main(argv, run_gh=gh, sleep=time.sleep, clock=time.monotonic):
    args = list(argv)
    opts = {'--interval': 20.0, '--timeout': 1800.0}
    try:
        for flag in opts:
            if flag in args:
                i = args.index(flag)
                opts[flag] = float(args[i + 1])
                del args[i:i + 2]
        pr = int(args[0]) if len(args) == 1 else None
    except (ValueError, IndexError):
        pr = None
    if pr is None:
        print('Usage: prwatch.py <pr number> [--interval S] [--timeout S]', file=sys.stderr)
        return 2
    start, head, first = clock(), None, True
    while True:
        try:
            answer = json.loads(run_gh(['pr', 'view', str(pr), '--json', FIELDS]))
        except (GhError, json.JSONDecodeError) as e:
            print(f'PR #{pr}: cannot read its checks: {e}', flush=True)
            return 2
        sha = (answer.get('headRefOid') or '')[:7]
        draft = ' (draft)' if answer.get('isDraft') else ''
        v = verdict(answer)
        if head is not None and sha != head:
            print(f'PR #{pr}: new push, now at {sha}; waiting for its checks again', flush=True)
            start = clock()
        head = sha
        if v[0] == 'green':
            print(f'PR #{pr} GREEN at {sha}{draft}', flush=True)
            return 0
        if v[0] == 'red':
            print(f"PR #{pr} RED at {sha}{draft}: {', '.join(v[1])}", flush=True)
            return 1
        if first:
            print(f'PR #{pr}: watching {v[2]} checks at {sha}{draft}, {v[1]} still running' if v[2]
                  else f'PR #{pr}: watching at {sha}{draft}, no check has started yet', flush=True)
            first = False
        if clock() - start >= opts['--timeout']:
            print(f"PR #{pr} TIMEOUT at {sha}{draft}: {v[1]} of {v[2]} checks still running after {opts['--timeout']:.0f} s", flush=True)
            return 3
        sleep(opts['--interval'])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
