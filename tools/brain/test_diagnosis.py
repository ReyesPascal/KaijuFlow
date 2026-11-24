"""Tests for Diagnosis (#283, spec #279), through its one call: an evidence folder in, for each failure of the play one
answer: found (a cause, proved by its Clues), suspected (a look-alike with no confirming test) or new (unmatched).
The evidence folders are real plays cut from run folders (fixtures/2026-11-24-diagnosis/README.md).
    python3 -I -m unittest discover -s tools/brain -p 'test_diagnosis.py'
"""
import contextlib
import io
import json
import os
import shutil
import unittest

import casebook
import clues
import diagnosis
import evidence
from test_evidence import run_failed_check
from test_quickcheck import CheckWorld, check_cfg, read, run_check
from test_settings import tempdir

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURES = os.path.join(HERE, 'fixtures', '2026-11-24-diagnosis')
READ_ERROR = os.path.join(CAPTURES, '219-witcher-read-error')  # HHWEB: read-error, original uploaded, volumes missing
TWO_REFUSALS = os.path.join(CAPTURES, '218-witcher-two-refusals')  # HHWEB read-error, then SiC refused for its extension
DEAD_PACK = os.path.join(CAPTURES, '189-twilight-dead-pack')  # an unchecked season pack, AltMount's fast-fail refused it
INDEXER_DOWN = os.path.join(CAPTURES, '265-inception-indexer-down')  # the search had no answer: an empty list
LOG_CUT = os.path.join(CAPTURES, '287-girlfriends-log-cut')  # video came, the log copied before its played line (#287)
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
                                    'altmount-fast-fail-refused, articles-missing')
        ruled = {t['id']: t for t in f['leads'] if t['result'] == 'ruled out'}
        self.assertEqual(set(ruled), {'unscramble-read-error'})  # it matched (all files failed validation), its recipe said no
        said = {c['clue']: c['answer'] for c in ruled['unscramble-read-error']['clues']}
        self.assertEqual(said['unscramble-read-error'], 'no')


class LibraryTest(unittest.TestCase):
    def test_a_lead_is_proved_by_the_clues_of_the_library_diagnosis_is_given(self):
        [f] = answers(INDEXER_DOWN)
        entry = {'id': 'indexer-down', 'match': [{'rules': 1, 'sign': f['fingerprint']}], 'occurrences': 0,
                 'status': 'open', 'whose': 'indexer', 'confirm': [{'clue': 'only-here', 'answer': 'yes'}]}
        library = dict(clues.CLUES, **{'only-here': clues.Clue('only-here', 'Only in this library?',
                                                                lambda ev, failure: (clues.YES, ['it is here']))})
        [f] = diagnosis.diagnose(INDEXER_DOWN, entries=[entry], library=library)['failures']
        self.assertEqual((f['verdict'], f['cause'], f['proved_by']), ('found', 'indexer-down', ['only-here']))


class FingerprintTest(unittest.TestCase):
    def test_one_cause_seen_in_two_runs_has_one_fingerprint_and_its_details_are_masked(self):
        [in_219], [in_218, sic] = answers(READ_ERROR), answers(TWO_REFUSALS)
        self.assertEqual(in_219['fingerprint'], in_218['fingerprint'])
        self.assertEqual(in_219['fingerprint'], 'check miss | import_wait not ok | AltMount could not process the Source: '
                         '{"error":{"code":"INTERNAL_SERVER_ERROR","details":"","message":"no files were successfully processed '
                         '(all files failed validation)"},"success":false}')
        self.assertTrue(sic['fingerprint'].startswith('check miss | import_wait not ok | AltMount could not process the '
                                                      'Source: {"error":{"code":"INTERNAL_SERVER_ERROR","details":"","message":"'
                                                      "file '<release>' does not match allowed extensions (allowed: [.mkv .mp4 "),
                        sic['fingerprint'])
        self.assertNotIn(SIC, sic['fingerprint'])


