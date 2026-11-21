"""Tests for runcheck.py (can a finished run serve as a baseline?). No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import runcheck


@contextlib.contextmanager
def tempdir():
    d = tempfile.mkdtemp()
    try:
        yield d
    finally:
        shutil.rmtree(d, True)


FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-usable')


def copy_run(tmp):
    dest = os.path.join(tmp, 'run')
    shutil.copytree(FIXTURE, dest)
    return dest


def edit(run, name, fn):
    path = os.path.join(run, name)
    with open(path) as f:
        data = json.load(f)
    fn(data)
    with open(path, 'w') as f:
        json.dump(data, f)


def run_check(run, store=False):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = runcheck.check_command(run, store=store)
    return code, out.getvalue()


def visit_of(raw, side, phase, title=None):
    return [x for x in raw['visits'] if x['side'] == side and x['phase'] == phase and (title is None or x['title'] == title)][0]


class CheckTests(unittest.TestCase):
    def test_usable_run_exits_zero(self):
        with tempdir() as tmp:
            code, out = run_check(copy_run(tmp))
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith('Usable as a baseline'))
        self.assertIn('Top picks played, KaijuFlow: cold 2 of 2, warm 2 of 2.', out)
        self.assertIn('Missed requests: none.', out)
        self.assertIn('Sides with no import time: none.', out)
        self.assertIn('Failures: none.', out)

    def test_missed_request_exits_nonzero_and_names_it(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'raw.json', lambda raw: visit_of(raw, 'kaijuflow', 'warm', 'Beta').update(misses=['ninjacentral search abc']))
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertTrue(out.startswith('Not usable as a baseline: 1 requests missed the recording in 1 visits.'), out)
        self.assertIn('KaijuFlow warm 1: 1', out)
        self.assertIn('Missed in warm rounds (side, title, round): KaijuFlow Beta (1).', out)

    def test_a_short_run_exits_nonzero_with_its_reason_and_still_prints_the_other_lines(self):
        for what in ('KaijuFlow, 1 round, 2 titles', 'KaijuFlow, 2 rounds, 1 title'):
            with tempdir() as tmp:
                run = copy_run(tmp)
                edit(run, 'meta.json', lambda m: m.update(short=what))
                code, out = run_check(run)
            self.assertEqual(code, 1, out)
            self.assertEqual(out.splitlines()[0], f'Not usable as a baseline: short run ({what}).')
            self.assertIn('Missed requests: none.', out)
            self.assertIn('Failures: none.', out)

    def test_absent_planned_side_exits_nonzero(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'meta.json', lambda m: m['sides'].append('kaijuflow-1page'))
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertIn('planned side absent: KaijuFlow, one page per indexer', out.splitlines()[0])

    def test_null_run_exits_nonzero(self):
        with tempdir() as tmp:
            run = copy_run(tmp)

            def null(m):
                m['status'] = 'null'
                m['null'] = {'indexer': 'ninjacentral', 'time': '2026-01-01T00:01:00Z', 'where': 'search'}
            edit(run, 'meta.json', null)
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertIn('the run is null (ninjacentral said its limit was reached', out.splitlines()[0])

    def test_failed_run_exits_nonzero(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'meta.json', lambda m: m.update(status='failed', error='RuntimeError: boom'))
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertIn('the run did not finish (RuntimeError: boom)', out)

    def test_stopped_run_exits_nonzero(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'meta.json', lambda m: m.update(status='stopped', stopped={
                'time': '2026-01-01T00:03:00.000Z', 'plays_done': 5, 'plays_planned': 8, 'during': None}))
            code, out = run_check(run)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], 'Not usable as a baseline: the run was stopped by hand at 2026-01-01T00:03:00.000Z: '
                                              '5 of 8 plays had finished, and it stopped between two plays.')

    def test_unreadable_folder_exits_nonzero(self):
        with tempdir() as tmp:
            code, out = run_check(os.path.join(tmp, 'nothing'))
        self.assertNotEqual(code, 0)
        self.assertIn('meta.json is missing', out)

    def test_failure_cause_and_step_gap_are_listed(self):
        with tempdir() as tmp:
            run = copy_run(tmp)

            def bad(raw):
                visit_of(raw, 'kaijuflow', 'warm', 'Beta').update(ok=False, note='HTTP 503')
                visit_of(raw, 'kaijuflow', 'cold').update(start_s=4.0)
            edit(run, 'raw.json', bad)
            code, out = run_check(run)
        self.assertEqual(code, 0)  # a failed play alone does not stop a baseline; only misses, an absent side or a null run do
        self.assertIn("- KaijuFlow, warm 1, Beta: HTTP 503", out)
        self.assertIn('KaijuFlow, cold 1, Alpha (', out)

    def test_side_without_import_time_is_named(self):
        with tempdir() as tmp:
            run = copy_run(tmp)

            def strip(raw):
                for v in raw['visits']:
                    v['steps'] = [x for x in v['steps'] if x['step'] != 'import_wait']
            edit(run, 'raw.json', strip)
            _, out = run_check(run)
        self.assertIn("Sides with no import time: KaijuFlow.", out)

    def test_store_writes_check_file(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            _, out = run_check(run, store=True)
            with open(os.path.join(run, runcheck.CHECK_FILE)) as f:
                self.assertEqual(f.read(), out)


def runs_pair(tmp, edit_this=None, edit_prev=None):
    """Two copies of the usable fixture in one runs root, the titles tagged (Alpha easy, Beta hard), both on the recording
    'l': the previous run (every KaijuFlow play 2.00 s title to video, no fail) and this run, each edited as given.
    Returns this run's folder."""
    root = os.path.join(tmp, 'runs')
    folders = []
    for name, fn in (('2026-01-01T000000Z-before', edit_prev), ('2026-01-02T000000Z-after', edit_this)):
        dest = os.path.join(root, name)
        shutil.copytree(FIXTURE, dest)
        edit(dest, 'meta.json', lambda m: m.update(recording='l', lists={'Alpha': 'easy', 'Beta': 'hard'}))

        def tag(raw, fn=fn):
            for v in raw['visits']:
                v['list'] = 'easy' if v['title'] == 'Alpha' else 'hard'
            if fn:
                fn(raw)
        edit(dest, 'raw.json', tag)
        folders.append(dest)
    return folders[1]


