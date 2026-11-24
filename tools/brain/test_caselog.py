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
import shutil
import threading
import unittest
from unittest import mock

import casebook
import caselog
import clues
import diagnosis
import drill
from test_diagnosis import DEAD_PACK, INDEXER_DOWN, READ_ERROR, SIC, TWO_REFUSALS, casebook_copy, stored_check
from test_evidence import run_failed_check
from test_quickcheck import read
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


class NewMaskingRulesTest(unittest.TestCase):
    def test_a_new_masking_version_fingerprints_the_case_logs_again_so_the_same_failure_joins_its_log(self):
        root, run_dir, cases, _ = after(self, (TWO_REFUSALS,))
        [(cid, log)] = logs(cases).items()
        rules = rules_v2()
        v = rules['version'] - 1

        _, later, _, summary = after(self, (TWO_REFUSALS,), cases=cases, rules=rules)

        [(again, log)] = logs(cases).items()  # one log still, under its first id
        self.assertEqual(again, cid)
        self.assertEqual([o['n'] for o in log['occurrences']], [1, 2])
        self.assertIn('"code":"<code>"', log['fingerprint'])
        self.assertEqual(log['rules'], v + 1)
        self.assertEqual([e['rules'] for e in log['earlier']], [v])
        self.assertEqual(summary['cases'], [{'id': cid, 'status': 'open', 'occurrences': 2, 'new': False}])


def rules_v2():
    """The masking rules of a next version: error codes masked too."""
    rules = diagnosis.load_rules()
    return dict(rules, version=rules['version'] + 1, masks=[{'name': 'error code', 'pattern': '[A-Z]+(_[A-Z]+)+', 'with': '<code>'}]
                + rules['masks'])


class NewMaskingRulesAndCaseLogsTest(unittest.TestCase):
    def setUp(self):
        _, self.run_dir, self.cases, _ = after(self, (TWO_REFUSALS,))
        [self.id] = logs(self.cases)

    def test_case_repeat_under_new_rules_fingerprints_the_log_again_first(self):
        _, again = stored_check(self, name='2026-11-25T090000Z-drill-down', plays=(TWO_REFUSALS,))
        with mock.patch.object(diagnosis, 'load_rules', return_value=rules_v2()):
            code, out = case_cmd(self.cases, 'repeat', self.id, os.path.join(again, 'evidence', '01-218-witcher-two-refusals'))
        self.assertEqual((code, out.strip()), (0, f'{self.id}: occurrence 2 added (repeat)'))
        log = logs(self.cases)[self.id]
        v = diagnosis.load_rules()['version']
        self.assertEqual((log['rules'], [e['rules'] for e in log['earlier']]), (v + 1, [v]))

    def test_a_log_whose_first_evidence_folder_is_gone_or_unreadable_is_fingerprinted_from_the_next(self):
        _, later, _, _ = after(self, (TWO_REFUSALS,), cases=self.cases)  # occurrence 2, another check's folder
        self.assertEqual(len(logs(self.cases)[self.id]['occurrences']), 2)
        first = os.path.join(self.run_dir, 'evidence', '01-218-witcher-two-refusals')
        with open(os.path.join(first, 'evidence.json')) as f:
            meta = json.load(f)
        put_json(os.path.join(first, 'evidence.json'), dict(meta, format=99))  # evidence.FormatUnknown

        self.assertEqual(caselog.refingerprint(self.cases, rules_v2()), [self.id])
        self.assertIn('"code":"<code>"', logs(self.cases)[self.id]['fingerprint'])

        shutil.rmtree(first)  # archived: gone
        rules = dict(rules_v2(), version=rules_v2()['version'] + 1)
        self.assertEqual(caselog.refingerprint(self.cases, rules), [self.id])
        self.assertEqual(logs(self.cases)[self.id]['rules'], rules['version'])


class NoFailureTest(unittest.TestCase):
    def test_a_check_with_no_failure_says_the_open_case_logs_too(self):
        root, run_dir, cases, _ = after(self, (INDEXER_DOWN,))  # one Case log left open
        quiet = os.path.join(root, '2026-11-25T070000Z-quick-check')
        os.makedirs(quiet)
        summary = diagnosis.after_check(quiet, root, cases=cases)
        lines = diagnosis.report_section(summary)
        self.assertEqual(lines[:3], ['## Diagnosis', '', 'None: no play failed or fell back; open Case logs: 1.'])
        self.assertTrue(any(line.startswith('Clues: ') for line in lines))
        self.assertFalse(os.path.exists(os.path.join(quiet, diagnosis.STORED)))


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


