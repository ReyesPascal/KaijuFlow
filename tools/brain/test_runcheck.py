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
        for what in ('KaijuFlow, 1 round, 2 titles', 'KaijuFlow, Usenet Ultimate, AltMount direct, 2 rounds, 1 title'):
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
            edit(run, 'meta.json', lambda m: m['sides'].append('uu'))
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertIn('planned side absent: Usenet Ultimate', out.splitlines()[0])

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
        self.assertEqual(target_lines(out), [])  # a null run's numbers are not used, so no target is judged on them

    def test_failed_run_exits_nonzero(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'meta.json', lambda m: m.update(status='failed', error='RuntimeError: boom'))
            code, out = run_check(run)
        self.assertNotEqual(code, 0)
        self.assertIn('the run did not finish (RuntimeError: boom)', out)
        self.assertEqual(target_lines(out), [])

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
                visit_of(raw, 'altmount-addon', 'cold').update(ok=False, note='HTTP 503')
                visit_of(raw, 'kaijuflow', 'cold').update(start_s=4.0)
            edit(run, 'raw.json', bad)
            code, out = run_check(run)
        self.assertEqual(code, 0)  # a failed play alone does not stop a baseline; only misses, an absent side or a null run do
        self.assertIn("- AltMount's own addon, cold 1, Alpha: HTTP 503", out)
        self.assertIn('KaijuFlow, cold 1, Alpha (', out)

    def test_side_without_import_time_is_named(self):
        with tempdir() as tmp:
            run = copy_run(tmp)

            def strip(raw):
                for v in raw['visits']:
                    if v['side'] == 'altmount-addon':
                        v['imports'] = []
            edit(run, 'raw.json', strip)
            _, out = run_check(run)
        self.assertIn("Sides with no import time: AltMount's own addon.", out)

    def test_store_writes_check_file(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            _, out = run_check(run, store=True)
            with open(os.path.join(run, runcheck.CHECK_FILE)) as f:
                self.assertEqual(f.read(), out)


BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-2026-11-13')


def target_lines(out):
    return [x for x in out.splitlines() if x.startswith('Target: ')]


class TargetTests(unittest.TestCase):
    """The six targets of targets.json. fixtures/run-2026-11-13 is the real 2026-11-13 baseline run (meta.json and raw.json,
    every visit cut down to the fields the targets read); the expected figures were worked out by hand for the published page."""

    def test_baseline_prints_six_target_lines_and_only_the_warm_list_is_met(self):
        code, out = run_check(BASELINE)
        self.assertEqual(code, 0, out)  # the targets do not decide whether a run can serve as a baseline
        self.assertEqual(target_lines(out), [
            'Target: Top pick plays on 10 of 10 titles, cold and warm. '
            'Measured: cold 10 of 10 and 9 of 10, warm 10 of 10 and 10 of 10. Not met.',
            'Target: Cold start no slower than Usenet Ultimate. Measured: KaijuFlow 6.73 s, Usenet Ultimate 5.51 s. '
            "Not met (1.22 s slower), inside the noise: KaijuFlow's two cold rounds differ by 1.86 s (8.59 and 6.73 s), "
            'more than the 1.22 s the target is missed by.',
            'Target: Warm list no slower than 4.7 s. Measured: KaijuFlow 3.46 s. Met.',
            'Target: Top pick plays at least as often as AltMount direct, and more often unless both play every time. '
            "Measured: KaijuFlow 39 of 40, AltMount's own addon 40 of 40. Not met.",
            "Target: Warm start within 0.05 s of AltMount direct. Measured: KaijuFlow 0.18 s, AltMount's own addon 0.07 s. "
            'Not met (0.11 s slower).',
            "Target: Cold start within 1 s of AltMount direct. Measured: KaijuFlow 6.73 s, AltMount's own addon 3.70 s. "
            'Not met (3.03 s slower).'])

    def test_a_target_whose_side_is_not_in_the_run_is_not_measured(self):
        code, out = run_check(FIXTURE)  # KaijuFlow and the addon only, one cold and one warm round of two titles
        self.assertEqual(code, 0, out)
        lines = target_lines(out)
        self.assertEqual(len(lines), 6, out)
        self.assertEqual(lines[0], 'Target: Top pick plays on 10 of 10 titles, cold and warm. '
                                   'Measured: cold 2 of 2, warm 2 of 2. Not met.')
        self.assertEqual(lines[1], 'Target: Cold start no slower than Usenet Ultimate. '
                                   'Measured: KaijuFlow 1.00 s, Usenet Ultimate no figure. Not measured.')
        self.assertEqual(lines[3], 'Target: Top pick plays at least as often as AltMount direct, and more often unless both '
                                   "play every time. Measured: KaijuFlow 4 of 4, AltMount's own addon 4 of 4. Met.")  # a tie at 4 of 4

    def test_a_run_with_no_visits_of_a_side_has_no_plays_figure(self):
        with tempdir() as tmp:
            run = copy_run(tmp)
            edit(run, 'raw.json', lambda raw: raw.update(visits=[v for v in raw['visits'] if v['side'] == 'kaijuflow']))
            _, out = run_check(run)
        self.assertEqual(target_lines(out)[3], 'Target: Top pick plays at least as often as AltMount direct, and more often '
                                               'unless both play every time. '
                                               "Measured: KaijuFlow 4 of 4, AltMount's own addon no figure. Not measured.")


FULL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-2026-11-13-imports')


class FirstTryTests(unittest.TestCase):
    """First-try plays and like for like in the check (#143). fixtures/run-2026-11-13-imports is the same baseline run with
    each visit's first try and imports, as raw.json kept them; it was run before like for like. Figures worked out by hand."""

    def test_the_targets_are_judged_on_like_for_like_titles_only(self):
        code, out = run_check(FULL)
        self.assertEqual(code, 0, out)  # the targets do not decide whether a run can serve as a baseline
        # From before like for like: against Usenet Ultimate only Breaking Bad S01E01 is left (the same 7.0 GB 4K file;
        # KaijuFlow 0.80 and 0.82 s, Usenet Ultimate 1.47 and 0.70 s), against AltMount direct no title.
        self.assertEqual(target_lines(out), [
            'Target: Top pick plays on 10 of 10 titles, cold and warm. '
            'Measured: cold 10 of 10 and 9 of 10, warm 10 of 10 and 10 of 10. Not met.',
            'Target: Cold start no slower than Usenet Ultimate. Measured: KaijuFlow 0.81 s, Usenet Ultimate 1.08 s '
            '(9 titles left out: not like for like). Met.',
            'Target: Warm list no slower than 4.7 s. Measured: KaijuFlow 3.46 s. Met.',
            'Target: Top pick plays at least as often as AltMount direct, and more often unless both play every time. '
            "Measured: KaijuFlow no figure, AltMount's own addon no figure (10 titles left out: not like for like). Not measured.",
            "Target: Warm start within 0.05 s of AltMount direct. Measured: KaijuFlow no figure, AltMount's own addon no figure "
            '(10 titles left out: not like for like). Not measured.',
            "Target: Cold start within 1 s of AltMount direct. Measured: KaijuFlow no figure, AltMount's own addon no figure "
            '(10 titles left out: not like for like). Not measured.'])

    def test_the_check_counts_first_try_plays_and_lists_the_fallbacks_apart(self):
        _, out = run_check(FULL)
        lines = out.splitlines()
        self.assertIn("Top picks played, AltMount's own addon: cold 18 of 20, warm 18 of 20.", lines)
        start = lines.index('Played after a fallback (4), not counted as played:')
        self.assertEqual(lines[start + 1:start + 5], [
            "- AltMount's own addon, cold 1, Chernobyl S01E02: played after 3 fallbacks",
            "- AltMount's own addon, warm 1, Chernobyl S01E02: played after 3 fallbacks",
            "- AltMount's own addon, cold 2, Chernobyl S01E02: played after 3 fallbacks",
            "- AltMount's own addon, warm 2, Chernobyl S01E02: played after 3 fallbacks"])

    def test_the_check_names_the_titles_that_are_not_like_for_like(self):
        _, out = run_check(FULL)  # from before like for like: AltMount direct picked 1080p, KaijuFlow 4K over the caps
        lines = out.splitlines()
        start = lines.index('Not like for like with KaijuFlow, so left out of the targets against that setup:')
        self.assertEqual(lines[start + 1], "- Usenet Ultimate, Inception: KaijuFlow's top pick breaks the like-for-like rules "
                                           '(Cold 1): 85.4 GB served, over the cap for a film (32.2 GB).')
        self.assertIn("- AltMount's own addon, Dune: KaijuFlow's top pick is 2160p, AltMount's own addon's is 1080p (Cold 1).",
                      lines)
        self.assertFalse([x for x in lines if x.startswith('- KaijuFlow, one page per indexer, Dune')])

    def test_a_like_for_like_run_says_so_in_one_line(self):
        _, out = run_check(FIXTURE)
        self.assertIn("Every title's top picks are like for like: the same resolution, inside the size caps, no disc images.",
                      out.splitlines())



TEST_1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-2026-11-15-test1')


class Test1Tests(unittest.TestCase):
    """Test 1 (#154). fixtures/run-2026-11-15-test1 is the real 2026-11-15T115540Z-baseline run: raw.json as the run kept
    it, meta.json cut down to the fields the check reads. AltMount direct played "1080p UHD" releases (1080p encodes from
    4K discs) where KaijuFlow played 4K; the check read them as 4K. Expected lines worked out by hand from raw.json."""

    def test_the_check_names_altmount_directs_1080p_titles_as_not_like_for_like(self):
        _, out = run_check(TEST_1)
        lines = out.splitlines()
        start = lines.index('Not like for like with KaijuFlow, so left out of the targets against that setup:')
        self.assertEqual(lines[start + 1:start + 8], [
            f"- AltMount's own addon, {t}: KaijuFlow's top pick is 2160p, AltMount's own addon's is 1080p (Cold 1)."
            for t in ('Inception', 'Interstellar', 'Oppenheimer', 'Dune', 'The Dark Knight', 'Pulp Fiction', 'Chernobyl S01E02')])
        self.assertTrue(lines[start + 8].startswith('Top picks per title, '), lines[start + 8])  # The Matrix: 1080p on every side

    def test_an_untagged_run_is_judged_on_the_six_targets_as_before_with_no_outcome_and_no_final_bar(self):
        _, out = run_check(TEST_1)  # the lines as the check gave them before #169
        self.assertEqual(target_lines(out), [
            'Target: Top pick plays on 10 of 10 titles, cold and warm. '
            'Measured: cold 10 of 10 and 10 of 10, warm 10 of 10 and 10 of 10. Met.',
            'Target: Cold start no slower than Usenet Ultimate. Measured: KaijuFlow 3.29 s, Usenet Ultimate 3.46 s. Met.',
            'Target: Warm list no slower than 4.7 s. Measured: KaijuFlow 0.20 s. Met.',
            'Target: Top pick plays at least as often as AltMount direct, and more often unless both play every time. '
            "Measured: KaijuFlow 12 of 12, AltMount's own addon 12 of 12 (7 titles left out: not like for like). Met.",
            "Target: Warm start within 0.05 s of AltMount direct. Measured: KaijuFlow 0.02 s, AltMount's own addon 0.00 s "
            '(7 titles left out: not like for like). Met.',
            "Target: Cold start within 1 s of AltMount direct. Measured: KaijuFlow 3.00 s, AltMount's own addon 3.06 s "
            "(7 titles left out: not like for like). Met, inside the noise: KaijuFlow's two cold rounds differ by 1.72 s "
            '(3.86 and 2.14 s), more than the 1.06 s the target is met by.'])
        self.assertFalse([x for x in out.splitlines() if x.startswith(('Outcome', 'Final bar'))], out)


    def test_the_check_prints_each_titles_top_picks_with_the_resolution_read_and_the_size(self):
        _, out = run_check(TEST_1)
        lines = out.splitlines()
        start = lines.index('Top picks per title, Cold 1: the resolution the like-for-like check reads, and the size '
                            'served (else listed).')
        self.assertEqual(lines[start + 1:start + 3], [
            "| Title | KaijuFlow | Usenet Ultimate | AltMount's own addon |", '|---|---|---|---|'])
        rows = {x.split(' | ')[0][2:]: x for x in lines[start + 3:start + 13]}
        self.assertEqual(len(rows), 10, lines[start:start + 13])
        self.assertEqual(rows['Inception'], '| Inception | 2160p, 26.6 GB | 2160p, 26.6 GB | 1080p, 18.6 GB |')
        self.assertEqual(rows['The Matrix'], '| The Matrix | 1080p, 23.8 GB | 1080p, 23.8 GB | 1080p, 18.5 GB |')
        # AltMount direct's top pick did not play (HTTP 503), so its size is the one its list states
        self.assertEqual(rows['Chernobyl S01E02'], '| Chernobyl S01E02 | 2160p, 8.1 GB | 2160p, 8.1 GB | 1080p, 4.24 GB listed |')


if __name__ == '__main__':
    unittest.main()
