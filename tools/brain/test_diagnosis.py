"""Tests for Diagnosis (#283, spec #279), through its one call: an evidence folder in, for each failure of the play one
answer: found (a cause, proved by its Clues), suspected (a look-alike with no confirming test) or new (unmatched).
The evidence folders are real plays cut from run folders (fixtures/2026-11-24-diagnosis/README.md).
    python3 -I -m unittest discover -s tools/brain -p 'test_diagnosis.py'
"""
import os
import unittest

import diagnosis

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURES = os.path.join(HERE, 'fixtures', '2026-11-24-diagnosis')
READ_ERROR = os.path.join(CAPTURES, '219-witcher-read-error')  # HHWEB: read-error, original uploaded, volumes missing
TWO_REFUSALS = os.path.join(CAPTURES, '218-witcher-two-refusals')  # HHWEB read-error, then SiC refused for its extension
DEAD_PACK = os.path.join(CAPTURES, '189-twilight-dead-pack')  # an unchecked season pack, AltMount's fast-fail refused it
INDEXER_DOWN = os.path.join(CAPTURES, '265-inception-indexer-down')  # the search had no answer: an empty list
HHWEB = 'The.Witcher.S01E01.The.Ends.Beginning.2160p.NF.WEB-DL.DDP5.1.Atmos.DV.HEVC-HHWEB'
SIC = 'The.Witcher.S01E01.2160p.NF.WEB-DL.DDPA5.1.HDR.DV.HEVC-SiC-AsRequested'
TWILIGHT = 'The.Twilight.Zone.(1959).S02.(1080p.BDRip.x265.10bit.FLAC.2.0.-.Frys).[TAoE]'


def answers(folder):
    return diagnosis.diagnose(folder)['failures']


class FoundTest(unittest.TestCase):
    def test_a_failure_with_a_proved_cause_says_found_and_names_its_clues(self):
        [f] = answers(READ_ERROR)
        self.assertEqual(f['release'], HHWEB)
        self.assertEqual(f['verdict'], 'found')
        self.assertEqual(f['cause'], 'unscramble-read-error')
        self.assertEqual(f['proved_by'], ['unscramble-read-error', 'original-uploaded-after-unscramble', 'altmount-missing-volumes'])
        self.assertEqual(f['says'], 'found: unscramble-read-error, proved by Clues unscramble-read-error, '
                                    'original-uploaded-after-unscramble, altmount-missing-volumes')

    def test_a_look_alike_whose_lead_is_ruled_out_is_found_by_the_lead_that_proves(self):
        [f] = answers(DEAD_PACK)
        self.assertEqual((f['release'], f['kind'], f['verdict']), (TWILIGHT, 'fail', 'found'))
        self.assertEqual(f['says'], 'found: unchecked-dead-season-pack, proved by Clues played-source-unchecked, '
                                    'altmount-fast-fail-refused')
        ruled = {t['id']: t for t in f['leads'] if t['result'] == 'ruled out'}
        self.assertEqual(set(ruled), {'unscramble-read-error'})  # it matched (all files failed validation), its recipe said no
        said = {c['clue']: c['answer'] for c in ruled['unscramble-read-error']['clues']}
        self.assertEqual(said['unscramble-read-error'], 'no')


class SuspectedAndNewTest(unittest.TestCase):
    def test_each_failure_of_a_play_is_answered_and_a_look_alike_without_a_confirming_test_is_suspected(self):
        first, second = answers(TWO_REFUSALS)
        self.assertEqual((first['release'], first['says']), (HHWEB, answers(READ_ERROR)[0]['says']))
        self.assertEqual(second['release'], SIC)
        self.assertEqual(second['verdict'], 'suspected')
        self.assertEqual(second['says'], 'suspected: no-extension-file-passed (no confirming test)')
        self.assertEqual(second['cause'], 'no-extension-file-passed')
        [lead] = second['leads']
        self.assertIn('nzb-file-without-extension', lead['why'])

    def test_an_unmatched_failure_is_new(self):
        [f] = answers(INDEXER_DOWN)
        self.assertEqual(f['fingerprint'], 'fail | indexer_page not ok | the list held no Source, and <indexer> did not '
                                           'answer its search (page <n>)')
        self.assertEqual((f['verdict'], f['leads'], f['says']), ('new', [], 'new: no Casebook entry matches'))


if __name__ == '__main__':
    unittest.main()
