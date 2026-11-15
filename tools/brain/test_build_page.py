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
from test_brainreport import TAGGED_TITLES, tagged_visit
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

    def test_the_report_has_kaijuflow_before_and_after_in_a_table(self):
        report = bp.build_report([self.earlier, self.later])
        changed = section(report, 'got faster since')
        self.assertIn('<h2>One of the four times got faster since the baseline run</h2>', changed)
        self.assertIn('<li>Health-check connections: 12 -&gt; 20 (kaijuflow).</li>', changed)
        rows = [text(r) for r in re.findall(r'<tr><th scope="row">.*?</tr>', changed)]
        self.assertEqual(rows, ['Cold start 7.73 s 6.73 s 1.00 s faster (13%)', 'Warm start 0.18 s 0.18 s No change',
                                'Cold list 9.73 s 9.73 s No change', 'Warm list 3.46 s 3.46 s No change',
                                'Top pick plays 39 of 40 39 of 40 No change'])


class Refusals(unittest.TestCase):
    def test_a_newest_run_that_did_not_finish_is_refused_with_the_reason(self):
        folder = copy_run(tempdir(self), status='stopped')
        with self.assertRaises(SystemExit) as e:
            bp.build([folder])
        self.assertIn('the run was stopped before its last play', str(e.exception))

    def test_a_short_run_folder_is_refused_with_one_sentence_saying_why(self):
        folder = copy_run(tempdir(self), short='KaijuFlow, 1 round, 2 titles')
        with self.assertRaises(SystemExit) as stop:
            bp.build([folder])
        self.assertEqual(str(stop.exception), f'{folder}: a short run (KaijuFlow, 1 round, 2 titles) is not a baseline, so the page does not show it.')

    def test_an_archived_run_is_refused_even_beside_a_newer_run(self):
        root = tempdir(self)
        old = copy_run(os.path.join(root, br.ARCHIVE))
        new = copy_run(root, '2026-11-20T000000Z-baseline')
        with self.assertRaises(SystemExit) as stop:
            bp.build([new, old])
        self.assertEqual(str(stop.exception), f'{old}: the run is archived (not like for like), so the page does not show it.')
        self.assertIn('No earlier run on this page to compare with.', bp.build([new]))

    def test_a_run_marked_never_compared_with_builds_alone_under_its_label(self):
        folder = copy_run(tempdir(self), label='Test 1', never_compared=True)
        for page in (bp.build([folder]), bp.build_report([folder])):
            self.assertIn('Test 1 run, 13 November 2026.', text(page))
            self.assertNotIn('Baseline run', text(page))

    def test_a_run_marked_never_compared_with_is_not_what_a_newer_run_is_compared_with(self):
        root = tempdir(self)
        marked = copy_run(root, label='Test 1', never_compared=True)
        new = copy_run(root, '2026-11-20T000000Z-baseline')
        index = bp.build([marked, new])
        self.assertIn('No earlier run on this page to compare with.', index)
        rows = [text(r) for r in re.findall(r'<tr class="[^"]*"><th scope="row">.*?</tr>', section(index, 'Every run so far'))]
        self.assertTrue(rows[1].startswith('Test 1 run 2026-11-13'), rows)

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
    def build(self, words, build=bp.build):
        folder = copy_run(tempdir(self))
        with open(os.path.join(folder, bp.FINDINGS_FILE), 'w') as f:
            f.write(words)
        return build([folder])

    def test_the_report_has_the_findings_and_the_next_step_too(self):
        report = self.build(FINDINGS, bp.build_report)
        found = section(report, 'What the run found')
        self.assertEqual(re.findall(r'<li><h3>(.*?)</h3>', found), ['Game of Thrones is the slow title.', 'Inception is hit-and-miss.'])
        nxt = section(report, 'Next: tuning run 1')
        self.assertIn('<p>Health-check connections raised from 12 to 20.</p>', nxt)

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


