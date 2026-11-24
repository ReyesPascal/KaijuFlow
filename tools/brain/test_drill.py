"""Tests for the Drill-down (#272, spec #279), through the evidence and Diagnosis seams: `brainrun.py drill` plays one
failed title again in the quick check's fake world (test_quickcheck.CheckWorld; test_evidence.FailedPlayWorld for the
captured failed play), saves the evidence folder a check saves, runs the suspected cause's confirming recipe of Clues on
it, and marks the Casebook entry proved fixed or reopened; `diagnosis.py record` writes the mark onto the entry. The
earlier check that proved the cause is the real play in fixtures/2026-11-24-diagnosis/219-witcher-read-error/; the
Casebook is a copy.
    python3 -I -m unittest discover -s tools/brain -p 'test_drill.py'
"""
import contextlib
import io
import json
import os
import unittest

import brainrun
import casebook
import diagnosis
import evidence
from test_diagnosis import READ_ERROR, casebook_copy, stored_check
from test_evidence import WITCHER, FailedPlayWorld
from test_quickcheck import CheckWorld, check_cfg, read
from test_settings import tempdir

EARLIER = '2026-11-24T070000Z-quick-check'  # the check that proved the cause on the Witcher (stored_check's name)
# the title as the earlier evidence folder names it (the captured run kept no draw, so no date)
TITLE = ['series', 'tt5180504:1:1', 'The Witcher S01E01', 'popular-episode', None]


def earlier_check(case, book, plays=(READ_ERROR,)):
    """A runs root holding one diagnosed check of the Witcher whose failure proved unscramble-read-error."""
    root, run_dir = stored_check(case, EARLIER, plays)
    diagnosis.diagnose_check(run_dir, diagnosis.load_index(book))
    return root


def drill_cfg(case, root, book, **kw):
    cfg = dict(check_cfg(case), runs_root=root, name='drill-down', casebook=book, tickets_dry_run=True,
               drill_title='tt5180504', drill_episode='S01E01', drill_entries=[])
    cfg.update(kw)
    return cfg


def run_drill(cfg, world):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = brainrun.drill_command(cfg, world)
    return code, out.getvalue()


def entry(book, entry_id):
    fields, sections = casebook.read_entry(os.path.join(book, entry_id + '.md'))
    return fields, sections


class ProvedFixedTest(unittest.TestCase):
    def setUp(self):
        self.book = casebook_copy(self)
        self.root = earlier_check(self, self.book)
        self.cfg = drill_cfg(self, self.root, self.book)
        self.world = CheckWorld(drawn=[WITCHER])  # the Witcher plays the right episode at once, no Source fails
        self.code, self.out = run_drill(self.cfg, self.world)
        self.folder = os.path.join(self.root, '2026-11-25T100000Z-drill-down')

    def test_it_plays_the_one_title_cold_and_live_with_the_quick_checks_verdict_and_draws_nothing(self):
        self.assertEqual(self.code, 0, self.out)
        self.assertIn('Pass: 0 fails in 1 title.', self.out)
        self.assertEqual(self.world.calls[:4], [('preflight', 'check'), ('reset', tuple(brainrun.ALL_TESTBED)),
                                                ('open-store',), ('standin', 'record')])
        self.assertNotIn('draw', [c[0] for c in self.world.calls])
        self.assertEqual([c[1] for c in self.world.calls if c[0] == 'visit'], [WITCHER[1]])
        self.assertFalse(os.path.exists(self.cfg['ledger']))  # the title is not added to the draw ledger again
        meta = json.loads(read(self.folder, 'meta.json'))
        self.assertEqual((meta['kind'], meta['verdict'], meta['titles']), ('drill-down', 'pass', [TITLE]))
        self.assertIn('| drill-down | pass |', read(self.root, 'INDEX.md'))

    def test_it_saves_the_evidence_folder_a_check_saves_even_for_a_play_that_went_fine(self):
        ev = evidence.read(os.path.join(self.folder, evidence.DIR, '01-the-witcher-s01e01'))
        self.assertEqual((ev.meta['kind'], ev.meta['kept_because'], ev.meta['title']), ('drill-down', None, TITLE))
        self.assertEqual([s['step'] for s in ev.steps], ['play_check', 'played'])
        self.assertEqual(diagnosis.diagnose(ev.folder, diagnosis.load_index(self.book))['failures'], [])

    def test_the_suspected_cause_is_marked_proved_fixed_and_record_writes_it_on_the_entry(self):
        [mark] = json.loads(read(self.folder, diagnosis.STORED))['drill']['marks']
        self.assertEqual((mark['entry'], mark['before'], mark['result']),
                         ('unscramble-read-error', 'fixed awaiting proof', 'proved fixed'))
        self.assertEqual(mark['from'], [f'{EARLIER}/evidence/01-219-witcher-read-error'])
        self.assertIn('## Drill-down\n\n- unscramble-read-error: proved fixed: The Witcher S01E01 played with no '
                      'failure (evidence/01-the-witcher-s01e01).', read(self.folder, 'report.md'))

        diagnosis.record(self.folder, self.book)

        fields, sections = entry(self.book, 'unscramble-read-error')
        self.assertEqual(fields['status'], 'proved fixed')
        self.assertIn('- 2026-11-25: proved fixed by the Drill-down 2026-11-25T100000Z-drill-down: The Witcher S01E01 '
                      'played with no failure (evidence/01-the-witcher-s01e01). (Drill-down, #272)', sections['History'])
        self.assertEqual(casebook.problems(self.book), [])
        before = read(self.book, 'unscramble-read-error.md')
        diagnosis.record(self.folder, self.book)  # nothing is written twice
        self.assertEqual(read(self.book, 'unscramble-read-error.md'), before)


if __name__ == '__main__':
    unittest.main()
