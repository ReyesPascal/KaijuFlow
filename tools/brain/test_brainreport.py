"""Tests for brainreport.py (log parsing, merge, failure split, diff, report, run records). No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import datetime
import json
import os
import re
import unittest
from unittest import mock

import brainreport as br
import common
import runcheck
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
                     '2026-11-10T18:05:00Z Failed to download NZB from althub: 429 Too Many Requests (indexer unavailable, Source kept)'):
            self.assertIsNotNone(br.limit_event(line + '\n', ['althub']), line)

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

    def test_a_visit_without_step_lines_takes_its_import_from_the_backend_log(self):
        v = self.visit(steps=[], imports=[{'ok': True, 'seconds': 3.5}])
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

    def test_yaml_lists_of_plain_values_and_quoted_values_are_read(self):
        # AltMount's layout (config.yaml on Brain, 2026-11-15): 4-space indent, list items under their key
        y = ('stremio:\n    scoring:\n        preset: ""\n        custom_formats:\n            - id: r2160\n'
             '              pattern: (?i)\\b(2160p?|4k|uhd)\\b\n              category: ""\n              score: 400\n'
             '            - id: r1080\n              pattern: "(?i)\\\\b1080[pi]?\\\\b"\n            - id: r720\n'
             "              pattern: '(?i)\\b720p?\\b it''s'\n        exclude_keywords:\n            - iso\n            - BDMV\n"
             '        preferred_languages: []\n    prowlarr:\n        host: http://localhost:9696\n        categories:\n'
             '            - 2000\n            - http://x.example/a\n        api_key: SECRETKEY\n')
        flat = br.flatten_yaml(y)
        self.assertEqual(flat['stremio.scoring.custom_formats[0].pattern'], r'(?i)\b(2160p?|4k|uhd)\b')
        self.assertEqual(flat['stremio.scoring.custom_formats[1].pattern'], r'(?i)\b1080[pi]?\b')  # "..." with its escapes
        self.assertEqual(flat['stremio.scoring.custom_formats[2].pattern'], r"(?i)\b720p?\b it's")
        self.assertEqual(flat['stremio.scoring.custom_formats[0].score'], '400')
        self.assertNotIn('stremio.scoring.preset', flat)
        self.assertNotIn('stremio.scoring.custom_formats[0].category', flat)
        self.assertEqual((flat['stremio.scoring.exclude_keywords[0]'], flat['stremio.scoring.exclude_keywords[1]']), ('iso', 'BDMV'))
        self.assertEqual(flat['stremio.scoring.preferred_languages'], '[]')
        self.assertEqual(flat['stremio.prowlarr.categories[0]'], '2000')
        self.assertEqual(flat['stremio.prowlarr.categories[1]'], 'http://x.example/a')
        self.assertEqual(flat['stremio.prowlarr.host'], 'http://localhost:9696')
        self.assertEqual(flat['stremio.prowlarr.api_key'], '***')


def runs_fixture(failing=False):
    visits = []
    for rnd in (1, 2):
        for phase in ('cold', 'warm'):
            for side, st in (('kaijuflow', 2.0), ('kaijuflow-1page', 3.0)):
                ok = not (failing and side == 'kaijuflow-1page' and phase == 'cold')
                visits.append(dict(side=side, phase=phase, round=rnd, title='Matrix', id='tt1', ok=ok, list_s=5.0,
                                   sources=4, start_s=st, note=None if ok else 'failure video', steps=[], imports=[],
                                   limit=None, t_start='2026-11-10T18:00:00Z', t_end='2026-11-10T18:00:07Z',
                                   tries=[]))
    return dict(name='t', status='ok', visits=visits, titles=['Matrix'], sides=['kaijuflow', 'kaijuflow-1page'],
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
        self.assertIn('KaijuFlow, one page per indexer', text)
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


def baseline_picks():
    """Three titles of the real 2026-11-13 baseline run on all four sides (fixtures/run-2026-11-13/top-picks.json): every
    visit cut down to what the top pick is read from. Captured before the standard sort and filter rules of #109."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-2026-11-13', 'top-picks.json')
    with open(path, encoding='utf-8') as f:
        visits = json.load(f)['visits']
    return dict(name='baseline', status='ok', visits=visits, titles=['Inception', 'The Matrix', 'Game of Thrones S02E03'],
                sides=['kaijuflow', 'uu', 'altmount-addon', 'kaijuflow-1page'], commit='750c2eb', dirty=False,
                indexers=['ninjacentral'], started='2026-11-13T05:32:00.550Z', settings={}, null=None, standin_misses=0)


class ListedSizeTest(unittest.TestCase):
    """The size a side's list text states is read from the whole text, before the text is cut to 140 characters for the
    run record; a top pick whose size is lost would be compared by its name and could be listed as changed."""

    def test_a_list_text_longer_than_what_is_kept_still_gives_its_stated_size(self):
        [visit] = [v for v in baseline_picks()['visits'] if (v['side'], v['title'], v['phase'], v['round']) ==
                   ('altmount-addon', 'Game of Thrones S02E03', 'cold', 1)]
        captured = visit['tries'][0]['title']  # the addon's list text as the 2026-11-13 run kept it: the size ends at 139 of 140
        self.assertTrue(captured.endswith('💾 4.07 GB ') and len(captured) == 140, captured)
        # The same Source listed as a REPACK (a release name 7 characters longer), with the addon's own end after the size
        # (' 🌐 ninja', as its Inception line shows): the cut now falls inside the size.
        whole = captured.replace('Die.1080p', 'Die.REPACK.1080p').rstrip() + ' 🌐 ninja'
        served = (206, {'Content-Range': 'bytes 0-65535/4370000000', 'Content-Type': 'video/x-matroska'}, b'\0' * 65536,
                  {'ready': 0.1, 'first_byte': 0.1, 'total': 0.2})
        with mock.patch.object(common, 'get', return_value=served):
            tried = common.play_stream({'name': 'AltMount', 'title': whole[len('AltMount '):], 'url': 'http://127.0.0.1:9/x.mkv'})
        self.assertEqual(len(tried['title']), 140)
        self.assertNotIn('4.07 GB', tried['title'])
        self.assertEqual(br.top_pick({'tries': [tried]})['listed'], '4.07 GB')
        self.assertEqual(br.top_pick({'tries': [{'title': captured}]})['listed'], '4.07 GB')  # a record made before: from its text


