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
HHWEB = 'The.Witcher.S01E01.The.Ends.Beginning.2160p.NF.WEB-DL.DDP5.1.Atmos.DV.HEVC-HHWEB'


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


if __name__ == '__main__':
    unittest.main()