class Report(unittest.TestCase):
    """The one-page Letter report (#133): the same run, numbers and verdicts as the page, on one sheet."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as root:
            folders = [copy_run(root), make_record(root)]
            cls.index, cls.report = bp.build(folders), bp.build_report(folders)

    def verdicts(self, page):
        """[(result, target)] of a page's target rows, in order."""
        return [(text(st), text(tt)) for st, tt in
                re.findall(r'<li class="sl-trow"><span class="sl-ts">(.*?)</span><span class="sl-tt">(.*?)</span>', page)]

    def test_the_report_and_the_page_show_the_same_verdicts(self):
        with open(os.path.join(BASELINE, 'raw.json')) as f:
            results = br.target_results(json.load(f)['visits'])
        expected = [(verdict['result'].capitalize(), target) for target, _, verdict in results]
        self.assertEqual(self.verdicts(self.report), expected)
        self.assertEqual(self.verdicts(self.report), self.verdicts(self.index))
        self.assertIn('<h1>1 of 6 targets met</h1>', self.report)

    def test_the_headline_numbers_are_the_pages(self):
        heads = re.search(r'<ul class="sl-heads">.*?</ul>', self.report).group(0)
        self.assertEqual(heads, re.search(r'<ul class="sl-heads">.*?</ul>', self.index).group(0))
        self.assertIn('Cold start 6.73 s Warm start 0.18 s Warm list 3.46 s Top pick plays 39 of 40', text(heads))

    def test_the_cold_start_and_warm_list_rulers_carry_every_setup_and_their_limits(self):
        cold, warm = re.findall(r'<figure class="sl-fig".*?</figure>', self.report)
        self.assertEqual(lanes(cold), [('AltMount direct', '3.70 s'), ('Usenet Ultimate', '5.51 s'),
                                       ('KaijuFlow, one page', '5.53 s'), ('KaijuFlow', '6.73 s')])
        self.assertEqual([text(f) for f in re.findall(r'<p class="sl-flag.*?</p>', cold)],
                         ['Limit 5.51 s: Usenet Ultimate Not met, 1.22 s over',
                          'Limit 4.70 s: AltMount direct + 1 s Not met, 2.03 s over'])
        self.assertEqual(lanes(warm), [('AltMount direct', '0.79 s'), ('KaijuFlow, one page', '3.16 s'),
                                       ('KaijuFlow', '3.46 s'), ('Usenet Ultimate', '4.08 s')])
        self.assertEqual([text(f) for f in re.findall(r'<p class="sl-flag.*?</p>', warm)], ['Limit 4.70 s Met, 1.24 s to spare'])

    def test_the_setups_are_named_in_the_pages_words(self):
        words = text(self.report)
        self.assertIn('AltMount direct', words)
        for avoid in ("AltMount's own addon", 'addon', 'altmount-addon', 'kaijuflow-1page'):
            self.assertNotIn(avoid, words)

    def test_without_an_earlier_run_it_says_what_meta_json_says_changed(self):
        self.assertIn('<li>No earlier run to compare with: this is the first one.</li>', self.report)

    def test_the_footer_says_what_start_and_list_mean_and_that_it_is_one_page(self):
        foot = text(re.search(r'<footer.*?</footer>', self.report).group(0))
        self.assertIn('Start: seconds from pressing play on the top pick until the first bytes of video arrive.', foot)
        self.assertIn('List: seconds from asking for a title until the list of Sources arrives.', foot)
        self.assertIn('Medians over 10 titles and both rounds of each kind.', foot)
        self.assertIn('Page 1 of 1', foot)
        self.assertIn('Inside the noise: KaijuFlow\'s own two rounds differ by more than the target is met or missed by.', foot)

    def test_a_target_inside_the_noise_says_so_with_both_rounds(self):
        row = target_row(self.report, 'Cold start no slower than Usenet Ultimate')
        self.assertEqual(row, 'Not met Cold start no slower than Usenet Ultimate KaijuFlow 6.73 s Limit 5.51 s 1.22 s over '
                              'Inside the noise (8.59 and 6.73 s)')

    def test_it_is_one_letter_sheet(self):
        self.assertRegex(self.report, r'@page \{ size: letter; margin: 0 \}')
        sheet = re.search(r'\.sl\.sl-rep \{([^}]*)\}', self.report).group(1)
        for rule in ('width: 816px', 'height: 1056px', 'overflow: hidden', 'box-sizing: border-box'):
            self.assertIn(rule, sheet)
        self.assertNotIn('@media (max-width: 860px)', self.report)   # the page's phone layout would fire at 816 px


