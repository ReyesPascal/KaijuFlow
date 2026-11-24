"""Tests for Case logs and the diagnosing agent (#287, spec #279), through Diagnosis: what a check leaves when a failure
has no proved cause (a Case log, the agent started, one line to the owner), and the commands the agent works the log
with (`diagnosis.py case ...`), each claim checked against the evidence it quotes. The evidence folders are the real
plays in fixtures/2026-11-24-diagnosis/ (README there).
    python3 -I -m unittest discover -s tools/brain -p 'test_caselog.py'
"""
import contextlib
import io
import json
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

    def test_what_code_observes_holds_the_same_claim_check_as_the_agent(self):
        root, run_dir, cases, summary = after(self, (INDEXER_DOWN, TWO_REFUSALS))
        for cid, log in logs(cases).items():
            self.assertTrue(log['observations'][0]['quotes'])  # the path, quoting its first wrong step
            for obs in log['observations']:
                if not obs['quotes']:
                    continue  # a lead with no confirming test: a fact about the Casebook, not the evidence
                with self.subTest(case=cid, says=obs['says']):
                    caselog.check_quotes(log, os.path.join(cases, cid), obs['quotes'], 'an observation')

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


KF_LOG = 'logs/kaijuflow-test.log'
STATUS_503 = '2026-11-24T06:00:46.966105433Z    Status: 503'


class CaseWrites(unittest.TestCase):
    """A Case log opened for Inception's empty list (no Casebook entry matches it), and the agent's `case add`."""
    def setUp(self):
        self.root, self.run_dir, self.cases, _ = after(self, (INDEXER_DOWN,))
        [self.id] = logs(self.cases)

    def add(self, write):
        path = os.path.join(tempdir(self), 'write.json')
        with open(path, 'w') as f:
            json.dump(write, f)
        return case_cmd(self.cases, 'add', self.id, path)


class ClaimsCheckedTest(CaseWrites):

    def test_a_claim_whose_quote_the_evidence_holds_is_written(self):
        n = len(logs(self.cases)[self.id]['observations']) + 1
        code, out = self.add({'write': 'observation', 'says': 'the stand-in answered the search with a 503',
                              'quotes': [{'occurrence': 1, 'file': KF_LOG, 'text': STATUS_503},
                                         {'occurrence': 1, 'clue': 'altmount-refused-import',
                                          'text': 'the failure names no Source'}]})
        self.assertEqual((code, out.strip()), (0, f'{self.id}: observation {n} written'))
        obs = logs(self.cases)[self.id]['observations'][-1]
        self.assertEqual((obs['by'], obs['says']), ('agent', 'the stand-in answered the search with a 503'))

    def test_a_quoted_claim_the_evidence_does_not_hold_is_refused_and_nothing_is_written(self):
        before = logs(self.cases)[self.id]
        invented = '2026-11-24T06:00:46.966105433Z    Status: 429'
        code, out = self.add({'write': 'observation', 'says': 'the indexer was at its limit (429)',
                              'quotes': [{'occurrence': 1, 'file': KF_LOG, 'text': STATUS_503},
                                         {'occurrence': 1, 'file': KF_LOG, 'text': invented}]})
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), f'refused: quote 2 is not in occurrence 1\'s {KF_LOG}: "{invented}"')
        self.assertEqual(logs(self.cases)[self.id], before)

    def test_every_claim_needs_a_quote_and_a_quote_is_read_only_from_the_evidence(self):
        for write, why in [
            ({'write': 'observation', 'says': 'the indexer is down', 'quotes': []},
             'an observation quotes the evidence it rests on: no quote given'),
            ({'write': 'observation', 'says': 'x', 'quotes': [{'occurrence': 1, 'file': KF_LOG, 'text': '503'}]},
             'quote 1 is too short to check (at least 10 characters that are not spaces)'),
            ({'write': 'observation', 'says': 'x', 'quotes': [{'occurrence': 1, 'file': '../../../meta.json',
                                                               'text': 'quick check here'}]},
             'quote 1 names ../../../meta.json, not a file in the evidence folder'),
            ({'write': 'observation', 'says': 'x', 'quotes': [{'occurrence': 3, 'file': KF_LOG, 'text': STATUS_503}]},
             'quote 1 names occurrence 3; this Case log has 1'),
            ({'write': 'observation', 'says': 'x', 'quotes': [{'occurrence': 1, 'clue': 'unscramble-read-error',
                                                               'text': 'read-error for HHWEB'}]},
             'quote 1 is not in what Clue unscramble-read-error said on occurrence 1: "read-error for HHWEB"'),
            ({'write': 'hypothesis', 'says': 'the stand-in lost its answer', 'refuted_if': '',
              'quotes': [{'occurrence': 1, 'file': KF_LOG, 'text': STATUS_503}]},
             'a hypothesis says what result would refute it (refuted_if)'),
            ({'write': 'guess', 'says': 'x'}, 'no write named guess (observation, hypothesis, result, research, ticket, ask, pause, conclude)'),
        ]:
            with self.subTest(why=why):
                code, out = self.add(write)
                self.assertEqual((code, out.strip()), (1, 'refused: ' + why))

    def test_a_hypothesis_is_kept_with_what_would_refute_it_and_its_result_is_checked_too(self):
        q = [{'occurrence': 1, 'file': KF_LOG, 'text': STATUS_503}]
        self.assertEqual(self.add({'write': 'hypothesis', 'says': 'the stand-in had no answer recorded for the search',
                                   'refuted_if': 'the answers kept for the play hold this search', 'quotes': q})[0], 0)
        code, out = self.add({'write': 'result', 'hypothesis': 1, 'now': 'holds', 'says': 'the store kept no answer',
                              'quotes': [{'occurrence': 1, 'file': KF_LOG, 'text': 'Data: not recorded'}]})
        self.assertEqual((code, out.strip()), (0, f'{self.id}: hypothesis 1 now holds'))
        [h] = logs(self.cases)[self.id]['hypotheses']
        self.assertEqual((h['status'], h['refuted_if'], h['result']['says']),
                         ('holds', 'the answers kept for the play hold this search', 'the store kept no answer'))
        self.assertEqual(self.add({'write': 'result', 'hypothesis': 2, 'now': 'refuted', 'says': 'x', 'quotes': q}),
                         (1, 'refused: this Case log has no hypothesis 2\n'))


