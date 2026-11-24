"""Tests for the scoreboard (#288, spec #279, story 58), through Diagnosis after a check and the check report's Diagnosis
section: Clues reused against new, fixes proved and comebacks, failures per check over time by cause, and research
count and usage. The evidence folders are the real plays in fixtures/2026-11-24-diagnosis/ (README there).
    python3 -I -m unittest discover -s tools/brain -p 'test_scoreboard.py'
"""
import json
import os
import shutil
import unittest

import caselog
import clues
import diagnosis
import evidence
from test_diagnosis import DEAD_PACK, INDEXER_DOWN, READ_ERROR, casebook_copy
from test_fixing import set_field
from test_quickcheck import read
from test_settings import tempdir

FIRST, SECOND, THIRD = '2026-11-24T070000Z-quick-check', '2026-11-25T070000Z-quick-check', '2026-11-26T070000Z-quick-check'


class Checks:
    """One runs root, checks added to it in order, each diagnosed after it as a check does."""

    def __init__(self, case, book=None):
        self.case, self.root = case, tempdir(case)
        self.cases, self.book = os.path.join(tempdir(case), 'cases'), book or casebook_copy(case)

    def add(self, name, plays, library=None):
        run_dir = os.path.join(self.root, name)
        for n, folder in enumerate(plays, 1):
            shutil.copytree(folder, os.path.join(run_dir, evidence.DIR, f'{n:02d}-{os.path.basename(folder)}'))
        return diagnosis.after_check(run_dir, self.root, library=library, cases=self.cases, book=self.book)


def ran_by_recipes(summary_dir):
    names = set()
    for p in diagnosis.stored_plays(summary_dir):
        for f in p['diagnosis']['failures']:
            for lead in f['leads']:
                names |= {c['clue'] for c in lead.get('clues') or []}
    return names


class CluesTest(unittest.TestCase):
    def test_the_clues_a_check_ran_are_told_reused_or_new_since_the_last_check(self):
        checks = Checks(self)
        older = {k: v for k, v in clues.CLUES.items() if k != 'articles-missing'}  # before the live Clue joined (#284)
        checks.add(FIRST, (READ_ERROR,), library=older)
        board = checks.add(SECOND, (DEAD_PACK,))['scoreboard']['clues']

        ran = ran_by_recipes(os.path.join(checks.root, SECOND))
        self.assertIn('articles-missing', ran)
        self.assertEqual(board['since'], FIRST)
        self.assertEqual(board['ran'], len(ran))
        self.assertEqual(board['new'], ['articles-missing'])
        self.assertEqual(board['reused'], len(ran) - 1)
        self.assertEqual(board['library'], len(clues.CLUES))
        self.assertEqual(board['joined'], ['articles-missing'])

    def test_with_no_earlier_library_none_is_told_new(self):
        board = Checks(self).add(FIRST, (READ_ERROR,))['scoreboard']['clues']
        self.assertEqual((board['since'], board['new'], board['joined']), (None, None, None))
        self.assertEqual(board['ran'], 3)

    def test_the_library_a_check_kept_outlives_a_new_masking_version(self):
        checks = Checks(self)
        checks.add(FIRST, (READ_ERROR,))
        rules = dict(diagnosis.load_rules(), version=2)
        diagnosis.refingerprint(checks.root, rules)
        kept = json.loads(read(checks.root, FIRST, diagnosis.STORED))
        self.assertEqual(kept['rules'], 2)
        self.assertEqual(kept['library'], sorted(clues.CLUES))


class FixesTest(unittest.TestCase):
    def test_fixes_proved_and_comebacks(self):
        book = casebook_copy(self)
        set_field(book, 'unscramble-read-error', 'status', 'proved fixed')
        set_field(book, 'unchecked-dead-season-pack', 'status', 'reopened')
        board = Checks(self, book).add(FIRST, (READ_ERROR,))['scoreboard']['fixes']
        # unscramble-read-error came back in this check: it no longer counts as proved fixed
        self.assertEqual(board, {'proved_fixed': 0, 'comebacks': 2, 'this_check': ['unscramble-read-error'],
                                 'tickets': 0})

    def test_a_proved_fixed_cause_that_did_not_come_back_counts(self):
        book = casebook_copy(self)
        set_field(book, 'unchecked-dead-season-pack', 'status', 'proved fixed')
        board = Checks(self, book).add(FIRST, (READ_ERROR,))['scoreboard']['fixes']
        self.assertEqual((board['proved_fixed'], board['comebacks'], board['this_check']), (1, 0, []))