class Command(unittest.TestCase):
    def test_writes_the_page_and_the_report_into_the_output_folder(self):
        root = tempdir(self)
        out = os.path.join(root, 'page')
        with contextlib.redirect_stdout(io.StringIO()) as said:
            bp.main([copy_run(root), make_record(root), '--out', out])
        self.assertEqual(sorted(os.listdir(out)), ['index.html', 'report.html'])
        for name in ('index.html', 'report.html'):
            with open(os.path.join(out, name)) as f:
                self.assertIn('<h1>1 of 6 targets met</h1>', f.read())
            self.assertIn(name, said.getvalue())


SPEED_SIDES = ('kaijuflow', 'uu', 'altmount-addon')
FAILED = {('kaijuflow', 'cold', 1, 'Old Film'), ('altmount-addon', 'cold', 2, 'Matrix'), ('uu', 'cold', 1, 'Old Film'),
          ('uu', 'cold', 2, 'Old Film')}
FALLBACK = ('altmount-addon', 'cold', 1, 'Rare Show S01E01')  # video only after its top pick's own import failed


def speed_test_run(root, folder_name='2026-11-16T100000Z-speed', **meta):
    """A finished speed test (a run on the tagged title list) as a run folder under root: KaijuFlow, Usenet Ultimate and
    AltMount direct, four rounds of Matrix and Dune (easy) and Old Film and Rare Show S01E01 (hard).

    Every top pick plays with list 2.0 s and start 1.5 s (3.5 s title to video), except: KaijuFlow lists in 1.0 s on the
    easy list (2.5 s) and plays warm in 0.4 + 0.2 s (0.6 s); AltMount direct lists in 0.5 s (2.0 s); the plays in FAILED
    give no video and FALLBACK plays after a fallback. So the easy list has KaijuFlow 0 fails, Usenet Ultimate 0, AltMount
    direct 1 (Matrix, Cold 2); the hard list KaijuFlow 1 (Old Film, Cold 1), Usenet Ultimate 2 (Old Film, both cold
    rounds), AltMount direct 1 (Rare Show S01E01, Cold 1, after a fallback). Worked out by hand: 5 of 6 targets met (the
    hard list's cold title to video is not: KaijuFlow 3.50 s, AltMount direct 2.00 s with as few fails), the outcome is
    "try KaijuFlow without its own pre-list check", and the final bar is met on the easy list and not on the hard one."""
    visits = [tagged_visit(side, phase, rnd, t[2]) for phase, rnd in br.RUN_ORDER for t in TAGGED_TITLES for side in SPEED_SIDES]
    for v in visits:
        key = (v['side'], v['phase'], v['round'], v['title'])
        if v['side'] == 'kaijuflow' and v['list'] == 'easy':
            v['list_s'] = 1.0
        if v['side'] == 'kaijuflow' and v['phase'] == 'warm':
            v.update(list_s=0.4, start_s=0.2)
        if v['side'] == 'altmount-addon':
            v['list_s'] = 0.5
        if key in FAILED:
            v.update(ok=False, start_s=None, note='failure video', tries=[{'plays': False, 'size': None, 'title': v['title']}])
        if key == FALLBACK:
            v['imports'] = [{'name': 'Rare Show S01E01.2160p.WEB-DL-GRP', 'ok': False}, {'name': 'Rare.Show.S01E01.720p-OTHER', 'ok': True}]
    folder = os.path.join(root, folder_name)
    os.makedirs(folder)
    m = dict(name='speed', label='Test 2', status='ok', started='2026-11-16T10:00:00Z', finished='2026-11-16T11:00:00Z',
             titles=[t[2] for t in TAGGED_TITLES], lists={t[2]: t[3] for t in TAGGED_TITLES}, sides=list(SPEED_SIDES),
             rounds=2, short=None, changes=['First speed test.'])
    m.update(meta)
    with open(os.path.join(folder, 'meta.json'), 'w') as f:
        json.dump(m, f)
    with open(os.path.join(folder, 'raw.json'), 'w') as f:
        json.dump({'status': 'ok', 'visits': visits}, f)
    return folder


