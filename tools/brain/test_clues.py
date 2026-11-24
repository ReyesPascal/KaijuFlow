"""Tests for the Clues of #284 (spec #279): the NNTP tool's provider read from the test copy's AltMount config, AltMount's
raw answer for an import, and the live read-only Clues (a full STAT sweep, a yEnc CRC check), tried on recorded NNTP
answers (fixtures/2026-11-24-live-clues/README.md) and run once right after a check with a failure.
    python3 -I -m unittest discover -s tools/brain -p 'test_clues.py'
"""
import os
import unittest

import nntp
from test_settings import SECRET, make_copies


class ProviderTest(unittest.TestCase):
    def test_the_provider_is_the_test_copys_first_main_altmount_provider(self):
        td = make_copies(self)
        self.assertEqual(nntp.provider(test_dir=td), ('news.example', 563, SECRET, SECRET))

    def test_the_test_folder_is_test_dir_when_set(self):
        td = make_copies(self)
        old = os.environ.get('TEST_DIR')
        os.environ['TEST_DIR'] = td
        try:
            self.assertEqual(nntp.provider()[0], 'news.example')
        finally:
            if old is None:
                del os.environ['TEST_DIR']
            else:
                os.environ['TEST_DIR'] = old

    def test_a_missing_config_names_the_file_it_looked_for(self):
        with self.assertRaises(FileNotFoundError) as e:
            nntp.provider(test_dir='/nonexistent-test-dir')
        self.assertIn('altmount-kf/config/config.yaml', str(e.exception))


if __name__ == '__main__':
    unittest.main()
