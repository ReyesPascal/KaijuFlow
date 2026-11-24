"""Tests for Fixing (#288, spec #279), through Diagnosis after a check: a proved KaijuFlow cause makes its fix ticket
(the text always, filed unless the check is a dry run), a cause that is not KaijuFlow's makes none, and a failure that
proves a proved-fixed cause is a comeback that reopens its entry. The evidence folders are the real plays in
fixtures/2026-11-24-diagnosis/ (README there); the Casebook is a copy whose entries' status or whose a test sets. No
test files a real ticket: a test either runs dry or hands Diagnosis a fake tracker.
    python3 -I -m unittest discover -s tools/brain -p 'test_fixing.py'
"""
import contextlib
import io
import json
import os
import re
import unittest
from unittest import mock

import casebook
import diagnosis
import fixing
from test_evidence import run_failed_check
from test_diagnosis import DEAD_PACK, HHWEB, INDEXER_DOWN, READ_ERROR, casebook_copy, stored_check
from test_quickcheck import read
from test_settings import tempdir


def set_field(book, entry_id, field, value):
    """Sets one front matter field of a Casebook entry (copy) and writes the index again."""
    path = os.path.join(book, entry_id + '.md')
    with open(path) as f:
        text = f.read()
    text, n = re.subn(rf'(?m)^{field}: .*$', f'{field}: {diagnosis._value(value)}', text, count=1)
    assert n == 1, (entry_id, field)
    with open(path, 'w') as f:
        f.write(text)
    casebook.write_index(book)


class FakeTracker:
    """The issue tracker as Diagnosis meets it: it lists the open tickets whose title holds a text, and files one.
    Like GitHub, it refuses a ticket with no title or no body."""

    def __init__(self, open_tickets=()):
        self.open, self.filed, self.next = list(open_tickets), [], 301

    def find(self, text):
        return next((ref for ref, title in self.open if text in title), None)

    def file(self, title, body):
        if not title.strip() or not body.strip():
            raise RuntimeError('title and body are required')
        ref = f'#{self.next}'
        self.next += 1
        self.filed.append((ref, title, body))
        self.open.append((ref, title))
        return ref, None


def after(case, plays, book, tracker=None, cases=None):
    root, run_dir = stored_check(case, plays=plays)
    summary = diagnosis.after_check(run_dir, root, book=book, tracker=tracker,
                                    cases=cases or os.path.join(tempdir(case), 'cases'))
    return run_dir, summary


def fixes(summary):
    return {f['entry']: f for f in summary['fixes']}