class ByCauseTest(unittest.TestCase):
    def test_failures_per_check_over_time_by_cause(self):
        checks = Checks(self)
        checks.add(FIRST, (READ_ERROR, INDEXER_DOWN))
        board = checks.add(SECOND, (DEAD_PACK,))['scoreboard']['by_cause']
        self.assertEqual(board, [
            {'check': FIRST, 'failures': 2, 'causes': {'unscramble-read-error': 1, 'unexplained': 1}},
            {'check': SECOND, 'failures': 1, 'causes': {'unchecked-dead-season-pack': 1}}])

    def test_it_keeps_the_last_ten_checks(self):
        checks = Checks(self)
        for day in range(1, 13):
            board = checks.add(f'2026-12-{day:02d}T070000Z-quick-check', (INDEXER_DOWN,))['scoreboard']['by_cause']
        self.assertEqual([b['check'][:10] for b in board], [f'2026-12-{d:02d}' for d in range(3, 13)])


class ResearchTest(unittest.TestCase):
    def test_research_count_and_usage_over_the_case_logs(self):
        checks = Checks(self)
        board = checks.add(FIRST, (INDEXER_DOWN,))['scoreboard']['research']
        self.assertEqual(board, {'count': 0, 'used': 0, 'logs': 0})
        [cid] = os.listdir(checks.cases)
        for used in (True, False):
            caselog.add(checks.cases, cid, {'write': 'research', 'question': 'Does NinjaCentral answer 503 at its limit?',
                                            'source': 'https://example.invalid/api-docs', 'found': 'It answers 429.',
                                            'used': used})
        board = checks.add(SECOND, (DEAD_PACK,))['scoreboard']['research']
        self.assertEqual(board, {'count': 2, 'used': 1, 'logs': 1})


class ReportTest(unittest.TestCase):
    def test_the_report_shows_the_four_extra_numbers(self):
        book = casebook_copy(self)
        set_field(book, 'unscramble-read-error', 'status', 'proved fixed')
        checks = Checks(self, book)
        older = {k: v for k, v in clues.CLUES.items() if k != 'articles-missing'}
        checks.add(FIRST, (INDEXER_DOWN,), library=older)
        summary = checks.add(SECOND, (READ_ERROR, DEAD_PACK))
        n = summary['scoreboard']['clues']['ran']
        lines = diagnosis.report_section(summary)
        text = '\n'.join(lines)
        self.assertIn(f'Clues: the confirming tests ran {n}: {n - 1} reused, 1 new since the check {FIRST} '
                      f'(articles-missing); the library holds {len(clues.CLUES)}, 1 joined since (articles-missing).', text)
        self.assertIn('Fixes: 0 proved fixed, 1 comeback in all; this check: 1 comeback (unscramble-read-error), '
                      '0 fix tickets filed.', text)
        self.assertIn('Research: 0 looked up in 0 Case logs, 0 used.', text)
        self.assertIn('Failures per check by cause (the last 10 checks with a failure):\n\n'
                      f'- {FIRST}: 1 failure: unexplained 1\n'
                      f'- {SECOND}: 2 failures: unchecked-dead-season-pack 1, unscramble-read-error 1', text)
        # the five numbers still come first
        self.assertTrue(lines[2].startswith('2 failures: 0 new, 2 matched, 2 proved, 0 unexplained'), lines[2])

    def test_with_no_case_logs_kept_research_says_so(self):
        root = tempdir(self)
        run_dir = os.path.join(root, FIRST)
        shutil.copytree(READ_ERROR, os.path.join(run_dir, evidence.DIR, '01-x'))
        summary = diagnosis.after_check(run_dir, root)
        self.assertIn('Research: not kept (no Case logs folder).', '\n'.join(diagnosis.report_section(summary)))
        self.assertIn('Clues: the confirming tests ran 3; the library holds', '\n'.join(diagnosis.report_section(summary)))


if __name__ == '__main__':
    unittest.main()