class SpeedTest(unittest.TestCase):
    """#171: a speed test (a tagged run) on the page and the one-page report: both lists, fails first, then title to video."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as root:
            folder = speed_test_run(root)
            cls.index, cls.report = bp.build([folder]), bp.build_report([folder])

    def test_the_verdict_counts_the_three_targets_on_each_list(self):
        for page in (self.index, self.report):
            self.assertIn('<h1>5 of 6 targets met</h1>', page)
            groups = re.findall(r'<h3 class="sl-list">(.*?)</h3><ul>(.*?)</ul>', page)
            self.assertEqual([g for g, _ in groups], ['Easy list', 'Hard list'])
            easy, hard = ([text(r) for r in re.findall(r'<li class="sl-trow">.*?</li>', rows)] for _, rows in groups)
            self.assertEqual([re.match('Not met|Met', r).group(0) for r in easy], ['Met', 'Met', 'Met'])
            self.assertEqual([re.match('Not met|Met', r).group(0) for r in hard], ['Met', 'Not met', 'Met'])
            self.assertTrue(easy[0].startswith('Met KaijuFlow fails no more titles than any other setup, and none on the easy '
                                               'list KaijuFlow 0 fails Limit 0 fails'), easy[0])
            self.assertTrue(hard[0].startswith('Met KaijuFlow fails no more titles than any other setup, and none on the easy '
                                               'list KaijuFlow 1 fail Limit 1 fail'), hard[0])
            self.assertTrue(hard[1].startswith("Not met KaijuFlow's median cold title to video is no slower than any setup "
                                               'with as many fails or more KaijuFlow 3.50 s Limit 2.00 s 1.50 s over'), hard[1])
            self.assertTrue(easy[2].startswith('Met Warm title to video under about 1 s KaijuFlow 0.60 s Limit 1.00 s '
                                               '0.40 s to spare'), easy[2])

    def test_the_lead_under_the_verdict_is_the_outcome_line(self):
        for page in (self.index, self.report):
            lead = text(re.search(r'<p class="sl-lead">.*?</p>', page).group(0))
            self.assertEqual(lead, 'Outcome on the hard list: KaijuFlow and AltMount direct fail the same number of titles '
                                   '(1 of 8 each) and AltMount direct is faster (cold title to video 2.00 s against 3.50 s), '
                                   'so try KaijuFlow without its own pre-list check, behind AltMount.')

    def test_the_final_bar_is_shown_apart_from_the_targets_and_not_counted_in_them(self):
        for page in (self.index, self.report):
            self.assertLess(page.rindex('<li class="sl-trow">'), page.index('<div class="sl-final">'))
            self.assertEqual(len(re.findall(r'<li class="sl-trow">', page)), 6)
            bar = text(re.search(r'<div class="sl-final">.*?</div>', page).group(0))
            self.assertEqual(bar, 'Final bar Not met On both lists, KaijuFlow has the fewest fails, and the fastest title to '
                                  'video among setups with as few fails. Easy list: met, KaijuFlow fails 0 of 8, the fewest, '
                                  'in 2.50 s cold title to video, the fastest among setups with as few fails. Hard list: not '
                                  "met, AltMount direct fails as few titles (1 of 8 against KaijuFlow's 1 of 8). "
                                  'Shown apart from the targets and not counted in them.')
            self.assertLess(page.index('<div class="sl-targets">'), page.index('<div class="sl-final">'))

    def test_the_first_rulers_are_cold_title_to_video_on_each_list_fewest_fails_first(self):
        for page in (self.index, self.report):
            easy, hard = re.findall(r'<figure class="sl-fig".*?</figure>', page)[:2]
            self.assertTrue(text(easy).startswith('Easy list: cold title to video.'), text(easy))
            self.assertTrue(text(hard).startswith('Hard list: cold title to video.'), text(hard))
            self.assertEqual(lanes(easy), [('KaijuFlow', '2.50 s'), ('Usenet Ultimate', '3.50 s'), ('AltMount direct', '2.00 s')])
            self.assertEqual(lanes(hard), [('AltMount direct', '2.00 s'), ('KaijuFlow', '3.50 s'), ('Usenet Ultimate', '3.50 s')])
            self.assertIn('<b>2.00 s</b><small>1 fail</small>', easy)
            self.assertIn('<b>3.50 s</b><small>2 fails</small>', hard)
            self.assertIn('Title asked for', easy)
        self.assertNotIn('Cold start.', text(self.index))

    def test_the_headline_numbers_are_kaijuflows_fails_then_its_title_to_video_on_each_list(self):
        for page in (self.index, self.report):
            heads = text(re.search(r'<ul class="sl-heads">.*?</ul>', page).group(0))
            self.assertEqual(heads, 'Fails, easy list 0 of 8 Fails, hard list 1 of 8 Title to video, easy list 2.50 s '
                                    'Title to video, hard list 3.50 s KaijuFlow in this run: its fails in all four rounds, '
                                    'and its median cold title to video.')


class SpeedTestAgainstEarlierRuns(unittest.TestCase):
    def test_a_speed_test_is_never_compared_with_a_run_without_tags_and_both_are_in_every_run_so_far(self):
        root = tempdir(self)
        index = bp.build([copy_run(root), speed_test_run(root)])
        self.assertIn('No earlier run on this page to compare with.', index)
        rows = [text(r) for r in re.findall(r'<tr class="[^"]*"><th scope="row">.*?</tr>', section(index, 'Every run so far'))]
        self.assertTrue(rows[0].startswith('Test 2 run 2026-11-16 First speed test. 5 of 6'), rows)
        self.assertTrue(rows[1].startswith('Baseline run 2026-11-13'), rows)

    def test_a_speed_test_is_compared_with_the_speed_test_before_it_fails_and_title_to_video_on_each_list(self):
        root = tempdir(self)
        earlier = speed_test_run(root, label='Test 1b')

        def all_play(visits):  # the later run: KaijuFlow plays Old Film too, and Usenet Ultimate is as before
            for v in visits:
                if (v['side'], v['title']) == ('kaijuflow', 'Old Film'):
                    v.update(ok=True, start_s=1.5, note=None)
        later = speed_test_run(root, '2026-11-20T100000Z-speed', finished='2026-11-20T11:00:00Z')
        path = os.path.join(later, 'raw.json')
        with open(path) as f:
            raw = json.load(f)
        all_play(raw['visits'])
        with open(path, 'w') as f:
            json.dump(raw, f)
        index = bp.build([earlier, later])
        self.assertIn('Compared with the Test 1b run of 16 November 2026.', index)
        heads = text(re.search(r'<ul class="sl-heads">.*?</ul>', index).group(0))
        self.assertTrue(heads.startswith('Fails, easy list 0 of 8 No change Fails, hard list 0 of 8 1 fewer '
                                         'Title to video, easy list 2.50 s No change Title to video, hard list 3.50 s No change'), heads)


REAL = os.path.expanduser('~/kaijuflow-notes/brain-runs/2026-11-15T115540Z-baseline/')  # Test 1 (#127, #150); 3.46 s since #154 reads The Matrix as 1080p on both sides


@unittest.skipUnless(os.path.exists(REAL + 'raw.json'), 'the real run folder is not on this machine')
class RealBaseline(unittest.TestCase):
    def test_the_real_run_folder_gives_the_same_verdict_as_its_fixture(self):
        index = bp.build([REAL])
        self.assertIn('<h1>6 of 6 targets met</h1>', index)
        self.assertIn('Limit 3.46 s: Usenet Ultimate', index)
        report = bp.build_report([REAL])
        self.assertIn('<h1>6 of 6 targets met</h1>', report)
        self.assertIn('Limit 3.46 s: Usenet Ultimate', report)


if __name__ == '__main__':
    unittest.main()
