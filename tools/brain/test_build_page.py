"""Tests for build_page.py over a small fixture run folder. No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import re
import unittest

import build_page as bp
from test_settings import tempdir

TITLES = ['Alpha', 'Beta']


def visit(side, phase, rnd, title, start=1.5, plays=True, list_s=2.0, **extra):
    v = {'side': side, 'phase': phase, 'round': rnd, 'title': title, 'start_s': start if plays else None, 'list_s': list_s,
         'misses': [], 'steps': [], 'tries': [{'plays': plays, 'ready_s': start}]}
    v.update(extra)
    return v


def make_run(root, name='fixture-run', fail=('uu', 'Beta'), sides=('kaijuflow', 'uu')):
    folder = os.path.join(root, name)
    os.makedirs(folder)
    visits = []
    for side in sides:
        for phase, rnd in bp.ROUNDS:
            for t in TITLES:
                visits.append(visit(side, phase, rnd, t, start=1.0 if side == 'kaijuflow' else 2.0, plays=(side, t) != fail))
    json.dump({'status': 'ok', 'visits': visits}, open(os.path.join(folder, 'raw.json'), 'w'))
    json.dump({'name': name, 'finished': '2026-11-11T10:00:00.000Z', 'indexers': ['ninjacentral'], 'error': None}, open(os.path.join(folder, 'meta.json'), 'w'))
    return folder


def make_record(root, name='fixture-run'):
    folder = os.path.join(root, name + '-record')
    os.makedirs(folder)
    json.dump({'name': name, 'mode': 'record', 'started': '2026-11-11T09:00:00.000Z', 'finished': '2026-11-11T09:05:00.000Z'}, open(os.path.join(folder, 'meta.json'), 'w'))
    return folder


STORY = """<h2>Fixture findings</h2>
<p>Beta is the slow one on Usenet Ultimate.</p>
<div class="answer">
  __SUMMARY_TABLE__
  __ROUND_TABLE__
