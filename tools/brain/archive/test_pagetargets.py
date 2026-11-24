"""Tests for pagetargets.py, the Speed Check page's judging of KaijuFlow against the other setups of a run (the targets of
targets.json, a speed test's targets, outcome and final bar, like for like). Page code: it goes with the page (#195).
No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import json
import os
import unittest

import brainreport as br
import runs
import pagetargets as pt
from test_brainreport import fail, merged, tagged_run_folder, video
from test_settings import tempdir


def runs_fixture(failing=False):
    """KaijuFlow, Usenet Ultimate and AltMount direct on one title, every round: the setups the targets are held against."""
    visits = []
    for rnd in (1, 2):
        for phase in ('cold', 'warm'):
            for side, st in (('kaijuflow', 2.0), ('uu', 3.0), ('altmount-addon', 1.0)):
                ok = not (failing and side == 'uu' and phase == 'cold')
                visits.append(dict(side=side, phase=phase, round=rnd, title='Matrix', id='tt1', ok=ok, list_s=5.0,
                                   sources=4, start_s=st, note=None if ok else 'failure video', steps=[], imports=[],
                                   limit=None, t_start='2026-11-10T18:00:00Z', t_end='2026-11-10T18:00:07Z',
                                   tries=[]))
    return dict(name='t', status='ok', visits=visits, titles=['Matrix'], sides=['kaijuflow', 'uu', 'altmount-addon'],
                commit='abc', dirty=False, indexers=['ninjacentral'], started='2026-11-10T18:00:00Z', settings={},
                null=None, standin_misses=0)


def picks_run(altmount_dune='Dune.2021.1080p.WEB-DL-GRP', altmount_dune_size=5_000_000_000):
    """KaijuFlow and AltMount direct on two films, every round. Matrix: both play a 2160p file inside the 30 GB cap, so the
    title is like for like. Dune: AltMount direct's top pick is the one given (by default a 1080p file); KaijuFlow is slow on it."""
    picks = {('kaijuflow', 'Matrix'): ('The.Matrix.1999.2160p.UHD.BluRay-GRP', 20_000_000_000, 2.0),
             ('altmount-addon', 'Matrix'): ('4K - The Matrix [2160p] The.Matrix.1999.2160p.WEB-DL-GRP', 18_000_000_000, 1.0),
             ('kaijuflow', 'Dune'): ('Dune.2021.2160p.UHD.BluRay-GRP', 25_000_000_000, 9.0),
             ('altmount-addon', 'Dune'): (altmount_dune, altmount_dune_size, 0.5)}
    visits = [dict(side=side, phase=phase, round=rnd, title=title, kind='movie', ok=True, list_s=1.0, start_s=start,
                   note=None, misses=[], steps=[], imports=[], played_source=None,
                   tries=[{'plays': True, 'size': size, 'title': name}])
              for phase, rnd in br.RUN_ORDER for (side, title), (name, size, start) in picks.items()]
    return dict(name='t', status='ok', visits=visits, titles=['Matrix', 'Dune'], sides=['kaijuflow', 'altmount-addon'],
                commit='abc', dirty=False, indexers=['ninjacentral'], started='2026-11-16T10:00:00Z', settings={},
                null=None, standin_misses=0)


