"""Tests for frontier.py (the map's next tickets, read from the tracker). The gh call is faked; no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import unittest

import frontier


def sub_issue(number, state='open', assignees=(), labels=('ready-for-agent',), blocked_by=0, title=None):
    """One entry as `gh api repos/<repo>/issues/<parent>/sub_issues` returns it (the fields the command reads)."""
    return {'number': number, 'title': title or f'Ticket {number}', 'state': state,
            'assignees': [{'login': a} for a in assignees], 'labels': [{'name': n} for n in labels],
            'issue_dependencies_summary': {'blocked_by': blocked_by, 'blocking': 0, 'total_blocked_by': blocked_by,
                                           'total_blocking': 0}}


SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', '2026-11-14', 'gh-sub-issues-58.json')


class FakeGh:
    """Answers `gh api` for one parent's sub-issues and refuses anything else, as gh does (a 404 for another issue)."""

    def __init__(self, issues, parent=58):
        self.issues, self.parent = issues, parent  # a list of entries, or the raw text gh printed

    def __call__(self, args):
        if args != ['api', f'repos/ReyesPascal/KaijuFlow/issues/{self.parent}/sub_issues?per_page=100']:
            raise frontier.GhError('gh: Not Found (HTTP 404)')
        return self.issues if isinstance(self.issues, str) else json.dumps(self.issues)


def run(argv, gh):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = frontier.main(argv, gh=gh)
    return code, out.getvalue()


def numbers(output):
    return [int(line.split()[0].lstrip('#')) for line in output.splitlines() if line.startswith('#')]


class FrontierTest(unittest.TestCase):
    def test_reads_a_captured_gh_answer(self):
        """#58's sub-issues as gh printed them on 2026-11-14 (bodies, repository and reactions removed)."""
        with open(SAMPLE) as f:
            code, out = run([], FakeGh(f.read()))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            '#119 [bug, ready-for-agent] Unscramble hits its 15 s limit when three large Sources are prepared at once, '
            'and a good Source fails',
            '#120 [bug, ready-for-agent] KaijuFlow lists and verifies disc images (.iso) that the Backend cannot play',
            '#111 [enhancement, ready-for-agent] brainrun: short runs by choosing sides, rounds and titles',
        ])

    def test_prints_open_sub_issues_in_map_order(self):
        gh = FakeGh([sub_issue(119), sub_issue(120), sub_issue(111)])
        code, out = run([], gh)
        self.assertEqual(code, 0)
        self.assertEqual(numbers(out), [119, 120, 111])

    def test_leaves_out_a_closed_sub_issue(self):
        code, out = run([], FakeGh([sub_issue(63, state='closed'), sub_issue(119)]))
        self.assertEqual(numbers(out), [119])

    def test_leaves_out_a_sub_issue_with_an_open_blocker(self):
        code, out = run([], FakeGh([sub_issue(64, blocked_by=2), sub_issue(120)]))
        self.assertEqual(numbers(out), [120])

    def test_leaves_out_an_assigned_sub_issue(self):
        code, out = run([], FakeGh([sub_issue(119, assignees=['ReyesPascal']), sub_issue(111)]))
        self.assertEqual(numbers(out), [111])

    def test_each_line_names_the_labels(self):
        gh = FakeGh([sub_issue(119, labels=['bug', 'ready-for-agent'], title='Unscramble limit'),
                     sub_issue(127, labels=['ready-for-human'], title='New baseline')])
        code, out = run([], gh)
        self.assertEqual(out.splitlines()[:2], ['#119 [bug, ready-for-agent] Unscramble limit',
                                                '#127 [ready-for-human] New baseline'])

    def test_reads_the_parent_given_on_the_command_line(self):
        code, out = run(['125'], FakeGh([sub_issue(130)], parent=125))
        self.assertEqual((code, numbers(out)), (0, [130]))

    def test_says_so_when_nothing_can_start(self):
        code, out = run([], FakeGh([sub_issue(64, blocked_by=2), sub_issue(63, state='closed')]))
        self.assertEqual((code, out), (0, 'Nothing can start: #58 has no open sub-issue without a blocker or an assignee.\n'))

    def test_exits_1_with_gh_message_when_gh_fails(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, out = run(['999'], FakeGh([sub_issue(119)]))
        self.assertEqual((code, out), (1, ''))
        self.assertIn('HTTP 404', err.getvalue())


if __name__ == '__main__':
    unittest.main()
