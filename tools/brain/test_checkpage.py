"""Tests for the Speed Check page of real-use checks (checkpage.py, #273, ADR 0010), on the quick check of 2026-11-24
(fixtures/2026-11-24-quick-check/: its meta.json and raw.json as the check wrote them; the expected numbers are its report.md's).
    python3 -I -m unittest discover -s tools/brain -p 'test_checkpage.py'
"""
import contextlib
import io
import json
import os
import re
import shutil
import unittest

import checkpage
import test_quickcheck
from test_settings import tempdir

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, 'fixtures', '2026-11-24-quick-check')


def check_folder(root, name, **meta):
    """A copy of the captured check folder in `root`, its meta.json changed by `meta`."""
    d = os.path.join(root, name)
    shutil.copytree(CAPTURED, d)
    if meta:
        with open(os.path.join(d, 'meta.json')) as f:
            m = json.load(f)
        m.update(meta)
        with open(os.path.join(d, 'meta.json'), 'w') as f:
            json.dump(m, f)
    return d


def check_folder_now(root, name):
    """The captured check folder as a check writes it since #304: raw.json's visits with their `list` steps and `found`
    (test_quickcheck.real_check rebuilds them from the captured lines), and the stand-in's log in logs/."""
    d = check_folder(root, name)
    check = test_quickcheck.real_check()
    with open(os.path.join(d, 'raw.json')) as f:
        raw = json.load(f)
    raw['visits'] = check['visits']
    with open(os.path.join(d, 'raw.json'), 'w') as f:
        json.dump(raw, f)
    os.makedirs(os.path.join(d, 'logs'))
    shutil.copy(os.path.join(CAPTURED, 'standin.log'), os.path.join(d, 'logs', 'standin.log'))
    return d


def table_rows(html, heading):
    """[[cell, ...]] of the table after `heading` on the page, its head row first."""
    part = html[html.index(heading):]
    part = part[:part.index('</table>')]
    return [[re.sub('<[^>]+>', '', c) for c in re.findall(r'<t[hd]>(.*?)</t[hd]>', row)] for row in re.findall(r'<tr>(.*?)</tr>', part)]


def build(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = checkpage.main(list(argv))
    return code, out.getvalue()


class CheckPageTest(unittest.TestCase):
    def setUp(self):
        self.root, self.out = tempdir(self), tempdir(self)

    def page(self, *folders):
        code, said = build(*folders, '--out', self.out)
        self.assertEqual(code, 0, said)
        with open(os.path.join(self.out, 'index.html')) as f:
            return f.read()

    def test_the_page_leads_with_the_newest_checks_verdict_and_its_fails(self):
        html = self.page(check_folder(self.root, '2026-11-24T122253Z-quick-check'))
        self.assertIn('Fail: 1 of 5 titles failed (Girlfriends S04E04).', html)
        self.assertIn("Girlfriends S04E04", html)
        self.assertIn("video came, but KaijuFlow&#x27;s log names no release played, so the right title cannot be told", html)

    def test_the_totals_are_the_reports_and_no_run_words_are_on_it(self):
        html = self.page(check_folder(self.root, '2026-11-24T122253Z-quick-check'))
        for words in ('1.38 s', 'median of 4 plays with the right video', 'Fallbacks not tested this time',
                      '5 titles', 'Quick check'):
            self.assertIn(words, html)
        for retired_word in ('Recording', 'Round', 'baseline', 'previous run', 'warm'):
            self.assertNotIn(retired_word, html)
        self.assertNotIn('Hunting Season', html)  # totals only: a title that played is not listed (rules.md, "The report")

    def test_every_check_given_has_a_row_newest_first_with_its_verdict(self):
        older = check_folder(self.root, '2026-11-20T090000Z-quick-check', started='2026-11-20T09:00:00.000Z', verdict='pass',
                             headline='Pass: 0 fails in 5 titles.')
        newer = check_folder(self.root, '2026-11-24T122253Z-quick-check')
        html = self.page(older, newer)
        rows = html[html.index('Every check so far'):]
        self.assertLess(rows.index('2026-11-24'), rows.index('2026-11-20'))
        self.assertIn('Pass: 0 fails in 5 titles.', rows)
        lead = html[:html.index('Every check so far')]
        self.assertIn('Fail: 1 of 5 titles failed', lead)  # the newest leads, whatever order the folders came in

    def test_a_check_without_a_verdict_says_why_and_is_no_lead(self):
        stopped = check_folder(self.root, '2026-11-25T090000Z-quick-check', started='2026-11-25T09:00:00.000Z', verdict=None,
                               status='null', headline='No verdict: ninjacentral said its limit was reached at 09:12, so the check stopped (the cap rule).')
        html = self.page(check_folder(self.root, '2026-11-24T122253Z-quick-check'), stopped)
        self.assertIn('No verdict: ninjacentral said its limit was reached', html)
        lead = html[:html.index('Every check so far')]
        self.assertIn('Fail: 1 of 5 titles failed', lead)

    def test_the_lead_check_has_the_indexer_table_of_its_report(self):
        html = self.page(check_folder_now(self.root, '2026-11-24T122253Z-quick-check'))
        self.assertEqual(table_rows(html, '<h2>Indexers</h2>'), [
            ['Indexer', 'Searches', 'Downloads', 'Answer time', 'Lists sent without it', 'Plays from a Release only it had'],
            ['DrunkenSlug', '21', '9', '0.49 s typical, 2.14 s slowest', '0 of 5', '3'],
            ['NinjaCentral', '20', '7', '0.42 s typical, 0.69 s slowest', '0 of 5', '0']])
        lead = html[:html.index('Every check so far')]
        self.assertIn('<h2>Indexers</h2>', lead)  # the newest check's, not the list's

    def test_a_check_brainrun_ran_gets_its_reports_indexer_rows_on_the_page(self):
        cfg = test_quickcheck.check_cfg(self)
        code, out = test_quickcheck.run_check(cfg, test_quickcheck.CheckWorld())
        self.assertEqual(code, 0, out)
        folder = os.path.join(cfg['runs_root'], '2026-11-25T100000Z-quick-check')
        with open(os.path.join(folder, 'report.md')) as f:
            report = f.read()
        section = report[report.index('## Indexers'):].split('\n\n')[1].splitlines()
        reported = [[c.strip() for c in line.strip('|').split('|')] for line in section if not line.startswith('|---')]
        self.assertEqual(reported[1], ['NinjaCentral', '5', '5', '0.30 s typical, 0.30 s slowest', '0 of 5', '5'])
        self.assertEqual(table_rows(self.page(folder), '<h2>Indexers</h2>'), reported)

    def test_a_folder_that_is_not_a_real_use_check_is_refused_in_one_sentence(self):
        run = os.path.join(self.root, '2026-11-23T100000Z-baseline')
        os.makedirs(run)
        with open(os.path.join(run, 'meta.json'), 'w') as f:
            json.dump({'name': 'baseline', 'status': 'ok', 'recording': 'kf-265'}, f)
        code, said = build(run, '--out', self.out)
        self.assertEqual(code, 1)
        self.assertIn('is not a real-use check', said)
        self.assertEqual(len(said.strip().splitlines()), 1, said)
        self.assertFalse(os.path.exists(os.path.join(self.out, 'index.html')))


if __name__ == '__main__':
    unittest.main()