class ResolutionTest(unittest.TestCase):
    """The resolution a top pick states (#154): a stated number wins over the words 4K, UHD and FHD, which count only when
    no number is stated. Names from Test 1 (2026-11-15T115540Z-baseline)."""

    def test_a_stated_number_wins_over_the_words(self):
        for text, want in {
                'AltMount FHD - Inception (2010) [1080p] Inception 2010 PROPER 1080p UHD BluRay DD+5.1 x264-LoRD': '1080p',
                'The Matrix 1999 4K Remaster 1080p BluRay DTS x264-Geek': '1080p',
                'The.Matrix.1999.1080p.UHD.BluRay.DD+7.1.DV.HDR.x265-HiDt': '1080p',
                'Breaking.Bad.S01E01.POLISH.2160p.WEB.H265-FLAME': '2160p',
                'Dune.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HDR.AV1-CoSMiCSuRFeR': '2160p',
                'Show.S01E02.720p.UHD.WEB': '720p'}.items():
            self.assertEqual(pt.resolution(text), want, text)

    def test_the_words_count_when_no_number_is_stated(self):
        for text, want in {'✅ 4K BluRay 🎬 Inception (2010) 💾 28.02 GB': '2160p', 'Film.2010.UHD.BluRay': '2160p',
                           'Film FHD BluRay': '1080p', 'Inception.2010.BluRay.x265-4K4U': None, 'Film.2010.DVDRip': None}.items():
            self.assertEqual(pt.resolution(text), want, text)

    def test_a_sides_own_label_is_read_with_the_release_name_the_first_stated_number_wins(self):
        self.assertEqual(pt.resolution('AltMount 4K - Film [2160p] Film.2010.1080p.WEB'), '2160p')


class LikeForLikeTest(unittest.TestCase):
    """Each title's top picks are compared across the setups (#143): a title whose picks differ beyond the like-for-like
    rules (resolution, size cap, disc images) is named and left out of judging KaijuFlow against that setup."""

    def test_a_title_with_unequal_picks_is_named_and_left_out_of_the_targets_against_that_setup(self):
        run = picks_run()
        self.assertEqual(pt.unlike_titles(run['visits']),
                         {'altmount-addon': {'Dune': "KaijuFlow's top pick is 2160p, AltMount direct's is 1080p (Cold 1)"}})
        rows = {t: (m, v) for t, m, v in pt.target_results(run['visits'])}
        measured, verdict = rows['Cold start within 1 s of AltMount direct']
        self.assertEqual(measured, "KaijuFlow 2.00 s, AltMount direct 1.00 s (1 title left out: not like for like)")
        self.assertEqual(verdict['result'], pt.MET)  # with Dune, KaijuFlow's median would be 5.50 s

    def test_a_target_held_to_a_fixed_limit_keeps_every_title(self):
        rows = {t: (m, v) for t, m, v in pt.target_results(picks_run()['visits'])}
        self.assertEqual(rows['Top pick plays on 10 of 10 titles, cold and warm'][0],
                         'cold 2 of 2 and 2 of 2, warm 2 of 2 and 2 of 2')

    def test_a_top_pick_over_the_size_cap_is_not_like_for_like(self):
        run = picks_run(altmount_dune='Dune.2021.2160p.UHD.BluRay.REMUX-GRP', altmount_dune_size=70_000_000_000)
        self.assertEqual(pt.unlike_titles(run['visits']), {'altmount-addon': {'Dune': (
            "AltMount direct's top pick breaks the like-for-like rules (Cold 1): 70.0 GB served, over the cap for a film (32.2 GB)")}})

    def test_equal_picks_say_so(self):
        self.assertEqual(pt.unlike_titles(picks_run(altmount_dune='Dune.2021.2160p.WEB-DL-GRP')['visits']), {})


def targets_run(**figures):
    """runs_fixture() with some figures replaced, named '<side> <phase> <round> <field>': targets_run(**{'uu cold 1 start_s': 2.5})."""
    run = runs_fixture()
    for name, value in figures.items():
        side, phase, rnd, field = name.split()
        [v] = [v for v in run['visits'] if (v['side'], v['phase'], str(v['round'])) == (side, phase, rnd)]
        v[field] = value
    return run


