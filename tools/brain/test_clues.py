"""Tests for the Clues of #284 (spec #279): the NNTP tool's provider read from the test copy's AltMount config, AltMount's
raw answer for an import, and the live read-only Clues (a full STAT sweep, a yEnc CRC check), tried on recorded NNTP
answers (fixtures/2026-11-24-live-clues/README.md) and run once right after a check with a failure.
    python3 -I -m unittest discover -s tools/brain -p 'test_clues.py'
"""
import copy
import json
import os
import unittest

import clues
import evidence
import nntp
import yenc
from test_diagnosis import DEAD_PACK, HHWEB, READ_ERROR, SIC, TWILIGHT, TWO_REFUSALS
from test_settings import SECRET, make_copies

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(HERE, 'fixtures', '2026-11-24-live-clues')
PLAYWEB = 'The Witcher S01E01 The Ends Beginning 2160p NF WEB-DL DD 5 1 Atmos DoVi HDR H 265-playWEB'
SIC_NZB = os.path.join(LIVE, 'sic-asrequested.nzb')  # every article there, its sampled bodies whole
DEAD_NZB = os.path.join(LIVE, 'aaf-tz-s02e06-dead.nzb')  # its articles gone from the provider
# The Clues this file tries on two captures (test_diagnosis.CLUE_CAPTURES tries the others).
TRIED_HERE = ('altmount-refused-import', 'segment-crc-bad')


def recorded():
    with open(os.path.join(LIVE, 'answers.json')) as f:
        return json.load(f)


def nfo_lines():
    """The recorded body of a real 2538-byte .nfo article, as BODY gives it (dot-unstuffed lines)."""
    with open(os.path.join(LIVE, 'nfo-article.yenc'), 'rb') as f:
        return f.read().split(b'\r\n')[:-1]


class Replay:
    """A Usenet that gives the recorded answers, in the order they were recorded, and refuses anything it has no
    recorded answer for (a real server would not have answered it the way a guess would)."""

    def __init__(self, answers=None):
        self.answers = copy.deepcopy(answers or recorded())
        self.closed, self.asked = False, 0

    def _next(self, kind, mid):
        left = self.answers[kind].get(mid)
        if not left:
            raise AssertionError(f'no recorded {kind} answer left for {mid}')
        self.asked += 1
        return left.pop(0)

    def stat(self, mids):
        assert not self.closed
        return [self._next('stat', m) for m in mids]

    def body(self, mid):
        assert not self.closed
        return self._next('body', mid)

    def close(self):
        self.closed = True


class Kept:
    """An evidence folder that kept one NZB, for a live Clue asked about it directly."""

    def __init__(self, path):
        with open(path, 'rb') as f:
            self.body = f.read()

    def nzb(self, release):
        return self.body


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


class AltMountAnswerTest(unittest.TestCase):
    """altmount-refused-import on real captures (fixtures/2026-11-24-diagnosis/): AltMount's raw answer to KaijuFlow and the
    reasons its log gives for that one import."""

    def ask(self, folder, release):
        return clues.run('altmount-refused-import', evidence.read(folder), {'release': release})

    def test_a_refused_import_gives_altmounts_answer_code_its_error_and_the_reason_under_it(self):
        got = self.ask(READ_ERROR, HHWEB)
        self.assertEqual(got['answer'], 'yes', got['facts'])
        self.assertEqual(got['facts'][0], 'AltMount answered KaijuFlow INTERNAL_SERVER_ERROR: no files were successfully '
                                          'processed (all files failed validation)')
        self.assertEqual(got['facts'][1], 'queue item 10: Processing failed: no files were successfully processed (all '
                                          'files failed validation)')
        self.assertTrue(any('msg="Skipping RAR archive group with missing volume(s)"' in f for f in got['facts'][2:]), got['facts'])
        self.assertFalse(any('First segment has no data' in f for f in got['facts']), got['facts'])

    def test_a_fast_fail_refusal_gives_its_own_answer_and_reasons(self):
        got = self.ask(DEAD_PACK, TWILIGHT)
        self.assertEqual(got['answer'], 'yes', got['facts'])
        self.assertIn('fast-fail segment check failed', got['facts'][0])
        self.assertTrue(any('Skipping file due to early fast-fail segment check error' in f for f in got['facts']), got['facts'])

    def test_an_import_altmount_took_answers_no(self):
        got = self.ask(READ_ERROR, PLAYWEB)
        self.assertEqual(got['answer'], 'no', got['facts'])
        self.assertEqual(got['facts'], ['queue item 11: Successfully processed queue item'])


class YencTest(unittest.TestCase):
    def test_a_whole_article_matches_its_trailer(self):
        got = yenc.check(nfo_lines())
        self.assertEqual((got['intact'], got['size'], got['crc']), (True, 2538, '1d74bd1e'))

    def test_a_body_cut_short_or_changed_does_not(self):
        lines = nfo_lines()
        self.assertEqual(yenc.check(lines[:-2])['why'], 'no =yend line: the body ends early')
        changed = lines[:2] + [lines[2][:5] + bytes([lines[2][5] ^ 1]) + lines[2][6:]] + lines[3:]
        got = yenc.check(changed)
        self.assertFalse(got['intact'])
        self.assertTrue(got['why'].startswith('CRC32 '), got['why'])
        self.assertEqual(yenc.check(lines[:2] + lines[3:])['why'], '2410 bytes decoded, its trailer names 2538')