class ProvedKaijuFlowCauseTest(unittest.TestCase):
    def setUp(self):
        self.book = casebook_copy(self)
        set_field(self.book, 'unscramble-read-error', 'status', 'open')

    def test_a_dry_run_writes_the_ticket_text_and_files_nothing(self):
        run_dir, summary = after(self, (READ_ERROR,), self.book)

        f = fixes(summary)['unscramble-read-error']
        self.assertEqual((f['action'], f['whose'], f['comeback']), ('ticket', 'KaijuFlow', False))
        t = f['ticket']
        self.assertEqual((t['filed'], t['dry_run']), (None, True))
        self.assertEqual(t['file'], 'fix-tickets/unscramble-read-error.md')
        self.assertEqual(t['title'], 'Fix: Unscramble could not read a Scrambled RAR set, so the scrambled original went up '
                                     'and AltMount refused it (Casebook unscramble-read-error)')
        text = read(run_dir, t['file'])
        self.assertTrue(text.startswith(f"# {t['title']}\n\n## Parent\n#183"), text[:200])
        self.assertIn('`ready-for-agent`', text)
        # the cause, from the entry
        self.assertIn('Unscramble could not read a Scrambled RAR set', text)
        # its proof: every Clue of the recipe, its answer and a fact it saw, on this failure's own evidence
        for clue in ('unscramble-read-error', 'original-uploaded-after-unscramble', 'altmount-missing-volumes'):
            self.assertIn(f'`{clue}` answered yes (wanted yes)', text)
        self.assertIn(f'The Witcher S01E01: {HHWEB}', text)
        self.assertIn('evidence/01-219-witcher-read-error', text)
        # the Drill-down command that proves the fix
        self.assertIn('python3 -I tools/brain/brainrun.py drill --title tt5180504 --episode S01E01', text)
        self.assertEqual(json.loads(read(run_dir, diagnosis.STORED))['fixes'], summary['fixes'])

    def test_with_a_tracker_it_files_the_ticket_once(self):
        tracker = FakeTracker()
        run_dir, summary = after(self, (READ_ERROR, READ_ERROR), self.book, tracker)  # proved twice in one check

        [(ref, title, body)] = tracker.filed
        t = fixes(summary)['unscramble-read-error']['ticket']
        self.assertEqual((t['filed'], t['dry_run'], ref), ('#301', False, '#301'))
        self.assertEqual(title, t['title'])
        self.assertEqual(f"# {title}\n\n{body}", read(run_dir, t['file']))
        self.assertEqual(len(fixes(summary)['unscramble-read-error']['proved_in']), 2)

    def test_an_open_ticket_for_the_cause_is_named_and_none_filed_again(self):
        tracker = FakeTracker([('#299', 'Fix: something (Casebook unscramble-read-error)')])
        _, summary = after(self, (READ_ERROR,), self.book, tracker)
        self.assertEqual(tracker.filed, [])
        t = fixes(summary)['unscramble-read-error']['ticket']
        self.assertEqual((t['filed'], t['already']), ('#299', True))

    def test_a_tracker_that_fails_is_said_and_the_text_is_kept(self):
        class Down(FakeTracker):
            def find(self, text):
                raise RuntimeError('gh: could not connect')
        run_dir, summary = after(self, (READ_ERROR,), self.book, Down())
        t = fixes(summary)['unscramble-read-error']['ticket']
        self.assertEqual(t['filed'], None)
        self.assertIn('could not connect', t['error'])
        self.assertTrue(os.path.exists(os.path.join(run_dir, t['file'])))

    def test_a_cause_whose_fix_is_under_way_gets_no_new_ticket(self):
        for status in ('fix in progress', 'fixed awaiting proof'):
            with self.subTest(status=status):
                set_field(self.book, 'unscramble-read-error', 'status', status)
                tracker = FakeTracker()
                run_dir, summary = after(self, (READ_ERROR,), self.book, tracker)
                f = fixes(summary)['unscramble-read-error']
                self.assertEqual((f['action'], f.get('ticket'), tracker.filed), ('under way', None, []))
                self.assertFalse(os.path.exists(os.path.join(run_dir, fixing.DIR)))

    def test_the_report_says_what_was_filed(self):
        _, summary = after(self, (READ_ERROR,), self.book, FakeTracker())
        report = '\n'.join(diagnosis.report_section(summary))
        self.assertIn('- unscramble-read-error (KaijuFlow): fix ticket #301 filed (`fix-tickets/unscramble-read-error.md`).',
                      report)
        _, summary = after(self, (READ_ERROR,), self.book)
        report = '\n'.join(diagnosis.report_section(summary))
        self.assertIn('- unscramble-read-error (KaijuFlow): fix ticket text written, not filed (a dry run): '
                      '`fix-tickets/unscramble-read-error.md`.', report)