class TargetsTest(unittest.TestCase):
    """The six targets of targets.json, judged on an untagged run (pagetargets.target_results)."""

    def verdicts(self, **figures):
        return {t: (m, v) for t, m, v in pt.target_results(targets_run(**figures)['visits'])}

    def test_a_met_target_a_missed_one_and_one_inside_the_noise(self):
        rows = self.verdicts(**{
            'kaijuflow cold 1 start_s': 4.0, 'kaijuflow cold 2 start_s': 2.0,   # median 3.00 s, the two rounds 2.00 s apart
            'uu cold 1 start_s': 2.5, 'uu cold 2 start_s': 2.5,
            'kaijuflow warm 1 list_s': 3.0, 'kaijuflow warm 2 list_s': 3.0})
        measured, verdict = rows['Warm list no slower than 4.7 s']
        self.assertEqual((measured, verdict['result']), ('KaijuFlow 3.00 s', pt.MET))
        measured, verdict = rows['Warm start within 0.05 s of AltMount direct']
        self.assertEqual((measured, verdict['result'], verdict['slower_s']),
                         ('KaijuFlow 2.00 s, AltMount direct 1.00 s', pt.NOT_MET, 1.0))
        measured, verdict = rows['Cold start no slower than Usenet Ultimate']
        self.assertEqual((measured, verdict['result'], verdict['slower_s']),
                         ('KaijuFlow 3.00 s, Usenet Ultimate 2.50 s', pt.NOT_MET, 0.5))
        self.assertEqual(verdict['noise'], {'phase': 'cold', 'rounds': (4.0, 2.0), 'by': 0.5})  # the rounds differ by more
        self.assertEqual(sum(1 for _, v in rows.values() if v['result'] == pt.MET), 2)  # the warm list, and the plays

    def test_a_met_target_can_be_inside_the_noise_too(self):
        _, verdict = self.verdicts(**{'kaijuflow cold 1 start_s': 4.0, 'kaijuflow cold 2 start_s': 2.0,
                                      'uu cold 1 start_s': 3.5, 'uu cold 2 start_s': 3.5})['Cold start no slower than Usenet Ultimate']
        self.assertEqual((verdict['result'], verdict['noise']), (pt.MET, {'phase': 'cold', 'rounds': (4.0, 2.0), 'by': 0.5}))

    def test_with_a_margin_the_noise_is_held_against_the_distance_to_the_margin(self):
        # 1.10 s behind the addon where 1 s is allowed: missed by 0.10 s, and the two cold rounds are 0.20 s apart
        _, verdict = self.verdicts(**{'kaijuflow cold 1 start_s': 2.2, 'kaijuflow cold 2 start_s': 2.0})[
            'Cold start within 1 s of AltMount direct']
        self.assertEqual(verdict['result'], pt.NOT_MET)
        self.assertAlmostEqual(verdict['slower_s'], 1.1)
        self.assertEqual(verdict['noise'], {'phase': 'cold', 'rounds': (2.2, 2.0), 'by': 0.1})

    def test_rounds_closer_together_than_the_gap_leave_the_result_plain(self):
        _, verdict = self.verdicts(**{'kaijuflow cold 1 start_s': 3.2, 'kaijuflow cold 2 start_s': 3.0})[
            'Cold start within 1 s of AltMount direct']
        self.assertEqual((verdict['result'], verdict['noise']), (pt.NOT_MET, None))
        self.assertAlmostEqual(verdict['slower_s'], 2.1)

    def plays_verdict(self, kaijuflow, altmount):
        """The verdict of the plays target ("at least as often as AltMount direct") when KaijuFlow's top picks play
        `kaijuflow` times out of 40 and AltMount direct's `altmount` times (spec #58, the tie rule of 2026-11-15)."""
        visits = []
        for side, plays in (('kaijuflow', kaijuflow), ('altmount-addon', altmount)):
            for i in range(40):
                visits.append(dict(side=side, phase='cold' if i % 2 else 'warm', round=1 + i % 4 // 2, title=f't{i}',
                                   ok=i < plays, list_s=1.0, start_s=1.0, steps=[], imports=[], note='failure video'))
        [(target, measured, verdict)] = [r for r in pt.target_results(visits) if r[0].startswith('Top pick plays at least')]
        return verdict

    def test_a_tie_at_the_maximum_counts_as_met(self):
        verdict = self.plays_verdict(40, 40)
        self.assertEqual(verdict['result'], pt.MET)
        self.assertEqual((verdict['value'], verdict['limit']), ((40, 40), (40, 40)))

    def test_a_tie_below_the_maximum_is_not_met_and_more_often_is(self):
        self.assertEqual(self.plays_verdict(39, 39)['result'], pt.NOT_MET)
        self.assertEqual(self.plays_verdict(40, 39)['result'], pt.MET)
        self.assertEqual(self.plays_verdict(38, 39)['result'], pt.NOT_MET)
        self.assertEqual(self.plays_verdict(39, 40)['result'], pt.NOT_MET)

    def test_the_targets_file_says_the_tie_rule_in_words(self):
        texts = [t['target'] for t in pt.load_targets()]
        self.assertIn('Top pick plays at least as often as AltMount direct, and more often unless both play every time', texts)

    def test_a_time_verdict_carries_kaijuflows_value_and_the_limit_it_is_held_to(self):
        rows = pt.target_results(targets_run(**{'kaijuflow cold 1 start_s': 2.2, 'kaijuflow cold 2 start_s': 2.0})['visits'])
        [(_, _, verdict)] = [r for r in rows if r[0].startswith('Cold start within 1 s')]
        self.assertEqual((verdict['value'], verdict['limit']), (2.1, 2.0))  # AltMount direct 1.00 s + the 1 s allowed
        [(_, _, verdict)] = [r for r in rows if r[0].startswith('Warm list')]
        self.assertEqual((verdict['value'], verdict['limit']), (5.0, 4.7))

    def test_the_plays_per_round_verdict_carries_the_plays_of_every_round_together(self):
        # the real 2026-11-13 baseline: cold 10 of 10 and 9 of 10, warm 10 of 10 and 10 of 10; 10 a round are needed
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fixtures', 'run-2026-11-13', 'raw.json')
        with open(path) as f:
            rows = pt.target_results(json.load(f)['visits'])
        [(_, _, verdict)] = [r for r in rows if r[0].startswith('Top pick plays on')]
        self.assertEqual((verdict['result'], verdict['value'], verdict['limit']), (pt.NOT_MET, (39, 40), (40, 40)))

    def test_a_missing_targets_file_gives_one_sentence(self):
        with self.assertRaisesRegex(ValueError, r'^targets\.json cannot be read: FileNotFoundError$'):
            pt.load_targets(os.path.join(tempdir(self), 'targets.json'))

    def test_an_entry_the_tools_cannot_judge_is_named(self):
        entry = {'target': 'Cold start no slower than Usenet Ultimate', 'measure': 'cold start', 'against': 'uu', 'margin': 0}
        bad = [({'measure': 'cold sprint'}, 'entry 2: the measure "cold sprint" is not known'),
               ({'margin': 'small'}, 'entry 2: the margin is not a number from 0 up'),
               ({'margin': -1}, 'entry 2: the margin is not a number from 0 up'),
               ({'against': 'nobody'}, 'entry 2: the side "nobody" is not known'),
               ({'limit': 3}, 'entry 2: "cold start" takes a side (against) or a fixed limit, one of the two'),
               ({'measure': 'plays per round'}, 'entry 2: "plays per round" takes a fixed limit, not a side'),
               ({'measure': 'plays', 'limit': 3}, 'entry 2: "plays" takes a side (against), not a fixed limit')]
        path = os.path.join(tempdir(self), 'targets.json')
        for change, why in bad:
            with open(path, 'w') as f:
                json.dump({'targets': [entry, {**entry, 'against': 'altmount-addon', **change}]}, f)
            with self.assertRaises(ValueError) as e:
                pt.load_targets(path)
            self.assertEqual(str(e.exception), f'targets.json, {why}')