def variant(case, folder, outcome, keep=None, failed_sources=False):
    """A copy of a captured play told as another outcome: evidence.json's `outcome` updated, no failed Source (unless
    `failed_sources`: its own kept), and only the step lines up to and with the first `keep` names (all when None)."""
    copy = os.path.join(tempdir(case), os.path.basename(folder))
    shutil.copytree(folder, copy)
    with open(os.path.join(copy, 'evidence.json')) as f:
        meta = json.load(f)
    meta['outcome'] = dict(meta['outcome'], **outcome)
    meta['kept_because'] = evidence.kept_because(meta['outcome'])
    if not failed_sources:
        meta['failed_sources'] = []
    with open(os.path.join(copy, 'evidence.json'), 'w') as f:
        json.dump(meta, f)
    if keep is not None:
        with open(os.path.join(copy, 'steps.jsonl')) as f:
            lines = f.readlines()
        at = next(i for i, line in enumerate(lines) if json.loads(line)['step'] == keep)
        with open(os.path.join(copy, 'steps.jsonl'), 'w') as f:
            f.writelines(lines[:at + 1])
    return copy


def signs_of(kind):
    return {e['id'] for e in diagnosis.load_index() for m in e['match'] if m['sign'].startswith(kind + ' | ')}


class EverySignCanMatchTest(unittest.TestCase):
    def test_a_slow_play_is_where_its_played_source_ended_and_where_its_time_went(self):
        # #218's Witcher told as a slow play: the Walk goes on after the played Source (playWEB) sent its first byte
        folder = variant(self, TWO_REFUSALS, {'outcome': 'played', 'why': '', 'slow': True, 'start_s': 75.0})
        [f] = diagnosis.diagnose(folder)['failures']
        self.assertEqual((f['kind'], f['where'], f['reason']), ('slow play', 'first_byte ok', 'most time in play_check'))
        self.assertEqual({t['id'] for t in f['leads']},
                         {'busy-machine', 'first-title-after-reset-swings', 'health-check-before-list', 'laptop-on-battery',
                          'warm-lists-slow-2026-11-13', 'head-start-ran-on', 'eeaao-slow-start'})

    def test_every_slow_play_sign_can_be_given(self):
        steps = ('nzb_fetch', 'unscramble', 'upload', 'import_wait', 'first_byte', 'play_check')
        reachable = {f'slow play | first_byte ok | most time in {s}' for s in steps}
        for e in diagnosis.load_index():
            for m in e['match']:
                if m['sign'].startswith('slow play | '):
                    with self.subTest(entry=e['id']):
                        self.assertTrue(any(diagnosis.sign_fits(m['sign'], fp) for fp in reachable), m['sign'])

    def test_nothing_to_play_with_the_dev_switch_on_is_where_the_search_failed(self):
        folder = variant(self, LOG_CUT, {'outcome': 'nothing to play', 'why': 'the list was empty', 'sources': 0},
                         keep='list')
        [f] = diagnosis.diagnose(folder)['failures']
        self.assertEqual((f['kind'], f['where']), ('nothing to play', 'indexer_page ok'))  # the search lines come after
        self.assertEqual({t['id'] for t in f['leads']}, signs_of('nothing to play'))


class WrongTitleTest(unittest.TestCase):
    def test_a_wrong_title_play_with_refused_sources_is_a_failure_of_its_own_beside_theirs(self):
        why = 'the wrong title played: The Witcher S01E02 instead of S01E01'
        folder = variant(self, TWO_REFUSALS, {'outcome': 'fail', 'why': why}, failed_sources=True)
        fs = diagnosis.diagnose(folder)['failures']
        self.assertEqual([(f['release'], f['kind']) for f in fs], [(HHWEB, 'check miss'), (SIC, 'check miss'),
                                                                   (None, 'wrong title')])
        self.assertEqual(fs[0]['verdict'], 'found')  # a refused Source's own cause is still found
        self.assertEqual((fs[2]['where'], fs[2]['reason']), ('import_wait not ok', why))  # its last step line


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