class NotOursTest(unittest.TestCase):
    def test_a_cause_that_is_not_kaijuflows_gets_its_workaround_and_no_ticket(self):
        book = casebook_copy(self)
        workaround = 'Workaround: ADR 0005 puts the parts in order before upload'
        for whose in ('AltMount', 'indexer', 'Usenet', 'test-only'):
            with self.subTest(whose=whose):
                set_field(book, 'unchecked-dead-season-pack', 'whose', whose)
                set_field(book, 'unchecked-dead-season-pack', 'status', 'open')
                set_field(book, 'unchecked-dead-season-pack', 'fix', workaround)
                tracker = FakeTracker()
                run_dir, summary = after(self, (DEAD_PACK,), book, tracker)

                f = fixes(summary)['unchecked-dead-season-pack']
                self.assertEqual((f['action'], f['whose'], f.get('ticket'), f['fix']), ('workaround', whose, None, workaround))
                self.assertEqual(tracker.filed, [])
                self.assertFalse(os.path.exists(os.path.join(run_dir, fixing.DIR)))
                self.assertIn(f'- unchecked-dead-season-pack ({whose}): not KaijuFlow\'s, no ticket; {workaround}.',
                              '\n'.join(diagnosis.report_section(summary)))

    def test_a_failure_with_no_proved_cause_makes_no_fix(self):
        _, summary = after(self, (INDEXER_DOWN,), casebook_copy(self), FakeTracker())
        self.assertEqual(summary['fixes'], [])


class ComebackTest(unittest.TestCase):
    def setUp(self):
        self.book = casebook_copy(self)
        set_field(self.book, 'unscramble-read-error', 'status', 'proved fixed')

    def test_a_failure_that_proves_a_proved_fixed_cause_is_a_comeback_with_a_ticket(self):
        tracker = FakeTracker()
        run_dir, summary = after(self, (READ_ERROR,), self.book, tracker)
        f = fixes(summary)['unscramble-read-error']
        self.assertEqual((f['action'], f['comeback'], f['status']), ('ticket', True, 'proved fixed'))
        [(_, title, body)] = tracker.filed
        self.assertTrue(title.startswith('Fix, a comeback: '), title)
        self.assertIn('#245 (PR #252', body)  # the fix that was proved, and came back
        self.assertIn('- unscramble-read-error (KaijuFlow): a comeback (it was proved fixed); `diagnosis.py record` '
                      'reopens it; fix ticket #301 filed', '\n'.join(diagnosis.report_section(summary)))

    def test_record_reopens_the_entry_and_notes_the_ticket(self):
        run_dir, _ = after(self, (READ_ERROR,), self.book, FakeTracker())

        diagnosis.record(run_dir, self.book)

        self.assertEqual(casebook.problems(self.book), [])
        fields, sections = casebook.read_entry(os.path.join(self.book, 'unscramble-read-error.md'))
        self.assertEqual(fields['status'], 'reopened')
        self.assertTrue(fields['fix'].startswith('#301 (fix ticket filed by Diagnosis, a comeback); #245 (PR #252'),
                        fields['fix'])
        history = sections['History'].splitlines()
        self.assertEqual(history[-1], '- 2026-11-23: reopened, a comeback: proved again in 2026-11-24T070000Z-quick-check, '
                                      'The Witcher S01E01 (evidence/01-219-witcher-read-error); fix ticket #301. '
                                      '(Diagnosis, #288)')
        before = read(self.book, 'unscramble-read-error.md')
        diagnosis.record(run_dir, self.book)  # recording again changes nothing
        self.assertEqual(read(self.book, 'unscramble-read-error.md'), before)

    def test_a_not_ours_comeback_reopens_with_no_ticket(self):
        set_field(self.book, 'unchecked-dead-season-pack', 'whose', 'AltMount')
        set_field(self.book, 'unchecked-dead-season-pack', 'status', 'proved fixed')
        tracker = FakeTracker()
        run_dir, summary = after(self, (DEAD_PACK,), self.book, tracker)
        f = fixes(summary)['unchecked-dead-season-pack']
        self.assertEqual((f['action'], f['comeback'], tracker.filed), ('workaround', True, []))
        diagnosis.record(run_dir, self.book)
        fields, sections = casebook.read_entry(os.path.join(self.book, 'unchecked-dead-season-pack.md'))
        self.assertEqual(fields['status'], 'reopened')
        self.assertIn('reopened, a comeback: proved again in 2026-11-24T070000Z-quick-check, The Twilight Zone S02E06 '
                      '(evidence/01-189-twilight-dead-pack); its workaround no longer holds. (Diagnosis, #288)',
                      sections['History'])


