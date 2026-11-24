"""The retired recording path (#273, ADR 0010): the commands real-use checks replaced stop here unless run with --revive.

The replayed Recording and everything around it (`brainrun.py run`, `record` and its top-ups and proof replay, `smoke`,
`preflight --for run|record` with their recording checks, `check --run` and the judgement against the previous run, the
speed tests' pool, `pool.py draw|check-ids`, and the Speed Check page of timed runs) is archived in tools/brain/archive/,
not deleted (archive/README.md). Each retired command prints one line saying so and exits EXIT_RETIRED, touching nothing;
with --revive it runs from the archive as it did before (owner, 2026-11-24: "ARCHIVE THE OLD STUFF AND STOP IT FROM COMING
BACK UNLESS WE TELL IT TO"). The archive is out of `npm run check:brain`, so a revived command may need fixing first.
"""
import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(HERE, 'archive')
EXIT_RETIRED = 5  # a retired command run without --revive (0-4 and 130 are the live commands' own codes)
REVIVE = '--revive'
# the live tool -> the archive module that holds its retired commands (each has main(argv))
ARCHIVED = {'brainrun': 'retired_run', 'pool': 'pool_draw', 'build_page': 'build_page'}


def message(command):
    """The one line a retired command prints."""
    return (f'`{command}` is retired by ADR 0010: real-use checks (brainrun.py check --quick, drill) replaced the replayed '
            'Recording. It is kept in tools/brain/archive/ (README.md there) and runs only when you add --revive, on the '
            "owner's word.")


def archived_main(name):
    """main(argv) of an archive module."""
    if ARCHIVE not in sys.path:
        sys.path.insert(0, ARCHIVE)
    return importlib.import_module(name).main


def revive(tool, argv):
    """Runs a retired command of `tool` from the archive with `argv` (--revive taken out); its exit code."""
    print(f'Revived from the archive (ADR 0010 retired it): {tool} {" ".join(argv)}', flush=True)
    return archived_main(ARCHIVED[tool])(argv)


def gate(tool, command, argv):
    """A retired command: without --revive, its one line and EXIT_RETIRED; with it, the archive's exit code."""
    if REVIVE not in argv:
        print(message(command))
        return EXIT_RETIRED
    return revive(tool, [a for a in argv if a != REVIVE])


# The live docs (repo paths) hold real-use checks only; test_live_docs.py fails when one describes a retired command again.
LIVE_DOCS = ('CLAUDE.md', 'tools/brain/RUNBOOK.md', 'tools/brain/README.md', 'tools/brain/docs/rules.md',
             'tools/brain/docs/formats.md', 'tools/brain/docs/testbed.md', 'tools/brain/docs/diagnosing-agent.md',
             'docs/agents/resume.md', 'docs/agents/testing.md', 'docs/agents/issue-tracker.md', 'docs/agents/domain.md',
             'docs/agents/triage-labels.md', 'docs/agents/review-standards.md')
# what a retired command or step looks like in a doc -> how the finding names it
RETIRED_WORDS = (
    (re.compile(r'brainrun\.py (run|record|smoke)\b'), lambda m: f'brainrun.py {m.group(1)} (a retired command)'),
    (re.compile(r'preflight --for (run|record)\b'), lambda m: f'preflight --for {m.group(1)} (a retired command)'),
    (re.compile(r'check --run\b'), lambda m: 'check --run (a retired command)'),
    (re.compile(r'pool\.py (draw|check-ids)\b'), lambda m: f'pool.py {m.group(1)} (a retired command)'),
    (re.compile(r'build_page\.py'), lambda m: 'build_page.py (the retired Speed Check page of timed runs)'),
    (re.compile(r'--no-wait\b'), lambda m: '--no-wait (the retired replay wait)'),
    (re.compile(r'\btop(?:ped|ping)?[- ](?:it )?up\b', re.I), lambda m: f'{m.group(0)} (a retired step: a top-up of a Recording)'),
    (re.compile(r'\b(grouped|halving) runs?\b', re.I), lambda m: f'{m.group(0)} (a retired run)'),
)


def retired_lines(name, text):
    """`<name>:<line>: <what>` for every retired command or step `text` describes."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for pattern, what in RETIRED_WORDS:
            out += [f'{name}:{n}: {what(m)}' for m in pattern.finditer(line)]
    return out