def kf(raw, phase, title):
    return visit_of(raw, 'kaijuflow', phase, title)


def judged_lines(out):
    lines = out.splitlines()
    start = next(i for i, x in enumerate(lines) if x.startswith('Against the previous run'))
    return lines[start:start + 4]


class PreviousRunTests(unittest.TestCase):
    """check judges a run against KaijuFlow's previous run on the same recording (#186): per list, fails and median cold
    title to video, each better, same or worse, and kept or not kept. Expected lines worked out by hand: every KaijuFlow
    play of the fixture is 1.00 s list and 1.00 s start, so 2.00 s title to video."""

    def test_a_faster_run_with_the_same_fails_is_kept(self):
        with tempdir() as tmp:
            run = runs_pair(tmp, edit_this=lambda raw: kf(raw, 'cold', 'Alpha').update(start_s=0.5))
            _, out = run_check(run)
        self.assertEqual(judged_lines(out), [
            'Against the previous run on the same recording (l): 2026-01-01T000000Z-before.',
            'KaijuFlow, easy list: fails 0 titles failed · 0 of 2 plays (was 0 titles failed · 0 of 2 plays), same; '
            'cold title to video 1.50 s (was 2.00 s), better; '
            'warm title to video 2.00 s (was 2.00 s), same; fallbacks 0 (was 0), same; fallback time 0.00 s (was 0.00 s), same. Kept.',
            'KaijuFlow, hard list: fails 0 titles failed · 0 of 2 plays (was 0 titles failed · 0 of 2 plays), same; '
            'cold title to video 2.00 s (was 2.00 s), same; '
            'warm title to video 2.00 s (was 2.00 s), same; fallbacks 0 (was 0), same; fallback time 0.00 s (was 0.00 s), same. Kept.',
            'Verdict against the previous run: kept.'])

    def test_a_faster_run_with_one_more_fail_is_not_kept(self):
        def faster_with_a_fail(raw):
            kf(raw, 'cold', 'Alpha').update(start_s=0.5)
            kf(raw, 'cold', 'Beta').update(start_s=0.5)
            kf(raw, 'warm', 'Beta').update(ok=False, note='failure video')
        with tempdir() as tmp:
            _, out = run_check(runs_pair(tmp, edit_this=faster_with_a_fail))
        self.assertEqual(judged_lines(out)[1:], [
            'KaijuFlow, easy list: fails 0 titles failed · 0 of 2 plays (was 0 titles failed · 0 of 2 plays), same; '
            'cold title to video 1.50 s (was 2.00 s), better; '
            'warm title to video 2.00 s (was 2.00 s), same; fallbacks 0 (was 0), same; fallback time 0.00 s (was 0.00 s), same. Kept.',
            'KaijuFlow, hard list: fails 1 title failed · 1 of 2 plays (was 0 titles failed · 0 of 2 plays), worse; '
            'cold title to video 1.50 s (was 2.00 s), better; '
            'warm title to video no figure (was 2.00 s), not compared; fallbacks 0 (was 0), same; fallback time 0.00 s (was 0.00 s), same. Not kept.',
            'Verdict against the previous run: not kept.'])

    def fall_back(self, raw, seconds):
        """KaijuFlow's cold Alpha play served video after its top pick's own import failed, the failed import taking
        `seconds` (None: not known); its title to video stays 2.00 s."""
        kf(raw, 'cold', 'Alpha').update(imports=[{'name': 'Alpha.2160p', 'ok': False, 'seconds': seconds},
                                                 {'name': 'Alpha.1080p', 'ok': True, 'seconds': 0.5}])

    def test_the_fallback_time_is_shown_against_the_previous_run_and_does_not_change_the_verdict(self):
        """Per list, how many plays fell back (spec #183) and their extra seconds added up (owner, 2026-11-20, #187), each
        better, same or worse; information only."""
        with tempdir() as tmp:
            run = runs_pair(tmp, edit_this=lambda raw: self.fall_back(raw, 1.25))
            _, out = run_check(run)
        self.assertEqual(judged_lines(out)[1:], [
            'KaijuFlow, easy list: fails 0 titles failed · 0 of 2 plays (was 0 titles failed · 0 of 2 plays), same; '
            'cold title to video 2.00 s (was 2.00 s), same; '
            'warm title to video 2.00 s (was 2.00 s), same; fallbacks 1 (was 0), worse; fallback time 1.25 s (was 0.00 s), worse. Kept.',
            'KaijuFlow, hard list: fails 0 titles failed · 0 of 2 plays (was 0 titles failed · 0 of 2 plays), same; '
            'cold title to video 2.00 s (was 2.00 s), same; '
            'warm title to video 2.00 s (was 2.00 s), same; fallbacks 0 (was 0), same; fallback time 0.00 s (was 0.00 s), same. Kept.',
            'Verdict against the previous run: kept.'])
        with tempdir() as tmp:  # the other way round: the previous run fell back, this one did not
            run = runs_pair(tmp, edit_prev=lambda raw: self.fall_back(raw, 1.25))
            _, out = run_check(run)
        self.assertIn('fallbacks 0 (was 1), better; fallback time 0.00 s (was 1.25 s), better. Kept.', judged_lines(out)[1])

    def test_a_fallback_whose_extra_seconds_are_not_known_makes_the_fallback_time_unknown_not_zero(self):
        with tempdir() as tmp:
            run = runs_pair(tmp, edit_this=lambda raw: self.fall_back(raw, None))
            _, out = run_check(run)
        self.assertEqual(judged_lines(out)[1],
                         'KaijuFlow, easy list: fails 0 titles failed · 0 of 2 plays (was 0 titles failed · 0 of 2 plays), same; '
                         'cold title to video 2.00 s (was 2.00 s), same; '
                         'warm title to video 2.00 s (was 2.00 s), same; fallbacks 1 (was 0), worse; fallback time unknown (was 0.00 s), not compared. Kept.')
        self.assertEqual(judged_lines(out)[3], 'Verdict against the previous run: kept.')

    def test_the_warm_title_to_video_is_shown_against_the_previous_run_and_does_not_change_the_verdict(self):
        """Spec #183: per list, the median warm title to video better, same or worse; information only, the verdict is
        fails and cold title to video."""
        def slower_warm(raw):
            kf(raw, 'warm', 'Alpha').update(start_s=0.5)
            kf(raw, 'warm', 'Beta').update(start_s=3.0)
        with tempdir() as tmp:
            _, out = run_check(runs_pair(tmp, edit_this=slower_warm))
        lines = judged_lines(out)
        self.assertIn('; cold title to video 2.00 s (was 2.00 s), same; warm title to video 1.50 s (was 2.00 s), better;',
                      lines[1])
        self.assertTrue(lines[1].endswith('. Kept.'), lines[1])
        self.assertIn('; cold title to video 2.00 s (was 2.00 s), same; warm title to video 4.00 s (was 2.00 s), worse;',
                      lines[2])
        self.assertTrue(lines[2].endswith('. Kept.'), lines[2])
        self.assertEqual(lines[3], 'Verdict against the previous run: kept.')

    def test_a_stopped_run_with_fewer_fails_is_not_judged(self):
        """Spec #183: a stopped run played fewer plays, so fewer fails says nothing; its lists are not judged, never kept."""
        def stopped_after_cold(m):
            m.update(status='stopped', stopped={'time': '2026-01-02T00:03:00.000Z', 'plays_done': 2, 'plays_planned': 4,
                                                'during': None})

        def cold_only(raw):
            raw['visits'] = [v for v in raw['visits'] if v['phase'] == 'cold']
        with tempdir() as tmp:
            run = runs_pair(tmp, edit_this=cold_only,
                            edit_prev=lambda raw: kf(raw, 'warm', 'Beta').update(ok=False, note='failure video'))
            edit(run, 'meta.json', stopped_after_cold)
            _, out = run_check(run)
        lines = judged_lines(out)
        self.assertTrue(lines[2].startswith('KaijuFlow, hard list: fails 0 titles failed · 0 of 1 plays '
                                            '(was 1 title failed · 1 of 2 plays), better;'), lines[2])
        self.assertTrue(lines[1].endswith('. Not judged: this run was stopped.'), lines[1])
        self.assertTrue(lines[2].endswith('. Not judged: this run was stopped.'), lines[2])
        self.assertEqual(lines[3], 'Verdict against the previous run: not judged, this run was stopped.')

    def test_a_short_run_is_not_judged(self):
        with tempdir() as tmp:
            run = runs_pair(tmp, edit_this=lambda raw: kf(raw, 'cold', 'Alpha').update(start_s=0.5))
            edit(run, 'meta.json', lambda m: m.update(short='KaijuFlow, 1 round, 2 titles'))
            _, out = run_check(run)
        lines = judged_lines(out)
        self.assertTrue(lines[1].endswith('better; warm title to video 2.00 s (was 2.00 s), same; fallbacks 0 (was 0), same; fallback time 0.00 s (was 0.00 s), same. '
                                          'Not judged: this run is short (KaijuFlow, 1 round, 2 titles).'), lines[1])
        self.assertEqual(lines[3], 'Verdict against the previous run: not judged, this run is short (KaijuFlow, 1 round, 2 titles).')

    def test_a_run_on_a_different_recording_is_not_compared(self):
        with tempdir() as tmp:
            run = runs_pair(tmp, edit_this=lambda raw: kf(raw, 'cold', 'Alpha').update(start_s=0.5))
            edit(run, 'meta.json', lambda m: m.update(recording='another'))
            _, out = run_check(run)
        lines = out.splitlines()
        self.assertIn('Against the previous run: not compared, no earlier run on the same recording (another).', lines)
        self.assertFalse([x for x in lines if x.startswith('Verdict against the previous run')], out)

    def test_a_previous_run_with_another_browse_pause_is_not_compared_and_check_says_why(self):
        # #205: the previous run (from before #205, so no Browse pause) against this run's 5 s pause
        with tempdir() as tmp:
            run = runs_pair(tmp, edit_this=lambda raw: kf(raw, 'cold', 'Alpha').update(start_s=0.5))
            edit(run, 'meta.json', lambda m: m.update(browse_pause_s=5))
            code, out = run_check(run)
        lines = out.splitlines()
        self.assertIn('Against the previous run on the same recording (l): 2026-01-01T000000Z-before: not compared, its '
                      "Browse pause was 0 s and this run's is 5 s; a run is judged only against a run with the same pause.", lines)
        self.assertFalse([x for x in lines if x.startswith('Verdict against the previous run') or '(was ' in x], out)
        self.assertEqual(code, 0)  # still usable as a baseline: the next run with its pause is judged against it

    def test_two_runs_with_the_same_browse_pause_are_judged(self):
        with tempdir() as tmp:
            run = runs_pair(tmp, edit_this=lambda raw: kf(raw, 'cold', 'Alpha').update(start_s=0.5))
            for folder in (run, os.path.join(os.path.dirname(run), '2026-01-01T000000Z-before')):
                edit(folder, 'meta.json', lambda m: m.update(browse_pause_s=5))
            _, out = run_check(run)
        self.assertEqual(judged_lines(out)[3], 'Verdict against the previous run: kept.')

    def test_an_earlier_run_marked_never_compared_with_or_archived_is_passed_over(self):
        with tempdir() as tmp:
            run = runs_pair(tmp, edit_this=lambda raw: kf(raw, 'cold', 'Alpha').update(start_s=0.5))
            root = os.path.dirname(run)
            between = os.path.join(root, '2026-01-01T120000Z-between')
            shutil.copytree(run, between)
            edit(between, 'meta.json', lambda m: m.update(never_compared=True, label='Test 1'))
            shutil.copytree(run, os.path.join(root, 'archive', '2026-01-01T180000Z-archived'))
            _, out = run_check(run)
        self.assertEqual(judged_lines(out)[0], 'Against the previous run on the same recording (l): 2026-01-01T000000Z-before.')


FULL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-2026-11-13-imports')


class EarlierRunTests(unittest.TestCase):
    """check reads a run from before #185 as it was (#187). fixtures/run-2026-11-13-imports is the real 2026-11-13 baseline,
    each visit with its first try and imports as raw.json kept them, played on the sides of then. Figures worked out by hand."""

    def test_the_check_counts_a_fallback_as_played_and_lists_the_fallbacks_apart(self):
        _, out = run_check(FULL)
        lines = out.splitlines()
        self.assertIn("Top picks played, AltMount direct: cold 20 of 20, warm 20 of 20.", lines)  # #185: a fallback plays
        start = lines.index('Played after a fallback (4), counted as played:')
        self.assertEqual(lines[start + 1:start + 5], [
            "- AltMount direct, cold 1, Chernobyl S01E02: played after 3 fallbacks",
            "- AltMount direct, warm 1, Chernobyl S01E02: played after 3 fallbacks",
            "- AltMount direct, cold 2, Chernobyl S01E02: played after 3 fallbacks",
            "- AltMount direct, warm 2, Chernobyl S01E02: played after 3 fallbacks"])


if __name__ == '__main__':
    unittest.main()