</div>
__DETAILS__
<p class="note">Written by hand.</p>
"""


def frozen_table(title):
    return f'<div class="scroll"><table class="grid"><tbody><tr><th scope="row">{title}</th></tr></tbody></table></div>'


def make_entry(archive, name, files):
    """One archived run in the archive folder: files maps a file name to its text (tables.json to a dict)."""
    entry = os.path.join(archive, name)
    os.makedirs(entry)
    for fname, content in files.items():
        with open(os.path.join(entry, fname), 'w') as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))
    return archive


def lost_run(archive):
    """An archive entry with every part: a section, blocks for below the word list, a footer line and the tables."""
    return make_entry(archive, '2026-11-01-lost', {
        'section.html': '<section>\n  <h2>Lost run, 2026-11-01</h2>\n  <div data-table="lost-start" class="slot">Loading the table...</div>\n</section>\n',
        'appendix.html': '<section>\n  <h2>Lost run, all numbers</h2>\n  <div data-table="lost-all" class="slot">Loading the table...</div>\n</section>\n',
        'footer.html': '  <div>The raw data of the lost run is gone.</div>\n',
        'tables.json': {'lost-start': frozen_table('Gamma'), 'lost-all': frozen_table('Delta')}})


class RunNumbers(unittest.TestCase):
    def test_medians_counts_and_failures(self):
        d = tempdir(self)
        run = bp.Run(make_run(d))
        self.assertEqual(run.titles, TITLES)
        self.assertEqual(run.plays('kaijuflow', 'cold', 1), (2, 2))
        self.assertEqual(run.plays('uu', 'cold', 1), (1, 2))
        self.assertEqual(run.start('uu', 'cold'), 2.0)
        self.assertEqual(run.listtime('kaijuflow', 'warm'), 2.0)
        self.assertEqual(run.failed_titles('uu'), ['Beta'])
        self.assertEqual(run.failed_titles('kaijuflow'), [])

    def test_not_recorded_visits_do_not_count_as_failures(self):
        d = tempdir(self)
        folder = make_run(d)
        raw = json.load(open(folder + '/raw.json'))
        raw['visits'][0].update(not_recorded=True, tries=[], start_s=None)
        json.dump(raw, open(folder + '/raw.json', 'w'))
        run = bp.Run(folder)
        self.assertEqual(run.failed_titles('kaijuflow'), [])
        self.assertEqual(run.plays('kaijuflow', 'cold', 1), (1, 1))


class BuildFixture(unittest.TestCase):
    def test_writes_small_index_and_tables_json_beside_it(self):
        d = tempdir(self)
        out = os.path.join(d, 'page')
        run, rec = make_run(d), make_record(d)
        index, tables = bp.write([rec, run], out, archive=None)
        self.assertEqual(sorted(os.listdir(out)), ['index.html', 'tables.json'])
        self.assertEqual(open(os.path.join(out, 'index.html')).read(), index)
        self.assertEqual(json.load(open(os.path.join(out, 'tables.json'))), tables)
        self.assertEqual(sorted(tables), ['fixture-run-list', 'fixture-run-start'])
        # per-title rows are in the data file, not in the page
        self.assertIn('<th scope="row">Alpha</th>', tables['fixture-run-start'])
        self.assertNotIn('<th scope="row">Alpha</th>', index)

    def test_a_short_run_folder_is_refused_with_one_sentence_saying_why(self):
        folder = make_run(tempdir(self))
        meta = json.load(open(folder + '/meta.json'))
        meta['short'] = 'KaijuFlow, 1 round, 2 titles'
        json.dump(meta, open(folder + '/meta.json', 'w'))
        with self.assertRaises(SystemExit) as stop:
            bp.build([folder], archive=None)
        self.assertEqual(str(stop.exception), f'{folder}: a short run (KaijuFlow, 1 round, 2 titles) is not a baseline, so the page does not show it.')

    def test_every_slot_has_a_table_and_the_page_loads_them_with_fetch(self):
        d = tempdir(self)
        index, tables = bp.build([make_run(d)], archive=None)
        slots = re.findall(r'data-table="([^"]+)"', index)
        self.assertEqual(sorted(slots), sorted(tables))
        self.assertIn("fetch('tables.json')", index)

    def test_failed_pick_and_round_numbers_show(self):
        d = tempdir(self)
        index, tables = bp.build([make_run(d)], archive=None)
        self.assertIn('Run fixture-run, 2026-11-11 (ninjacentral)', index)
        self.assertIn('the top pick did not play for Beta', index)
        self.assertIn('<td class="bad">1 of 2</td>', index)   # uu round table: Beta fails every round
        self.assertIn('<td class="bad">fails</td>', tables['fixture-run-start'])
        self.assertIn('<th scope="col">Cold 1</th>', tables['fixture-run-start'])

    def test_the_one_page_side_is_named_in_words_everywhere(self):
        d = tempdir(self)
        index, tables = bp.build([make_run(d, sides=('kaijuflow', 'uu', 'kaijuflow-1page'))], archive=None)
        everything = index + ''.join(tables.values())
        self.assertNotIn('kaijuflow-1page', everything)
        self.assertIn('<th scope="row">KaijuFlow, one page per indexer</th>', index)   # summary and round tables
        self.assertIn('class="side">KaijuFlow, one page per indexer</th>', tables['fixture-run-start'])
        self.assertIn('<dt>KaijuFlow, one page per indexer</dt>', index)   # Who's who

    def test_a_run_without_story_html_gets_the_numbers_only_section(self):
        d = tempdir(self)
        index, _ = bp.build([make_run(d)], archive=None)
        self.assertIn('Numbers only; no written story for this run yet.', index)
        self.assertIn('<h3>Summary</h3>', index)

    def test_story_html_in_the_run_folder_is_the_runs_section_with_the_run_tables_put_in(self):
        d = tempdir(self)
        run = make_run(d)
        with open(os.path.join(run, 'story.html'), 'w') as fh:
            fh.write(STORY)
        index, tables = bp.build([run], archive=None)
        self.assertIn('<h2>Fixture findings</h2>', index)
        self.assertIn('<p>Beta is the slow one on Usenet Ultimate.</p>', index)
        self.assertNotIn('Numbers only', index)
        self.assertNotIn('Run fixture-run, 2026-11-11', index)   # the story brings its own heading
        for name in ('__SUMMARY_TABLE__', '__ROUND_TABLE__', '__DETAILS__'):
            self.assertNotIn(name, index)
        section = index[index.index('<h2>Fixture findings</h2>'):index.index('<p class="note">Written by hand.</p>')]
        self.assertIn('<th scope="col">Start, cold</th>', section)   # the summary table
        self.assertIn('<td class="bad">1 of 2</td>', section)   # the round table: Beta fails on uu every round
        self.assertEqual(re.findall(r'data-table="([^"]+)"', section), ['fixture-run-start', 'fixture-run-list'])
        self.assertEqual(sorted(tables), ['fixture-run-list', 'fixture-run-start'])
        self.assertEqual(index.count('<section>'), index.count('</section>'))

    def test_two_runs_with_the_same_name_share_a_page_each_with_its_own_tables(self):
        d = tempdir(self)
        old = make_run(d, '2026-11-13T053200Z-baseline', fail=('uu', 'Beta'))
        new = make_run(d, '2026-11-20T090000Z-baseline', fail=('kaijuflow', 'Alpha'))
        for folder in (old, new):
            json.dump({'name': 'baseline', 'finished': '2026-11-11T10:00:00.000Z', 'indexers': ['ninjacentral']},
                      open(os.path.join(folder, 'meta.json'), 'w'))
        index, tables = bp.build([old, new], archive=None)
        self.assertEqual(re.findall(r'data-table="([^"]+)"', index), [
            '2026-11-20T090000Z-baseline-start', '2026-11-20T090000Z-baseline-list',
            '2026-11-13T053200Z-baseline-start', '2026-11-13T053200Z-baseline-list'])
        self.assertEqual(sorted(tables), sorted(re.findall(r'data-table="([^"]+)"', index)))
        self.assertNotIn('<td class="bad">fails</td>', tables['2026-11-13T053200Z-baseline-start'].split('Alpha')[1].split('</tr>')[0])
        self.assertIn('<td class="bad">fails</td>', tables['2026-11-20T090000Z-baseline-start'].split('Alpha')[1].split('</tr>')[0])

    def test_recording_folder_alone_is_not_enough(self):
        d = tempdir(self)
        with self.assertRaises(SystemExit):
            bp.build([make_record(d)], archive=None)

    def test_newest_run_first(self):
        d = tempdir(self)
        old = make_run(d, '2026-11-10T000000Z-a')
        new = make_run(d, '2026-11-11T000000Z-b')
        index, _ = bp.build([old, new], archive=None)
        self.assertLess(index.index('Run 2026-11-11T000000Z-b'), index.index('Run 2026-11-10T000000Z-a'))


class ArchivedSections(unittest.TestCase):
    """Runs whose folders are gone: their frozen sections and tables come from the archive folder."""

    def test_an_archived_section_sits_below_the_runs_with_its_tables_as_frozen(self):
        d = tempdir(self)
        index, tables = bp.build([make_run(d)], archive=lost_run(os.path.join(d, 'archive')))
        self.assertLess(index.index('Run fixture-run'), index.index('<h2>Lost run, 2026-11-01</h2>'))
        self.assertLess(index.index('<h2>Lost run, 2026-11-01</h2>'), index.index('<h2>What the words mean</h2>'))
        self.assertEqual(tables['lost-start'], frozen_table('Gamma'))
        self.assertEqual(sorted(tables), ['fixture-run-list', 'fixture-run-start', 'lost-all', 'lost-start'])
        self.assertEqual(sorted(re.findall(r'data-table="([^"]+)"', index)), sorted(tables))

    def test_an_entrys_appendix_goes_below_the_word_list_and_its_footer_line_into_the_footer(self):
        d = tempdir(self)
        index, _ = bp.build([make_run(d)], archive=lost_run(os.path.join(d, 'archive')))
        self.assertLess(index.index('<h2>What the words mean</h2>'), index.index('<h2>Lost run, all numbers</h2>'))
        self.assertLess(index.index('<h2>Lost run, all numbers</h2>'), index.index('<footer>'))
        footer = index[index.index('<footer>'):index.index('</footer>')]
        self.assertIn('<div>The raw data of the lost run is gone.</div>', footer)

    def test_archived_runs_are_newest_first_and_an_entry_may_be_a_section_alone(self):
        d = tempdir(self)
        archive = lost_run(os.path.join(d, 'archive'))
        make_entry(archive, '2026-10-20-older', {'section.html': '<section>\n  <h2>Older lost run, 2026-10-20</h2>\n</section>\n'})
        index, tables = bp.build([make_run(d)], archive=archive)
        self.assertLess(index.index('<h2>Lost run, 2026-11-01</h2>'), index.index('<h2>Older lost run, 2026-10-20</h2>'))
        self.assertLess(index.index('<h2>Older lost run, 2026-10-20</h2>'), index.index('<h2>What the words mean</h2>'))
        self.assertEqual(index.count('<section>'), index.count('</section>'))
        self.assertEqual(sorted(tables), ['fixture-run-list', 'fixture-run-start', 'lost-all', 'lost-start'])

    def test_without_an_archive_the_page_holds_the_given_runs_only(self):
        d = tempdir(self)
        index, _ = bp.build([make_run(d)], archive=None)
        self.assertNotIn('<footer>', index)
        self.assertNotIn('Earlier answers', index)
        self.assertIn('<p class="lede">Newest first: the timed runs on the test copies.</p>', index)

    def test_a_table_name_used_twice_is_refused(self):
        d = tempdir(self)
        archive = make_entry(os.path.join(d, 'archive'), '2026-11-01-lost', {
            'section.html': '<section>\n  <div data-table="fixture-run-start" class="slot">Loading the table...</div>\n</section>\n',
            'tables.json': {'fixture-run-start': frozen_table('Gamma')}})
        with self.assertRaises(SystemExit) as stop:
            bp.build([make_run(d)], archive=archive)
        self.assertIn('fixture-run-start', str(stop.exception))

    def test_a_place_for_a_table_that_nobody_supplies_is_refused(self):
        d = tempdir(self)
        archive = make_entry(os.path.join(d, 'archive'), '2026-11-01-lost', {
            'section.html': '<section>\n  <div data-table="lost-start" class="slot">Loading the table...</div>\n</section>\n'})
        with self.assertRaises(SystemExit) as stop:
            bp.build([make_run(d)], archive=archive)
        self.assertIn('lost-start', str(stop.exception))


class RepoArchive(unittest.TestCase):
    """The archive in the repo: the 2026-11-10 and 2026-11-09 sections as published. It is what a normal build uses."""

    def setUp(self):
        d = tempdir(self)
        self.out = os.path.join(d, 'page')
        with contextlib.redirect_stdout(io.StringIO()):
            bp.main([make_run(d), make_record(d), '--out', self.out])
        self.index = open(os.path.join(self.out, 'index.html')).read()
        self.tables = json.load(open(os.path.join(self.out, 'tables.json')))

    def test_one_command_with_run_and_recording_folder_keeps_the_lost_runs(self):
        order = ['Run fixture-run, 2026-11-11', '<h2>First baseline, 2026-11-10 (old machine, NinjaCentral only)</h2>',
                 '<h2>Earlier answers, 2026-11-09 (live services)</h2>', '<h2>What the words mean</h2>',
                 'All numbers: evening cold run, search side by side', '<h2>Worth knowing</h2>', '<footer>']
        places = [self.index.index(text) for text in order]
        self.assertEqual(places, sorted(places))
        self.assertIn('Its run record was lost with that machine.', self.index)
        self.assertIn('Whiplash and Band of Brothers S01E02', self.index)   # hand-corrected sentence, kept word for word
        self.assertIn('The raw data of 2026-11-09 and 2026-11-10 was lost with the old machine.', self.index)

    def test_the_lost_runs_tables_are_in_the_data_file(self):
        self.assertEqual(sorted(self.tables), ['afternoon-parity', 'afternoon-search', 'baseline-nc-list', 'baseline-nc-start',
                                               'evening-cold', 'evening-parity', 'evening-warm', 'fixture-run-list', 'fixture-run-start'])
        self.assertIn('Same video bytes', self.tables['evening-parity'])
        self.assertIn('HTTP 503', self.tables['evening-cold'])
        self.assertIn('<th scope="row">Oppenheimer</th>', self.tables['baseline-nc-start'])
        self.assertEqual(sorted(re.findall(r'data-table="([^"]+)"', self.index)), sorted(self.tables))

    def test_the_page_is_balanced(self):
        for tag in ('section', 'details', 'footer', 'main', 'dl', 'ul', 'table'):
            self.assertEqual(self.index.count('<' + tag), self.index.count('</' + tag + '>'), tag)


class HeaderWords(unittest.TestCase):
    def test_the_written_header_is_only_for_the_page_it_was_written_for(self):
        d = tempdir(self)
        written, _ = bp.build([make_run(d, bp.HEADER_FOR)])
        self.assertIn('<div class="eyebrow">Brain · 2026-11-13 baseline run · 2026-11-10 first baseline · 2026-11-09 live runs</div>', written)
        self.assertIn('the baseline run of 2026-11-13 on the new machine, four setups', written)
        other, _ = bp.build([make_run(d)])
        self.assertIn('<div class="eyebrow">Brain · timed runs</div>', other)
        self.assertNotIn('the baseline run of 2026-11-13', other)
        both, _ = bp.build([os.path.join(d, bp.HEADER_FOR), make_run(d, '2026-11-14T000000Z-later')])
        self.assertNotIn('the baseline run of 2026-11-13', both)


class PageRules(unittest.TestCase):
    def setUp(self):
        root = tempdir(self)
        self.index, self.tables = bp.build([make_run(root)])

    def test_title_is_two_to_four_words(self):
        title = re.search(r'<title>(.*?)</title>', self.index).group(1)
        self.assertTrue(2 <= len(title.split()) <= 4, title)

    def test_colors_are_tokens_with_both_dark_mode_forms_and_body_background(self):
        self.assertRegex(self.index, r':root\s*\{[^}]*--bg:')
        self.assertIn('@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {', self.index)
        self.assertIn(':root[data-theme="dark"] {', self.index)
        self.assertRegex(self.index, r'body \{ background: var\(--bg\)')

    def test_no_external_scripts_and_phone_gutter(self):
        self.assertNotRegex(self.index, r'<script[^>]*src=')
        self.assertIn('max(16px, env(safe-area-inset-left', self.index)
        self.assertIn('@media (max-width: 640px)', self.index)

    def test_page_is_small_next_to_its_tables(self):
        self.assertLess(len(self.index), 60000)

    def test_every_table_is_balanced_html(self):
        for tid, t in self.tables.items():
            for tag in ('table', 'tr', 'tbody', 'thead', 'div'):
                self.assertEqual(t.count('<' + tag), t.count('</' + tag + '>'), (tid, tag))


REAL = os.path.expanduser('~/kaijuflow-notes/brain-runs/2026-11-13T053200Z-baseline/')
REC = os.path.expanduser('~/kaijuflow-notes/brain-runs/2026-11-13T035846Z-baseline-record/')
V7 = os.path.expanduser('~/kaijuflow-notes/retro-2026-11-13-build/page-v7/')  # the page as published on 2026-11-13


@unittest.skipUnless(os.path.exists(REAL + 'story.html') and os.path.exists(REC + 'meta.json'), 'the real run folders are not on this machine')
class RealBaseline(unittest.TestCase):
    def test_the_2026_11_13_baseline_gets_its_story_with_its_numbers(self):
        index, tables = bp.build([REAL, REC])
        section = index[index.index('<!-- baseline 2026-11-13 start -->'):index.index('<!-- baseline 2026-11-13 end -->')]
        self.assertIn('<h2>Baseline run, 2026-11-13 (new machine, NinjaCentral only)</h2>', section)
        self.assertIn('<strong>Inception is hit-and-miss on KaijuFlow.</strong>', section)   # a written finding
        self.assertNotIn('Numbers only', index)
        # numbers the builder puts into the story: the one-page side's row of the summary table, as published
        self.assertIn('<tr><th scope="row">KaijuFlow, one page per indexer</th><td class="num">5.53 s</td>', section)
        self.assertEqual(re.findall(r'data-table="([^"]+)"', section),
                         ['2026-11-13T053200Z-baseline-start', '2026-11-13T053200Z-baseline-list'])
        self.assertIn('2026-11-13 baseline run · 2026-11-10 first baseline', index)
        self.assertEqual(len(tables), 9)
        self.assertIn('<td class="bad">fails</td>', tables['2026-11-13T053200Z-baseline-start'])

    @unittest.skipUnless(os.path.exists(V7 + 'index.html'), 'the published version 7 is not on this machine')
    def test_the_build_is_the_published_version_7_with_the_runs_tables_named_after_its_folder(self):
        """Version 7 named the run's two tables after the run (baseline-start, baseline-list); a build names them after
        the run folder, in the slots and in tables.json alike. Nothing else differs but a blank line."""
        index, tables = bp.build([REAL, REC])
        with open(V7 + 'index.html') as fh:
            published = fh.read()
        with open(V7 + 'tables.json') as fh:
            published_tables = json.load(fh)
        renamed = {'baseline-start': '2026-11-13T053200Z-baseline-start', 'baseline-list': '2026-11-13T053200Z-baseline-list'}
        self.assertEqual(tables, {renamed.get(k, k): v for k, v in published_tables.items()})
        for old, new in renamed.items():
            published = published.replace(f'data-table="{old}"', f'data-table="{new}"')

        def blank_lines_as_one(text):
            return re.sub(r'\n{3,}', '\n\n', text)
        self.assertEqual(blank_lines_as_one(index), blank_lines_as_one(published))


if __name__ == '__main__':
    unittest.main()