class NeverGivesUpTest(CaseWrites):
    Q = [{'occurrence': 1, 'file': KF_LOG, 'text': STATUS_503}]

    def hypotheses(self, n):
        for i in range(n):
            self.assertEqual(self.add({'write': 'hypothesis', 'says': f'cause {i + 1}', 'refuted_if': 'a test says no',
                                       'quotes': self.Q})[0], 0)

    def test_research_and_a_ticket_for_a_new_fact_are_kept_and_counted(self):
        self.assertEqual(self.add({'write': 'research', 'question': 'When does the stand-in answer 503?',
                                   'source': 'tools/brain/indexer_standin.py', 'found': 'a miss in replay mode is a 503',
                                   'used': True}), (0, f'{self.id}: research 1 written\n'))
        self.assertEqual(self.add({'write': 'ticket', 'ref': '#999', 'fact': 'the stand-in names the missed request'}),
                         (0, f'{self.id}: ticket 1 written\n'))
        log = logs(self.cases)[self.id]
        self.assertEqual((log['research'][0]['used'], log['tickets'][0]['ref']), (True, '#999'))
        self.assertEqual(self.add({'write': 'ticket', 'ref': 'soon', 'fact': 'x'}),
                         (1, 'refused: a ticket is named by its number (#123) or its link\n'))

    def test_the_owner_is_asked_only_for_what_only_they_can_give(self):
        self.assertEqual(self.add({'write': 'ask', 'kind': 'live go', 'what': 'play Inception again live'})[0], 0)
        self.assertEqual(self.add({'write': 'ask', 'kind': 'login', 'what': 'the second provider'})[0], 0)
        self.assertEqual(self.add({'write': 'ask', 'kind': 'opinion', 'what': 'which cause do you think?'}),
                         (1, 'refused: a Case log comes to the owner only for what only they can give: a live go or a '
                             'login (kind)\n'))

    def test_a_pause_keeps_several_hypotheses_and_says_what_comes_next(self):
        nxt = {'do': 'research', 'what': "read the stand-in's replay code"}
        self.hypotheses(1)
        self.assertEqual(self.add({'write': 'pause', 'next': nxt}),
                         (1, 'refused: keep several hypotheses at once: this Case log has 1\n'))
        self.hypotheses(1)
        self.assertEqual(self.add({'write': 'pause'}),
                         (1, 'refused: a stuck case keeps going: say what comes next (next.do: research, clue, ticket, '
                             'owner, capture)\n'))
        self.assertEqual(self.add({'write': 'pause', 'next': {'do': 'owner', 'what': 'wait'}}),
                         (1, 'refused: the next step is the owner only after an ask (a live go or a login)\n'))
        self.assertEqual(self.add({'write': 'pause', 'next': nxt}), (0, f'{self.id}: attempt 2 paused; next: research\n'))
        self.assertEqual(logs(self.cases)[self.id]['attempts'][-1]['next'], nxt)


if __name__ == '__main__':
    unittest.main()
