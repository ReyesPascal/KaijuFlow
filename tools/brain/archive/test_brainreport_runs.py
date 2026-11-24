"""The archived tests of test_brainreport.py (ADR 0010, #273): a run folder's check (runcheck.py).
"""
import unittest

import test_brainreport
from test_brainreport import *  # noqa: F401,F403  (the live file's helpers)
import runcheck  # noqa: E402,F401


class BestPressFixtureTest(test_brainreport.BestPressFixtureTest):
    def test_the_head_starts_work_is_no_part_of_the_start(self):
        # checks, import and first byte all ran before the press (#206): no step is measured against the start
        _, v = self.visit()
        self.assertTrue(any(s['step'] == 'import_wait' for s in v['steps']))
        self.assertEqual(runcheck._from_the_play(v)['steps'], [])


class KaijuFlowAloneTest(test_brainreport.KaijuFlowAloneTest):
    def test_check_counts_a_fallback_as_played_and_says_its_extra_seconds(self):
        usable, lines = runcheck.check_run(self.folder)
        self.assertIn('Top picks played, KaijuFlow: cold 7 of 8, warm 8 of 8.', lines)
        start = lines.index('Played after a fallback (1), counted as played:')
        self.assertEqual(lines[start + 1], '- KaijuFlow, cold 1, Old Film: played after 1 fallback, 2.50 s extra')
        self.assertIn('- KaijuFlow, cold 2, Rare Show S01E01: failure video', lines)  # the fail is still a failure

    def test_check_gives_per_list_the_fails_the_fallbacks_and_the_cold_and_warm_title_to_video(self):
        usable, lines = runcheck.check_run(self.folder)
        self.assertIn('KaijuFlow, easy list: fails 0 titles failed · 0 of 8 plays; fallbacks none; '
                      'cold title to video 3.50 s; warm title to video 3.50 s.', lines)
        # hard, cold: Old Film 8.0 (2.0 + 6.0, after the fallback) and 3.5, Rare Show 6.0, its Cold 2 a fail: median 6.0
        self.assertIn('KaijuFlow, hard list: fails 1 title failed · 1 of 8 plays (Cold 2 Rare Show S01E01); '
                      'fallbacks 1 (Cold 1 Old Film, played after 1 fallback, 2.50 s extra); '
                      'cold title to video 6.00 s; warm title to video 3.50 s.', lines)

    def test_a_run_without_tags_gets_one_such_line_for_every_title(self):
        with open(os.path.join(self.folder, 'raw.json')) as f:
            raw = json.load(f)
        for v in raw['visits']:
            v.pop('list')
        with open(os.path.join(self.folder, 'raw.json'), 'w') as f:
            json.dump(raw, f)
        usable, lines = runcheck.check_run(self.folder)
        self.assertIn('KaijuFlow, every title: fails 1 title failed · 1 of 16 plays (Cold 2 Rare Show S01E01); '
                      'fallbacks 1 (Cold 1 Old Film, played after 1 fallback, 2.50 s extra); '
                      'cold title to video 3.50 s; warm title to video 3.50 s.', lines)


class TaggedRunTest(test_brainreport.TaggedRunTest):
    def test_the_check_names_the_fails_of_each_setup_per_list(self):
        usable, lines = runcheck.check_run(tagged_run_folder(self, self.FAILS))
        times = 'cold title to video 3.50 s; warm title to video 3.50 s.'
        self.assertEqual([x for x in lines if ' list: fails ' in x], [
            f'KaijuFlow, easy list: fails 0 titles failed · 0 of 8 plays; fallbacks none; {times}',
            f'KaijuFlow, hard list: fails 1 title failed · 1 of 8 plays (Cold 1 Old Film); fallbacks none; {times}',
            f'KaijuFlow, one page per indexer, easy list: fails 1 title failed · 1 of 8 plays (Cold 2 Matrix); fallbacks none; {times}',
            'KaijuFlow, one page per indexer, hard list: fails 0 titles failed · 0 of 8 plays; '
            f'fallbacks 1 (Cold 1 Rare Show S01E01, played after 1 fallback); {times}'])

    def test_a_title_that_fails_in_both_cold_rounds_is_one_title_and_two_plays(self):
        usable, lines = runcheck.check_run(tagged_run_folder(self, {**fail('kaijuflow', 'Old Film'), **fail('kaijuflow', 'Old Film', 2)}))
        self.assertIn('KaijuFlow, hard list: fails 1 title failed · 2 of 8 plays (Cold 1 Old Film; Cold 2 Old Film); '
                      'fallbacks none; cold title to video 3.50 s; warm title to video 3.50 s.', lines)


MOVED = [('BestPressFixtureTest', 'test_the_head_starts_work_is_no_part_of_the_start'), ('KaijuFlowAloneTest', 'test_check_counts_a_fallback_as_played_and_says_its_extra_seconds'), ('KaijuFlowAloneTest', 'test_check_gives_per_list_the_fails_the_fallbacks_and_the_cold_and_warm_title_to_video'), ('KaijuFlowAloneTest', 'test_a_run_without_tags_gets_one_such_line_for_every_title'), ('TaggedRunTest', 'test_the_check_names_the_fails_of_each_setup_per_list'), ('TaggedRunTest', 'test_a_title_that_fails_in_both_cold_rounds_is_one_title_and_two_plays')]


def load_tests(loader, tests, pattern):
    """Only the archived tests, not the live ones the classes inherit."""
    suite = unittest.TestSuite(globals()[c](n) for c, n in MOVED)
    suite.addTests(t for t in tests if not any(isinstance(x, tuple(globals()[c] for c, _ in MOVED)) for x in _flat(t)))
    return suite


def _flat(t):
    return [t] if isinstance(t, unittest.TestCase) else [x for s in t for x in _flat(s)]


if __name__ == '__main__':
    unittest.main()
