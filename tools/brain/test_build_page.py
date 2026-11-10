"""Tests for build_page.py over a small fixture run folder. No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
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


def make_run(root, name='fixture-run', fail=('uu', 'Beta')):
    folder = os.path.join(root, name)
    os.makedirs(folder)
    visits = []
    for side in ('kaijuflow', 'uu'):
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


def side_1109(sources, first):
    return {'sources': sources, 'list_s': 1.5, 'first_try_plays': first, 'first_byte_s': 2.0, 'broken': 0 if first else 1,
            'tries': [{'plays': first, 'note': None if first else 'HTTP 503'}]}


def make_notes(root):
    os.makedirs(root)
    search = [{'title': 'Alpha', 'altmount-addon': side_1109(10, True), 'kaijuflow-altmount': side_1109(20, True), 'uu-nzbdav': side_1109(20, False)}]
    ends = {'size': 5, 'ready_s': 0.5, 'seek50': {'s': 0.2}, 'seek90': {'s': 0.3}}
    parity = [{'title': 'Alpha', 'nzbdav': ends, 'altmount': dict(ends, unscramble={'parts': 3, 'ms': 900}), 'bytes_match': True, 'same_file': True}]
    for name, data in [('search.json', search), ('cold-search.json', search), ('warm-search.json', search),
                       ('parity-run3.json', parity), ('parity-fresh.json', parity)]:
        json.dump(data, open(os.path.join(root, name), 'w'))
    return root


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
        index, tables = bp.write([rec, run], out, with_1109=False)
        self.assertEqual(sorted(os.listdir(out)), ['index.html', 'tables.json'])
        self.assertEqual(open(os.path.join(out, 'index.html')).read(), index)
        self.assertEqual(json.load(open(os.path.join(out, 'tables.json'))), tables)
        self.assertEqual(sorted(tables), ['fixture-run-list', 'fixture-run-start'])
        # per-title rows are in the data file, not in the page
        self.assertIn('<th scope="row">Alpha</th>', tables['fixture-run-start'])
        self.assertNotIn('<th scope="row">Alpha</th>', index)

    def test_every_slot_has_a_table_and_the_page_loads_them_with_fetch(self):
        d = tempdir(self)
        index, tables = bp.build([make_run(d)], with_1109=False)
        slots = re.findall(r'data-table="([^"]+)"', index)
        self.assertEqual(sorted(slots), sorted(tables))
        self.assertIn("fetch('tables.json')", index)

    def test_failed_pick_and_round_numbers_show(self):
        d = tempdir(self)
        index, tables = bp.build([make_run(d)], with_1109=False)
        self.assertIn('Run fixture-run, 2026-11-11 (ninjacentral)', index)
        self.assertIn('the top pick did not play for Beta', index)
        self.assertIn('<td class="bad">1 of 2</td>', index)   # uu round table: Beta fails every round
        self.assertIn('<td class="bad">fails</td>', tables['fixture-run-start'])
        self.assertIn('<th scope="col">Cold 1</th>', tables['fixture-run-start'])

    def test_recording_folder_alone_is_not_enough(self):
        d = tempdir(self)
        with self.assertRaises(SystemExit):
            bp.build([make_record(d)], with_1109=False)

    def test_newest_run_first(self):
        d = tempdir(self)
        old = make_run(d, '2026-11-10T000000Z-a')
        new = make_run(d, '2026-11-11T000000Z-b')
        index, _ = bp.build([old, new], with_1109=False)
        self.assertLess(index.index('Run 2026-11-11T000000Z-b'), index.index('Run 2026-11-10T000000Z-a'))

    def test_hand_text_not_used_when_shape_differs(self):
        d = tempdir(self)
        index, _ = bp.build([make_run(d, 'baseline-nc')], with_1109=False)
        self.assertNotIn('Where KaijuFlow stands against the targets', index)
        self.assertIn('Numbers only; no written story for this run yet.', index)


class PageRules(unittest.TestCase):
    def setUp(self):
        root = tempdir(self)
        self.index, self.tables = bp.build([make_run(root)], make_notes(os.path.join(root, 'notes')))

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

    def test_1109_text_is_in_the_page_and_its_tables_in_the_data_file(self):
        self.assertIn('Earlier answers, 2026-11-09 (live services)', self.index)
        self.assertIn('Whiplash and Band of Brothers S01E02', self.index)   # hand-corrected sentence, kept word for word
        self.assertIn('<h3>4. The cold run, side by side</h3>', self.index)
        for tid in ('evening-cold', 'evening-warm', 'evening-parity', 'afternoon-search', 'afternoon-parity'):
            self.assertIn(tid, self.tables)
        self.assertIn('Same video bytes', self.tables['evening-parity'])
        self.assertIn('HTTP 503', self.tables['evening-cold'])
        self.assertEqual(sorted(re.findall(r'data-table="([^"]+)"', self.index)), sorted(self.tables))

    def test_every_table_is_balanced_html(self):
        for tid, t in self.tables.items():
            for tag in ('table', 'tr', 'tbody', 'thead', 'div'):
                self.assertEqual(t.count('<' + tag), t.count('</' + tag + '>'), (tid, tag))


REAL = '/home/ryan/kaijuflow-notes/brain-runs/2026-11-10T073655Z-baseline-nc/'
REC = '/home/ryan/kaijuflow-notes/brain-runs/2026-11-10T072719Z-baseline-nc-record/'


@unittest.skipUnless(os.path.exists(REAL + 'raw.json') and os.path.exists(REC + 'meta.json'), 'the real run folders are not on this machine')
class RealBaseline(unittest.TestCase):
    def test_baseline_nc_gets_its_written_section_with_its_numbers(self):
        index, tables = bp.build([REC, REAL], with_1109=False)
        self.assertIn('Where KaijuFlow stands against the targets', index)
        self.assertIn('Recording 07:27 to 07:35 UTC, timed run 07:37 to 07:59 UTC.', index)
        self.assertEqual(sorted(tables), ['baseline-nc-list', 'baseline-nc-start'])
        self.assertIn('Oppenheimer', tables['baseline-nc-start'])


if __name__ == '__main__':
    unittest.main()
