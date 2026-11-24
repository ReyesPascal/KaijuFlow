"""Tests for the evidence folder (#280, spec #279): a check's collection run (brainrun.quick_check_all, the fake world of
test_quickcheck) saves one evidence folder per failed or fallen-back play, from what KaijuFlow, AltMount and the stand-in
really wrote in one failed play (fixtures/2026-11-23-failed-play/), and nothing more for a play that went fine.
    python3 -I -m unittest discover -s tools/brain -p 'test_evidence.py'
"""
import datetime
import json
import os
import shutil
import threading
import unittest
import urllib.request

import brainrun
import brainreport as br
import evidence
import indexer_standin
from test_quickcheck import DRAWN, CheckWorld, check_cfg, read, run_check
from test_settings import SECRET, make_copies, tempdir

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURE = os.path.join(HERE, 'fixtures', '2026-11-23-failed-play')
UTC = datetime.timezone.utc
WITCHER = ['series', 'tt5180504:1:1', 'The Witcher S01E01', 'popular-episode', '2019-12-20']
HHWEB = 'The.Witcher.S01E01.The.Ends.Beginning.2160p.NF.WEB-DL.DDP5.1.Atmos.DV.HEVC-HHWEB'
PLAYWEB = 'The Witcher S01E01 The Ends Beginning 2160p NF WEB-DL DD 5 1 Atmos DoVi HDR H 265-playWEB'
CRYBABIES = 'The.Witcher.S01E01.The.Ends.Beginning.2160p.NF.WEB-DL.DDP5.1.Atmos.DV.H.265-CRYBABIES'
SONARR = "The Witcher - S01E01 - The End's Beginning WEBDL-2160p"
SEARCH = 'api cat=5000&extended=1&q=The Witcher S01E01&t=search'
PLANTED = 'PLANTED-SECRET-9f3'  # a key file's value, planted in both logs, bare and as a query parameter
CHECK = '2026-11-23T191000Z-quick-check'


def captured(name):
    return read(CAPTURE, name)


