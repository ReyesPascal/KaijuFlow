"""Tests for Case logs and the diagnosing agent (#287, spec #279), through Diagnosis: what a check leaves when a failure
has no proved cause (a Case log, the agent started, one line to the owner), and the commands the agent works the log
with (`diagnosis.py case ...`), each claim checked against the evidence it quotes. The evidence folders are the real
plays in fixtures/2026-11-24-diagnosis/ (README there).
    python3 -I -m unittest discover -s tools/brain -p 'test_caselog.py'
"""
import contextlib
import io
import os
import unittest

import caselog
import clues
import diagnosis
from test_diagnosis import DEAD_PACK, INDEXER_DOWN, READ_ERROR, SIC, TWO_REFUSALS, stored_check
from test_settings import tempdir

INCEPTION_PAGE = ('{"step": "indexer_page", "source": "NinjaCentral", "ms": 3, "ok": false, "t": '
                  '"2026-11-24T06:00:46.965Z", "ref": "tt1375666", "page": 1}')


def after(case, plays, cases=None, **kw):
    root, run_dir = stored_check(case, plays=plays)
    cases = cases or os.path.join(tempdir(case), 'cases')
    summary = diagnosis.after_check(run_dir, root, cases=cases, **kw)
    return root, run_dir, cases, summary


def case_cmd(cases, *args):
    """`diagnosis.py case <args> --cases <cases>`: (exit code, what it printed)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = diagnosis.main(['diagnosis.py', 'case', *args, '--cases', cases])
    return code, out.getvalue()


def logs(cases):
    return {name: caselog.load(os.path.join(cases, name)) for name in sorted(os.listdir(cases))}


class OpensACaseLogTest(unittest.TestCase):
    def test_an_unmatched_failure_opens_a_case_log_with_its_path_and_every_clue_run(self):
        root, run_dir, cases, summary = after(self, (INDEXER_DOWN,))

        [(name, log)] = logs(cases).items()
        self.assertEqual(log['id'], name)
        self.assertEqual(log['status'], 'open')
        self.assertEqual(log['fingerprint'], summary['plays'][0]['failures'][0]['fingerprint'])
        [occ] = log['occurrences']
        self.assertEqual((occ['n'], occ['check'], occ['label'], occ['release'], occ['how']),
                         (1, '2026-11-24T060037Z-grouped-265', 'Inception', None, 'check'))
        self.assertTrue(os.path.samefile(caselog.evidence_folder(os.path.join(cases, name), occ),
                                         os.path.join(run_dir, 'evidence', '01-265-inception-indexer-down')))
        path = log['observations'][0]
        self.assertEqual(path['by'], 'code')
        self.assertIn('the first step whose output is wrong: indexer_page not ok', path['says'])
        self.assertEqual(path['quotes'], [{'occurrence': 1, 'file': 'steps.jsonl', 'text': INCEPTION_PAGE}])
        self.assertEqual(sorted(r['clue'] for r in log['clue_runs']), sorted(clues.CLUES))  # the library, once
        self.assertEqual({r['occurrence'] for r in log['clue_runs']}, {1})
        self.assertTrue(os.path.exists(os.path.join(cases, name, caselog.READABLE)))
        self.assertEqual(summary['cases'], [{'id': name, 'status': 'open', 'occurrences': 1, 'new': True}])
        self.assertIn('open Case logs: 1', '\n'.join(diagnosis.report_section(summary)))

    def test_a_proved_failure_opens_none_and_a_suspected_one_does(self):
        root, run_dir, cases, summary = after(self, (READ_ERROR, TWO_REFUSALS))
        [log] = logs(cases).values()  # HHWEB is found twice; SiC-AsRequested's look-alike has no confirming test
        self.assertEqual([o['release'] for o in log['occurrences']], [SIC])
        self.assertTrue(log['id'].startswith('check-miss-import-wait-'), log['id'])

    def test_the_same_failure_in_a_later_check_joins_its_case_log(self):
        root, run_dir, cases, _ = after(self, (INDEXER_DOWN,))
        _, later, _, summary = after(self, (INDEXER_DOWN, DEAD_PACK), cases=cases)
        [log] = logs(cases).values()
        self.assertEqual([o['n'] for o in log['occurrences']], [1, 2])
        self.assertEqual(summary['cases'], [{'id': log['id'], 'status': 'open', 'occurrences': 2, 'new': False}])
        again = diagnosis.after_check(later, os.path.dirname(later), cases=cases)  # the same check once more: no new occurrence
        self.assertEqual(len(logs(cases)[log['id']]['occurrences']), 2)
        self.assertEqual(again['cases'][0]['occurrences'], 2)


class NeverRepeatsAClueTest(unittest.TestCase):
    def setUp(self):
        self.root, self.run_dir, self.cases, _ = after(self, (INDEXER_DOWN,))
        [self.id] = logs(self.cases)
        self.asked = []

        def counted(ev, failure):  # a Clue built after the case opened, counting how often it is asked
            self.asked.append(failure['fingerprint'])
            return clues.NO, ['the stand-in kept no answer for the search']
        clues.CLUES['search-answer-kept'] = clues.Clue('search-answer-kept', 'Did the stand-in keep an answer?', counted)
        self.addCleanup(clues.CLUES.pop, 'search-answer-kept')

    def test_a_second_attempt_skips_the_clues_already_run_and_runs_only_the_new_one(self):
        before = logs(self.cases)[self.id]['clue_runs']

        code, out = case_cmd(self.cases, 'run', self.id, 'unscramble-read-error', 'search-answer-kept')
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines(), [
            "occurrence 1: search-answer-kept: no: the stand-in kept no answer for the search",
            "occurrence 1: unscramble-read-error: already run (can't tell), not run again"])
        code, out = case_cmd(self.cases, 'run', self.id, 'search-answer-kept')  # a later attempt: nothing new to run
        self.assertEqual(out.splitlines(), ['occurrence 1: search-answer-kept: already run (no), not run again'])

        log = logs(self.cases)[self.id]
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(log['clue_runs'][:len(before)], before)
        self.assertEqual([r['clue'] for r in log['clue_runs'][len(before):]], ['search-answer-kept'])
        self.assertEqual([(a['by'], a['ran'], a['skipped']) for a in log['attempts'][1:]], [
            ('agent', ['search-answer-kept'], ['unscramble-read-error']), ('agent', [], ['search-answer-kept'])])

    def test_the_failure_seen_again_in_a_later_check_runs_the_library_on_its_own_evidence_only(self):
        after(self, (INDEXER_DOWN,), cases=self.cases)
        log = logs(self.cases)[self.id]
        self.assertEqual(sorted(r['clue'] for r in log['clue_runs'] if r['occurrence'] == 2), sorted(clues.CLUES))
        self.assertEqual(len(self.asked), 1)  # the new Clue ran once, on the new occurrence; the first one was opened before it

    def test_a_clue_the_library_does_not_hold_is_refused(self):
        code, out = case_cmd(self.cases, 'run', self.id, 'no-such-clue')
        self.assertEqual((code, out.strip()), (1, 'refused: no Clue named no-such-clue in the library'))


if __name__ == '__main__':
    unittest.main()
