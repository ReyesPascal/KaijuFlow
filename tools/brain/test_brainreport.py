"""Tests for brainreport.py (log parsing, merge, failure split, diff, report, run records). No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import datetime
import json
import os
import tempfile
import unittest

import brainreport as br

KF_LOG = """2026-11-10T18:00:01.100000000Z [KF-STEP] {"step":"indexer_page","source":"NinjaCentral","ms":200,"ok":true,"t":"2026-11-10T18:00:01.000Z","ref":"tt1","page":1}
2026-11-10T18:00:01.300000000Z [KF-STEP] {"step":"indexer_page","source":"NinjaCentral","ms":100,"ok":true,"t":"2026-11-10T18:00:01.200Z","ref":"tt1","page":2}
2026-11-10T18:00:01.400000000Z [KF-STEP] {"step":"indexer_page","source":"DrunkenSlug","ms":250,"ok":true,"t":"2026-11-10T18:00:01.300Z","ref":"tt1","page":1}
2026-11-10T18:00:02.000000000Z [KF-STEP] {"step":"health_batch","ms":1500,"ok":true,"t":"2026-11-10T18:00:02.000Z","ref":"tt1","count":3,"checked":3,"indexers":["NinjaCentral"]}
2026-11-10T18:00:02.100000000Z [KF-STEP] {"step":"health_batch","ms":500,"ok":true,"t":"2026-11-10T18:00:02.100Z","ref":"tt1","count":3,"checked":3,"indexers":["NinjaCentral"]}
2026-11-10T18:00:03.000000000Z [KF-STEP] {"step":"indexer_page","source":"NinjaCentral","ms":99,"ok":true,"t":"2026-11-10T18:00:03.000Z","ref":"tt2","page":1}
2026-11-10T18:00:05.000000000Z [KF-STEP] {"step":"nzb_fetch","source":"NinjaCentral","ms":300,"ok":true,"t":"2026-11-10T18:00:05.000Z","title":"Rel.A"}
2026-11-10T18:00:05.100000000Z [KF-STEP] {"step":"unscramble","source":"NinjaCentral","ms":700,"ok":true,"t":"2026-11-10T18:00:05.100Z","title":"Rel.A","result":"unscrambled","parts":4}
2026-11-10T18:00:06.000000000Z [KF-STEP] {"step":"import_wait","source":"NinjaCentral","ms":2000,"ok":true,"t":"2026-11-10T18:00:06.000Z","title":"Rel.A","includes_upload":true,"job":"1"}
2026-11-10T18:00:06.100000000Z [KF-STEP] {"step":"first_byte","source":"NinjaCentral","ms":150,"ok":true,"t":"2026-11-10T18:00:06.100Z","title":"Rel.A","job":"1"}
some other line
2026-11-10T18:00:06.200000000Z [KF-STEP] {broken json
"""

AM_LOG = """2026-11-10T18:00:03.000000000Z time=2026-11-10T12:00:03.000-06:00 level=INFO msg="Added NZB file to queue" component=importer-service file="/tmp/.altmount-queue/Rel A.nzb" queue_id=7 file_size=1
2026-11-10T18:00:05.500000000Z time=x level=INFO msg="Successfully processed queue item" component=importer-service queue_id=7 file="/tmp/.altmount-queue/Rel A.nzb"
2026-11-10T18:00:06.000000000Z time=x level=INFO msg="Added NZB file to queue" component=importer-service file=/tmp/.altmount-queue/Bad.nzb queue_id=8 file_size=1
2026-11-10T18:00:06.400000000Z time=x level=ERROR msg="Item failed" component=importer-service queue_id=8 file=/tmp/.altmount-queue/Bad.nzb
"""

NZBDAV_LOG = """2026-11-10T18:00:10.000000000Z POST /api?mode=addfile&cat=Movies&nzbname=Rel.A&apikey=SECRETKEY 200 - - 55.0 ms
2026-11-10T18:00:13.500000000Z [INF] Job completed: Rel.A
2026-11-10T18:00:20.000000000Z POST /api?mode=addfile&cat=Movies&nzbname=Rel%20B&apikey=SECRETKEY 500 - - 55.0 ms
"""


def dt(s):
    return br.parse_ts(s)


class ParseTest(unittest.TestCase):
    def test_step_lines_parsed_and_junk_skipped(self):
        steps = br.parse_step_lines(KF_LOG)
        self.assertEqual(len(steps), 10)
        self.assertEqual(steps[0]['step'], 'indexer_page')

    def test_altmount_imports(self):
        imps = br.altmount_imports(AM_LOG)
        self.assertEqual([i['ok'] for i in imps], [True, False])
        self.assertAlmostEqual(imps[0]['seconds'], 2.5)
        self.assertEqual(imps[0]['name'], 'Rel A')

    def test_nzbdav_imports_start_end_and_rejection(self):
        imps = br.nzbdav_imports(NZBDAV_LOG)
        self.assertAlmostEqual(imps[0]['seconds'], 3.5)
        self.assertTrue(imps[0]['ok'])
        self.assertFalse(imps[1]['ok'])
        self.assertNotIn('SECRETKEY', json.dumps(imps))

    def test_nzbdav_without_end_line_has_no_seconds(self):
        imps = br.nzbdav_imports(NZBDAV_LOG.split('\n')[0])
        self.assertIsNone(imps[0]['seconds'])

    def test_limit_event_names_indexer(self):
        text = ('2026-11-10T18:00:01Z all fine\n'
                '2026-11-10T18:05:00.5Z DrunkenSlug: API limit reached, Retry in 40 minutes\n')
        ev = br.limit_event(text, ['NinjaCentral', 'DrunkenSlug'])
        self.assertEqual(ev['indexer'], 'DrunkenSlug')
        self.assertTrue(ev['time'].startswith('2026-11-10T18:05:00'))
        self.assertIsNone(br.limit_event('size 4290000 bytes, 1429 items\n', ['x']))

    def test_limit_event_uses_the_wordings_the_sides_print(self):
        for line in ('2026-11-10T18:05:00Z Indexer search failed indexer=althub error="newsnab: search returned HTTP 429 (althub): '
                     'newznab API error 500: Request limit reached. Retry in 113 minutes"',
                     '2026-11-10T18:05:00Z LIMIT_REACHED indexer=althub at=2026-11-10T18:05:00Z status=200',
                     '2026-11-10T18:05:00Z Failed to download NZB from althub: 429 Too Many Requests (indexer unavailable, Source kept)',
                     '2026-11-10T18:05:00Z    Status: 429'):
            self.assertIsNotNone(br.limit_event(line + '\n', ['althub']), line)
        self.assertEqual(br.limit_event('2026-11-10T18:05:00Z altHUB: text\n2026-11-10T18:05:01Z \u274c Search error for altHUB:\n'
                                        '2026-11-10T18:05:01Z    Status: 429\n', ['altHUB'])['indexer'], 'altHUB')

    def test_limit_event_ignores_benign_lines(self):
        for line in ('Backup processing limit reached (3/3) - draining pool', 'Download limit: 5 per minute (setting)',
                     'API limit set to 100 in the config', 'rate limit middleware loaded', 'Grabbed 429 bytes',
                     'size 1429 items, status=4290', 'Connection limit exceeded for provider'):
            self.assertIsNone(br.limit_event('2026-11-10T18:05:00Z ' + line + '\n', ['x']), line)


class StatsTest(unittest.TestCase):
    def visit(self, **kw):
        v = dict(side='kaijuflow', phase='cold', round=1, title='Matrix', id='tt1', ok=True, list_s=4.0, sources=5,
                 start_s=3.0, note=None, steps=br.parse_step_lines(KF_LOG)[:10], imports=[],
                 t_start='2026-11-10T18:00:00Z', t_end='2026-11-10T18:00:07Z', limit=None, plays=True)
        v.update(kw)
        return v

    def test_metrics_from_steps(self):
        m = br.visit_metrics(self.visit())
        self.assertEqual(m['search_s'], 4.0)
        self.assertEqual(m['nzb_fetch_s'], 0.3)
        self.assertEqual(m['import_s'], 2.0)
        self.assertEqual(m['start_s'], 3.0)
        self.assertEqual(m['health_s'], 2.0)
        self.assertEqual(m['unscramble_s'], 0.7)
        # only this title's pages (ref tt1): slowest indexer = Ninja 300 ms
        self.assertEqual(m['indexer_wait_s'], 0.3)
        self.assertEqual(m['probe_s'], 0.15)

    def test_other_side_import_from_backend_log(self):
        v = self.visit(side='uu', steps=[], imports=[{'ok': True, 'seconds': 3.5}])
        m = br.visit_metrics(v)
        self.assertEqual(m['import_s'], 3.5)
        self.assertIsNone(m['nzb_fetch_s'])
        self.assertIsNone(m['health_s'])

    def test_failure_split(self):
        c = br.classify_failure
        self.assertIsNone(c(self.visit()))
        self.assertEqual(c(self.visit(ok=False, limit={'indexer': 'X'}, note='failure video')), 'indexer_limit')
        self.assertEqual(c(self.visit(ok=False, imports=[{'ok': False}], note='failure video')), 'backend_rejection')
        self.assertEqual(c(self.visit(ok=False, note='failure video')), 'failure_video')
        self.assertEqual(c(self.visit(ok=False, note='HTTP 500')), 'other')

    def test_median(self):
        self.assertEqual(br.median([1, 3, None, 2]), 2)
        self.assertIsNone(br.median([None]))


class DiffTest(unittest.TestCase):
    base = {'settings': {'kaijuflow': {'a.sampleCount': 3, 'b': 1}}, 'commit': 'aaa', 'dirty': False,
            'titles': ['Matrix', 'Dune'], 'indexers': ['ninjacentral'], 'sides': ['kaijuflow'],
            'started': '2026-11-10T18:00:00Z'}

    def test_first_run(self):
        self.assertIn('first', br.diff_runs(None, self.base)[0].lower())

    def test_nothing_changed(self):
        out = br.diff_runs(self.base, dict(self.base))
        self.assertTrue(out[0].startswith('Nothing changed'))

    def test_time_of_day_of_both_runs_is_always_listed(self):
        cur = dict(self.base, started='2026-11-10T18:30:00Z')  # half an hour later
        text = '\n'.join(br.diff_runs(self.base, cur))
        self.assertIn('Time of day', text)
        self.assertIn('18:00', text)
        self.assertIn('18:30', text)

    def test_null_runs_between_are_counted_with_times(self):
        cur = dict(self.base, started='2026-11-11T09:00:00Z')
        nulls = [{'started': '2026-11-10T20:00:00Z', 'null': {'indexer': 'altHUB'}},
                 {'started': '2026-11-10T22:30:00Z', 'null': {'indexer': 'DrunkenSlug'}}]
        text = '\n'.join(br.diff_runs(self.base, cur, nulls))
        self.assertIn('2 null runs', text)
        self.assertIn('2026-11-10 20:00', text)
        self.assertIn('2026-11-10 22:30', text)
        self.assertNotIn('null run', '\n'.join(br.diff_runs(self.base, cur)))

    def test_null_runs_between_found_in_runs_root(self):
        root = tempfile.mkdtemp()
        for name, status, started in (('a', 'ok', '2026-11-10T10:00:00Z'), ('b', 'null', '2026-11-10T11:00:00Z'),
                                      ('c', 'ok', '2026-11-10T12:00:00Z'), ('d', 'null', '2026-11-10T13:00:00Z')):
            os.makedirs(os.path.join(root, name))
            with open(os.path.join(root, name, 'meta.json'), 'w') as f:
                json.dump({'status': status, 'started': started}, f)
        found = br.null_runs_between(root, '2026-11-10T10:00:00Z', exclude='d')
        self.assertEqual([n['started'] for n in found], ['2026-11-10T11:00:00Z'])

    def test_every_kind_of_change(self):
        cur = json.loads(json.dumps(self.base))
        cur['settings']['kaijuflow']['a.sampleCount'] = 5
        cur['settings']['kaijuflow']['new'] = 'x'
        del cur['settings']['kaijuflow']['b']
        cur.update(commit='bbb', titles=['Matrix', 'Heat'], indexers=['ninjacentral', 'althub'], started='2026-11-11T02:00:00Z')
        text = '\n'.join(br.diff_runs(self.base, cur))
        for part in ('kaijuflow a.sampleCount: 3 -> 5', 'kaijuflow new: (not set) -> x', 'kaijuflow b: 1 -> (not set)',
                     'KaijuFlow code: aaa -> bbb', 'Titles added: Heat', 'Titles removed: Dune',
                     'Indexers added: althub', 'Time of day'):
            self.assertIn(part, text)


class ScrubTest(unittest.TestCase):
    def test_only_real_secret_fields_are_masked(self):
        flat = br.flatten({'bypass_x': 'on', 'maxUsers': 5, 'max_users': 6, 'keepAlive': 1, 'keywords': 'a', 'passes': 2,
                           'apiKey': 'S1', 'API_KEY': 'S2', 'api-key': 'S3', 'password': 'S4', 'Password': 'S5',
                           'username': 'S6', 'user': 'S7', 'login': 'S8', 'authToken': 'S9', 'jwtSecret': 'S10',
                           'usenet': {'pass': 'S11', 'host': 'news.example'}, 'nzbdavApiKey': 'S12'})
        for k in ('bypass_x', 'maxUsers', 'max_users', 'keepAlive', 'keywords', 'passes', 'usenet.host'):
            self.assertNotEqual(flat[k], '***', k)
        for k in ('apiKey', 'API_KEY', 'api-key', 'password', 'Password', 'username', 'user', 'login', 'authToken',
                  'jwtSecret', 'usenet.pass', 'nzbdavApiKey'):
            self.assertEqual(flat[k], '***', k)

    def test_secrets_removed(self):
        flat = br.flatten({'apiKey': 'S3CRET', 'url': 'http://h/api?apikey=S3CRET&x=1', 'n': 3,
                           'nested': {'password': 'pw', 'maxPages': 3}, 'lst': [{'token': 't'}]})
        text = json.dumps(flat)
        for bad in ('S3CRET', '"pw"', '"t"'):
            self.assertNotIn(bad, text)
        self.assertEqual(flat['nested.maxPages'], 3)
        self.assertIn('x=1', flat['url'])

    def test_yaml_flatten_and_scrub(self):
        y = 'usenet:\n  providers:\n    - host: news.example\n      password: hunter2\nimport:\n  max_processor_workers: 2\napi_key: abc\n'
        flat = br.flatten_yaml(y)
        self.assertEqual(flat['import.max_processor_workers'], '2')
        self.assertNotIn('hunter2', json.dumps(flat))
        self.assertNotIn('abc', json.dumps(flat))


def runs_fixture(failing=False):
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


class ReportTest(unittest.TestCase):
    def test_report_structure_and_order(self):
        text = br.render_report(runs_fixture(), ['First run.'])
        order = [text.index(h) for h in ('What changed since the last run', 'Steps every side shares',
                                         'Extras', 'Failures', 'Per title')]
        self.assertEqual(order, sorted(order))
        self.assertLess(text.index('\n'), text.index('What changed'))
        first = text.split('\n')[0]
        self.assertIn('KaijuFlow', first)
        self.assertEqual(text.count('Usenet Ultimate') > 0, True)
        self.assertNotIn('AltMount-addon', text)
        self.assertIn('Cold 1', text)
        self.assertIn('Warm 2', text)
        self.assertNotIn('Ultimate Fallback', text)

    def test_every_column_defined(self):
        text = br.render_report(runs_fixture(), [])
        for col in br.COLUMN_HELP:
            self.assertIn('**' + col + '**', text)

    def test_failures_counted_by_cause(self):
        text = br.render_report(runs_fixture(failing=True), [])
        self.assertIn('failure video', text.lower())

    def test_null_report_has_no_numbers(self):
        run = runs_fixture()
        run.update(status='null', null={'indexer': 'DrunkenSlug', 'time': '2026-11-10T18:05:00Z', 'where': 'x'})
        text = br.render_null_report(run)
        self.assertIn('DrunkenSlug', text)
        self.assertIn('2026-11-10T18:05:00Z', text)
        self.assertNotIn('median', text.lower())
        self.assertNotIn(' s ', text)

    def test_headline_numbers_for_index(self):
        h = br.headline(runs_fixture())
        self.assertIn('KaijuFlow', h)
        self.assertIn('2', h)


STANDIN_LOG = [
    'HIT ninjacentral api t=search&q=matrix wait_ms=400',
    'HIT ninjacentral api t=search&q=matrix&offset=100 wait_ms=300',
    'HIT drunkenslug api t=search&q=matrix wait_ms=500',
    'HIT ninjacentral api t=get&id=7 wait_ms=900',
    'MISS drunkenslug api t=search&q=matrix&offset=100',
    'MISS ninjacentral nzb abcdef123456',
    'HIT ninjacentral api t=search&q=matrix wait_ms=0',
    'HIT drunkenslug api t=search&q=matrix',
]


class StandinLinesTest(unittest.TestCase):
    def test_parse_lines(self):
        p = br.parse_standin_lines(STANDIN_LOG)
        self.assertEqual(p['misses'], ['drunkenslug api t=search&q=matrix&offset=100', 'ninjacentral nzb abcdef123456'])
        # indexers are asked at the same time: the slowest indexer's search waits added up; NZB files are not search time
        self.assertEqual(p['indexer_s'], 0.7)

    def test_no_lines_means_zero_wait(self):
        p = br.parse_standin_lines([])
        self.assertEqual((p['misses'], p['indexer_s']), ([], 0))

    def test_lines_go_to_the_visit_that_was_running(self):
        vs = [dict(log_from=0), dict(log_from=3), dict(log_from=5)]
        br.assign_standin(vs, STANDIN_LOG)
        self.assertEqual(vs[0]['indexer_s'], 0.7)
        self.assertEqual(vs[0]['misses'], [])
        self.assertEqual(vs[1]['misses'], ['drunkenslug api t=search&q=matrix&offset=100'])
        self.assertEqual(vs[1]['indexer_s'], 0)  # the NZB file's wait is not search time
        self.assertEqual(vs[2]['misses'], ['ninjacentral nzb abcdef123456'])

    def test_visit_without_a_mark_is_left_alone(self):
        vs = [dict(side='old')]
        br.assign_standin(vs, STANDIN_LOG)
        self.assertNotIn('misses', vs[0])


def with_misses():
    run = runs_fixture()
    for v in run['visits']:
        v['misses'], v['indexer_s'] = [], 1.0
    uu_cold1 = next(v for v in run['visits'] if v['side'] == 'uu' and v['phase'] == 'cold' and v['round'] == 1)
    uu_cold1.update(ok=False, note='no Sources', misses=['ninjacentral api t=search&q=matrix', 'drunkenslug api t=search&q=matrix'])
    kf_warm1 = next(v for v in run['visits'] if v['side'] == 'kaijuflow' and v['phase'] == 'warm' and v['round'] == 1)
    kf_warm1['misses'] = ['drunkenslug api t=search&q=matrix&offset=100']  # still played
    run['topup_command'] = 'python3 -I tools/brain/brainrun.py record --name x --store S --list L'
    run['standin_misses'] = 3
    return run


class MissReportTest(unittest.TestCase):
    def test_failure_with_a_miss_is_its_own_cause(self):
        run = with_misses()
        v = next(v for v in run['visits'] if v['side'] == 'uu' and v['phase'] == 'cold' and v['round'] == 1)
        self.assertEqual(br.classify_failure(v), 'not_recorded')
        self.assertEqual(br.classify_failure(dict(v, limit={'indexer': 'x'})), 'indexer_limit')  # the cap rule still wins
        self.assertIsNone(br.classify_failure(next(x for x in run['visits'] if x['misses'] and x['ok'])))
        self.assertEqual(br.CAUSES[-1], ('not_recorded', 'Not recorded'))  # a fifth cause next to the four

    def test_plays_figure_leaves_the_miss_out(self):
        run = with_misses()
        text = br.render_report(run, ['x'])
        row = next(line for line in text.splitlines() if line.startswith('| Usenet Ultimate | Cold 1 | ') and ' of ' in line)
        self.assertIn('| 0 of 0 |', row)  # one title, and it failed only because of a miss
        self.assertIn('Usenet Ultimate 3 s (1 of 1 top picks played)', br.answer_sentence(run))
        self.assertIn('plays 3/3', br.headline(run).split('Usenet Ultimate')[1])  # 4 visits, 1 left out

    def test_not_recorded_section(self):
        text = br.render_report(with_misses(), ['x'])
        sec = text.split('## Not recorded', 1)[1].split('\n## ', 1)[0]
        self.assertIn('| Usenet Ultimate | Matrix | 2 |', sec)
        self.assertIn('| KaijuFlow | Matrix | 1 |', sec)
        self.assertIn('Usenet Ultimate, Matrix, Cold 1', sec)  # the top pick left out, by name
        self.assertIn('python3 -I tools/brain/brainrun.py record --name x --store S --list L', sec)

    def test_no_section_without_misses(self):
        text = br.render_report(runs_fixture(), ['x'])
        self.assertNotIn('## Not recorded', text)
        self.assertIn('**Not recorded**', text)  # the cause is still defined

    def test_indexer_time_and_own_work_are_separate_columns(self):
        text = br.render_report(with_misses(), ['x'])
        head = next(line for line in text.splitlines() if line.startswith('| Side | Run | Search'))
        cols = [c.strip() for c in head.strip('|').split('|')]
        self.assertEqual(cols[:5], ['Side', 'Run', 'Search', 'Indexers', "Side's own work"])
        row = next(line for line in text.splitlines() if line.startswith('| Usenet Ultimate | Warm 1 |') and '| 5 |' in line)
        cells = [c.strip() for c in row.strip('|').split('|')]
        self.assertEqual(cells[2:5], ['5', '1', '4'])  # search 5 s = indexers 1 s + own work 4 s

    def test_old_run_without_log_data_shows_a_dash(self):
        text = br.render_report(runs_fixture(), ['x'])
        row = next(line for line in text.splitlines() if line.startswith('| KaijuFlow | Cold 1 |') and '| 5 |' in line)
        cells = [c.strip() for c in row.strip('|').split('|')]
        self.assertEqual(cells[2:5], ['5', '-', '-'])


class AttributionTest(unittest.TestCase):
    def visit(self, vid='tt1', start='2026-11-10T18:00:00Z', played='Rel.A.2160p', **kw):
        v = dict(side='kaijuflow', id=vid, t_start=start, t_end='2026-11-10T18:00:07Z', tries=[{'title': played}])
        v.update(kw)
        return v

    @staticmethod
    def line(step, t, ms=100, **kw):
        return dict(step=step, ms=ms, t=t, ok=True, **kw)

    def test_late_health_batch_is_kept_until_the_next_visit_of_that_side(self):
        steps = [self.line('indexer_page', '2026-11-10T18:00:02Z', ref='tt1', source='N', page=1),
                 self.line('health_batch', '2026-11-10T18:00:40Z', ref='tt1'),  # 40 s later: no fixed cut
                 self.line('health_batch', '2026-11-10T18:00:50Z', ref='tt2')]
        got = br.attribute_steps(self.visit(), steps, end=br.parse_ts('2026-11-10T18:01:00Z'))
        self.assertEqual([(s['step'], s['ref']) for s in got], [('indexer_page', 'tt1'), ('health_batch', 'tt1')])
        # after the side's next visit has started, the line belongs to that visit
        got = br.attribute_steps(self.visit(), steps, end=br.parse_ts('2026-11-10T18:00:30Z'))
        self.assertEqual([s['step'] for s in got], ['indexer_page'])

    def test_prepare_lines_of_the_previous_title_stay_out(self):
        steps = [  # previous title's background work: started before this visit, ends inside it
            self.line('import_wait', '2026-11-10T18:00:05Z', ms=30000, title='Other.Movie.1080p', job='9'),
            self.line('first_byte', '2026-11-10T18:00:06Z', ms=100, title='Other.Movie.1080p', job='9'),
            self.line('nzb_fetch', '2026-11-10T18:00:03Z', ms=200, title='Rel.A.2160p'),
            self.line('import_wait', '2026-11-10T18:00:20Z', ms=15000, title='Rel.A.2160p', job='10'),
            self.line('first_byte', '2026-11-10T18:00:21Z', ms=100, title='Rel.A.2160p', job='10')]
        got = br.attribute_steps(self.visit(), steps, end=None)
        self.assertEqual({s['title'] for s in got}, {'Rel.A.2160p'})
        self.assertEqual(len(got), 3)

    def test_played_source_decides_when_two_titles_started_inside_the_visit(self):
        steps = [self.line('nzb_fetch', '2026-11-10T18:00:03Z', title='Rel.B.1080p'),
                 self.line('nzb_fetch', '2026-11-10T18:00:04Z', title='Rel.A.2160p')]
        got = br.attribute_steps(self.visit(played='Name\nRel.A.2160p 12 GB'), steps, end=None)
        self.assertEqual([s['title'] for s in got], ['Rel.A.2160p'])

    def test_nothing_before_the_visit_started(self):
        steps = [self.line('nzb_fetch', '2026-11-09T18:00:03Z', title='Rel.A.2160p')]
        self.assertEqual(br.attribute_steps(self.visit(), steps, end=None), [])


class RunRecordTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_folder_never_overwritten(self):
        now = datetime.datetime(2026, 11, 10, 18, 0, 5, tzinfo=datetime.timezone.utc)
        a = br.create_run_dir(self.root, 'base line!', now)
        b = br.create_run_dir(self.root, 'base line!', now)
        self.assertNotEqual(a, b)
        self.assertTrue(os.path.basename(a).startswith('2026-11-10T180005Z-base-line'))
        self.assertTrue(os.path.isdir(a) and os.path.isdir(b))

    def test_index_appends_only(self):
        idx = os.path.join(self.root, 'INDEX.md')
        br.append_index_row(idx, dict(date='2026-11-10T18:00:05Z', name='one', result='ok', changed=['a | b', 'c'],
                                      headline='KF 2 s', folder='f1'))
        first = open(idx).read()
        br.append_index_row(idx, dict(date='2026-11-10T19:00:05Z', name='two', result='null', changed=['x'],
                                      headline='NULL: DrunkenSlug limit at 2026-11-10T19:01:00Z', folder='f2'))
        second = open(idx).read()
        self.assertTrue(second.startswith(first))
        self.assertEqual(second.count('\n| 2026'), 2)
        self.assertIn('a / b; c', second)
        self.assertEqual(second.count('| Date (UTC) |'), 1)
        with self.assertRaises(ValueError):
            br.append_index_row(idx, dict(date='d', name='two', result='ok', changed=[], headline='', folder='f2'))

    def test_previous_run_skips_null_and_self(self):
        for name, status in (('2026-11-10T100000Z-a', 'ok'), ('2026-11-10T110000Z-b', 'null'), ('2026-11-10T120000Z-c', 'ok')):
            d = os.path.join(self.root, name)
            os.makedirs(d)
            json.dump({'status': status, 'commit': name}, open(os.path.join(d, 'meta.json'), 'w'))
        prev = br.previous_run(self.root, exclude='2026-11-10T120000Z-c')
        self.assertEqual(prev['commit'], '2026-11-10T100000Z-a')
        self.assertIsNone(br.previous_run(self.root + '/none'))


if __name__ == '__main__':
    unittest.main()