class FailedPlayWorld(CheckWorld):
    """A check whose first title is the captured failed play (the Witcher, chain A): its list, its press, both containers'
    logs and the stand-in's lines are the captured ones, and the check's store holds the captured search answer and an
    NZB at each stored key its links give. The other four titles play as CheckWorld plays them. AltMount's test copy holds
    its copy of the failed import at the path its log names; a key file holds PLANTED."""

    def __init__(self, settings=None, **kw):
        super().__init__(drawn=[WITCHER] + DRAWN[:4], **kw)
        self.clock = datetime.datetime(2026, 11, 23, 19, 10, 0, tzinfo=UTC)
        self.settings = settings or {'kaijuflow': {'ultimateFallback.whenToResolve': 'on-results', 'altmountApiKey': '***'}}
        self.root = None
        kf = captured('kaijuflow-test.log').splitlines()
        kf.insert(5, f'2026-11-23T19:12:12.700000000Z 🔍 Searching NinjaCentral: http://host.docker.internal:1340/ninjacentral/api?t=tvsearch&apikey={PLANTED}')
        am = captured('altmount-kf-test.log').splitlines()
        am.insert(3, f'2026-11-23T19:12:26.300000000Z time=x level=WARN msg="provider login" component=nntp user=kf pass {PLANTED}')
        self.captured = {brainrun.KF_CONTAINER: kf, brainrun.ALTMOUNT_CONTAINER: am}
        self.nzbs, self.altmount_nzb = {}, b'<nzb>AltMount copy of ' + HHWEB.encode() + b'</nzb>\n'

    def snapshot(self):
        return self.settings

    def open_check_store(self, run_dir):
        super().open_check_store(run_dir)
        self.root = tempdir(self.case)
        d = os.path.join(self.root, 'store', 'check', 'ninjacentral')
        os.makedirs(d)
        items = [tuple(kv.split('=', 1)) for kv in SEARCH[len('api '):].split('&')]
        key = indexer_standin.cache_key('api', items)
        with open(os.path.join(d, key + '.body'), 'wb') as f:
            f.write(captured('search-answer.xml').encode())
        with open(os.path.join(d, key + '.meta.json'), 'w') as f:
            json.dump({'status': 200, 'content_type': 'application/rss+xml', 'request': SEARCH, 'ms': 512}, f)
        for token, title in indexer_standin.nzb_titles(d).items():  # the NZB each stored link gives, as a check stores it
            nzb = indexer_standin.cache_key('nzb', [('token', token)])
            body = f'<nzb>{title}</nzb>\n'.encode()
            self.nzbs[title] = body
            with open(os.path.join(d, nzb + '.body'), 'wb') as f:
                f.write(body)
            with open(os.path.join(d, nzb + '.meta.json'), 'w') as f:
                json.dump({'status': 200, 'content_type': 'application/x-nzb', 'request': 'nzb ' + nzb[:12], 'ms': 871}, f)

    def close_check_store(self):  # as RealIO's: the check's answers are deleted with its store
        super().close_check_store()
        shutil.rmtree(os.path.join(self.root, 'store'))

    def check_answers(self):
        return os.path.join(self.root, 'store', 'check')

    def standin_lines(self):
        return captured('standin.log').splitlines()

    def altmount_file(self, path):
        if path == f'/config/.nzbs/failed/kaijuflow/{HHWEB}.nzb':
            return self.altmount_nzb
        return None

    def secret_values(self):
        return [PLANTED]

    def check_visit(self, kind, vid, pause_s):
        if vid != WITCHER[1]:
            return super().check_visit(kind, vid, pause_s)
        self.calls.append(('visit', vid))
        self.clock = datetime.datetime(2026, 11, 23, 19, 12, 12, 663000, tzinfo=UTC)
        body = json.dumps({'streams': [{'name': 'KaijuFlow', 'title': 'KaijuFlow ▶ Best', 'url': 'http://x/play/stream/ultimate-fallback'},
                                       *({'name': 'KaijuFlow', 'title': t} for t in (HHWEB, PLAYWEB, CRYBABIES, SONARR))]}).encode()

        def press(stream):
            self.clock = datetime.datetime(2026, 11, 23, 19, 12, 31, 500000, tzinfo=UTC)
            return {'plays': True, 'first_byte_s': 14.0, 'note': None}
        self.takes(1.0)
        return brainrun.check_visit_answer((200, {}, body, {'ready': 1.0, 'total': 1.0}), press, pause_s, self.sleep)

    def logs(self, container, since):
        lines = [line for line in self.captured.get(container, []) if line[:24] >= since[:24]]
        return '\n'.join(lines + [super().logs(container, since)])


def run_failed_check(case, **kw):
    cfg, world = check_cfg(case), FailedPlayWorld(**kw)
    world.case = case
    code, out = run_check(cfg, world)
    folder = os.path.join(cfg['runs_root'], CHECK)
    return code, out, folder, world


def files_under(root):
    return sorted(os.path.relpath(os.path.join(d, n), root) for d, _, names in os.walk(root) for n in names)


class FailedPlayEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = cls('test_the_failed_play_gets_one_folder_and_the_played_titles_none')
        cls.case.setUp()
        cls.code, cls.out, cls.folder, cls.world = run_failed_check(cls.case)
        cls.ev = os.path.join(cls.folder, 'evidence', '01-the-witcher-s01e01')

    @classmethod
    def tearDownClass(cls):
        cls.case.doCleanups()

    def meta(self):
        return json.loads(read(self.ev, 'evidence.json'))

    def test_the_failed_play_gets_one_folder_and_the_played_titles_none(self):
        self.assertEqual(self.code, brainrun.EXIT_FAILS, self.out)
        self.assertEqual(os.listdir(os.path.join(self.folder, 'evidence')), ['01-the-witcher-s01e01'])
        raw = json.loads(read(self.folder, 'raw.json'))
        self.assertEqual([o.get('evidence') for o in raw['outcomes']], ['evidence/01-the-witcher-s01e01', None, None, None, None])
        self.assertNotIn('evidence', raw['visits'][1])  # a play that went fine keeps only what a check keeps today
        self.assertEqual(sorted(os.listdir(self.folder)), ['diagnosis.json', 'evidence', 'logs', 'meta.json', 'raw.json', 'report.md', 'settings.json',
                                                           'titles.json'])

    def test_it_says_what_it_is_for_whom_and_why_it_was_kept(self):
        m = self.meta()
        self.assertEqual((m['format'], m['check'], m['kind'], m['title'], m['kept_because']),
                         (1, CHECK, 'quick check', WITCHER, 'fail'))
        self.assertEqual(m['outcome']['outcome'], 'fail')
        self.assertEqual((m['commit'], m['head'], m['dirty']), ('img1', 'head1', False))
        self.assertEqual(json.loads(read(self.ev, 'settings.json')), self.world.settings)

    def test_every_step_line_of_the_play_is_kept_in_order(self):
        want = [s for s in br.parse_step_lines(captured('kaijuflow-test.log'))]
        got = [json.loads(line) for line in read(self.ev, 'steps.jsonl').splitlines()]
        self.assertEqual(got, want)
        self.assertEqual([s['step'] for s in got].count('unscramble'), 2)  # steps a check's raw.json does not keep

    def test_both_logs_and_the_stand_ins_lines_are_kept_scrubbed_with_no_secret(self):
        kf, am = read(self.ev, 'logs', 'kaijuflow-test.log'), read(self.ev, 'logs', 'altmount-kf-test.log')
        self.assertIn('Archive inspection failed (Newshosting): Article not found: 430 No Such Article', kf)
        self.assertIn('msg="Skipping RAR archive group with missing volume(s)" first_file=7a870da9cbcc480a075cde6a2bd4dbd5.10 parts=74', am)
        self.assertIn('apikey=***', kf)
        self.assertEqual(read(self.ev, 'logs', 'standin.log').splitlines(), captured('standin.log').splitlines())
        for name in files_under(self.folder):  # nowhere in the evidence, nor in the check's own logs
            with open(os.path.join(self.folder, name), 'rb') as f:
                self.assertNotIn(PLANTED.encode(), f.read(), name)

    def test_the_nzb_of_every_failed_source_and_altmounts_copy_are_kept(self):
        m = self.meta()
        self.assertEqual(m['failed_sources'], [
            {'release': CRYBABIES, 'failed': 'check', 'status': 'blocked', 'nzb': None},  # in no answer the visit kept
            {'release': SONARR, 'failed': 'check', 'status': 'blocked', 'nzb': None},
            {'release': HHWEB, 'failed': 'import', 'status': None, 'nzb': f'nzbs/{HHWEB}.nzb'}])
        with open(os.path.join(self.ev, 'nzbs', HHWEB + '.nzb'), 'rb') as f:
            self.assertEqual(f.read(), self.world.nzbs[HHWEB])
        self.assertEqual(m['altmount_nzbs'], [{'from': f'/config/.nzbs/failed/kaijuflow/{HHWEB}.nzb',
                                               'nzb': f'nzbs/altmount/{HHWEB}.nzb'}])
        with open(os.path.join(self.ev, 'nzbs', 'altmount', HHWEB + '.nzb'), 'rb') as f:
            self.assertEqual(f.read(), self.world.altmount_nzb)

    def test_the_indexer_answers_are_kept_and_the_stand_in_replays_them(self):
        m = self.meta()
        self.assertEqual(m['answers']['list'], 'answers')
        self.assertEqual(m['answers']['kept'], 3)  # the stored search answer and the two NZBs the visit asked for
        self.assertIn('MISS ninjacentral nzb 49dfcbc6a806 The.Witcher.2019.S01E01.2160p.NF.WEB-DL.H265.SDR.DDP.Atmos.5.1.English-HONE',
                      m['answers']['not_stored'][-1])
        server = indexer_standin.make_server({'indexers': {}}, self.ev, 'replay', 'answers', port=0, bind='127.0.0.1', wait=False)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        q = SEARCH[len('api '):].replace(' ', '%20')
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/ninjacentral/api?{q}&apikey=x', timeout=5) as r:
            body = r.read()
        self.assertIn(HHWEB.encode(), body)

    def test_the_dev_switchs_state_is_recorded(self):
        self.assertEqual(self.meta()['dev_switch'], {'setting': False, 'step_lines': 0, 'of': 17})


