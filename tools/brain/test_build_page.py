"""Tests for build_page.py: the Speed Check page built from run folders. No Docker, no network.

fixtures/run-2026-11-13 is the real 2026-11-13 baseline run (meta.json and raw.json, every visit cut down to the fields
the targets read). Its figures were worked out by hand for the published page (test_runcheck.TargetTests).

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import html
import io
import json
import os
import re
import shutil
import tempfile
import unittest

import brainreport as br
import build_page as bp
from test_settings import tempdir

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-2026-11-13')
FOLDER = '2026-11-13T053200Z-baseline'


def copy_run(root, folder_name=FOLDER, edit_visits=None, **meta):
    """The 2026-11-13 baseline as a run folder named folder_name under root, its visits changed by edit_visits(visits)
    and its meta.json fields by meta."""
    folder = os.path.join(root, folder_name)
    shutil.copytree(BASELINE, folder)
    if edit_visits:
        path = os.path.join(folder, 'raw.json')
        with open(path) as f:
            raw = json.load(f)
        edit_visits(raw['visits'])
        with open(path, 'w') as f:
            json.dump(raw, f)
    if meta:
        path = os.path.join(folder, 'meta.json')
        with open(path) as f:
            m = json.load(f)
        m.update(meta)
        with open(path, 'w') as f:
            json.dump(m, f)
    return folder


def make_record(root, name='2026-11-13T035846Z-baseline-record'):
    folder = os.path.join(root, name)
    os.makedirs(folder)
    with open(os.path.join(folder, 'meta.json'), 'w') as f:
        json.dump({'name': 'baseline', 'mode': 'record', 'started': '2026-11-13T03:58:46.000Z'}, f)
    return folder


def text(page):
    """The page's words without tags, spaces folded."""
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', page))).strip()


def section(index, heading):
    """The <section> holding the given heading text."""
    for s in re.findall(r'<section.*?</section>', index, re.S):
        if heading in s:
            return s
    raise AssertionError(f'no section with {heading!r}')


def target_row(index, target):
    [row] = [r for r in re.findall(r'<li class="sl-trow">.*?</li>', index) if target in r]
    return text(row)


def lanes(fig_html):
    """[(lane name, time)] of a ruler, in the order drawn."""
    return re.findall(r'<span class="sl-name">([^<]*)</span><span class="sl-track">(?:<span class="sl-bar"[^>]*></span>'
                      r'<span class="sl-val"[^>]*><b>([^<]*)</b>)?', fig_html)