class RecordTicketTest(unittest.TestCase):
    def test_a_filed_ticket_puts_an_open_entry_in_progress(self):
        book = casebook_copy(self)
        set_field(book, 'unscramble-read-error', 'status', 'open')
        set_field(book, 'unscramble-read-error', 'fix', 'none yet')
        run_dir, _ = after(self, (READ_ERROR,), book, FakeTracker())
        diagnosis.record(run_dir, book)
        fields, sections = casebook.read_entry(os.path.join(book, 'unscramble-read-error.md'))
        self.assertEqual((fields['status'], fields['fix']), ('fix in progress', '#301 (fix ticket filed by Diagnosis)'))
        self.assertTrue(sections['History'].endswith('- 2026-11-23: fix ticket #301 filed by Diagnosis, proved in '
                                                     '2026-11-24T070000Z-quick-check, The Witcher S01E01 '
                                                     '(evidence/01-219-witcher-read-error). (Diagnosis, #288)'),
                        sections['History'][-300:])

    def test_a_dry_run_ticket_changes_no_entry(self):
        book = casebook_copy(self)
        set_field(book, 'unscramble-read-error', 'status', 'open')
        run_dir, _ = after(self, (READ_ERROR,), book)
        diagnosis.record(run_dir, book)
        self.assertEqual(casebook.read_entry(os.path.join(book, 'unscramble-read-error.md'))[0]['status'], 'open')


class FixCommandTest(unittest.TestCase):
    """`diagnosis.py fix <check folder>`: a check diagnosed again with a Casebook that has the cause now (a Case log
    written up as an entry), its fixes made as after the check: filed, or only written with --dry-run."""

    def test_a_dry_run_writes_the_ticket_text_of_a_cause_the_casebook_has_now(self):
        book = casebook_copy(self)
        root, run_dir = stored_check(self, plays=(READ_ERROR,))
        diagnosis.after_check(run_dir, root, book=book, cases=os.path.join(tempdir(self), 'cases'))
        set_field(book, 'unscramble-read-error', 'status', 'open')  # as `case entry` writes a solved cause
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = diagnosis.main(['diagnosis.py', 'fix', run_dir, '--casebook', book, '--dry-run'])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), '- unscramble-read-error (KaijuFlow): fix ticket text written, not filed (a dry '
                                         'run): `fix-tickets/unscramble-read-error.md`.\n')
        summary = json.loads(read(run_dir, diagnosis.STORED))
        self.assertEqual(summary['fixes'][0]['action'], 'ticket')
        self.assertIn('scoreboard', summary)  # what the check wrote is kept
        self.assertTrue(read(run_dir, 'fix-tickets', 'unscramble-read-error.md').startswith('# Fix: '))

    def test_without_dry_run_it_files_with_the_real_tracker(self):
        book = casebook_copy(self)
        set_field(book, 'unscramble-read-error', 'status', 'open')
        root, run_dir = stored_check(self, plays=(READ_ERROR,))
        tracker = FakeTracker()
        with mock.patch.object(fixing, 'GitHub', return_value=tracker), contextlib.redirect_stdout(io.StringIO()):
            diagnosis.main(['diagnosis.py', 'fix', run_dir, '--casebook', book])
        self.assertEqual([r for r, _, _ in tracker.filed], ['#301'])