# Every Clue, on two real captures: (Clue, capture with the cause present, its failed Source, the same absent).
CLUE_CAPTURES = [
    ('unscramble-read-error', READ_ERROR, HHWEB, DEAD_PACK, TWILIGHT),
    ('original-uploaded-after-unscramble', READ_ERROR, HHWEB, DEAD_PACK, TWILIGHT),
    ('altmount-missing-volumes', READ_ERROR, HHWEB, DEAD_PACK, TWILIGHT),
    ('played-source-unchecked', DEAD_PACK, TWILIGHT, READ_ERROR, HHWEB),
    ('altmount-fast-fail-refused', DEAD_PACK, TWILIGHT, READ_ERROR, HHWEB),
    ('check-passed-source', TWO_REFUSALS, SIC, DEAD_PACK, TWILIGHT),
    ('altmount-extension-refused', TWO_REFUSALS, SIC, TWO_REFUSALS, HHWEB),
    ('articles-missing', DEAD_PACK, TWILIGHT, TWO_REFUSALS, SIC),  # asked live (#284), the answers kept in live.json
    ('log-cut-at-press', LOG_CUT, None, READ_ERROR, HHWEB),  # the play's own failure (no Source failed); the log goes on
]
# Every confirming recipe that runs (all its Clues built), the same way.
RECIPE_CAPTURES = [
    ('unscramble-read-error', READ_ERROR, HHWEB, DEAD_PACK, TWILIGHT),
    ('unchecked-dead-season-pack', DEAD_PACK, TWILIGHT, READ_ERROR, HHWEB),
]


def failure_of(folder, release):
    ev = evidence.read(folder)
    return ev, next(f for f in diagnosis.failures(ev) if f['release'] == release)


class CluesOnRealCapturesTest(unittest.TestCase):
    def test_every_clue_says_yes_with_the_cause_present_and_no_with_it_absent(self):
        for name, yes_folder, yes_release, no_folder, no_release in CLUE_CAPTURES:
            for folder, release, want in ((yes_folder, yes_release, 'yes'), (no_folder, no_release, 'no')):
                with self.subTest(clue=name, capture=os.path.basename(folder), want=want):
                    got = clues.run(name, *failure_of(folder, release))
                    self.assertEqual(got['answer'], want, got['facts'])
                    self.assertTrue(got['facts'])
                    ev = evidence.read(folder)
                    seen = ev.kf_lines + ev.am_lines
                    for f in got['facts']:  # a fact quoting a log line is that line, as the evidence holds it
                        if f.startswith('20') and ' ' in f:
                            self.assertTrue(any(line.startswith(f.rstrip('…')) for line in seen), f)

    def test_every_clue_in_the_library_is_tried_on_two_captures(self):
        from test_clues import TRIED_HERE  # the Clues test_clues.py tries on two captures (#284)
        self.assertEqual(sorted(clues.CLUES), sorted([c[0] for c in CLUE_CAPTURES] + list(TRIED_HERE)))

    def test_every_recipe_that_runs_proves_its_cause_present_and_rules_it_out_absent(self):
        entries = {e['id']: e for e in diagnosis.load_index()}
        for cause, yes_folder, yes_release, no_folder, no_release in RECIPE_CAPTURES:
            lead = dict(entries[cause], sign='*', sign_rules=1)
            for folder, release, want in ((yes_folder, yes_release, 'proved'), (no_folder, no_release, 'ruled out')):
                with self.subTest(recipe=cause, capture=os.path.basename(folder)):
                    ev, f = failure_of(folder, release)
                    self.assertEqual(diagnosis.prove(lead, ev, f, clues.CLUES)['result'], want)

    def test_every_recipe_that_runs_is_tried_on_two_captures(self):
        runs = sorted(e['id'] for e in diagnosis.load_index()
                      if e['confirm'] != casebook.NO_EVIDENCE and all(c['clue'] in clues.CLUES for c in e['confirm']))
        self.assertEqual(runs, sorted(r[0] for r in RECIPE_CAPTURES))