class Baseline(unittest.TestCase):
    """The page of the 2026-11-13 baseline: every number from its run folder, every verdict from target_results."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as root:
            cls.index = bp.build([copy_run(root), make_record(root)])

    def test_the_verdict_counts_the_targets_target_results_meets(self):
        self.assertIn('<h1>1 of 6 targets met</h1>', self.index)
        self.assertIn('<h2>One target met, five still open</h2>', self.index)

    def test_every_target_row_shows_the_verdict_and_figures_of_target_results(self):
        with open(os.path.join(BASELINE, 'raw.json')) as f:
            results = br.target_results(json.load(f)['visits'])
        rows = [text(r) for r in re.findall(r'<li class="sl-trow">.*?</li>', self.index)]
        self.assertEqual(len(rows), len(results))
        for row, (target, _, verdict) in zip(rows, results):
            self.assertTrue(row.startswith(verdict['result'].capitalize() + ' ' + target), row)
        # the figures, as worked out by hand for the published page
        self.assertEqual(rows[1], 'Not met Cold start no slower than Usenet Ultimate KaijuFlow 6.73 s Limit 5.51 s 1.22 s over '
                                  "Inside the noise: KaijuFlow's two cold rounds differ by 1.86 s (8.59 and 6.73 s), more than that. "
                                  '0 s 7 s')
        self.assertEqual(rows[2], 'Met Warm list no slower than 4.7 s KaijuFlow 3.46 s Limit 4.70 s 1.24 s to spare 0 s 5 s')
        self.assertIn('KaijuFlow 39 of 40 Limit 40 of 40 Less often', rows[3])
        self.assertIn('KaijuFlow 0.18 s Limit 0.12 s 0.06 s over', rows[4])
        self.assertIn('KaijuFlow 6.73 s Limit 4.70 s 2.03 s over', rows[5])
        self.assertIn('KaijuFlow 39 of 40 Limit 40 of 40 1 top pick did not play', rows[0])

    def test_headline_numbers_are_kaijuflows_medians(self):
        heads = text(re.search(r'<ul class="sl-heads">.*?</ul>', self.index).group(0))
        self.assertEqual(heads, 'Cold start 6.73 s Warm start 0.18 s Warm list 3.46 s Top pick plays 39 of 40 KaijuFlow in this run.')

    def test_the_cold_start_ruler_has_every_setup_fastest_first_and_both_cold_start_limits(self):
        hero = re.search(r'<div class="sl-plot sl-hero">.*?</ol>', self.index).group(0)
        self.assertEqual(lanes(hero), [('AltMount direct', '3.70 s'), ('Usenet Ultimate', '5.51 s'),
                                       ('KaijuFlow, one page', '5.53 s'), ('KaijuFlow', '6.73 s')])
        flags = [text(f) for f in re.findall(r'<p class="sl-flag.*?</p>', hero)]
        self.assertEqual(flags, ['Limit 5.51 s: Usenet Ultimate Not met, 1.22 s over',
                                 'Limit 4.70 s: AltMount direct + 1 s Not met, 2.03 s over'])
        # on a ruler of 0 to 7 s
        self.assertEqual(re.findall(r'class="sl-lim" style="[^"]*left:([\d.]+)%', hero), ['78.71', '67.14'])
        self.assertIn('<span class="sl-tick" style="left:100%">7 s</span>', self.index)

    def test_the_setups_are_named_in_the_pages_words(self):
        words = text(self.index)
        self.assertIn('AltMount direct', words)
        for avoid in ("AltMount's own addon", 'addon', 'altmount-addon', 'kaijuflow-1page'):
            self.assertNotIn(avoid, words)

    def test_the_four_setup_rulers_carry_the_limits_of_their_measure(self):
        four = section(self.index, 'Top pick plays</h3>')
        self.assertIn('<h2>KaijuFlow starts slower than Usenet Ultimate</h2>', four)
        caps = re.findall(r'<figcaption class="sl-cap"><b>([^<]*)</b>', four)
        self.assertEqual(caps, ['Start, cold', 'Start, warm', 'List, cold', 'List, warm'])
        flags = [text(f) for f in re.findall(r'<p class="sl-flag.*?</p>', four)]
        self.assertEqual(flags, ['Limit 5.51 s: Usenet Ultimate', 'Limit 4.70 s: AltMount direct + 1 s',
                                 'Limit 0.12 s: AltMount direct + 0.05 s', 'Limit 4.70 s'])
        self.assertIn('No target: AltMount direct checks nothing before it lists', four)
        self.assertIn('<span class="sl-num sl-pv">40 of 40</span><span class="sl-pn">AltMount direct</span>', four)

    def test_the_title_ruler_names_the_slow_title_and_marks_a_failed_round(self):
        titles = section(self.index, 'cold start for each title')
        self.assertIn('<h2>Game of Thrones S02E03 is far slower than the rest</h2>', titles)
        drawn = lanes(titles)
        self.assertEqual(drawn[-1], ('Game of Thrones S02E03', '50.48 s'))   # 44.19 and 56.78 s, rounded as brainreport does
        self.assertIn(('Inception', '21.94 s'), drawn)                         # the second cold round failed
        self.assertIn('<b>21.94 s</b><small>1 of 2 failed</small>', titles)
        # the table's columns: the setups in the page's order; the one-page side failed The Matrix in both cold rounds
        self.assertEqual(re.findall(r'<th scope="col" class="sl-r[^"]*"><span>([^<]*)</span>', titles),
                         ['KaijuFlow', 'Usenet Ultimate', 'AltMount direct', 'KaijuFlow, one page'])
        [matrix] = [text(r) for r in re.findall(r'<tr><th scope="row">The Matrix</th>.*?</tr>', titles)]
        self.assertTrue(matrix.startswith('The Matrix 11.43 '), matrix)
        self.assertTrue(matrix.endswith(' – did not play'), matrix)

    def test_without_an_earlier_run_the_page_shows_what_meta_json_says_changed(self):
        self.assertIn('No earlier run on this page to compare with.', self.index)
        self.assertIn('<li>No earlier run to compare with: this is the first one.</li>', self.index)
        self.assertNotIn('Every run so far', self.index)

    def test_without_findings_html_there_is_no_findings_section(self):
        self.assertNotIn('What the run found', self.index)


class TieAtTheMaximum(unittest.TestCase):
    def test_both_setups_playing_every_top_pick_is_met_on_the_page(self):
        def every_kaijuflow_pick_plays(visits):
            for v in visits:
                if v['side'] == 'kaijuflow':
                    v.update(ok=True, start_s=v['start_s'] or 5.0)
        index = bp.build([copy_run(tempdir(self), edit_visits=every_kaijuflow_pick_plays)])
        row = target_row(index, 'at least as often as AltMount direct')
        self.assertEqual(row, 'Met Top pick plays at least as often as AltMount direct, and more often unless both play every '
                              'time KaijuFlow 40 of 40 Limit 40 of 40 Both played every top pick')
        self.assertIn('<h1>3 of 6 targets met</h1>', index)


class AgainstAnEarlierRun(unittest.TestCase):
    def setUp(self):
        root = tempdir(self)

        def slower(visits):  # KaijuFlow's cold starts 1 s slower in the earlier run
            for v in visits:
                if v['side'] == 'kaijuflow' and v['phase'] == 'cold' and v['start_s'] is not None:
                    v['start_s'] = round(v['start_s'] + 1, 2)
        self.earlier = copy_run(root, edit_visits=slower)
        self.later = copy_run(root, '2026-11-16T050000Z-tuning-1', name='tuning-1', finished='2026-11-16T06:00:00.000Z',
                              changes=['Health-check connections: 12 -> 20 (kaijuflow).'])
        self.index = bp.build([self.earlier, self.later])

    def test_the_newest_run_is_judged_and_compared_with_the_one_before(self):
        self.assertIn('<b>Tuning 1 run, 16 November 2026.</b> Compared with the baseline run of 13 November 2026.', self.index)
        heads = text(re.search(r'<ul class="sl-heads">.*?</ul>', self.index).group(0))
        self.assertEqual(heads, 'Cold start 6.73 s 1.00 s faster (13%) Warm start 0.18 s No change Warm list 3.46 s No change '
                                'Top pick plays 39 of 40 No change KaijuFlow in this run, with the change since the run it is compared with.')
        self.assertIn('<b>As many as the baseline run.</b>', self.index)

    def test_what_changed_lists_the_runs_own_changes_and_pairs_kaijuflow_before_and_after(self):
        changed = section(self.index, 'got faster since')
        self.assertIn('<h2>One of the four times got faster since the baseline run</h2>', changed)   # the cold start; the rest are the same
        self.assertIn('<li>Health-check connections: 12 -&gt; 20 (kaijuflow).</li>', changed)
        self.assertEqual(lanes(changed)[:2], [('Before', '7.73 s'), ('This run', '6.73 s')])

    def test_every_run_so_far_lists_both_runs_newest_first(self):
        rows = [text(r) for r in re.findall(r'<tr class="[^"]*"><th scope="row">.*?</tr>', section(self.index, 'Every run so far'))]
        self.assertEqual(rows, ['Tuning 1 run 2026-11-16 Health-check connections: 12 -> 20 (kaijuflow). 1 of 6 6.73 s 0.18 s 39 of 40',
                                'Baseline run 2026-11-13 No earlier run to compare with: this is the first one. 1 of 6 7.73 s 0.18 s 39 of 40'])

    def test_a_stopped_run_is_never_the_one_compared_with(self):
        stopped = copy_run(tempdir(self), '2026-11-15T000000Z-stopped', name='stopped', status='stopped')
        index = bp.build([self.earlier, stopped, self.later])
        self.assertIn('Compared with the baseline run of 13 November 2026.', index)
        self.assertIn('<td class="sl-r">not judged</td>', section(index, 'Every run so far'))


class Refusals(unittest.TestCase):
    def test_a_newest_run_that_did_not_finish_is_refused_with_the_reason(self):
        folder = copy_run(tempdir(self), status='stopped')
        with self.assertRaises(SystemExit) as e:
            bp.build([folder])
        self.assertIn('the run was stopped before its last play', str(e.exception))

    def test_a_recording_folder_alone_is_not_enough(self):
        with self.assertRaises(SystemExit):
            bp.build([make_record(tempdir(self))])


FINDINGS = """<h3>Game of Thrones is the slow title.</h3>
<p>Its top pick is a 26.5 GB 4K release.</p>
<h3>Inception is hit-and-miss.</h3>
<p>It played in the first cold round only.</p>
<h2>Next: tuning run 1</h2>
<p>Health-check connections raised from 12 to 20.</p>
"""


class Findings(unittest.TestCase):
    def build(self, words):
        folder = copy_run(tempdir(self))
        with open(os.path.join(folder, bp.FINDINGS_FILE), 'w') as f:
            f.write(words)
        return bp.build([folder])

    def test_findings_html_gives_the_findings_and_the_next_step(self):
        index = self.build(FINDINGS)
        found = section(index, 'What the run found')
        self.assertEqual(re.findall(r'<li><h3>(.*?)</h3>', found), ['Game of Thrones is the slow title.', 'Inception is hit-and-miss.'])
        nxt = section(index, 'Next: tuning run 1')
        self.assertIn('<p>Health-check connections raised from 12 to 20.</p>', nxt)
        self.assertLess(index.index('What the run found'), index.index('Next: tuning run 1'))

    def test_words_before_the_first_finding_are_refused(self):
        with self.assertRaises(SystemExit) as e:
            self.build('<p>Stray words.</p>\n' + FINDINGS)
        self.assertIn(bp.FINDINGS_FILE, str(e.exception))


class PageRules(unittest.TestCase):
    """The artifact page contract and the design's table rules."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as root:
            cls.index = bp.build([copy_run(root)])

    def test_title_is_two_to_four_words(self):
        title = re.search(r'<title>(.*?)</title>', self.index).group(1)
        self.assertTrue(2 <= len(title.split()) <= 4, title)

    def test_dark_mode_in_both_forms_and_a_body_background(self):
        self.assertIn('@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .sl {', self.index)
        self.assertIn(':root[data-theme="dark"] .sl {', self.index)
        self.assertRegex(self.index, r'body \{[^}]*background:')

    def test_no_scripts_and_a_phone_gutter(self):
        self.assertNotIn('<script', self.index)
        self.assertIn('max(16px, env(safe-area-inset-left', self.index)

    def test_every_table_has_a_caption_and_its_own_scroll_box(self):
        tables = re.findall(r'(.{30})<table>(.{9})', self.index)
        self.assertTrue(tables)
        for before, after in tables:
            self.assertTrue(before.endswith('<div class="sl-scroll">'), before)
            self.assertEqual(after, '<caption>')
        self.assertNotRegex(self.index, r'<th[^>]*></th>')

    def test_the_page_is_balanced(self):
        for tag in ('section', 'div', 'ul', 'ol', 'li', 'table', 'tr', 'figure', 'p', 'span', 'dl'):
            self.assertEqual(len(re.findall(f'<{tag}[ >]', self.index)), self.index.count(f'</{tag}>'), tag)


class Command(unittest.TestCase):
    def test_writes_index_html_into_the_output_folder(self):
        root = tempdir(self)
        out = os.path.join(root, 'page')
        with contextlib.redirect_stdout(io.StringIO()) as said:
            bp.main([copy_run(root), make_record(root), '--out', out])
        self.assertEqual(os.listdir(out), ['index.html'])
        with open(os.path.join(out, 'index.html')) as f:
            self.assertIn('<h1>1 of 6 targets met</h1>', f.read())
        self.assertIn('index.html', said.getvalue())


REAL = os.path.expanduser('~/kaijuflow-notes/brain-runs/2026-11-13T053200Z-baseline/')


@unittest.skipUnless(os.path.exists(REAL + 'raw.json'), 'the real run folder is not on this machine')
class RealBaseline(unittest.TestCase):
    def test_the_real_run_folder_gives_the_same_verdict_as_its_fixture(self):
        index = bp.build([REAL])
        self.assertIn('<h1>1 of 6 targets met</h1>', index)
        self.assertIn('Limit 5.51 s: Usenet Ultimate', index)


if __name__ == '__main__':
    unittest.main()