THREE = ('kaijuflow', 'uu', 'altmount-addon')


def speed_run_folder(case, *changes, sides=THREE):
    """A finished tagged run folder of `sides` with the `changed` entries of fail() and video() applied together."""
    return tagged_run_folder(case, merged(*changes), sides)


def speed_judgement(case, *changes, sides=THREE):
    return pt.speed_test_judgement(runs.load(speed_run_folder(case, *changes, sides=sides))['visits'])


def speed_verdicts(case, *changes, sides=THREE):
    """{(target number, list): result} of a fake tagged run, as pagetargets.speed_test_judgement gives them."""
    return {(r['number'], r['list']): r['verdict']['result'] for r in speed_judgement(case, *changes, sides=sides)['targets']}


class SpeedTestTargetsTest(unittest.TestCase):
    """#169: a tagged run (a speed test) is judged per list on three targets: fails, cold title to video against the
    setups with as few fails or fewer, and warm title to video under 1 s."""

    def test_the_fails_target_is_met_on_a_list_where_kaijuflow_fails_no_more_than_any_other_setup(self):
        verdicts = speed_verdicts(self, fail('kaijuflow', 'Old Film'), fail('uu', 'Old Film'),
                                  fail('altmount-addon', 'Rare Show S01E01'), fail('altmount-addon', 'Old Film', 2))
        self.assertEqual((verdicts[1, 'easy'], verdicts[1, 'hard']), (pt.MET, pt.MET))  # hard: 1 against 1 and 2

    def test_the_fails_target_is_not_met_on_the_hard_list_when_another_setup_fails_fewer(self):
        verdicts = speed_verdicts(self, fail('kaijuflow', 'Old Film'), fail('kaijuflow', 'Rare Show S01E01'),
                                  fail('uu', 'Old Film'), fail('uu', 'Rare Show S01E01'), fail('altmount-addon', 'Old Film'))
        self.assertEqual((verdicts[1, 'easy'], verdicts[1, 'hard']), (pt.MET, pt.NOT_MET))

    def test_a_fail_on_the_easy_list_fails_the_fails_target_even_when_every_other_setup_fails_more(self):
        verdicts = speed_verdicts(self, fail('kaijuflow', 'Matrix'), fail('uu', 'Matrix'), fail('uu', 'Dune'),
                                  fail('altmount-addon', 'Matrix'), fail('altmount-addon', 'Dune'))
        self.assertEqual((verdicts[1, 'easy'], verdicts[1, 'hard']), (pt.NOT_MET, pt.MET))

    def test_the_cold_title_to_video_target_is_met_when_kaijuflow_is_no_slower_than_every_setup_with_as_few_fails(self):
        verdicts = speed_verdicts(self, video('uu', 'easy', 5.0), video('altmount-addon', 'hard', 3.5))  # KaijuFlow 3.5
        self.assertEqual((verdicts[2, 'easy'], verdicts[2, 'hard']), (pt.MET, pt.MET))

    def test_the_cold_title_to_video_target_is_not_met_on_a_list_where_a_setup_as_reliable_is_faster(self):
        easy = speed_verdicts(self, video('altmount-addon', 'easy', 2.0))
        self.assertEqual((easy[2, 'easy'], easy[2, 'hard']), (pt.NOT_MET, pt.MET))
        hard = speed_verdicts(self, video('uu', 'hard', 2.0), fail('kaijuflow', 'Old Film'), fail('uu', 'Old Film', 2))
        self.assertEqual((hard[2, 'easy'], hard[2, 'hard']), (pt.MET, pt.NOT_MET))

    def test_a_faster_setup_with_more_fails_does_not_count_against_the_cold_title_to_video_target(self):
        verdicts = speed_verdicts(self, video('altmount-addon', 'hard', 2.0), fail('altmount-addon', 'Old Film'))
        self.assertEqual(verdicts[2, 'hard'], pt.MET)

    def test_the_warm_title_to_video_target_is_met_under_1_s_on_each_list_on_its_own(self):
        verdicts = speed_verdicts(self, video('kaijuflow', 'easy', 0.8, 'warm'), video('kaijuflow', 'hard', 1.0, 'warm'))
        self.assertEqual((verdicts[3, 'easy'], verdicts[3, 'hard']), (pt.MET, pt.NOT_MET))  # 1.00 s is not under 1 s
        verdicts = speed_verdicts(self, video('kaijuflow', 'easy', 1.2, 'warm'), video('kaijuflow', 'hard', 0.5, 'warm'))
        self.assertEqual((verdicts[3, 'easy'], verdicts[3, 'hard']), (pt.NOT_MET, pt.MET))

    def outcome(self, *changes):
        return speed_judgement(self, *changes)['outcome']

    def test_the_outcome_is_to_tune_kaijuflows_speed_when_it_fails_fewer_hard_titles_than_altmount_direct(self):
        outcome = self.outcome(fail('altmount-addon', 'Old Film'), video('altmount-addon', 'hard', 2.0),
                               fail('kaijuflow', 'Matrix'))  # the easy list does not decide the outcome
        self.assertEqual(outcome['outcome'], pt.OUTCOME_TUNE)
        self.assertEqual(outcome['text'], 'Outcome on the hard list: KaijuFlow fails fewer plays than AltMount direct '
                                          '(KaijuFlow 0 titles failed · 0 of 8 plays against AltMount direct 1 title failed · '
                                          '1 of 8 plays), so tune its speed.')

    def test_the_outcome_is_to_try_kaijuflow_without_its_pre_list_check_when_it_ties_and_altmount_direct_is_faster(self):
        outcome = self.outcome(fail('altmount-addon', 'Old Film'), fail('kaijuflow', 'Rare Show S01E01', 2),
                               video('altmount-addon', 'hard', 2.0))
        self.assertEqual(outcome['outcome'], pt.OUTCOME_NO_PRE_LIST_CHECK)
        self.assertEqual(outcome['text'], 'Outcome on the hard list: KaijuFlow and AltMount direct fail as many plays '
                                          '(KaijuFlow 1 title failed · 1 of 8 plays against AltMount direct 1 title failed · '
                                          '1 of 8 plays) and AltMount direct is faster (cold title to video 2.00 s against '
                                          '3.50 s), so try KaijuFlow without its own pre-list check, behind AltMount.')

    def test_the_outcome_is_a_bug_in_kaijuflows_checking_when_altmount_direct_fails_fewer_hard_titles(self):
        outcome = self.outcome(fail('kaijuflow', 'Old Film'), video('kaijuflow', 'hard', 1.0))
        self.assertEqual(outcome['outcome'], pt.OUTCOME_BUG)
        self.assertEqual(outcome['text'], 'Outcome on the hard list: AltMount direct fails fewer plays than KaijuFlow '
                                          '(KaijuFlow 1 title failed · 1 of 8 plays against AltMount direct 0 titles failed · '
                                          "0 of 8 plays), so KaijuFlow's checking has a bug to find first.")

    def test_a_tie_where_kaijuflow_is_no_slower_is_as_reliable_and_no_slower_so_tune_its_speed(self):
        outcome = self.outcome(video('altmount-addon', 'hard', 4.0))
        self.assertEqual(outcome['outcome'], pt.OUTCOME_TUNE)
        self.assertEqual(outcome['text'], 'Outcome on the hard list: KaijuFlow is as reliable and no slower: tune its speed '
                                          '(KaijuFlow 0 titles failed · 0 of 8 plays against AltMount direct 0 titles '
                                          'failed · 0 of 8 plays; cold title to video 3.50 s against 4.00 s).')

    def test_the_outcome_counts_failed_plays_so_a_title_failed_twice_weighs_two(self):
        outcome = self.outcome(fail('kaijuflow', 'Old Film'), fail('kaijuflow', 'Old Film', 2),
                               fail('altmount-addon', 'Old Film'), fail('altmount-addon', 'Rare Show S01E01'))
        self.assertEqual(outcome['outcome'], pt.OUTCOME_TUNE)  # 2 failed plays each, 1 title against 2: a tie, not fewer
        self.assertIn('KaijuFlow 1 title failed · 2 of 8 plays against AltMount direct 2 titles failed · 2 of 8 plays', outcome['text'])