def stored_check(case, name='2026-11-24T070000Z-quick-check', plays=(READ_ERROR, DEAD_PACK)):
    """A runs root holding one check whose evidence/ holds copies of the captured plays, as a check stores them."""
    root = tempdir(case)
    run_dir = os.path.join(root, name)
    for n, folder in enumerate(plays, 1):
        shutil.copytree(folder, os.path.join(run_dir, evidence.DIR, f'{n:02d}-{os.path.basename(folder)}'))
    return root, run_dir


def stored(run_dir):
    out = {}
    for name in sorted(os.listdir(os.path.join(run_dir, evidence.DIR))):
        with open(os.path.join(run_dir, evidence.DIR, name, diagnosis.STORED)) as f:
            out[name] = json.load(f)
    return out


class StoredFailuresTest(unittest.TestCase):
    def test_a_new_masking_version_fingerprints_every_stored_failure_again(self):
        root, run_dir = stored_check(self)
        diagnosis.diagnose_check(run_dir)
        before = stored(run_dir)
        rules = diagnosis.load_rules()
        v = rules['version']
        self.assertEqual({d['rules'] for d in before.values()}, {v})
        rules = dict(rules, version=v + 1, masks=[{'name': 'error code', 'pattern': '[A-Z]+(_[A-Z]+)+', 'with': '<code>'}] + rules['masks'])
        path = os.path.join(tempdir(self), 'masking-rules.json')
        with open(path, 'w') as f:
            json.dump(rules, f)

        changed = diagnosis.refingerprint(root, diagnosis.load_rules(path))

        after = stored(run_dir)
        self.assertEqual(sorted(changed), sorted(os.path.join(run_dir, evidence.DIR, n) for n in after))
        for name, d in after.items():
            self.assertEqual(d['rules'], v + 1)
            old = [f['fingerprint'] for f in before[name]['failures']]
            self.assertEqual(d['earlier'], [{'rules': v, 'fingerprints': old}])
            for f in d['failures']:
                self.assertIn('"code":"<code>"', f['fingerprint'])
                self.assertNotIn('INTERNAL_SERVER_ERROR', f['fingerprint'])
        self.assertEqual(diagnosis.refingerprint(root, diagnosis.load_rules(path)), [])  # the same version: nothing to do


def casebook_copy(case):
    folder = os.path.join(tempdir(case), 'casebook')
    shutil.copytree(casebook.FOLDER, folder)
    return folder


class RecordTest(unittest.TestCase):
    def test_a_proved_cause_gets_the_occurrence_and_a_failed_recipe_goes_into_ruled_out(self):
        root, run_dir = stored_check(self)
        diagnosis.diagnose_check(run_dir)
        book = casebook_copy(self)

        diagnosis.record(run_dir, book)

        entries, problems = casebook.load(book)
        self.assertEqual(casebook.problems(book), [])  # still the format, and the index was written again
        self.assertEqual(entries['unscramble-read-error']['seen'][-1], {
            'check': '2026-11-23T190950Z-grouped-219', 'title': 'The Witcher S01E01', 'play': 'evidence/01-219-witcher-read-error',
            'date': '2026-11-23', 'rules': diagnosis.load_rules()['version']})
        self.assertEqual(entries['unchecked-dead-season-pack']['seen'][-1]['play'], 'evidence/02-189-twilight-dead-pack')
        _, sections = casebook.read_entry(os.path.join(book, 'unscramble-read-error.md'))
        ruled = sections['Ruled out'].splitlines()[-1]
        self.assertTrue(ruled.startswith('- 2026-11-20, 2026-11-20T223814Z-baseline-189, The Twilight Zone S02E06 '
                                         '(evidence/02-189-twilight-dead-pack): matched'), ruled)
        self.assertIn('unscramble-read-error answered no (wanted yes)', ruled)
        _, sections = casebook.read_entry(os.path.join(book, 'unchecked-dead-season-pack.md'))
        self.assertEqual(sections['Ruled out'], 'Nothing tested and rejected yet.')  # proved here, ruled out nowhere

        diagnosis.record(run_dir, book)  # recording again adds nothing
        self.assertEqual(casebook.load(book)[0], entries)