def per_title_rows(report, section='## Per title'):
    """The rows of the report's per-title table (or the first table of another section) as {column: cell}."""
    lines = report.split(section)[1].strip().splitlines()
    cols = [c.strip() for c in lines[0].strip('|').split('|')]
    rows = []
    for line in lines[2:]:
        if not line.startswith('|'):
            break
        rows.append(dict(zip(cols, [c.strip() for c in line.strip('|').split('|')])))
    return rows


class TopPickTest(unittest.TestCase):
    """Ticket #109: the per-title table names the top pick of every visit and its size."""
    FGT = 'Inception.2010.2160p.UHD.BluRay.Remux.HEVC.DTS-HD.MA.5.1-FGT'

    def rows(self, run, **where):
        return [r for r in per_title_rows(br.render_report(run, ['x'])) if all(r[k] == v for k, v in where.items())]

    def test_a_row_names_the_release_kaijuflow_played_and_the_size_of_the_file(self):
        row, = self.rows(baseline_picks(), Title='Inception', Side='KaijuFlow', Run='Cold 1')
        self.assertEqual((row['Top pick'], row['Size']), (self.FGT, '85.4 GB'))  # 85436578297 bytes

    def test_a_side_without_a_release_name_shows_the_text_of_its_list_entry(self):
        row, = self.rows(baseline_picks(), Title='Inception', Side='Usenet Ultimate', Run='Cold 1')
        self.assertEqual(row['Top pick'], '✅ 4K BluRay REMUX 🎬 Inception (2010) 🗣️ English ⚙️ hevc 💾 95.01 GB 🔊 DTS-HD MA 🏴‍☠️ FGT '
                                          '🗂️ NinjaCentral 📅 4.2y 📡 Newshosting (3/3) 📊 91.9 Mb')
        self.assertEqual(row['Size'], '85.4 GB')
        row, = self.rows(baseline_picks(), Title='Inception', Side="AltMount direct", Run='Warm 2')
        self.assertEqual(row['Top pick'], 'AltMount 🌍 FHD - Inception (2010) [1080p][Dual] Inception 2010 1080p NF WEB-DL DUAL DDP5 1 H 264-TURG '
                                          '💾 4.05 GB 🌐 ninja')
        self.assertEqual(row['Size'], '3.5 GB')  # 3549321653 bytes

    def test_a_top_pick_that_did_not_play_shows_the_size_its_list_entry_states(self):
        # a failed play serves the failure video, so its size says nothing about the Source
        row, = self.rows(baseline_picks(), Title='Inception', Side='KaijuFlow', Run='Cold 2')
        self.assertEqual((row['Top pick'], row['Size']), (self.FGT, '95.01 GB listed'))
        self.assertNotEqual(row['Result'], 'plays')
        row, = self.rows(baseline_picks(), Title='Game of Thrones S02E03', Side='Usenet Ultimate', Run='Cold 1')
        self.assertEqual(row['Size'], '27.71 GB listed')
        row, = self.rows(baseline_picks(), Title='The Matrix', Side='KaijuFlow, one page per indexer', Run='Cold 2')
        self.assertEqual((row['Top pick'], row['Size']), ('The.Matrix.1999.4K.Remastered.Multi.Complete.UHD.BluRay-MAMA', '73.07 GB listed'))

    def test_every_row_of_the_real_run_shows_a_name_and_a_size(self):
        rows = self.rows(baseline_picks())
        self.assertEqual(len(rows), 3 * 4 * 4)  # three titles, four sides, four rounds
        for row in rows:
            self.assertNotIn(row['Top pick'], ('', '-'), row)
            self.assertRegex(row['Size'], r'^\d+(\.\d+)? GB( listed)?$', row)

    def test_the_sample_of_the_real_run_holds_no_address_and_no_key(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-2026-11-13', 'top-picks.json')
        with open(path, encoding='utf-8') as f:
            text = f.read()
        for pattern in (r'://', r'(?i)api_?key', r'(?i)(?:key|token|password|secret)=', r'\b\d{1,3}(\.\d{1,3}){3}\b'):
            self.assertIsNone(re.search(pattern, text), pattern)

    def test_a_visit_without_a_source_has_no_top_pick(self):
        run = runs_fixture()  # its visits list Sources but carry no play
        run['visits'][0].update(sources=0, tries=[], ok=False, note='no Sources')
        row = self.rows(run, Side='KaijuFlow', Run='Cold 1')[0]
        self.assertEqual((row['Top pick'], row['Size']), ('-', '-'))

    def test_a_bar_in_a_name_cannot_break_the_table(self):
        run = baseline_picks()
        run['visits'][1]['tries'][0]['title'] = 'A | B 💾 1.5 GB'
        row, = self.rows(run, Title='Inception', Side='Usenet Ultimate', Run='Cold 1')
        self.assertEqual((row['Top pick'], row['Result']), ('A / B 💾 1.5 GB', 'plays'))

    # ---- a top pick that changed since the last run is listed under "What changed since the last run"
    def with_pick(self, side, title, name, size, text, rounds=br.RUN_ORDER):
        """The real run again, with another top pick for one side and title in the given rounds."""
        run = baseline_picks()
        run['started'] = '2026-11-14T05:32:00.550Z'
        for v in run['visits']:
            if (v['side'], v['title']) == (side, title) and (v['phase'], v['round']) in rounds:
                v.update(ok=True, played_source=name, tries=[{'plays': True, 'size': size, 'note': None, 'title': text}])
        return run

    def changed(self, prev, cur):
        return [line for line in br.diff_runs(prev, cur) if line.startswith('Top pick changed')]

    def test_a_changed_top_pick_is_listed_with_its_side_title_rounds_old_and_new_pick(self):
        cur = self.with_pick('kaijuflow', 'Inception', 'Inception.2010.2160p.WEB-DL.DDP5.1.HEVC-NEW', 22300000000,
                             '✅ 4K WEB-DL 🎬 Inception (2010) 💾 21.9 GB 🏴‍☠️ NEW')
        self.assertEqual(self.changed(baseline_picks(), cur), [
            f'Top pick changed: KaijuFlow, Inception (Cold 1, Warm 1, Cold 2, Warm 2): {self.FGT}, 85.4 GB -> '
            'Inception.2010.2160p.WEB-DL.DDP5.1.HEVC-NEW, 22.3 GB'])

    def test_the_same_source_is_no_change_whether_it_played_or_not_and_whatever_its_list_text_says_today(self):
        cur = baseline_picks()
        for v in cur['visits']:
            if (v['side'], v['title'], v['phase'], v['round']) == ('kaijuflow', 'Inception', 'cold', 2):
                v['tries'][0].update(plays=True, size=85436578297, note=None)  # failed last time, plays now: the same Source
                v['ok'] = True
            if (v['side'], v['title'], v['phase'], v['round']) == ('uu', 'Inception', 'cold', 1):
                v['tries'][0].update(plays=False, size=1242455, note='failure video')  # played last time, fails now
                v['ok'] = False
            if v['side'] == 'uu':  # a day later the list text shows another age, and a Source not health-checked has no mark
                v['tries'][0]['title'] = v['tries'][0]['title'].replace('📅 4.2y', '📅 4.3y').replace('✅ ', '')
        self.assertEqual(self.changed(baseline_picks(), cur), [])
        self.assertEqual(self.changed(baseline_picks(), baseline_picks()), [])

    def test_only_the_rounds_that_differ_are_named_and_a_side_that_now_lists_nothing_is_a_change(self):
        text = '✅ 4K WEB-DL 🎬 Game of Thrones S02E03 💾 8.36 GB 🏴‍☠️ Weasley'
        cur = self.with_pick('uu', 'Game of Thrones S02E03', None, 8037378833, text, rounds=[('cold', 1), ('cold', 2)])
        for v in cur['visits']:
            if (v['side'], v['title'], v['phase']) == ('altmount-addon', 'The Matrix', 'warm'):
                v.update(ok=False, sources=0, tries=[], note='no Sources')
        self.assertEqual(self.changed(baseline_picks(), cur), [
            "Top pick changed: AltMount direct, The Matrix (Warm 1, Warm 2): "
            'AltMount 🇩🇪 4K - Matrix (1999) [2160p][Deu] Matrix.1999.GERMAN.DL.DV.HDR.2160p.WEB.H265-SunDry 💾 24.01 GB 🌐 ninja, 21.2 GB '
            '-> no top pick',
            'Top pick changed: Usenet Ultimate, Game of Thrones S02E03 (Cold 1, Cold 2): 4K BluRay 🎬 Game of Thrones S02E03 🗣️ English '
            f'⚙️ hevc 💾 27.71 GB 🏴‍☠️ BRIENNE 🗂️ NinjaCentral 📅 5.4y 📊 76.3 Mbps, 27.71 GB listed -> {text}, 8.0 GB'])

    def test_a_title_or_a_side_that_only_one_run_has_is_not_a_changed_top_pick(self):
        prev = baseline_picks()
        prev['visits'] = [v for v in prev['visits'] if v['title'] != 'Inception' and v['side'] != 'kaijuflow-1page']
        prev.update(titles=['The Matrix', 'Game of Thrones S02E03'], sides=['kaijuflow', 'uu', 'altmount-addon'])
        self.assertEqual(self.changed(prev, baseline_picks()), [])

    def test_nothing_changed_says_so_for_the_top_picks_too_when_both_runs_hold_them(self):
        self.assertEqual(br.diff_runs(baseline_picks(), baseline_picks())[0],
                         'Nothing changed in the settings, KaijuFlow code, titles, indexers, sides or top picks.')
        no_picks = {k: v for k, v in baseline_picks().items() if k != 'visits'}  # a run meta whose top picks are not known
        self.assertEqual(br.diff_runs(no_picks, baseline_picks())[0],
                         'Nothing changed in the settings, KaijuFlow code, titles, indexers or sides.')

    def run_folder(self, root, name, run, visits):
        """A run folder as the runner leaves it: meta.json without the visits, raw.json with them."""
        os.makedirs(os.path.join(root, name))
        with open(os.path.join(root, name, 'meta.json'), 'w') as f:
            json.dump({k: v for k, v in run.items() if k != 'visits'}, f)
        if visits is not None:
            with open(os.path.join(root, name, 'raw.json'), 'w') as f:
                json.dump({'status': run['status'], 'visits': visits}, f)

    def test_the_top_picks_of_the_previous_run_are_read_from_its_run_folder(self):
        root, prev = tempdir(self), baseline_picks()
        self.run_folder(root, '2026-11-13T053200Z-baseline', prev, prev['visits'])
        cur = self.with_pick('kaijuflow', 'Inception', 'Inception.2010.2160p.WEB-DL.DDP5.1.HEVC-NEW', 22300000000, 'x 💾 21.9 GB')
        lines = self.changed(br.previous_run(root), cur)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn('KaijuFlow, Inception (Cold 1, Warm 1, Cold 2, Warm 2)', lines[0])

    def test_a_previous_run_folder_that_holds_no_top_picks_is_not_compared(self):
        cur = self.with_pick('kaijuflow', 'Inception', 'Inception.2010.2160p.WEB-DL.DDP5.1.HEVC-NEW', 22300000000, 'x 💾 21.9 GB')
        prev = baseline_picks()
        cut_down = [{k: v for k, v in visit.items() if k not in ('tries', 'played_source')} for visit in prev['visits']]
        for name, visits in (('no-raw', None), ('cut-down', cut_down)):
            root = tempdir(self)
            self.run_folder(root, name, prev, visits)
            out = br.diff_runs(br.previous_run(root), cur)
            self.assertEqual(self.changed(br.previous_run(root), cur), [], name)
            self.assertEqual(out[0], 'Nothing changed in the settings, KaijuFlow code, titles, indexers or sides.', name)


def baseline_run():
    """The real 2026-11-13 baseline (fixtures/run-2026-11-13-imports): every visit with its first try and its imports, as
    raw.json kept them. It was run before like for like (#142): AltMount direct's hidden fallback was on."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-2026-11-13-imports')
    with open(os.path.join(folder, 'meta.json')) as f:
        run = json.load(f)
    with open(os.path.join(folder, 'raw.json'), encoding='utf-8') as f:
        run['visits'] = json.load(f)['visits']
    return run


def played_visit(imports, **kw):
    """One KaijuFlow visit that served video, its top pick named by KaijuFlow's log, with the imports its AltMount logged."""
    v = dict(side='kaijuflow', phase='cold', round=1, title='Chernobyl S01E02', kind='series', ok=True, list_s=1.0,
             start_s=9.0, note=None, misses=[], played_source='Chernobyl.S01E02.Please.Remain.Calm.1080p-onlyfaffs.mkv',
             imports=imports, tries=[{'plays': True, 'size': 8090794799,
                                      'title': 'Chernobyl.S01E02.Please.Remain.Calm.1080p-onlyfaffs.mkv 💾 0.78 GB'}])
    v.update(kw)
    return v


class FirstTryTest(unittest.TestCase):
    """Video served after the top pick's own import failed is a fallback (#143): counted as played since #185, and shown as
    one."""

    def test_video_after_the_top_picks_import_failed_is_played_after_a_fallback(self):
        top = 'Chernobyl.S01E02.Please.Remain.Calm.1080p-onlyfaffs.mkv-6632d89ee069de68'
        fallback = played_visit([{'name': top, 'ok': False, 'seconds': 1.25},
                                 {'name': 'Chernobyl - S01E02 - Bluray-2160p-fcecc767e7065bed', 'ok': True, 'seconds': 2.0}])
        first_try = played_visit([{'name': top, 'ok': True}])
        self.assertEqual(br.side_plays([fallback, first_try], 'kaijuflow'), (2, 2))
        self.assertEqual((br.fallbacks(fallback), br.fallback_s(fallback), br.fallbacks(first_try)), (1, 1.25, 0))
        self.assertEqual(br.title_to_video(fallback), 10.0)  # its 1.0 s list and 9.0 s start, the fallback's seconds in them

    def test_the_2026_11_13_baseline_shows_altmount_directs_four_fallbacks_and_none_of_the_others(self):
        visits = baseline_run()['visits']
        self.assertEqual(br.side_plays(visits, 'altmount-addon'), (40, 40))
        self.assertEqual([(v['phase'], v['round'], v['title']) for v in visits if br.fallbacks(v)],  # every round, one title
                         [(p, r, 'Chernobyl S01E02') for p, r in br.RUN_ORDER])
        self.assertEqual({v['side'] for v in visits if br.fallbacks(v)}, {'altmount-addon'})
        # KaijuFlow and Usenet Ultimate queue their next Sources too; a failed one of those is no fallback
        self.assertEqual(br.side_plays(visits, 'kaijuflow'), (39, 40))
        self.assertEqual(br.side_plays(visits, 'uu'), (38, 40))

    def test_the_report_counts_a_fallback_as_played_and_shows_it(self):
        text = br.render_report(baseline_run(), ['x'])
        self.assertIn('| Side | Run | Top pick plays | Fallback | Indexer limit |', text)
        self.assertIn("| AltMount direct | Cold 1 | 10 of 10 | 1 | 0 | 0 | 0 | 0 | 0 |", text)
        self.assertIn("| KaijuFlow | Cold 1 | 10 of 10 | 0 | 0 | 0 | 0 | 0 | 0 |", text)
        [row] = [r for r in per_title_rows(text)
                 if (r['Title'], r['Side'], r['Run']) == ('Chernobyl S01E02', "AltMount direct", 'Cold 1')]
        self.assertEqual(row['Result'], 'played after 3 fallbacks')  # this run's failed imports kept no time


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


ADDR = {'kaijuflow-test': ['10.0.0.2']}


class StandinLinesTest(unittest.TestCase):
    def test_parse_a_line(self):
        p = br.parse_standin_line(line('HIT', 'ninja', 'api q=x&t=search', 3, wait=400))
        self.assertEqual((p['kind'], p['slug'], p['request'], p['wait_ms'], p['ip']), ('HIT', 'ninja', 'api q=x&t=search', 400, '10.0.0.2'))
        self.assertEqual(p['t'], int(T0 + 3000))
        self.assertEqual(br.parse_standin_line(line('MISS', 'ninja', 'nzb abc', 1))['kind'], 'MISS')
        self.assertIsNone(br.parse_standin_line('LIST movies'))
        self.assertIsNone(br.parse_standin_line('HIT ninja api x wait_ms=3'))  # no time: cannot be placed

    def test_within_a_side_the_visit_current_for_that_side_gets_the_line(self):
        a, b = vis('kaijuflow', 0, 5), vis('kaijuflow', 30, 35)
        br.assign_standin([a, b], [line('MISS', 's', 'api t=search', 29), line('MISS', 's', 'api t=search', 31)], ADDR)
        self.assertEqual((len(a['misses']), len(b['misses'])), (1, 1))

    def test_unknown_address_falls_back_to_the_visit_in_progress_and_is_counted(self):
        kf, one_page = vis('kaijuflow', 0, 10), vis('kaijuflow-1page', 10, 20)
        lines = [line('MISS', 's', 'api t=search', 5, ip='172.99.0.9'), line('MISS', 's', 'api t=search', 15, ip='172.99.0.9'),
                 line('MISS', 's', 'api t=search', 16, ip='10.0.0.2')]
        unmatched = br.assign_standin([kf, one_page], lines, ADDR)
        self.assertEqual((len(kf['misses']), len(one_page['misses'])), (1, 2))
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
    one_page_cold1 = next(v for v in run['visits'] if v['side'] == 'kaijuflow-1page' and v['phase'] == 'cold' and v['round'] == 1)
    one_page_cold1.update(ok=False, note='no Sources', sources=0, not_recorded=True, misses=['ninjacentral api t=search&q=matrix', 'drunkenslug api t=search&q=matrix'])
    kf_warm1 = next(v for v in run['visits'] if v['side'] == 'kaijuflow' and v['phase'] == 'warm' and v['round'] == 1)
    kf_warm1['misses'] = ['drunkenslug api t=search&q=matrix&offset=100']  # still played
    run['topup_command'] = 'python3 -I tools/brain/brainrun.py record --name x --store S --list L'
    run['standin_misses'] = 3
    return run


class MissReportTest(unittest.TestCase):
    def test_failure_with_a_miss_is_its_own_cause(self):
        run = with_misses()
        v = next(v for v in run['visits'] if v['side'] == 'kaijuflow-1page' and v['phase'] == 'cold' and v['round'] == 1)
        self.assertEqual(br.classify_failure(v), 'not_recorded')
        self.assertEqual(br.classify_failure(dict(v, limit={'indexer': 'x'})), 'indexer_limit')  # the cap rule still wins
        self.assertIsNone(br.classify_failure(next(x for x in run['visits'] if x['misses'] and x['ok'])))
        self.assertEqual(br.CAUSES[-1], ('not_recorded', 'Not recorded'))  # a fifth cause next to the four

    def test_plays_figure_leaves_the_miss_out(self):
        run = with_misses()
        text = br.render_report(run, ['x'])
        row = next(line for line in text.splitlines() if line.startswith('| KaijuFlow, one page per indexer | Cold 1 | ') and ' of ' in line)
        self.assertIn('| 0 of 0 |', row)  # one title, and it failed only because of a miss
        self.assertIn('KaijuFlow, one page per indexer 3 s (1 of 1 top picks played)', br.answer_sentence(run))
        self.assertIn('plays 3/3', br.headline(run).split('KaijuFlow, one page per indexer')[1])  # 4 visits, 1 left out

    def test_not_recorded_section(self):
        text = br.render_report(with_misses(), ['x'])
        sec = text.split('## Not recorded', 1)[1].split('\n## ', 1)[0]
        self.assertIn('| KaijuFlow, one page per indexer | Matrix | 2 |', sec)
        self.assertIn('| KaijuFlow | Matrix | 1 |', sec)
        self.assertIn('KaijuFlow, one page per indexer, Matrix, Cold 1', sec)  # the top pick left out, by name
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
        row = next(line for line in text.splitlines() if line.startswith('| KaijuFlow, one page per indexer | Warm 1 |') and '| 5 |' in line)
        cells = [c.strip() for c in row.strip('|').split('|')]
        self.assertEqual(cells[2:5], ['5', '1', '4'])  # search 5 s = indexers 1 s + own work 4 s

    def test_old_run_without_log_data_shows_a_dash(self):
        text = br.render_report(runs_fixture(), ['x'])
        row = next(line for line in text.splitlines() if line.startswith('| KaijuFlow | Cold 1 |') and '| 5 |' in line)
        cells = [c.strip() for c in row.strip('|').split('|')]
        self.assertEqual(cells[2:5], ['5', '-', '-'])


class WallClockTest(unittest.TestCase):
    """Where the wall-clock time of a run went (#112). The run's own timing is tested in test_brainrun.py, on its fake clock."""

    def timed_run(self, **parts):
        run = runs_fixture(failing=True)  # 8 visits of 7 s; the one-page side's two cold top picks fail
        run.update(finished='2026-11-10T18:03:20Z', timing={
            'seconds': 200.0, 'settle_s': 3, 'passes': [{'name': 'main sides', 'seconds': 190.0}],
            'rounds': [{'pass': 'main sides', 'phase': 'cold', 'round': 1, 'start': '2026-11-10T18:00:20.000Z', 'seconds': 80.0,
                        'plays': 3, 'pause_s': 9.0},
                       {'pass': 'main sides', 'phase': 'warm', 'round': 1, 'start': '2026-11-10T18:01:40.000Z', 'seconds': 70.0,
                        'plays': 3, 'pause_s': 9.0}],
            'resets': [{'pass': 'main sides', 'phase': 'cold', 'round': 1, 'start': '2026-11-10T18:00:04.500Z', 'seconds': 15.5},
                       {'pass': 'main sides', 'phase': 'cold', 'round': 2, 'start': '2026-11-10T18:02:50.000Z', 'seconds': 25.3}]})
        run['timing']['parts'] = parts or br.time_parts(run)
        return run

    def test_the_parts_are_measured_from_the_visits_rounds_and_resets_and_the_rest_is_what_is_left(self):
        self.assertEqual(self.timed_run()['timing']['parts'], {
            'measured_s': 44.0,   # list 5 s + start: KaijuFlow 4 x (5 + 2), the one-page side warm 2 x (5 + 3)
            'pauses_s': 18.0, 'browse_s': 0.0, 'resets_s': 40.8,
            'failed_s': 14.0,     # two failed visits of 7 s, start to end
            'other_s': 83.2})     # 200 - 44 - 18 - 14 - 40.8

    def test_a_visit_without_its_times_costs_no_error(self):
        run = self.timed_run()
        for v in run['visits']:
            if not v['ok']:
                del v['t_end']
        self.assertEqual(br.time_parts(run)['failed_s'], 0.0)
        self.assertIn('| failure video: failure video |', br.render_report(run, ['x']))  # and no time in the Result column

    def test_the_parts_as_printed_are_within_a_second_of_the_whole_run(self):
        # every part ends on .44 s: printed to a whole second they would lose 2.2 s between them
        run = self.timed_run(measured_s=110.44, pauses_s=18.44, browse_s=0.0, failed_s=14.44, resets_s=40.44, other_s=16.44)
        run['timing']['seconds'] = 200.2
        rows = br.render_report(run, ['x']).split('| Part | Seconds | Minutes |\n|---|---|---|\n')[1].split('\n\n')[0].split('\n')
        seconds = [float(r.split(' | ')[1]) for r in rows]
        self.assertEqual([r.split(' | ')[0] for r in rows][-1], '| The whole run')
        self.assertEqual(seconds[-1], 200.2)
        self.assertLessEqual(abs(sum(seconds[:-1]) - seconds[-1]), 1.0)

    def test_the_section_comes_last_and_a_run_that_was_not_timed_has_none(self):
        text = br.render_report(self.timed_run(), ['x'])
        self.assertGreater(text.index('## Where the time went'), text.index('## Per title'))
        self.assertIn('The whole run took 3.3 minutes (200.0 s), from 18:00:00 to 18:03:20 UTC: the main sides 3.2 minutes (190.0 s).', text)
        self.assertIn('- **Pauses (`--settle`)**: the pause after every play, 3 s each (6 plays).', text)
        self.assertIn('| Main sides | Cold 2 | - | 25.3 | 0 | - | - |', text)  # a reset with no round after it
        self.assertNotIn('Where the time went', br.render_report(runs_fixture(), ['x']))


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


class BestPressFixtureTest(unittest.TestCase):
    """A Best press from KaijuFlow's own log (#190): captured from the Play-time check Parity suite
    (tests/integration/parity/play-time-scenarios.mjs, best-press-log-lines-the-brain-tools-read), real KaijuFlow with
    fakes for indexer, news server and AltMount. The first Source is dead, the second plays, the third is Best's backup."""
    DEAD, OK, BACKUP = (f'KaijuFlow.PlayTime.{t}.2026.2160p.WEB-DL.H265-GRP' for t in ('log-dead', 'log-ok', 'log-backup'))
    PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', '2026-11-21-best', 'kaijuflow-best-dead-first.txt')

    def visit(self):
        with open(self.PATH, encoding='utf-8') as f:
            text = f.read()
        # the list came 5 s before the press (the Browse pause); the press is the '/stream hit' line at 02:34:08.722
        v = dict(side='kaijuflow', id='tt1000002', t_start='2026-11-21T02:34:03.622Z', list_s=0.1, browse_pause_s=5,
                 start_s=0.206, ok=True, tries=[{'title': 'KaijuFlow ▶ Best'}], played_source=br.played_source(text))
        v['steps'] = br.attribute_steps(v, br.parse_step_lines(text))
        return text, v

    def test_fixture_holds_no_keys(self):
        text, _ = self.visit()
        self.assertIsNone(re.search(r'(?i)api_?key|(?:key|token|password|secret)=\S', text))

    def test_the_played_source_is_the_first_healthy_one(self):
        _, v = self.visit()
        self.assertEqual(v['played_source'], self.OK)

    def test_every_checked_source_keeps_its_check_and_only_the_played_one_its_prepare_steps(self):
        _, v = self.visit()
        self.assertEqual([(s['title'], s['ok']) for s in v['steps'] if s['step'] == 'play_check'],
                         [(self.DEAD, False), (self.OK, True), (self.BACKUP, True)])
        self.assertEqual([(s['step'], s['title']) for s in v['steps'] if s['step'] != 'play_check'],
                         [(n, self.OK) for n in ('nzb_fetch', 'unscramble', 'import_wait', 'first_byte')])

    def test_the_wait_for_the_checks_is_the_health_time(self):
        # dead 08.767-08.841 and played 08.779-08.845 checked together: 78 ms; the backup's check ended later
        _, v = self.visit()
        self.assertEqual(br.play_check_s(v), 0.078)
        self.assertEqual(br.visit_metrics(v)['health_s'], 0.078)

    def test_the_checks_are_part_of_the_steps_the_start_is_measured_against(self):
        # nzb_fetch 1 + unscramble 1 + import 41 + first byte 14 ms + 78 ms of checks against a 206 ms start
        _, v = self.visit()
        self.assertEqual(runcheck._step_gap(v), 0.07)

    def test_without_a_play_check_line_there_is_no_check_time(self):
        _, v = self.visit()
        v['steps'] = [s for s in v['steps'] if s['step'] != 'play_check']
        self.assertIsNone(br.play_check_s(v))
        self.assertIsNone(br.visit_metrics(v)['health_s'])


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


TAGGED_TITLES = [('movie', 'tt1', 'Matrix', 'easy'), ('movie', 'tt2', 'Dune', 'easy'),
                 ('movie', 'tt3', 'Old Film', 'hard'), ('series', 'tt4:1:1', 'Rare Show S01E01', 'hard')]


def tagged_visit(side, phase, rnd, title, **kw):
    """One visit of a run on the tagged title list: its top pick plays on the first try in 2.0 s list and 1.5 s start time,
    unless kw says otherwise (ok=False: no video)."""
    kind, vid, label, lst = next(t for t in TAGGED_TITLES if t[2] == title)
    ok = kw.pop('ok', True)
    v = dict(side=side, phase=phase, round=rnd, title=label, id=vid, kind=kind, list=lst, ok=ok, list_s=2.0,
             start_s=1.5 if ok else None, sources=5, note=None if ok else 'failure video', misses=[], steps=[], imports=[],
             played_source=None, limit=None, t_start='2026-11-16T10:00:00Z', t_end='2026-11-16T10:00:04Z',
             tries=[{'plays': ok, 'size': 10_000_000_000 if ok else None, 'title': f'{label}.2160p.WEB-DL-GRP'}])
    v.update(kw)
    return v


def tagged_run_folder(case, changed=None, sides=('kaijuflow', 'kaijuflow-1page')):
    """A finished run folder on the tagged title list, KaijuFlow and its one-page side (or `sides`), four rounds: every visit
    as tagged_visit makes it, except those named in `changed` ({(side, phase, round, title): {field: value}})."""
    changed = changed or {}
    visits = [tagged_visit(side, phase, rnd, t[2], **changed.get((side, phase, rnd, t[2]), {}))
              for phase, rnd in br.RUN_ORDER for t in TAGGED_TITLES for side in sides]
    folder = os.path.join(tempdir(case), '2026-11-16T100000Z-speed')
    os.makedirs(folder)
    meta = dict(name='speed', status='ok', started='2026-11-16T10:00:00Z', finished='2026-11-16T11:00:00Z', commit='abc',
                dirty=False, titles=[t[2] for t in TAGGED_TITLES], lists={t[2]: t[3] for t in TAGGED_TITLES},
                indexers=['ninjacentral'], sides=list(sides), rounds=2, short=None, settings={},
                null=None, standin_misses=0, changes=['First run.'])
    with open(os.path.join(folder, 'meta.json'), 'w') as f:
        json.dump(meta, f)
    with open(os.path.join(folder, 'raw.json'), 'w') as f:
        json.dump({'status': 'ok', 'visits': visits}, f)
    return folder


def tagged_report(case, changed=None):
    return br.render_report(br.load_run(tagged_run_folder(case, changed)), ['First run.'])


class KaijuFlowAloneTest(unittest.TestCase):
    """#185: a run of KaijuFlow alone, its fallback on. A fallback counts as played: `check` and the report say "played
    after N fallbacks" and the seconds its failed imports took, and those seconds are in its title to video."""

    CHANGED = {
        ('kaijuflow', 'cold', 1, 'Old Film'): dict(  # its top pick's import failed after 2.5 s; the next Source played
            start_s=6.0, played_source='Old Film.2160p.WEB-DL-GRP', imports=[
                {'name': 'Old Film.2160p.WEB-DL-GRP-0123456789abcdef', 'ok': False, 'seconds': 2.5},
                {'name': 'Old.Film.1080p.BluRay-OTHER-fedcba9876543210', 'ok': True, 'seconds': 2.0}]),
        ('kaijuflow', 'cold', 1, 'Rare Show S01E01'): dict(start_s=4.0),  # 6.0 s title to video
        ('kaijuflow', 'cold', 2, 'Rare Show S01E01'): dict(ok=False)}     # no video: a fail

    def setUp(self):
        self.folder = tagged_run_folder(self, self.CHANGED, sides=('kaijuflow',))

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

    def test_the_report_shows_the_fallback_as_played_with_its_title_to_video(self):
        text = br.render_report(br.load_run(self.folder), ['First run.'])
        [row] = [r for r in per_title_rows(text) if (r['Title'], r['Side'], r['Run']) == ('Old Film', 'KaijuFlow', 'Cold 1')]
        self.assertEqual((row['Title to video'], row['Result']), ('8', 'played after 1 fallback, 2.50 s extra'))
        self.assertIn('| KaijuFlow | Cold 1 | 4 of 4 | 1 | 0 | 0 | 0 | 0 | 0 |', text)  # played, and shown as a fallback
        self.assertIn('| KaijuFlow | Cold 2 | 3 of 4 | 0 |', text)


class TaggedRunTest(unittest.TestCase):
    """#167: a run on a tagged title list (easy and hard) is judged on title to video and fails, per list."""

    def row(self, report, title, side, run):
        [r] = [r for r in per_title_rows(report) if (r['Title'], r['Side'], r['Run']) == (title, side, run)]
        return r

    def test_a_visits_title_to_video_is_its_list_time_plus_its_start_time_and_a_visit_with_no_video_has_none(self):
        text = tagged_report(self, {('kaijuflow', 'cold', 1, 'Dune'): dict(list_s=3.25, start_s=4.5),
                                    ('kaijuflow', 'cold', 1, 'Old Film'): dict(ok=False)})
        dune, old = self.row(text, 'Dune', 'KaijuFlow', 'Cold 1'), self.row(text, 'Old Film', 'KaijuFlow', 'Cold 1')
        self.assertEqual((dune['List'], dune['Title to video']), ('easy', '7.75'))
        self.assertEqual((old['List'], old['Title to video']), ('hard', '-'))

    def list_rows(self, report):
        return {(r['Side'], r['List'], r['Phase']): r for r in per_title_rows(report, '## Fails and title to video per list')}

    def test_the_median_title_to_video_is_given_per_side_phase_and_list_over_the_top_picks_that_played(self):
        rows = self.list_rows(tagged_report(self, {
            ('kaijuflow', 'cold', 1, 'Dune'): dict(list_s=3.25, start_s=4.5),   # 7.75
            ('kaijuflow', 'cold', 2, 'Dune'): dict(list_s=2.0, start_s=4.0),    # 6.0; Matrix 3.5 in both cold rounds
            ('kaijuflow', 'cold', 1, 'Old Film'): dict(ok=False, list_s=30.0),  # no video: not in the median
            ('kaijuflow', 'cold', 1, 'Rare Show S01E01'): dict(list_s=1.0, start_s=1.0),
            ('kaijuflow-1page', 'warm', 2, 'Matrix'): dict(list_s=0.5, start_s=0.25)}))
        self.assertEqual(rows['KaijuFlow', 'easy', 'Cold']['Title to video'], '4.75')
        self.assertEqual(rows['KaijuFlow', 'hard', 'Cold']['Title to video'], '3.5')  # 2.0, 3.5, 3.5
        self.assertEqual(rows['KaijuFlow', 'easy', 'Warm']['Title to video'], '3.5')
        self.assertEqual(rows['KaijuFlow, one page per indexer', 'easy', 'Warm']['Title to video'], '3.5')  # 0.75, 3.5, 3.5, 3.5
        self.assertEqual(len(rows), 2 * 2 * 2)

    FAILS = {('kaijuflow', 'cold', 1, 'Old Film'): dict(ok=False),  # a cold fail; the warm play after it works
             ('kaijuflow-1page', 'cold', 1, 'Rare Show S01E01'): dict(imports=[  # video only after its top pick's import failed
                 {'name': 'Rare Show S01E01.2160p.WEB-DL-GRP', 'ok': False}, {'name': 'Rare.Show.S01E01.720p-OTHER', 'ok': True}]),
             ('kaijuflow-1page', 'cold', 2, 'Matrix'): dict(ok=False)}

    def test_a_title_with_no_video_is_a_fail_counted_per_side_round_and_list_and_a_fallback_is_played(self):
        text = tagged_report(self, self.FAILS)
        rows = self.list_rows(text)
        self.assertEqual(rows['KaijuFlow', 'hard', 'Cold']['Fails'],
                         '1 title failed · 1 of 4 plays: 1 of 2 in Cold 1, 0 of 2 in Cold 2')
        self.assertEqual(rows['KaijuFlow', 'hard', 'Warm']['Fails'],
                         '0 titles failed · 0 of 4 plays: 0 of 2 in Warm 1, 0 of 2 in Warm 2')  # the warm play counts
        self.assertEqual(rows['KaijuFlow', 'easy', 'Cold']['Fails'],
                         '0 titles failed · 0 of 4 plays: 0 of 2 in Cold 1, 0 of 2 in Cold 2')
        self.assertEqual(rows['KaijuFlow, one page per indexer', 'hard', 'Cold']['Fails'],
                         '0 titles failed · 0 of 4 plays: 0 of 2 in Cold 1, 0 of 2 in Cold 2')  # its fallback played (#185)
        self.assertEqual(rows['KaijuFlow, one page per indexer', 'easy', 'Cold']['Fails'],
                         '1 title failed · 1 of 4 plays: 0 of 2 in Cold 1, 1 of 2 in Cold 2')
        fallback = self.row(text, 'Rare Show S01E01', 'KaijuFlow, one page per indexer', 'Cold 1')
        self.assertEqual((fallback['Result'], fallback['Title to video']), ('played after 1 fallback', '3.5'))  # no import time kept
        self.assertEqual(self.row(text, 'Old Film', 'KaijuFlow', 'Warm 1')['Result'], 'plays')

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

    def test_the_report_of_a_tagged_run_opens_on_fails_then_title_to_video_and_start_times_stay_as_detail(self):
        run = br.load_run(tagged_run_folder(self, merged(self.FAILS, video('kaijuflow', 'hard', 5.0))))
        first = br.render_report(run, ['First run.']).splitlines()[0]
        self.assertEqual(first, 'Across 4 titles (2 easy, 2 hard), each round done twice. Fails, every round: KaijuFlow '
                                'easy 0 titles failed · 0 of 8 plays, hard 1 title failed · 1 of 8 plays; KaijuFlow, one page per indexer '
                                'easy 1 title failed · 1 of 8 plays, hard 0 titles failed · 0 of 8 plays. Median cold title '
                                'to video: KaijuFlow easy 3.5 s, hard 5 s; KaijuFlow, one page per indexer easy 3.5 s, hard 3.5 s.')
        self.assertEqual(br.headline(run), 'KaijuFlow fails easy 0 titles failed · 0 of 8 plays, hard 1 title failed · 1 of 8 '
                                           'plays, cold title to video 3.5 s / 5 s; KaijuFlow, one page per indexer fails easy 1 title failed · '
                                           '1 of 8 plays, hard 0 titles failed · 0 of 8 plays, cold title to video 3.5 s / 3.5 s')
        self.assertNotIn('pressing play', first)

    def test_the_replayed_2026_11_13_run_read_untagged_gives_altmount_direct_40_of_40_and_no_lists(self):
        run = br.load_run(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'run-2026-11-13-imports'))
        self.assertEqual(br.side_plays(run['visits'], 'altmount-addon'), (40, 40))  # four of them after a fallback (#185)
        self.assertEqual(br.run_lists(run['visits']), [])
        text = br.render_report(run, ['x'])
        self.assertNotIn(br.LIST_SECTION, text)
        self.assertEqual(list(per_title_rows(text)[0]), br.TITLE_COLS)

    def test_an_untagged_run_has_no_list_section_and_its_per_title_table_as_before(self):
        text = br.render_report(runs_fixture(), [])
        self.assertNotIn('per list', text)
        self.assertNotIn('Title to video', text)
        self.assertEqual(list(per_title_rows(text)[0]), br.TITLE_COLS)



def merged(*changes):
    """The `changed` entries of tagged_run_folder from fail() and video() applied together."""
    out = {}
    for c in changes:
        for k, v in c.items():
            out[k] = {**out.get(k, {}), **v}
    return out


def fail(side, title, rnd=1):
    """A `changed` entry of tagged_run_folder: that side's top pick of the title gives no video in that cold round."""
    return {(side, 'cold', rnd, title): dict(ok=False)}


def video(side, lst, secs, phase='cold'):
    """`changed` entries of tagged_run_folder: every title to video of that side, list and phase takes `secs`."""
    return {(side, phase, rnd, t[2]): dict(list_s=secs - 1.5) for p, rnd in br.RUN_ORDER if p == phase
            for t in TAGGED_TITLES if t[3] == lst}


if __name__ == '__main__':
    unittest.main()