class WhichPlaysTest(unittest.TestCase):
    def test_a_fallback_or_a_slow_play_gets_a_folder_and_a_clean_play_none(self):
        clean = {'outcome': 'played', 'fallbacks': 0, 'slow': False}
        self.assertIsNone(evidence.kept_because(clean))
        self.assertEqual(evidence.kept_because({**clean, 'fallbacks': 1}), 'fallback')
        self.assertEqual(evidence.kept_because({**clean, 'slow': True}), 'slow play')
        self.assertEqual(evidence.kept_because({'outcome': 'fail', 'fallbacks': 0}), 'fail')
        self.assertEqual(evidence.kept_because({'outcome': 'nothing to play', 'fallbacks': 0}), 'nothing to play')

    def test_with_the_dev_switch_on_its_state_and_marked_lines_are_recorded(self):
        settings = {'kaijuflow': {'devDiagnostics': True}}
        code, out, folder, world = run_failed_check(self, settings=settings)
        m = json.loads(read(folder, 'evidence', '01-the-witcher-s01e01', 'evidence.json'))
        self.assertEqual(m['dev_switch'], {'setting': True, 'step_lines': 0, 'of': 17})


class RealPartsTest(unittest.TestCase):
    """The parts of RealIO the evidence step reads with, on fixture test copies."""

    def test_the_test_copies_secret_values_are_found_for_scrubbing(self):
        td = make_copies(self)
        values = brainrun.RealIO({'test_dir': td}).secret_values()
        self.assertIn(SECRET, values)
        self.assertTrue(all(len(v) >= 6 for v in values))
        self.assertEqual(evidence.scrub(f'login {SECRET} and apikey=abc123', values), 'login *** and apikey=***')

    def test_only_altmounts_failed_nzbs_are_read_from_its_test_copy(self):
        td = make_copies(self)
        failed = os.path.join(td, 'altmount-kf', 'config', '.nzbs', 'failed', 'kaijuflow')
        os.makedirs(failed)
        with open(os.path.join(failed, 'Rel.nzb'), 'wb') as f:
            f.write(b'<nzb/>')
        real = brainrun.RealIO({'test_dir': td})
        self.assertEqual(real.altmount_file('/config/.nzbs/failed/kaijuflow/Rel.nzb'), b'<nzb/>')
        self.assertIsNone(real.altmount_file('/config/.nzbs/failed/kaijuflow/Gone.nzb'))
        for path in ('/config/config.yaml', '/config/.nzbs/failed/../../config.yaml', '/config/.nzbs/failed/kaijuflow/x.txt'):
            self.assertIsNone(real.altmount_file(path), path)

    def test_the_check_answers_are_the_check_stores_list(self):
        cfg = {'test_dir': tempdir(self)}
        real = brainrun.RealIO(cfg)
        real.open_check_store('/runs/2026-11-25T100000Z-quick-check')
        self.assertEqual(real.check_answers(), os.path.join(cfg['store'], 'check'))
        real.close_check_store()


if __name__ == '__main__':
    unittest.main()
