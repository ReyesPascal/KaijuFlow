"""Tests for prwatch.py (wait for a PR's CI, say once whether it is ready to merge). gh is faked; no network."""
import contextlib
import copy
import io
import json
import os
import unittest

import prwatch

GREEN = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', '2026-11-23-prwatch',
                                    'pr-230-green.json')))  # PR #230 as gh 2.46 printed it, all three checks passed


def with_checks(answer, **changes):
    """The captured answer with the named checks changed, e.g. a4-isolated={'status': 'IN_PROGRESS', 'conclusion': ''}."""
    a = copy.deepcopy(answer)
    for c in a['statusCheckRollup']:
        c.update(changes.get(c['name'].split(' ')[0], {}))
    return a


RUNNING = with_checks(GREEN, **{'a4-isolated': {'status': 'IN_PROGRESS', 'conclusion': ''}})
RED = with_checks(GREEN, **{'discovery-stream': {'conclusion': 'FAILURE'}})


class FakeGh:
    """Answers `gh pr view` with the next answer in turn (the last one repeats); an Exception in the list is raised."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, args):
        self.calls.append(args)
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a if isinstance(a, str) else json.dumps(a)


def run(argv, fake, slept=None):
    """main's exit code and lines; `slept`, when given, gets each wait main asks for."""
    out, t = io.StringIO(), [0.0]

    def sleep(s):
        t[0] += s
        if slept is not None:
            slept.append(s)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = prwatch.main(argv, run_gh=fake, sleep=sleep, clock=lambda: t[0])
    return code, out.getvalue().splitlines()


class PrWatchTest(unittest.TestCase):
    def test_green_says_ready_at_once_and_exits_0(self):
        code, lines = run(['230'], FakeGh(GREEN))
        self.assertEqual((code, lines), (0, ['PR #230 GREEN at b025f27']))

    def test_reads_the_fields_gh_2_46_has(self):
        fake = FakeGh(GREEN)
        run(['230'], fake)
        self.assertEqual(fake.calls[0], ['pr', 'view', '230', '--json', 'headRefOid,isDraft,statusCheckRollup'])

    def test_running_prints_one_line_at_once_then_the_verdict_when_done(self):
        code, lines = run(['230'], FakeGh(RUNNING, RUNNING, RUNNING, GREEN))
        self.assertEqual(code, 0)
        self.assertEqual(lines, ['PR #230: watching 3 checks at b025f27, 1 still running', 'PR #230 GREEN at b025f27'])

    def test_the_last_check_finishing_is_seen_within_5_s(self):
        slept = []
        self.assertEqual(run(['230'], FakeGh(RUNNING, GREEN), slept)[0], 0)
        self.assertEqual(slept, [5.0])

    def test_red_names_the_failed_checks_and_exits_1(self):
        code, lines = run(['230'], FakeGh(RUNNING, RED))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], 'PR #230 RED at b025f27: discovery-stream')

    def test_a_failed_check_is_red_at_once_while_others_still_run(self):
        # 2026-11-24, indexers-298 at 19c40ba: KaijuFlow CI failed 81 s in, discovery-stream ran 4 more minutes
        failed_early = with_checks(RED, **{'a4-isolated': {'status': 'IN_PROGRESS', 'conclusion': ''}})
        fake = FakeGh(failed_early, GREEN)
        code, lines = run(['230'], fake)
        self.assertEqual((code, lines), (1, ['PR #230 RED at b025f27: discovery-stream (1 check still running)']))
        self.assertEqual(len(fake.calls), 1)

    def test_a_draft_is_named_so(self):
        draft = dict(GREEN, isDraft=True)
        self.assertEqual(run(['230'], FakeGh(draft))[1], ['PR #230 GREEN at b025f27 (draft)'])

    def test_no_checks_yet_counts_as_running(self):
        none = dict(GREEN, statusCheckRollup=[])
        code, lines = run(['230'], FakeGh(none, GREEN))
        self.assertEqual(lines, ['PR #230: watching at b025f27, no check has started yet', 'PR #230 GREEN at b025f27'])

    def test_a_gh_failure_is_printed_and_exits_2_instead_of_waiting(self):
        code, lines = run(['230'], FakeGh(prwatch.GhError('unknown flag: --json')))
        self.assertEqual(code, 2)
        self.assertIn('unknown flag: --json', lines[0])

    def test_output_that_is_not_json_exits_2(self):
        self.assertEqual(run(['230'], FakeGh('not json'))[0], 2)

    def test_still_running_after_the_timeout_exits_3(self):
        code, lines = run(['230', '--interval', '10', '--timeout', '30'], FakeGh(RUNNING))
        self.assertEqual(code, 3)
        self.assertEqual(lines[-1], 'PR #230 TIMEOUT at b025f27: 1 of 3 checks still running after 30 s')

    def test_a_new_push_is_said_and_its_checks_are_waited_for(self):
        pushed = dict(RUNNING, headRefOid='c0ffee1' + GREEN['headRefOid'][7:])
        code, lines = run(['230'], FakeGh(RUNNING, pushed, dict(GREEN, headRefOid=pushed['headRefOid'])))
        self.assertEqual(code, 0)
        self.assertIn('PR #230: new push, now at c0ffee1; waiting for its checks again', lines)
        self.assertEqual(lines[-1], 'PR #230 GREEN at c0ffee1')

    def test_a_commit_status_counts_too(self):
        status = dict(GREEN, statusCheckRollup=GREEN['statusCheckRollup'] + [{'__typename': 'StatusContext', 'context': 'ext', 'state': 'PENDING'}])
        self.assertEqual(prwatch.verdict(status), ('running', 1, 4))
        status['statusCheckRollup'][-1]['state'] = 'ERROR'
        self.assertEqual(prwatch.verdict(status), ('red', ['ext'], 0))

    def test_a_bad_argument_exits_2(self):
        for argv in ([], ['x'], ['230', '--interval']):
            self.assertEqual(run(argv, FakeGh(GREEN))[0], 2, argv)


if __name__ == '__main__':
    unittest.main()
