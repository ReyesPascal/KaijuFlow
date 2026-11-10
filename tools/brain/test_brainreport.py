"""Tests for brainreport.py (log parsing, merge, failure split, diff, report, run records). No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import datetime
import json
import os
import re
import unittest

import brainreport as br
from test_settings import tempdir

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

    def test_nzbdav_job_time_from_history_fixture(self):
        fx = json.load(open(os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'fixtures', 'backends',
                                         'nzbdav-history.json')))['reply']
        slot = fx['history']['slots'][0]
        before = {'history': {'slots': []}}
        after = {'history': {'slots': [dict(slot, nzo_id='n1', nzb_name='Rel.A', status='Completed', download_time=7),
                                       dict(slot, nzo_id='n2', nzb_name='Bad', status='Failed', download_time=0)]}}
        imps = br.nzbdav_job_imports(before, after)
        self.assertEqual([(i['name'], i['seconds'], i['ok']) for i in imps], [('Rel.A', 7.0, True), ('Bad', 0.0, False)])
        old = {'history': {'slots': [dict(slot, nzo_id='n1')]}}
        self.assertEqual([i['name'] for i in br.nzbdav_job_imports(old, after)], ['Bad'])

    def test_nzbdav_history_unreadable_gives_no_figure(self):
        self.assertEqual(br.nzbdav_job_imports(None, {'history': {'slots': [{'nzo_id': 'a'}]}}), [])
        self.assertEqual(br.nzbdav_job_imports({'history': {'slots': []}}, None), [])

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
        root = tempdir(self)
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

    # ---- run-level facts live in the meta, not in the settings snapshot (review fix 12)
    def test_run_facts_are_listed_from_the_meta(self):
        prev = dict(self.base, facts={'stand-in replay wait': 'on', 'one-page side': 'no'})
        cur = dict(self.base, facts={'stand-in replay wait': 'off', 'one-page side': 'yes'}, started='2026-11-10T19:00:00Z')
        text = '\n'.join(br.diff_runs(prev, cur))
        self.assertIn('stand-in replay wait: on -> off', text)
        self.assertIn('one-page side: no -> yes', text)

    def test_a_previous_run_in_the_older_shape_gives_no_false_difference(self):
        old = dict(self.base, settings={'kaijuflow': {'a.sampleCount': 3, 'b': 1}, 'stand-in': {'replay wait': 'on'}})
        old_one_page = dict(old, sides=['kaijuflow', 'kaijuflow-1page'],
                            settings=dict(old['settings'], **{'kaijuflow-1page': {'indexers[N].pagination': False}}))
        new = dict(self.base, facts={'stand-in replay wait': 'on', 'one-page side': 'no'}, started='2026-11-10T19:00:00Z')
        self.assertTrue(br.diff_runs(old, new)[0].startswith('Nothing changed'), br.diff_runs(old, new))
        new_one_page = dict(new, sides=['kaijuflow', 'kaijuflow-1page'], facts={'stand-in replay wait': 'on', 'one-page side': 'yes'})
        out = br.diff_runs(old_one_page, new_one_page)
        self.assertEqual([x for x in out if 'pagination' in x or 'one-page side' in x], [], out)
        self.assertIn('one-page side: yes -> no', '\n'.join(br.diff_runs(old_one_page, new)))


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


T0 = dt('2026-11-10T18:00:00Z').timestamp() * 1000   # epoch ms of the first visit's start


def vis(side, start_s, end_s, list_s=2.0, sources=5, ok=True, **kw):
    """A visit that began start_s seconds after T0 and ended end_s seconds after it."""
    def iso(sec):
        return br.iso(datetime.datetime.fromtimestamp((T0 + sec * 1000) / 1000, datetime.timezone.utc))
    v = dict(side=side, id='tt1', title='Matrix', ok=ok, list_s=list_s, sources=sources, note=None, limit=None,
             t_start=iso(start_s), t_end=iso(end_s))
    v.update(kw)
    return v


def line(kind, slug, req, at_s, ip='10.0.0.2', wait=None):
    """A stand-in log line sent at_s seconds after T0."""
    w = f' wait_ms={wait}' if wait is not None else ''
    return f'{kind} {slug} {req}{w} from={ip} t={int(T0 + at_s * 1000)}'


ADDR = {'kaijuflow-test': ['10.0.0.2'], 'uu-test': ['10.0.0.3'], 'altmount-addon-test': ['10.0.0.4']}


class StandinLinesTest(unittest.TestCase):
    def test_parse_a_line(self):
        p = br.parse_standin_line(line('HIT', 'ninja', 'api q=x&t=search', 3, wait=400))
        self.assertEqual((p['kind'], p['slug'], p['request'], p['wait_ms'], p['ip']), ('HIT', 'ninja', 'api q=x&t=search', 400, '10.0.0.2'))
        self.assertEqual(p['t'], int(T0 + 3000))
        self.assertEqual(br.parse_standin_line(line('MISS', 'ninja', 'nzb abc', 1))['kind'], 'MISS')
        self.assertIsNone(br.parse_standin_line('LIST movies'))
        self.assertIsNone(br.parse_standin_line('HIT ninja api x wait_ms=3'))  # no time: cannot be placed

    def test_a_late_request_lands_on_the_side_that_asked_not_on_the_next_visit(self):
        kf, uu = vis('kaijuflow', 0, 10), vis('uu', 10, 20)
        lines = [line('MISS', 'ninja', 'api q=x&t=search', 12, ip='10.0.0.2'),   # KaijuFlow's late background request
                 line('MISS', 'ninja', 'api q=y&t=search', 14, ip='10.0.0.3')]
        unmatched = br.assign_standin([kf, uu], lines, ADDR)
        self.assertEqual(kf['misses'], ['ninja api q=x&t=search'])
        self.assertEqual(uu['misses'], ['ninja api q=y&t=search'])
        self.assertEqual(unmatched, 0)

    def test_within_a_side_the_visit_current_for_that_side_gets_the_line(self):
        a, b = vis('kaijuflow', 0, 5), vis('kaijuflow', 30, 35)
        br.assign_standin([a, b], [line('MISS', 's', 'api t=search', 29), line('MISS', 's', 'api t=search', 31)], ADDR)
        self.assertEqual((len(a['misses']), len(b['misses'])), (1, 1))

    def test_unknown_address_falls_back_to_the_visit_in_progress_and_is_counted(self):
        kf, uu = vis('kaijuflow', 0, 10), vis('uu', 10, 20)
        lines = [line('MISS', 's', 'api t=search', 5, ip='172.99.0.9'), line('MISS', 's', 'api t=search', 15, ip='172.99.0.9'),
                 line('MISS', 's', 'api t=search', 16, ip='10.0.0.3')]
        unmatched = br.assign_standin([kf, uu], lines, ADDR)
        self.assertEqual((len(kf['misses']), len(uu['misses'])), (1, 2))
        self.assertEqual(unmatched, 2)
        self.assertEqual(br.assign_standin([vis('kaijuflow', 0, 10)], lines[:1], None), 1)  # no address map at all

    def test_one_page_side_shares_the_kaijuflow_container(self):
        a, b = vis('kaijuflow', 0, 10), vis('kaijuflow-1page', 100, 110)
        br.assign_standin([a, b], [line('MISS', 's', 'api t=search', 105)], ADDR)
        self.assertEqual((len(a['misses']), len(b['misses'])), (0, 1))

    def test_indexer_time_is_the_union_of_waits_while_the_list_loaded(self):
        v = vis('kaijuflow', 0, 10, list_s=3.0)
        lines = [line('HIT', 'ninja', 'api q=x&t=search', 1.4, wait=400),             # 1.0 - 1.4
                 line('HIT', 'drunken', 'api q=x&t=search', 1.5, wait=400),           # 1.1 - 1.5, in parallel: overlaps
                 line('HIT', 'ninja', 'api q=x&t=search&offset=3', 2.5, wait=300),    # 2.2 - 2.5, separate
                 line('HIT', 'ninja', 'nzb abc', 2.8, wait=900),                      # an NZB file is not search time
                 line('HIT', 'ninja', 'api t=get&id=7', 2.9, wait=900),
                 line('HIT', 'ninja', 'api q=late&t=search', 6.0, wait=800)]          # play time, after the list arrived
        br.assign_standin([v], lines, ADDR)
        self.assertEqual(v['indexer_s'], 0.8)  # 0.5 for the two parallel waits + 0.3

    def test_no_lines_or_wait_off_means_zero(self):
        v = vis('kaijuflow', 0, 10)
        br.assign_standin([v], [line('HIT', 'n', 'api t=search', 1, wait=0)], ADDR)
        self.assertEqual((v['misses'], v['indexer_s']), ([], 0))
        w = vis('kaijuflow', 0, 10)
        br.assign_standin([w], [], ADDR)
        self.assertEqual((w['misses'], w['indexer_s']), ([], 0))

    def test_a_visit_without_a_start_is_left_alone(self):
        vs = [dict(side='old')]
        br.assign_standin(vs, [line('MISS', 's', 'api t=search', 1)], ADDR)
        self.assertNotIn('misses', vs[0])

    def test_not_recorded_only_when_the_miss_can_be_the_cause(self):
        a = vis('kaijuflow', 0, 10, ok=False, sources=0)  # (a) empty list and a search miss
        br.assign_standin([a], [line('MISS', 's', 'api t=search', 1)], ADDR)
        self.assertEqual(br.classify_failure(a), 'not_recorded')
        b = vis('kaijuflow', 0, 10, ok=False, sources=5, note='failure video')  # a search miss, but the list was not empty
        br.assign_standin([b], [line('MISS', 's', 'api t=search', 1)], ADDR)
        self.assertEqual(br.classify_failure(b), 'failure_video')
        self.assertEqual(b['misses'], ['s api t=search'])  # still counted as a miss
        c = vis('kaijuflow', 0, 10, ok=False, sources=5, note='failure video')  # (b) NZB miss while the top pick played
        br.assign_standin([c], [line('MISS', 's', 'nzb abc', 5)], ADDR)
        self.assertEqual(br.classify_failure(c), 'not_recorded')
        d = vis('kaijuflow', 0, 10, ok=False, sources=5, note='failure video')  # NZB miss before the list arrived
        br.assign_standin([d], [line('MISS', 's', 'nzb abc', 1)], ADDR)
        self.assertEqual(br.classify_failure(d), 'failure_video')
        e = vis('kaijuflow', 0, 10, ok=True, sources=0)  # a visit that played is never "not recorded"
        br.assign_standin([e], [line('MISS', 's', 'api t=search', 1)], ADDR)
        self.assertIsNone(br.classify_failure(e))


def with_misses():
    run = runs_fixture()
    for v in run['visits']:
        v['misses'], v['indexer_s'] = [], 1.0
    uu_cold1 = next(v for v in run['visits'] if v['side'] == 'uu' and v['phase'] == 'cold' and v['round'] == 1)
    uu_cold1.update(ok=False, note='no Sources', sources=0, not_recorded=True, misses=['ninjacentral api t=search&q=matrix', 'drunkenslug api t=search&q=matrix'])
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

    def test_report_says_how_many_lines_were_matched_by_time_only(self):
        run = with_misses()
        self.assertNotIn('matched by time', br.render_report(run, ['x']))
        run['standin_unmatched'] = 4
        text = br.render_report(run, ['x'])
        self.assertIn('4 indexer stand-in requests came from an address that is not a test container', text)
        self.assertIn('matched by time', text)

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


FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', '2026-11-10')


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as f:
        return f.read()


class FixtureTest(unittest.TestCase):
    """Scrubbed samples of the real 2026-11-10 baseline run (NinjaCentral only)."""
    OPP = 'Oppenheimer.2023.2160p.MA.WEB-DL.DTS-HD.MA.5.1.DV.H.265-FLUX.mkv'

    def opp_visit(self):
        return dict(side='kaijuflow', id='tt15398776', t_start='2026-11-10T07:39:07.701Z', ok=False, note='failure video',
                    tries=[{'title': '4K WEB-DL Oppenheimer (2023) hevc 36.94 GB FLUX NinjaCentral'}])

    def test_fixtures_hold_no_keys(self):
        names = sorted(os.listdir(FIXTURES))
        self.assertGreaterEqual(len(names), 5)
        for name in names:
            text = fixture(name)
            self.assertIsNone(re.search(r'(?i)api_?key', text), name)
            self.assertIsNone(re.search(r'(?i)(?:key|token|password|secret)=(?!\*\*\*)\S', text), name)
            self.assertIsNone(re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', text), name)

    def test_the_scrub_check_would_catch_a_key(self):
        self.assertTrue(re.search(r'(?i)api_?key', 'GET /api?apikey=abc123'))

    def test_failed_top_pick_shows_its_real_cause(self):
        text = fixture('kaijuflow-oppenheimer-cold1.txt')
        self.assertEqual(br.failure_cause(text), 'Video file not servable (probe failed after 2 attempts); AltMount probe returned 400')
        self.assertEqual(br.played_source(text), self.OPP)
        v = self.opp_visit()
        v['played_source'] = br.played_source(text)
        v['cause'] = br.failure_cause(text)
        v['steps'] = br.attribute_steps(v, br.parse_step_lines(text))
        self.assertEqual(br.classify_failure(v), 'backend_rejection')
        self.assertIn('probe returned 400', br.visit_cause(v))
        # without KaijuFlow's reason, the first-byte step line still gives a cause
        self.assertEqual(br.visit_cause(dict(v, cause='')), 'first byte failed after 2.1 s')
        # "failure video" with no cause is the fallback only
        self.assertEqual(br.classify_failure(dict(v, steps=[], cause='')), 'failure_video')

    def test_only_the_played_sources_steps_count(self):
        text = fixture('kaijuflow-oppenheimer-cold1.txt')
        v = self.opp_visit()
        v['played_source'] = br.played_source(text)
        got = br.attribute_steps(v, br.parse_step_lines(text))
        self.assertEqual({s['title'] for s in got if 'title' in s}, {self.OPP})
        self.assertEqual([s['step'] for s in got],
                         ['health_batch', 'nzb_fetch', 'unscramble', 'import_wait', 'first_byte'])
        # the other two Sources prepared in the background (DV.HDR...) stay out
        self.assertEqual(sum(1 for s in br.parse_step_lines(text) if s.get('title') and s['title'] != self.OPP), 3)

    def test_without_a_known_played_source_no_prepare_lines_are_guessed(self):
        text = fixture('kaijuflow-oppenheimer-cold1.txt')
        got = br.attribute_steps(self.opp_visit(), br.parse_step_lines(text))  # display name matches no release name
        self.assertEqual([s['step'] for s in got], ['health_batch'])

    def test_a_warm_start_shows_no_import_and_no_unscramble(self):
        warm = fixture('kaijuflow-matrix-warm1.txt')
        self.assertEqual(br.played_source(warm), 'The Matrix 1999 2160p MA WEB-DL TrueHD Atmos 7 1 DV HDR H 265-FLUX')
        v = dict(side='kaijuflow', id='tt0133093', t_start='2026-11-10T07:45:41.014Z', ok=True,
                 tries=[{'title': 'x'}], played_source=br.played_source(warm), imports=[])
        steps = br.parse_step_lines(warm)
        # the cold visit's lines are older than this visit; a background line of another Source started inside it
        steps.append(dict(step='import_wait', ms=900, t='2026-11-10T07:45:45.000Z', ok=True, title='The.Matrix.Other.2160p', job='99'))
        steps.append(dict(step='unscramble', ms=900, t='2026-11-10T07:45:46.000Z', ok=True, title='The.Matrix.Other.2160p'))
        v['steps'] = br.attribute_steps(v, steps)
        self.assertEqual([s['step'] for s in v['steps']], ['health_batch'])
        m = br.visit_metrics(v)
        self.assertIsNone(m['import_s'])
        self.assertIsNone(m['unscramble_s'])

    def test_altmount_logs_give_import_times(self):
        kf = br.altmount_imports(fixture('altmount-kf-oppenheimer-cold1.txt'))
        self.assertEqual([(i['name'], i['queue_id'], i['ok']) for i in kf],
                         [(self.OPP, '6', True), ('Oppenheimer.2023.2160p.MA.WEB-DL.DTS-HD.MA.5.1.DV.HDR.H.265-FLUX', '7', None)])
        self.assertEqual(kf[0]['seconds'], 0.666)
        addon = br.altmount_imports(fixture('altmount-addon-inception-cold1.txt'))
        self.assertEqual(len(addon), 1)
        self.assertTrue(addon[0]['ok'])
        self.assertEqual(addon[0]['seconds'], 3.0)

    def test_standin_lines_parse(self):
        rows = [br.parse_standin_line(x) for x in fixture('standin-oppenheimer.txt').splitlines()]
        rows = [r for r in rows if r]
        self.assertEqual(len(rows), 6)
        self.assertEqual({r['kind'] for r in rows}, {'HIT'})
        self.assertEqual(rows[0]['wait_ms'], 499)
        self.assertEqual(rows[0]['ip'], '192.168.80.6')


class RunRecordTest(unittest.TestCase):
    def setUp(self):
        self.root = tempdir(self)

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