class AQuickCheckTest(unittest.TestCase):
    """Through the quick check (brainrun.py check): its proved KaijuFlow cause files the ticket with the check's tracker,
    or writes only the text with --tickets-dry-run."""

    def setUp(self):
        self.book = casebook_copy(self)
        set_field(self.book, 'unscramble-read-error', 'status', 'open')

    def test_a_check_files_the_fix_ticket_of_its_proved_kaijuflow_cause(self):
        code, out, folder, world = run_failed_check(self, cfg={'casebook': self.book})
        [filed] = [c for c in world.calls if c[0] == 'file ticket']
        self.assertTrue(filed[1].endswith('(Casebook unscramble-read-error)'), filed)
        self.assertIn('- unscramble-read-error (KaijuFlow): fix ticket #401 filed (`fix-tickets/unscramble-read-error.md`).',
                      read(folder, 'report.md'))

    def test_a_dry_run_check_files_nothing_and_keeps_the_text(self):
        code, out, folder, world = run_failed_check(self, cfg={'casebook': self.book, 'tickets_dry_run': True})
        self.assertEqual([c for c in world.calls if c[0] == 'file ticket'], [])
        self.assertIn('(a dry run): `fix-tickets/unscramble-read-error.md`', read(folder, 'report.md'))
        self.assertTrue(read(folder, 'fix-tickets', 'unscramble-read-error.md').startswith('# Fix: Unscramble'))


class GitHubTrackerTest(unittest.TestCase):
    """The real tracker's calls, on gh's answers as gh 2.46 gives them (no `--parent`: the sub-issue goes through the
    API, docs/agents/issue-tracker.md). A call gh would not take is refused."""

    def gh(self, answers):
        calls = []

        class Done:
            def __init__(self, out='', code=0, err=''):
                self.stdout, self.returncode, self.stderr = out, code, err

        def run(cmd, **kw):
            calls.append(cmd)
            self.assertEqual(cmd[0], 'gh')
            self.assertNotIn('--parent', cmd)
            for prefix, answer in answers:
                if cmd[1:1 + len(prefix)] == prefix:
                    return Done(*answer) if isinstance(answer, tuple) else Done(answer)
            return Done('', 1, f'unknown command {cmd[1:3]}')
        return fixing.GitHub(run=run), calls

    def test_it_files_a_ready_for_agent_ticket_under_the_map(self):
        t, calls = self.gh([(['issue', 'create'], 'https://github.com/ReyesPascal/KaijuFlow/issues/312\n'),
                            (['api', 'repos/{owner}/{repo}/issues/312'], '3712345678\n'),
                            (['api', '--method', 'POST'], '{}')])
        self.assertEqual(t.file('Fix: x (Casebook y)', 'body'), ('#312', None))
        create = calls[0]
        self.assertEqual(create[create.index('--label') + 1], 'ready-for-agent')
        self.assertEqual(create[create.index('--title') + 1], 'Fix: x (Casebook y)')
        self.assertEqual(calls[2], ['gh', 'api', '--method', 'POST', 'repos/{owner}/{repo}/issues/183/sub_issues',
                                    '-F', 'sub_issue_id=3712345678'])

    def test_a_ticket_filed_but_not_put_under_the_map_says_so(self):
        t, _ = self.gh([(['issue', 'create'], 'https://github.com/ReyesPascal/KaijuFlow/issues/312\n')])
        ref, problem = t.file('Fix: x (Casebook y)', 'body')
        self.assertEqual(ref, '#312')
        self.assertIn('not put under the map #183', problem)

    def test_it_finds_an_open_ticket_by_its_title(self):
        t, calls = self.gh([(['issue', 'list'], json.dumps([{'number': 7, 'title': 'Fix: a (Casebook other-y)'},
                                                             {'number': 8, 'title': 'Fix: b (Casebook y)'}]))])
        self.assertEqual(t.find('(Casebook y)'), '#8')
        self.assertEqual(t.find('(Casebook z)'), None)
        self.assertEqual(calls[0][calls[0].index('--search') + 1], '"Casebook y" in:title')
        self.assertEqual(calls[0][calls[0].index('--state') + 1], 'open')

    def test_a_refused_call_raises_with_what_gh_said(self):
        t, _ = self.gh([(['issue', 'create'], ('', 1, 'HTTP 401: Bad credentials'))])
        with self.assertRaisesRegex(RuntimeError, 'Bad credentials'):
            t.file('Fix: x (Casebook y)', 'body')


if __name__ == '__main__':
    unittest.main()