class SweepTest(unittest.TestCase):
    """articles-missing asked live, on recorded NNTP answers."""

    def test_a_release_with_every_article_says_no_after_asking_all_of_them(self):
        usenet = Replay()
        got = clues.run_live('articles-missing', Kept(SIC_NZB), {'release': 'SiC'}, usenet)
        self.assertEqual(got['answer'], 'no', got['facts'])
        self.assertEqual(got['facts'], ['STAT of all 1872 articles of 1 file (par2 left out): 0 missing (430 when asked '
                                        'twice), 0 other answers'])
        self.assertEqual(usenet.asked, 1872)

    def test_a_dead_release_says_yes_and_stops_after_ten_misses_each_asked_twice(self):
        usenet = Replay()
        got = clues.run_live('articles-missing', Kept(DEAD_NZB), {'release': 'aAF'}, usenet)
        self.assertEqual(got['answer'], 'yes', got['facts'])
        self.assertEqual(got['facts'][0], 'STAT of 10 of 1551 articles of 27 files (par2 left out): 10 missing (430 when '
                                          'asked twice), 0 other answers; the sweep stopped once 10 had not answered 223')
        self.assertEqual(usenet.asked, 20)

    def test_a_moments_miss_that_answers_the_second_time_is_not_counted(self):
        answers = recorded()
        first = clues.nzb_files(Kept(SIC_NZB).body)[2][1][0][2]  # 3YuT.mkv's first article
        answers['stat'][first] = [430, 223]
        got = clues.run_live('articles-missing', Kept(SIC_NZB), {'release': 'SiC'}, Replay(answers))
        self.assertEqual(got['answer'], 'no', got['facts'])

    def test_with_no_nzb_kept_it_cannot_tell_and_asks_nothing(self):
        usenet = Replay()
        got = clues.run_live('articles-missing', evidence.read(TWO_REFUSALS), {'release': HHWEB}, usenet)
        self.assertEqual((got['answer'], usenet.asked), ("can't tell", 0))


class KeptAnswersTest(unittest.TestCase):
    """A diagnosis reads the live Clues' answers the check kept (live.json); it never asks again."""

    def test_the_kept_answer_is_given_with_when_it_was_asked(self):
        ev = evidence.read(TWO_REFUSALS)
        got = clues.run('segment-crc-bad', ev, {'release': SIC})
        self.assertEqual(got['answer'], 'no', got['facts'])
        self.assertEqual(got['facts'][0], 'asked live at 2026-11-24T10:51:46.034Z')
        self.assertEqual(clues.run('articles-missing', evidence.read(DEAD_PACK), {'release': TWILIGHT})['answer'], 'yes')

    def test_a_source_not_asked_live_cannot_tell(self):
        got = clues.run('articles-missing', evidence.read(READ_ERROR), {'release': HHWEB})
        self.assertEqual(got, {'clue': 'articles-missing', 'answer': "can't tell", 'facts': [
            f'articles-missing was not asked live for {HHWEB}: no NZB of it was kept']})


class CrcTest(unittest.TestCase):
    """segment-crc-bad asked live: the first, middle and last article of the biggest file, read and checked."""

    def test_whole_bodies_say_no(self):
        got = clues.run_live('segment-crc-bad', Kept(SIC_NZB), {'release': 'SiC'}, Replay())
        self.assertEqual(got['answer'], 'no', got['facts'])
        self.assertEqual(got['facts'][1:], [f'3YuT.mkv article {n}: size and CRC32 match its trailer' for n in (1, 937, 1872)])

    def test_a_body_that_comes_back_cut_short_says_yes(self):
        # Derived: no damaged article was found on the provider, so the middle article's answer is the real .nfo
        # article's body cut short (a truncated transfer), as yenc.check reads it.
        answers = recorded()
        middle = clues.nzb_files(Kept(SIC_NZB).body)[2][1][936][2]
        answers['body'][middle] = [dict(yenc.check(nfo_lines()[:-2]), code=222)]
        got = clues.run_live('segment-crc-bad', Kept(SIC_NZB), {'release': 'SiC'}, Replay(answers))
        self.assertEqual(got['answer'], 'yes', got['facts'])
        self.assertIn('3YuT.mkv article 937: no =yend line: the body ends early', got['facts'])

    def test_articles_the_provider_lost_cannot_tell(self):
        got = clues.run_live('segment-crc-bad', Kept(DEAD_NZB), {'release': 'aAF'}, Replay())
        self.assertEqual(got['answer'], "can't tell", got['facts'])


if __name__ == '__main__':
    unittest.main()