class CommandTest(unittest.TestCase):
    def test_the_diagnose_command_says_one_line_per_failure_and_stores_the_answers(self):
        root, run_dir = stored_check(self, plays=(TWO_REFUSALS, INDEXER_DOWN))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = diagnosis.main(['diagnosis.py', 'diagnose', run_dir])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().splitlines(), [
            f'01-218-witcher-two-refusals: The Witcher S01E01: {HHWEB}: {answers(READ_ERROR)[0]["says"]}',
            f'01-218-witcher-two-refusals: The Witcher S01E01: {SIC}: suspected: no-extension-file-passed (no confirming test)',
            '02-265-inception-indexer-down: Inception: new: no Casebook entry matches',
            '3 failures: 1 new, 2 matched, 1 proved, 2 unexplained'])
        self.assertEqual(len(json.loads(read(run_dir, diagnosis.STORED))['plays']), 2)

    def test_diagnosing_a_check_again_keeps_the_rest_of_its_summary(self):
        root, run_dir = stored_check(self, plays=(INDEXER_DOWN,))
        diagnosis.diagnose_check(run_dir)
        path = os.path.join(run_dir, diagnosis.STORED)
        summary = json.loads(read(run_dir, diagnosis.STORED))
        kept = {'fixes': [{'entry': 'x', 'ticket': '#1'}], 'drill': {'entry': 'x', 'repeated': True},
                'cases': [{'id': 'c', 'status': 'open', 'occurrences': 1, 'new': True}], 'scoreboard': {'n': 1}}
        with open(path, 'w') as f:
            json.dump(dict(summary, **kept), f)
        with contextlib.redirect_stdout(io.StringIO()):
            diagnosis.main(['diagnosis.py', 'diagnose', run_dir])
        again = json.loads(read(run_dir, diagnosis.STORED))
        self.assertEqual({k: again.get(k) for k in kept}, kept)
        self.assertEqual(again['plays'], summary['plays'])

    def test_one_evidence_folder_can_be_diagnosed_alone(self):
        root, run_dir = stored_check(self, plays=(INDEXER_DOWN,))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = diagnosis.main(['diagnosis.py', 'diagnose', os.path.join(run_dir, evidence.DIR, '01-265-inception-indexer-down')])
        self.assertEqual((code, out.getvalue()), (0, '01-265-inception-indexer-down: Inception: new: no Casebook entry matches\n'))


class AfterACheckTest(unittest.TestCase):
    def test_a_check_with_a_failure_runs_diagnosis_by_itself_and_its_report_says_what_it_found(self):
        code, out, folder, world = run_failed_check(self)
        summary = json.loads(read(folder, diagnosis.STORED))
        [play] = summary['plays']
        self.assertEqual(play['evidence'], 'evidence/01-the-witcher-s01e01')
        [f] = play['failures']
        self.assertEqual(f['says'], answers(READ_ERROR)[0]['says'])
        self.assertTrue(os.path.exists(os.path.join(folder, play['evidence'], diagnosis.STORED)))
        report = read(folder, 'report.md')
        self.assertIn('## Diagnosis\n\n1 failure: 0 new, 1 matched, 1 proved, 0 unexplained; open Case logs: 0.\n\n'
                      f'- The Witcher S01E01: {HHWEB}: {f["says"]}.\n', report)

    def test_a_check_with_no_failure_diagnoses_nothing(self):
        cfg = check_cfg(self)
        code, out = run_check(cfg, CheckWorld())
        folder = os.path.join(cfg['runs_root'], '2026-11-25T100000Z-quick-check')
        self.assertFalse(os.path.exists(os.path.join(folder, diagnosis.STORED)))
        report = read(folder, 'report.md')
        self.assertIn('## Diagnosis\n\nNone: no play failed or fell back; open Case logs: 0.\n\nClues: the confirming tests ran 0', report)
        self.assertIn('Fixes: ', report)  # the scoreboard after every check (spec #279)
        self.assertIn('Failures per check by cause (the last 10 checks with a failure):', report)


if __name__ == '__main__':
    unittest.main()
