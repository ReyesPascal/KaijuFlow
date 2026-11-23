"""Tests for runs.py, the runs root (#241): one Previous run for CHECK.txt, report.md, the INDEX.md row and the page, and
the preflight's own question. Run folders are made in a temp directory. No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_runs.py'
"""
import datetime
import os
import re
import unittest

import brainreport as br
import brainrun
import build_page as bp
import runcheck
import runs
from runfolders import run_folder
from test_brainrun import CleanIO, make_cfg, read
from test_build_page import text
from test_settings import tempdir


def run_on(tmp, name, recording, commit, minutes):
    """A whole run through brainrun's run command, on `recording`, `minutes` after the fake world's clock starts; its
    CHECK.txt stored as the run command stores it."""
    io = CleanIO(commit=commit)
    io.clock += datetime.timedelta(minutes=minutes)
    run = brainrun.run_all(make_cfg(tmp, name=name, listname=recording), io)
    runcheck.check_and_store(run['dir'])
    return run


class OnePreviousRun(unittest.TestCase):
    """The glossary's Previous run: the newest earlier finished run on the same Recording. Every tool names that one."""

    def setUp(self):
        tmp = tempdir(self)
        self.root = os.path.join(tmp, 'runs')
        self.same = run_on(tmp, 'same', 'kf-189', 'c1', 0)
        self.other = run_on(tmp, 'other', 'another-list', 'c2', 5)  # newer, but on another Recording
        self.run = run_on(tmp, 'now', 'kf-189', 'c3', 10)
        self.folder = os.path.basename(self.same['dir'])

    def test_check_txt_names_the_previous_run_on_the_same_recording(self):
        check = read(os.path.join(self.run['dir'], 'CHECK.txt'))
        self.assertIn(f'Against the previous run on the same recording (kf-189): {self.folder}.', check)

    def test_report_md_says_what_changed_since_the_previous_run_on_the_same_recording(self):
        report = read(os.path.join(self.run['dir'], 'report.md'))
        changed = report.split('## What changed since the last run')[1].split('\n## ')[0]
        self.assertIn(f'Against the previous run on the same recording (kf-189): {self.folder}.', changed)
        self.assertIn('KaijuFlow code: c1 -> c3', changed)

    def test_the_index_row_names_the_previous_run_on_the_same_recording(self):
        [row] = [x for x in read(os.path.join(self.root, 'INDEX.md')).splitlines()
                 if f"[{os.path.basename(self.run['dir'])}]" in x]
        self.assertIn(f'Against the previous run on the same recording (kf-189): {self.folder}.', row)
        self.assertIn('KaijuFlow code: c1 -> c3', row)

    def test_the_page_compares_with_the_previous_run_on_the_same_recording(self):
        page = text(bp.build([self.run['dir'], self.other['dir'], self.same['dir']]))
        self.assertTrue(re.search(r'Now run, 10 November 2026\. Compared with the same run of 10 November 2026\.', page), page[:400])


def finished(started, **meta):
    """meta.json of a finished run on the recording 'l' that started at `started`."""
    return {'name': 'run', 'status': 'ok', 'started': started, 'recording': 'l', **meta}


class PreviousRunRule(unittest.TestCase):
    """runs.previous over run folders in a temp runs root: the newest earlier finished run on the same Recording, not
    archived, not short, not marked never compared with (GLOSSARY "Previous run")."""

    def setUp(self):
        self.root = tempdir(self)
        self.first = run_folder(self.root, '2026-11-10T100000Z-first', finished('2026-11-10T10:00:00Z'), [])

    def previous(self, recording='l'):
        run = runs.load(run_folder(self.root, '2026-11-12T100000Z-this', finished('2026-11-12T10:00:00Z', recording=recording), []))
        return runs.previous(run)

    def test_every_run_that_is_not_one_is_passed_over(self):
        for name, meta in (('null', {'status': 'null'}), ('stopped', {'status': 'stopped'}), ('failed', {'status': 'failed'}),
                           ('short', {'short': 'KaijuFlow, 1 round, 2 titles'}), ('never', {'never_compared': True}),
                           ('other', {'recording': 'another-list'}), ('old', {'recording': None})):
            run_folder(self.root, f'2026-11-11T100000Z-{name}', finished('2026-11-11T10:00:00Z', **meta), [])
        run_folder(os.path.join(self.root, br.ARCHIVE), '2026-11-11T110000Z-archived', finished('2026-11-11T11:00:00Z'), [])
        run_folder(self.root, '2026-11-11T120000Z-norawjson', finished('2026-11-11T12:00:00Z'))
        run_folder(self.root, '2026-11-13T100000Z-newer', finished('2026-11-13T10:00:00Z'), [])
        self.assertEqual(self.previous()['folder'], os.path.basename(self.first))

    def test_it_is_read_as_load_reads_it(self):
        run_folder(self.root, '2026-11-11T100000Z-second', finished('2026-11-11T10:00:00Z', commit='c2'),
                   [{'side': 'kaijuflow', 'title': 'Matrix'}])
        prev = self.previous()
        self.assertEqual((prev['folder'], prev['commit'], prev['visits']),
                         ('2026-11-11T100000Z-second', 'c2', [{'side': 'kaijuflow', 'title': 'Matrix'}]))

    def test_a_run_on_a_recording_no_earlier_run_replayed_has_none(self):
        self.assertIsNone(self.previous('another-list'))

    def test_a_run_from_before_186_names_no_recording_and_has_none(self):
        self.assertIsNone(self.previous(None))

    def test_the_null_runs_between_are_the_ones_that_started_after_the_previous_run(self):
        for name, status, started in (('b', 'null', '2026-11-10T11:00:00Z'), ('c', 'ok', '2026-11-10T12:00:00Z'),
                                      ('d', 'null', '2026-11-09T13:00:00Z')):
            run_folder(self.root, f'2026-11-10T1{name}-{status}', {'status': status, 'started': started})
        run = runs.load(run_folder(self.root, '2026-11-12T100000Z-this', finished('2026-11-12T10:00:00Z', status='null'), []))
        nulls = runs.nulls_between(run, runs.load(self.first))
        self.assertEqual([n['started'] for n in nulls], ['2026-11-10T11:00:00Z'])
        self.assertEqual(runs.nulls_between(run, None), [])


REAL_ROOT = os.path.expanduser('~/kaijuflow-notes/brain-runs')
REAL = ('2026-11-23T183239Z-baseline-218', '2026-11-23T190950Z-grouped-219')  # the #218 baseline and #219's grouped run


@unittest.skipUnless(all(os.path.exists(os.path.join(REAL_ROOT, d, runcheck.CHECK_FILE)) for d in REAL),
                     'the real run folders are not on this machine')
class RealRuns(unittest.TestCase):
    def test_checking_the_218_baseline_and_219_again_gives_their_check_txt(self):
        for d in REAL:
            with self.subTest(d):
                stored = read(os.path.join(REAL_ROOT, d, runcheck.CHECK_FILE)).splitlines()
                self.assertEqual(runcheck.check_run(os.path.join(REAL_ROOT, d))[1], stored)


if __name__ == '__main__':
    unittest.main()