SLOWER = [video(s, x, 5.0) for s in ('uu', 'altmount-addon') for x in br.LISTS]  # KaijuFlow 3.5 s, the others 5.0 s


class FinalBarTest(unittest.TestCase):
    """#169 (was #141): "On both lists, KaijuFlow has the fewest fails (a tie counts as fewest), and the fastest title to
    video among setups with as few fails." Judged on a tagged run beside the targets, on failed plays; any tie on fails
    counts as fewest (owner, 2026-11-15)."""

    def bar(self, *changes):
        bar = speed_judgement(self, *changes)['final_bar']
        return bar['verdict']['result'], {x: r['result'] for x, r in bar['lists'].items()}

    def test_the_targets_file_holds_the_final_bar_in_the_owners_words_beside_the_three_targets(self):
        speed = pt.load_speed_targets()
        self.assertEqual(len(speed['targets']), 3)
        self.assertEqual(speed['final_bar'], 'On both lists, KaijuFlow has the fewest fails (a tie counts as fewest), and the '
                                             'fastest title to video among setups with as few fails.')
        self.assertEqual([t['target'] for t in speed['targets']], [
            'KaijuFlow fails no more plays than any other setup, and none on the easy list',
            "KaijuFlow's median cold title to video is no slower than any setup with as few fails or fewer",
            'Warm title to video under about 1 s'])

    def test_the_bar_is_met_with_no_fails_anywhere_when_kaijuflow_is_the_fastest_on_both_lists(self):
        self.assertEqual(self.bar(*SLOWER), (pt.MET, {'easy': pt.MET, 'hard': pt.MET}))  # a tie on fails is fewest

    def test_the_bar_is_not_met_on_a_list_where_a_setup_with_as_few_fails_is_as_fast(self):
        self.assertEqual(self.bar(*SLOWER, video('altmount-addon', 'easy', 2.0)),
                         (pt.NOT_MET, {'easy': pt.NOT_MET, 'hard': pt.MET}))
        self.assertEqual(self.bar(*SLOWER, video('uu', 'hard', 3.5)), (pt.NOT_MET, {'easy': pt.MET, 'hard': pt.NOT_MET}))

    def test_any_tie_on_fails_counts_as_fewest_when_kaijuflow_is_the_fastest_of_the_tied(self):
        self.assertEqual(self.bar(*SLOWER, fail('kaijuflow', 'Old Film'), fail('uu', 'Rare Show S01E01'),
                                  fail('altmount-addon', 'Old Film'), fail('altmount-addon', 'Old Film', 2)),
                         (pt.MET, {'easy': pt.MET, 'hard': pt.MET}))  # hard: 1 failed play against 1 and 2

    def test_a_tie_on_fails_with_a_faster_setup_is_not_met(self):
        self.assertEqual(self.bar(*SLOWER, fail('kaijuflow', 'Old Film'), fail('uu', 'Rare Show S01E01'), video('uu', 'hard', 2.0)),
                         (pt.NOT_MET, {'easy': pt.MET, 'hard': pt.NOT_MET}))

    def test_the_bar_is_not_met_on_a_list_where_another_setup_fails_fewer_whatever_the_speed(self):
        self.assertEqual(self.bar(*SLOWER, fail('kaijuflow', 'Matrix'), video('kaijuflow', 'easy', 0.5)),
                         (pt.NOT_MET, {'easy': pt.NOT_MET, 'hard': pt.MET}))

    def test_a_targets_file_whose_speed_test_part_cannot_be_used_gives_one_sentence(self):
        visits = runs.load(speed_run_folder(self))['visits']
        path = os.path.join(tempdir(self), 'targets.json')
        with open(pt.TARGETS_FILE) as f:
            data = json.load(f)
        del data['speed_test']['final_bar']
        with open(path, 'w') as f:
            json.dump(data, f)
        with self.assertRaises(ValueError) as e:
            pt.speed_test_judgement(visits, path)
        self.assertEqual(str(e.exception), 'targets.json, speed test: the final bar has no text')

    def test_a_faster_setup_with_more_fails_does_not_cost_kaijuflow_the_bar(self):
        self.assertEqual(self.bar(*SLOWER, fail('uu', 'Old Film'), video('uu', 'hard', 1.0)),
                         (pt.MET, {'easy': pt.MET, 'hard': pt.MET}))


if __name__ == '__main__':
    unittest.main()