class OneWriterAtATimeTest(CaseWrites):
    def test_a_write_waits_for_another_writer_of_the_same_log_and_neither_is_lost(self):
        d = os.path.join(self.cases, self.id)
        said = []
        write = {'write': 'research', 'question': 'Was the indexer down?', 'source': 'https://example.org/status',
                 'found': 'it was down that morning'}
        with caselog.locked(d):  # another writer (a second agent, or a check joining the log) holds it
            log = caselog.load(d)
            other = threading.Thread(target=lambda: said.append(self.add(write)))
            other.start()
            other.join(0.3)
            self.assertTrue(other.is_alive())  # it waits
            log['tickets'].append({'n': 1, 'ref': '#1', 'fact': 'x', 'by': 'agent', 't': 'now'})
            caselog.save(d, log)
        other.join(5)
        self.assertEqual(said, [(0, f'{self.id}: research 1 written\n')])
        log = caselog.load(d)
        self.assertEqual((len(log['tickets']), len(log['research'])), (1, 1))


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


AM_LOG = 'logs/altmount-kf-test.log'
SIC_REFUSED = 'level=WARN msg="File does not match allowed extensions" filename=' + SIC
SIC_CHECKED = f'"title": "{SIC}", "status": "verified"'
RECIPE = [{'clue': 'check-passed-source', 'answer': 'yes'}, {'clue': 'altmount-extension-refused', 'answer': 'yes'}]
_SIC = [{'occurrence': 1, 'file': AM_LOG, 'text': SIC_REFUSED}]
HYPOTHESES = ({'says': 'AltMount refuses the file for its name, which ends in no video extension, although the health '
                       'check passed it', 'refuted_if': 'AltMount took the file', 'quotes': _SIC},
              {'says': "the Source's articles are gone", 'refuted_if': 'the health check passed it', 'quotes': _SIC})
REFUTE_2 = {'write': 'result', 'hypothesis': 2, 'now': 'refuted', 'says': 'its check verified it',
            'quotes': [{'occurrence': 1, 'file': 'steps.jsonl', 'text': SIC_CHECKED}]}


def drilled(case, name):
    """The evidence folder a Drill-down of #218's Witcher left (a copy of the capture, its kind a Drill-down's)."""
    _, run_dir = stored_check(case, name=name, plays=(TWO_REFUSALS,))
    folder = os.path.join(run_dir, 'evidence', '01-218-witcher-two-refusals')
    with open(os.path.join(folder, 'evidence.json')) as f:
        meta = json.load(f)
    put_json(os.path.join(folder, 'evidence.json'), dict(meta, kind=drill.KIND))
    return folder


class SolvedTest(CaseWrites):
    """SiC-AsRequested in #218: its check passed it, AltMount refused its file for the extension; the Casebook's
    look-alike (no-extension-file-passed) has no confirming test, so the failure opens a Case log."""
    def setUp(self):
        self.root, self.run_dir, self.cases, _ = after(self, (TWO_REFUSALS,))
        [self.id] = logs(self.cases)
        for h in HYPOTHESES:
            self.assertEqual(self.add(dict(h, write='hypothesis'))[0], 0)
        self.assertEqual(self.add(REFUTE_2)[0], 0)

    def conclude(self, **kw):
        write = dict({'write': 'conclude', 'hypothesis': 1, 'title': 'AltMount refused a file the check passed, for '
                      'its extension.', 'saw': 'The play fell back to the next Source after a wait.',
                      'cause': "The release's video file has no video extension in its name, so AltMount refuses it.",
                      'whose': 'AltMount', 'step': 'import_wait', 'recipe': RECIPE,
                      'quotes': [{'occurrence': 1, 'file': AM_LOG, 'text': SIC_REFUSED}]}, **kw)
        return self.add(write)

    def hold(self):
        self.assertEqual(self.add({'write': 'result', 'hypothesis': 1, 'now': 'holds', 'says': 'AltMount said so',
                                   'quotes': [{'occurrence': 1, 'file': AM_LOG, 'text': SIC_REFUSED}]})[0], 0)

    def test_a_conclusion_needs_its_hypothesis_held_the_others_settled_and_a_recipe_that_passes(self):
        self.assertEqual(self.conclude(), (1, 'refused: hypothesis 1 does not hold yet (open)\n'))
        self.hold()
        self.assertEqual(self.conclude(recipe=[{'clue': 'unscramble-read-error', 'answer': 'yes'}]),
                         (1, 'refused: the recipe says no on occurrence 1: unscramble-read-error answered no '
                             '(wanted yes)\n'))
        self.assertEqual(self.conclude(recipe=[{'clue': 'not-built', 'answer': 'yes'}]),
                         (1, 'refused: no Clue named not-built in the library\n'))
        self.assertEqual(self.conclude(whose='nobody'),
                         (1, 'refused: whose must be one of: KaijuFlow, AltMount, indexer, Usenet, test-only\n'))

    def test_a_case_seen_only_in_checks_is_probable_and_one_repeated_at_will_is_proved(self):
        self.hold()
        self.assertEqual(self.conclude(), (0, f'{self.id}: concluded: probable (the recipe passed on occurrence 1; '
                                              'not repeated at will)\n'))
        self.assertEqual(logs(self.cases)[self.id]['status'], 'probable')
        _, again = stored_check(self, plays=(TWO_REFUSALS,))  # the evidence folder a Drill-down of the title left
        code, out = case_cmd(self.cases, 'repeat', self.id, os.path.join(again, 'evidence', '01-218-witcher-two-refusals'))
        self.assertEqual((code, out.strip()), (0, f'{self.id}: occurrence 2 added (repeat); now proved'))
        log = logs(self.cases)[self.id]
        self.assertEqual((log['status'], log['conclusion']['passed_on']), ('proved', [1, 2]))
        code, out = case_cmd(self.cases, 'repeat', self.id, os.path.join(self.run_dir, 'evidence', '01-218-witcher-two-refusals'))
        self.assertEqual((code, out.strip()), (1, 'refused: that evidence folder is occurrence 1 already (check)'))
        code, out = case_cmd(self.cases, 'repeat', self.id, INDEXER_DOWN)
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("refused: no failure in that evidence folder has this Case log's fingerprint"), out)

    def test_a_drill_down_that_repeats_the_failure_joins_as_a_repeat_and_proves_the_case(self):
        self.hold()
        self.conclude()
        folder = drilled(self, '2026-11-25T090000Z-drill-down')
        run_dir = os.path.dirname(os.path.dirname(folder))

        summary = diagnosis.after_check(run_dir, os.path.dirname(run_dir), cases=self.cases)

        log = logs(self.cases)[self.id]
        self.assertEqual([o['how'] for o in log['occurrences']], ['check', 'repeat'])
        self.assertEqual((log['status'], log['conclusion']['passed_on']), ('proved', [1, 2]))
        self.assertEqual(summary['cases'], [{'id': self.id, 'status': 'proved', 'occurrences': 2, 'new': False}])
        code, out = case_cmd(self.cases, 'repeat', self.id, folder)
        self.assertEqual((code, out.strip()), (1, 'refused: that evidence folder is occurrence 2 already (repeat)'))

    def test_a_case_log_a_drill_down_opened_is_proved_by_a_later_drill_down(self):
        cases = os.path.join(tempdir(self), 'cases')
        run_dir = os.path.dirname(os.path.dirname(drilled(self, '2026-11-25T090000Z-drill-down')))
        diagnosis.after_check(run_dir, os.path.dirname(run_dir), cases=cases)
        [cid] = logs(cases)
        self.assertEqual([o['how'] for o in logs(cases)[cid]['occurrences']], ['check'])  # the first sighting
        self.id, self.cases = cid, cases
        for h in HYPOTHESES:
            self.assertEqual(self.add(dict(h, write='hypothesis'))[0], 0)
        self.assertEqual(self.add(REFUTE_2)[0], 0)
        self.hold()
        self.assertIn('probable', self.conclude()[1])
        again = drilled(self, '2026-11-26T090000Z-drill-down')
        self.assertEqual(case_cmd(cases, 'repeat', cid, again), (0, f'{cid}: occurrence 2 added (repeat); now proved\n'))

    def test_a_solved_case_written_up_as_an_entry_passes_the_casebook_format_and_index_test(self):
        self.hold()
        self.conclude()
        book = casebook_copy(self)
        code, out = case_cmd(self.cases, 'entry', self.id, 'altmount-extension-refused-file', '--casebook', book)
        self.assertEqual((code, out.strip()), (0, f'{self.id}: Casebook entry altmount-extension-refused-file written, index '
                                                  'written again: commit both through review'))

        self.assertEqual(casebook.problems(book), [])
        entries, _ = casebook.load(book)
        e = entries['altmount-extension-refused-file']
        self.assertEqual((e['kind'], e['step'], e['whose'], e['status'], e['confirm']),
                         ('check miss', 'import_wait', 'AltMount', 'open', RECIPE))
        self.assertEqual(e['seen'], [{'check': '2026-11-23T183239Z-baseline-218', 'title': 'The Witcher S01E01',
                                      'play': 'evidence/01-218-witcher-two-refusals', 'date': '2026-11-23',
                                      'rules': diagnosis.load_rules()['version']}])
        _, sections = casebook.read_entry(os.path.join(book, 'altmount-extension-refused-file.md'))
        self.assertIn("the Source's articles are gone", sections['Ruled out'])
        self.assertIn('Probable, not proved', sections['How it was proved'])
        self.assertIn(SIC_REFUSED, sections['Signs'])
        self.assertEqual(logs(self.cases)[self.id]['entry'], 'altmount-extension-refused-file')

        [_, sic] = diagnosis.diagnose(TWO_REFUSALS, entries=diagnosis.load_index(book))['failures']  # the next one
        self.assertEqual((sic['release'], sic['verdict'], sic['cause']), (SIC, 'found', 'altmount-extension-refused-file'))
        self.assertEqual(case_cmd(self.cases, 'entry', self.id, 'unscramble-read-error', '--casebook', book),
                         (1, 'refused: the Casebook has an entry unscramble-read-error already\n'))

    def test_an_unconcluded_case_is_not_written_up(self):
        self.assertEqual(case_cmd(self.cases, 'entry', self.id, 'x-y', '--casebook', casebook_copy(self)),
                         (1, f'refused: {self.id} is not concluded yet (open)\n'))


def put_json(path, data, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(json.dumps(data, indent=1, **kw))


class WhatChangedTest(unittest.TestCase):
    """Story 42: what changed since the last check that passed: the image's commit, the settings, AltMount's version."""
    AM_OLD = {'image': 'ghcr.io/kipsilabs/altmount:v0.3.9', 'id': 'sha256:0ld'}
    AM_NEW = {'image': 'ghcr.io/kipsilabs/altmount:v0.4.0', 'id': 'sha256:feed'}

    def failing_check(self, good=True, altmount=True):
        root, run_dir = stored_check(self, name='2026-11-24T070000Z-quick-check', plays=(INDEXER_DOWN,))
        ev = os.path.join(run_dir, 'evidence', '01-265-inception-indexer-down')
        with open(os.path.join(ev, 'evidence.json')) as f:
            meta = json.load(f)
        if altmount:
            meta['altmount'] = self.AM_NEW
        put_json(os.path.join(ev, 'evidence.json'), meta)
        put_json(os.path.join(ev, 'settings.json'), {'kaijuflow': {'healthCheck.sampleCount': 3, 'devDiagnostics': True}},
                 sort_keys=True)
        put_json(os.path.join(run_dir, 'meta.json'), {'kind': 'quick check', 'started': '2026-11-24T07:00:00Z',
                                                      'verdict': 'fail'}, sort_keys=True)
        if good:
            for name, verdict, commit in (('2026-11-22T080000Z-quick-check', 'pass', 'a1b2c3'),
                                          ('2026-11-23T080000Z-quick-check', 'fail', 'ffffff'),
                                          ('2026-11-25T080000Z-quick-check', 'pass', 'later')):
                put_json(os.path.join(root, name, 'meta.json'), {'kind': 'quick check', 'verdict': verdict, 'commit': commit,
                                                                 'started': name[:4] + '-' + name[5:7] + '-' + name[8:10],
                                                                 'altmount': self.AM_OLD}, sort_keys=True)
                put_json(os.path.join(root, name, 'settings.json'),
                         {'kaijuflow': {'healthCheck.sampleCount': 5, 'devDiagnostics': True}}, sort_keys=True)
        cases = os.path.join(tempdir(self), 'cases')
        diagnosis.after_check(run_dir, root, cases=cases)
        [(cid, log)] = logs(cases).items()
        return cid, log, cases

    def changed(self, log):
        return next(o for o in log['observations'] if o['says'].startswith('since the last check that passed')
                    or o['says'].startswith('no check passed'))

    def test_the_commit_the_settings_and_altmount_are_compared_with_the_last_check_that_passed(self):
        cid, log, cases = self.failing_check()
        obs = self.changed(log)
        self.assertEqual(obs['says'], 'since the last check that passed (2026-11-22T080000Z-quick-check): the commit '
                                      'changed (a1b2c3 to fd19e62c5a1a0de5b9758db9d8584518c321d995); AltMount changed '
                                      '(ghcr.io/kipsilabs/altmount:v0.3.9 to ghcr.io/kipsilabs/altmount:v0.4.0); 1 setting '
                                      'changed: kaijuflow.healthCheck.sampleCount 5 to 3')
        caselog.check_quotes(log, os.path.join(cases, cid), obs['quotes'], 'an observation')
        self.assertEqual({q.get('check') for q in obs['quotes']}, {None, '2026-11-22T080000Z-quick-check'})

    def test_what_was_not_recorded_is_said_so(self):
        _, log, _ = self.failing_check(altmount=False)
        self.assertIn("AltMount's version is not recorded in this play's evidence", self.changed(log)['says'])
        _, log, _ = self.failing_check(good=False)
        self.assertEqual(self.changed(log)['says'], 'no check passed before this one: nothing to compare with')


class AgentStartsByItselfTest(unittest.TestCase):
    def test_a_check_whose_failure_has_no_proved_cause_starts_the_agent_and_tells_the_owner_in_one_line(self):
        with mock.patch.object(diagnosis, 'load_index', return_value=[]):  # a Casebook that knows nothing yet
            code, out, folder, world = run_failed_check(self)
        [cid] = os.listdir(world.cases)
        self.assertIn(('diagnosing agent', [cid]), world.calls)
        [line] = [c[1] for c in world.calls if c[0] == 'alert']
        self.assertEqual(line, f'Diagnosis: 1 failure in {os.path.basename(folder)} has no proved cause; the diagnosing '
                               f'agent is on Case log {cid} (herdr agent diag-test).')
        report = read(folder, 'report.md')
        self.assertIn('open Case logs: 1.', report)
        self.assertIn(f'- Case log `{cid}`: opened (1 occurrence, open).', report)
        self.assertIn('The diagnosing agent started: herdr agent diag-test.', report)

    def test_a_check_whose_failures_are_all_proved_starts_no_agent(self):
        code, out, folder, world = run_failed_check(self)
        self.assertEqual([c for c in world.calls if c[0] in ('diagnosing agent', 'alert')], [])

    def test_an_agent_that_cannot_start_is_said_in_the_line(self):
        def refuse(cases, ids, run_dir):
            raise OSError('herdr is not running')
        alerts = []
        root, run_dir, cases, summary = after(self, (INDEXER_DOWN,), agent=refuse, alert=alerts.append)
        [cid] = logs(cases)
        self.assertEqual(alerts, [f'Diagnosis: 1 failure in 2026-11-24T070000Z-quick-check has no proved cause; the '
                                  f'diagnosing agent could not start (OSError: herdr is not running): Case log {cid} '
                                  'waits for it.'])
        self.assertEqual(summary['agent'], {'started': None, 'error': 'OSError: herdr is not running', 'cases': [cid]})


# What herdr answered on Brain, 2026-11-24 (tab list, pane list cut to its fields), and pane split's answer as kf-next
# reads it.
TABS = ('{"id":"cli:tab:list","result":{"tabs":[{"agent_status":"done","focused":false,"label":"1","number":1,'
        '"pane_count":1,"tab_id":"w5:t1","workspace_id":"w5"},{"agent_status":"working","focused":true,"label":"agents",'
        '"number":3,"pane_count":5,"tab_id":"w5:t3","workspace_id":"w5"}],"type":"tab_list"}}')
PANES = ('{"id":"cli:pane:list","result":{"panes":[{"agent":"claude","agent_status":"done","cwd":"/home/brain/code/'
         'KaijuFlow","focused":false,"pane_id":"w5:p0","tab_id":"w5:t1","workspace_id":"w5"},{"agent":"claude",'
         '"agent_status":"idle","cwd":"/home/brain/code/KaijuFlow","focused":true,"pane_id":"w5:pV","tab_id":"w5:t3",'
         '"workspace_id":"w5"}]}}')
SPLIT = '{"id":"cli:pane:split","result":{"pane":{"pane_id":"w5:p12","tab_id":"w5:t3"}}}'


# `agent wait` on Brain, 2026-11-24: an agent in the state asked for (its agent_info, on stdout), and one that was not
# in it before the timeout (exit 1, the error on stderr). `agent prompt --wait` waits the same way, by default for the
# turn's end (idle, done or blocked).
TIMEOUT = '{"error":{"code":"timeout","message":"timed out waiting for agent status"},"id":"cli:agent:wait"}'
STALLED = ('{"error":{"code":"agent_prompt_stalled","message":"agent did not start working after the prompt"},'
           '"id":"cli:agent:prompt"}')


def agent_info(name, status):
    return ('{"id":"cli:agent:wait","result":{"agent":{"agent":"claude","agent_status":"%s","interactive_ready":true,'
            '"name":"%s","pane_id":"w5:p12","tab_id":"w5:t3","workspace_id":"w5"},"type":"agent_info"}}' % (status, name))


class FakeHerdr:
    """herdr as the launcher meets it: its list and split answers, and an agent with a state. A started agent is idle; a
    prompt makes it working (or, `stall`, the prompt sits in its input box until Enter). `--wait` without `--until` waits
    for the turn's end, which a diagnosing agent's turn never reaches within the timeout; `wait --until` answers at once
    when the agent is in one of those states, else times out."""
    def __init__(self, tabs=TABS, stall=False, never_works=False):
        self.calls, self.tabs, self.stall, self.never_works, self.status = [], tabs, stall, never_works, None

    def __call__(self, cmd, capture_output=True, text=True, timeout=None, check=False):
        self.calls.append(cmd)
        if cmd[1:3] == ['agent', 'start']:
            self.status = 'idle'
        elif cmd[1:3] == ['agent', 'prompt']:
            if self.status is None:
                return mock.Mock(returncode=1, stdout='', stderr='{"error":{"code":"agent_not_found"}}')
            if not self.stall and not self.never_works:
                self.status = 'working'
            if '--wait' in cmd:
                until = [cmd[i + 1] for i, a in enumerate(cmd) if a == '--until'] or ['idle', 'done', 'blocked']
                if self.stall:
                    return mock.Mock(returncode=1, stdout='', stderr=STALLED)
                if self.status not in until:  # the turn goes on past the timeout
                    return mock.Mock(returncode=1, stdout='', stderr=TIMEOUT.replace('agent:wait', 'agent:prompt'))
            return mock.Mock(returncode=0, stdout='{"id":"cli:agent:prompt","result":{}}', stderr='')
        elif cmd[1:3] == ['agent', 'send-keys']:
            if self.stall and not self.never_works:
                self.status, self.stall = 'working', False
        elif cmd[1:3] == ['agent', 'wait']:
            until = [cmd[i + 1] for i, a in enumerate(cmd) if a == '--until'] or ['idle', 'done', 'blocked']
            if self.status not in until:
                return mock.Mock(returncode=1, stdout='', stderr=TIMEOUT)
            return mock.Mock(returncode=0, stdout=agent_info(cmd[3], self.status), stderr='')
        out = {('tab', 'list'): self.tabs, ('pane', 'list'): PANES, ('pane', 'split'): SPLIT,
               ('tab', 'create'): '{"id":"cli:tab:create","result":{}}'}.get(tuple(cmd[1:3]), '{"result":{}}')
        if cmd[1:3] == ['tab', 'create']:
            self.tabs = TABS
        return mock.Mock(returncode=0, stdout=out, stderr='')


class LauncherTest(unittest.TestCase):
    def test_inside_herdr_the_agent_starts_in_a_new_pane_of_the_agents_tab(self):
        herdr = FakeHerdr()
        said = caselog.start_agent('/n/cases', ['fail-indexer-page-e5f2211b'], '/n/runs/check', run=herdr,
                                   env={'HERDR_ENV': '1'}, name='diag-1124')
        self.assertEqual(said, 'herdr agent diag-1124 in pane w5:p12')
        self.assertEqual(herdr.calls[2][:4], ['herdr', 'pane', 'split', 'w5:pV'])
        self.assertEqual(herdr.calls[3][:7], ['herdr', 'agent', 'start', 'diag-1124', '--kind', 'claude', '--pane'])
        prompt = herdr.calls[4]
        self.assertEqual(prompt[:4], ['herdr', 'agent', 'prompt', 'diag-1124'])
        self.assertIn('fail-indexer-page-e5f2211b', prompt[4])
        self.assertIn('tools/brain/docs/diagnosing-agent.md', prompt[4])
        self.assertIn('--cases /n/cases', prompt[4])
        self.assertEqual(herdr.status, 'working')

    def test_a_started_agent_that_takes_the_prompt_is_started_though_its_turn_goes_on(self):
        herdr = FakeHerdr()
        said = caselog.start_agent('/n/cases', ['x'], '/n/runs/check', run=herdr, env={'HERDR_ENV': '1'}, name='diag-1124')
        self.assertEqual(said, 'herdr agent diag-1124 in pane w5:p12')
        self.assertEqual([c for c in herdr.calls if c[1:3] == ['agent', 'send-keys']], [])

    def test_a_prompt_that_sat_in_the_input_box_is_sent_with_enter(self):
        herdr = FakeHerdr(stall=True)
        said = caselog.start_agent('/n/cases', ['x'], '/n/runs/check', run=herdr, env={'HERDR_ENV': '1'}, name='diag-1124')
        self.assertEqual(said, 'herdr agent diag-1124 in pane w5:p12')
        self.assertIn(['herdr', 'agent', 'send-keys', 'diag-1124', 'enter'], herdr.calls)
        self.assertEqual(herdr.status, 'working')

    def test_an_agent_that_never_takes_the_prompt_could_not_start(self):
        herdr = FakeHerdr(stall=True, never_works=True)
        with self.assertRaisesRegex(OSError, 'did not take the prompt'):
            caselog.start_agent('/n/cases', ['x'], '/n/runs/check', run=herdr, env={'HERDR_ENV': '1'}, name='diag-1124')

    def test_the_routine_the_prompt_names_is_there_and_names_every_write(self):
        with open(os.path.join(caselog.REPO, caselog.ROUTINE)) as f:
            routine = f.read()
        for write in caselog.WRITES:
            self.assertIn(f'| `{write}` |', routine)

    def test_with_no_agents_tab_it_makes_one(self):
        herdr = FakeHerdr(tabs=TABS.replace('"agents"', '"other"'))
        caselog.start_agent('/n/cases', ['x'], '/n/runs/check', run=herdr, env={'HERDR_ENV': '1'}, name='diag-1124')
        self.assertEqual(herdr.calls[1][:5], ['herdr', 'tab', 'create', '--label', 'agents'])

    def test_outside_herdr_it_runs_claude_detached_with_its_output_beside_the_case_logs(self):
        cases = tempdir(self)
        started = []
        said = caselog.start_agent(cases, ['x'], '/n/runs/check', env={}, name='diag-1124',
                                   popen=lambda cmd, **kw: started.append((cmd, kw)) or mock.Mock(pid=42))
        [(cmd, kw)] = started
        self.assertEqual(cmd[:2], ['claude', '-p'])
        self.assertTrue(kw['start_new_session'])
        self.assertEqual(said, f"claude -p (pid 42), its output in {os.path.join(cases, 'diag-1124.log')}")


if __name__ == '__main__':
    unittest.main()
