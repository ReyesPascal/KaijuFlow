"""Test for indexer_standin.py: record a fake indexer on loopback, replay it with the indexer gone, compare bytes.

Run: python3 -m unittest discover -s tools/brain -p 'test_*.py'  (CI runs it). No real indexer is contacted.
"""
import http.server, json, os, re, shutil, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indexer_standin  # noqa: E402

REAL_KEY = 'REALSECRETKEY123'
PAGE = 7  # items per search page: all seven on the first one


def nzb_bytes(n):
    """Binary-ish NZB payload: CRLF, a NUL and high bytes, so any text re-encoding would show."""
    return b'<?xml version="1.0"?>\r\n<nzb id="%d">\x00\xff\xfe\r\n</nzb>\n' % n + bytes(range(256)) * 3


class FakeIndexer(http.server.BaseHTTPRequestHandler):
    hits = 0
    limit = False
    json_escaped = True  # for o=json answers: escape slashes like PHP does
    error_body = None  # when set, every request is answered with this body
    delay = 0.0  # seconds the fake indexer takes to answer
    seen = []  # query parameter names of every request received
    force_status = None  # when set, every request is answered with this HTTP status and a plain body

    def log_message(self, *a):
        pass

    def do_GET(self):
        cls = type(self)
        cls.hits += 1
        u = urlparse(self.path)
        cls.seen.append(sorted(parse_qs(u.query)))
        time.sleep(cls.delay)
        if cls.force_status:
            return self.send(cls.force_status, 'text/plain', b'trouble')
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if cls.error_body is not None:
            return self.send(200, 'application/json', cls.error_body)
        if q.get('apikey') != REAL_KEY:
            return self.send(200, 'text/xml', b'<error code="100" description="Incorrect user credentials"/>')
        if cls.limit:
            return self.send(200, 'text/xml', b'<error code="500" description="Request limit reached"/>')
        if q.get('t') == 'get':
            return self.send(200, 'application/x-nzb', nzb_bytes(int(q['id'])))
        off = int(q.get('offset', 0))
        base = f'http://127.0.0.1:{self.server.server_port}'
        if q.get('o') == 'json':
            links = [f'{base}/api?t=get&id={i}&apikey={REAL_KEY}' for i in range(off, min(off + PAGE, 7))]
            body = json.dumps({'item': [{'title': f'Rel {i}', 'link': u, 'enclosure': {'@attributes': {'url': u}}}
                                        for i, u in enumerate(links, off)]}).encode()
            if cls.json_escaped:
                body = body.replace(b'/', b'\\/')
            return self.send(200, 'application/json', body)
        items = ''.join(
            f'<item><title>Rel {i} &amp; co</title><link>{base}/api?t=get&amp;id={i}&amp;apikey={REAL_KEY}</link>'
            f'<enclosure url="{base}/api?t=get&amp;id={i}&amp;apikey={REAL_KEY}" length="5" type="application/x-nzb"/></item>'
            for i in range(off, min(off + PAGE, 7)))
        body = f'<?xml version="1.0"?>\n<rss><channel><newznab:response offset="{off}" total="7"/>{items}</channel></rss>\n'
        self.send(200, 'application/rss+xml', body.encode())

    def send(self, status, ctype, body):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class StandinTest(unittest.TestCase):
    def assertBytes(self, a, b, msg=''):
        self.assertTrue(a == b, f'bytes differ ({len(a)} vs {len(b)} bytes) {msg}')

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        FakeIndexer.hits, FakeIndexer.limit, FakeIndexer.json_escaped, FakeIndexer.error_body = 0, False, True, None
        FakeIndexer.delay, FakeIndexer.seen, FakeIndexer.force_status = 0.0, [], None
        self.fake = serve(http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeIndexer))
        self.cfg = {'indexers': {'fake': {'url': f'http://127.0.0.1:{self.fake.server_port}', 'apikey': REAL_KEY}}}
        self.store = os.path.join(self.tmp, 'store')

    def standin(self, mode, listname='list-a', port=0, cfg=None, **kw):
        s = serve(indexer_standin.make_server(cfg or self.cfg, self.store, mode, listname, port=port, bind='127.0.0.1', **kw))
        self.addCleanup(s.server_close)
        self.addCleanup(s.shutdown)
        self.last = s
        return s, f'http://127.0.0.1:{s.server_port}'

    def crawl(self, base):
        """What a side does: the search with a dummy key, then every NZB link it was handed."""
        out = []
        for off in (0,):
            st, body = fetch(f'{base}/fake/api?t=search&q=inception&offset={off}&apikey=dummy')
            self.assertEqual(st, 200)
            out.append(body)
            for link in re.findall(rb'<link>([^<]*)</link>', body):
                url = link.decode().replace('&amp;', '&')
                self.assertTrue(url.startswith(base + '/'), 'NZB link must lead back to the stand-in: ' + url)
                out.append(fetch(url)[1])
        return out

    def test_record_then_replay_is_byte_identical_and_never_contacts_indexer(self):
        rec, rbase = self.standin('record')
        port = rec.server_port  # links carry the stand-in's address, so replay uses the same one (1340 in real runs)
        recorded = self.crawl(rbase)
        self.assertGreater(FakeIndexer.hits, 0)
        self.assertEqual(len(recorded), 1 + 7)  # 1 page + 7 NZBs
        rec.shutdown()
        rec.server_close()
        self.fake.shutdown()
        self.fake.server_close()
        hits = FakeIndexer.hits
        _, pbase = self.standin('replay', port=port)
        replayed = self.crawl(pbase)
        self.assertEqual(FakeIndexer.hits, hits)
        for i, (a, b) in enumerate(zip(recorded, replayed)):
            self.assertBytes(a, b, f'answer {i}')
        self.assertBytes(recorded[1], nzb_bytes(0))  # NZB passes through untouched

    def test_real_key_is_not_in_store_answers_or_logs(self):
        s, base = self.standin('record')
        blob = b''.join(self.crawl(base))
        for root, _, files in os.walk(self.store):
            for f in files:
                blob += open(os.path.join(root, f), 'rb').read()
        blob += '\n'.join(s.state.log_lines).encode()
        self.assertNotIn(REAL_KEY.encode(), blob)
        self.assertNotIn(b'dummy', blob)

    def test_title_lists_are_stored_apart(self):
        s, base = self.standin('record', 'list-a')
        fetch(f'{base}/fake/api?t=search&q=x&offset=0&apikey=d')
        fetch(f'{base}/_standin/list?name=list-b')
        before = FakeIndexer.hits
        fetch(f'{base}/fake/api?t=search&q=x&offset=0&apikey=d')
        self.assertEqual(FakeIndexer.hits, before + 1)  # list-b has no answer yet, so it asks the indexer
        self.assertTrue(os.path.isdir(os.path.join(self.store, 'list-a')))
        self.assertTrue(os.path.isdir(os.path.join(self.store, 'list-b')))

    def test_replay_miss_is_404_and_logged(self):
        s, base = self.standin('replay')
        st, _ = fetch(f'{base}/fake/api?t=search&q=never&apikey=d')
        self.assertEqual(st, 404)
        self.assertTrue(any(line.startswith('MISS ') for line in s.state.log_lines))

    def test_limit_reached_is_flagged_not_stored_and_passed_on(self):
        s, base = self.standin('record')
        fetch(f'{base}/fake/api?t=search&q=ok&apikey=d')
        FakeIndexer.limit = True
        st, body = fetch(f'{base}/fake/api?t=search&q=limited&apikey=d')
        self.assertIn(b'limit', body.lower())  # the side sees the indexer's own answer
        marker = os.path.join(self.store, 'LIMIT_REACHED.json')
        self.assertTrue(os.path.exists(marker))
        self.assertEqual(json.load(open(marker))['indexer'], 'fake')
        self.assertNotIn(REAL_KEY.encode(), open(marker, 'rb').read())
        self.assertTrue(any(line.startswith('LIMIT_REACHED indexer=fake ') for line in s.state.log_lines))
        self.assertTrue(s.state.limit_reached)
        status = json.loads(fetch(f'{base}/_standin/status')[1])
        self.assertEqual(status['limit_reached']['indexer'], 'fake')
        FakeIndexer.limit = False
        _, pbase = self.standin('replay')
        self.assertEqual(fetch(f'{pbase}/fake/api?t=search&q=limited&apikey=d')[0], 404)  # never stored

    def json_links(self, body):
        text = body.decode().replace('\\/', '/')
        return [i['link'] for i in json.loads(text)['item']]

    def json_crawl(self, base):
        out = []
        for off in (0,):
            st, body = fetch(f'{base}/fake/api?t=search&q=x&o=json&offset={off}&apikey=dummy')
            self.assertEqual(st, 200)
            out.append(body)
            for url in self.json_links(body):
                self.assertTrue(url.startswith(base + '/'), 'JSON NZB link must lead back to the stand-in: ' + url)
                out.append(fetch(url)[1])
        return out

    def test_json_answers_have_links_rewritten_escaped_and_unescaped(self):
        for escaped in (True, False):
            FakeIndexer.json_escaped = escaped
            self.tmp2 = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, self.tmp2, True)
            self.store = os.path.join(self.tmp2, 'store')
            s, base = self.standin('record')
            blob = b''.join(self.json_crawl(base))
            self.assertNotIn(REAL_KEY.encode(), blob)
            self.assertNotIn(b'127.0.0.1:%d' % self.fake.server_port, blob)

    def test_json_record_then_replay_is_byte_identical(self):
        rec, rbase = self.standin('record')
        port = rec.server_port
        recorded = self.json_crawl(rbase)
        rec.shutdown()
        rec.server_close()
        self.fake.shutdown()
        self.fake.server_close()
        _, pbase = self.standin('replay', port=port)
        for i, (a, b) in enumerate(zip(recorded, self.json_crawl(pbase))):
            self.assertBytes(a, b, f'answer {i}')

    def test_no_real_key_reaches_a_side_or_the_store_in_any_body(self):
        bodies = {
            'xml': b'<error code="100" description="bad key %s"/>' % REAL_KEY.encode(),
            'json-escaped': json.dumps({'error': {'@attributes': {'code': '100', 'description': 'k ' + REAL_KEY}}}).encode(),
            'json-plain': ('{"msg": "' + REAL_KEY + '", "u": "http://elsewhere.example/x?apikey=' + REAL_KEY + '"}').encode(),
            'urlencoded': b'key=' + REAL_KEY.encode(),
        }
        s, base = self.standin('record')
        for name, body in bodies.items():
            FakeIndexer.error_body = body
            st, got = fetch(f'{base}/fake/api?t=search&q={name}&apikey=dummy')
            self.assertNotIn(REAL_KEY.encode(), got, name)
        stored = b''
        for root, _, files in os.walk(self.store):
            for f in files:
                stored += open(os.path.join(root, f), 'rb').read()
        self.assertNotIn(REAL_KEY.encode(), stored)

    def test_json_limit_error_is_detected(self):
        for body in (b'{"error":{"@attributes":{"code":"500","description":"Request limit reached"}}}',
                     b'{"error":{"@attributes":{"code":"429","description":"x"}}}',
                     b'{"error":{"code":"100","description":"API limit exceeded"}}'):
            self.assertTrue(indexer_standin.is_limit(200, body), body)
        for body in (b'{"error":{"@attributes":{"code":"100","description":"Incorrect user credentials"}}}',
                     b'{"item":[]}', b'not json'):
            self.assertFalse(indexer_standin.is_limit(200, body), body)

    def test_json_limit_answer_writes_marker(self):
        s, base = self.standin('record')
        FakeIndexer.error_body = b'{"error":{"@attributes":{"code":"500","description":"Daily limit reached"}}}'
        fetch(f'{base}/fake/api?t=search&q=l&o=json&apikey=d')
        self.assertTrue(s.state.limit_reached)

    def test_record_nzb_token_for_another_host_is_refused(self):
        import base64
        other = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeIndexer)
        serve(other)
        self.addCleanup(other.server_close)
        self.addCleanup(other.shutdown)
        s, base = self.standin('record')
        hits = FakeIndexer.hits
        for host in (f'127.0.0.1:{other.server_port}', f'127.0.0.1:{self.fake.server_port}@127.0.0.1:{other.server_port}'):
            url = f'http://{host}/api?t=get&id=1&apikey={{KEY}}'
            token = base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')
            st, _ = fetch(f'{base}/fake/nzb/{token}')
            self.assertEqual(st, 403)
        self.assertEqual(FakeIndexer.hits, hits)  # nothing was sent anywhere

    def record_one_search(self, delay):
        """Record one search page and its NZBs against a fake indexer that takes `delay` seconds; returns the bytes."""
        FakeIndexer.delay = delay
        rec, rbase = self.standin('record')
        out = self.crawl(rbase)
        rec.shutdown()
        rec.server_close()
        FakeIndexer.delay = 0.0
        return rec.server_port, out

    def timed_crawl(self, base):
        t = time.monotonic()
        out = self.crawl(base)
        return time.monotonic() - t, out

    def test_replay_waits_as_long_as_the_real_indexer_took_and_bytes_match(self):
        port, recorded = self.record_one_search(0.15)
        took, replayed = self.timed_crawl(self.standin('replay', port=port, cfg={'indexers': {}})[1])
        self.assertGreaterEqual(took, 0.15 * 8 * 0.9)  # 1 search page + 7 NZB files, each waits
        for a, b in zip(recorded, replayed):
            self.assertBytes(a, b)
        self.assertEqual(len(recorded), len(replayed))

    def test_replay_wait_can_be_switched_off(self):
        port, recorded = self.record_one_search(0.15)
        took, replayed = self.timed_crawl(self.standin('replay', port=port, wait=False)[1])
        self.assertLess(took, 0.5)
        for a, b in zip(recorded, replayed):
            self.assertBytes(a, b)

    def test_replayed_log_line_shows_the_wait_in_milliseconds(self):
        port, _ = self.record_one_search(0.2)
        s, base = self.standin('replay', port=port)
        fetch(f'{base}/fake/api?t=search&q=inception&offset=0&apikey=dummy')
        line = [x for x in s.state.log_lines if x.startswith('HIT ')][0]
        m = re.match(r'^HIT fake api offset=0&q=inception&t=search wait_ms=(\d+) from=\S+ t=\d+$', line)
        self.assertTrue(m, line)
        self.assertGreaterEqual(int(m.group(1)), 190)

    def test_wait_off_logs_zero_wait(self):
        port, _ = self.record_one_search(0.2)
        s, base = self.standin('replay', port=port, wait=False)
        fetch(f'{base}/fake/api?t=search&q=inception&offset=0&apikey=dummy')
        self.assertIn(' wait_ms=0 from=', s.state.log_lines[-1])

    def test_recording_without_a_recorded_time_replays_without_waiting(self):
        port, recorded = self.record_one_search(0.0)
        for root, _, files in os.walk(self.store):
            for f in files:
                if f.endswith('.meta.json'):
                    path = os.path.join(root, f)
                    meta = json.load(open(path))
                    meta.pop('ms', None)  # what a recording made before this change looks like
                    json.dump(meta, open(path, 'w'))
        shutil.rmtree(os.path.join(self.store, 'list-a', 'fake', 'indexer.json'), True)
        s, base = self.standin('replay', port=port)
        took, replayed = self.timed_crawl(base)
        self.assertLess(took, 0.5)
        for a, b in zip(recorded, replayed):
            self.assertBytes(a, b)
        self.assertIn(' wait_ms=0 from=', s.state.log_lines[-1])

    def drop_cfg(self):
        ix = dict(self.cfg['indexers']['fake'], drop_params=['o'])
        return {'indexers': {'fake': ix}}

    def test_dropped_parameter_never_reaches_the_indexer_and_hits_the_same_answer(self):
        s, base = self.standin('record', cfg=self.drop_cfg())
        a = fetch(f'{base}/fake/api?t=search&q=x&o=json&apikey=dummy')
        self.assertEqual(a[0], 200)
        hits = FakeIndexer.hits
        b = fetch(f'{base}/fake/api?t=search&q=x&apikey=dummy')
        self.assertEqual(FakeIndexer.hits, hits)  # same stored answer, no second request
        self.assertBytes(a[1], b[1])
        self.assertTrue(a[1].lstrip().startswith(b'<?xml'))  # the indexer answered XML, as the live proxy makes it
        self.assertTrue(all('o' not in names for names in FakeIndexer.seen))

    def test_other_indexers_keep_the_parameter(self):
        s, base = self.standin('record')
        self.assertEqual(fetch(f'{base}/fake/api?t=search&q=x&o=json&apikey=dummy')[0], 200)
        self.assertIn('o', FakeIndexer.seen[-1])

    def test_replay_honours_the_dropped_parameter_without_a_key_file(self):
        s, base = self.standin('record', cfg=self.drop_cfg())
        recorded = fetch(f'{base}/fake/api?t=search&q=x&o=json&apikey=dummy')[1]
        s.shutdown()
        s.server_close()
        p, pbase = self.standin('replay', port=s.server_port, cfg={'indexers': {}})
        for suffix in ('&o=json', ''):
            st, body = fetch(f'{pbase}/fake/api?t=search&q=x{suffix}&apikey=dummy')
            self.assertEqual(st, 200)
            self.assertBytes(body, recorded)
        self.assertFalse([x for x in p.state.log_lines if x.startswith('MISS')])

    def test_dropped_parameter_setting_holds_no_key(self):
        s, base = self.standin('record', cfg=self.drop_cfg())
        fetch(f'{base}/fake/api?t=search&q=x&o=json&apikey=dummy')
        saved = open(os.path.join(self.store, 'list-a', 'fake', 'indexer.json')).read()
        self.assertEqual(json.loads(saved), {'drop_params': ['o']})
        self.assertNotIn(REAL_KEY, saved)

    # ---- who asked and when (review fix 1)
    def test_every_request_line_carries_the_client_address_and_the_time_it_was_answered(self):
        s, base = self.standin('record')
        before = int(time.time() * 1000)
        fetch(f'{base}/fake/api?t=search&q=a&apikey=d')   # RECORD
        fetch(f'{base}/fake/api?t=search&q=a&apikey=d')   # HIT
        FakeIndexer.force_status = 503
        fetch(f'{base}/fake/api?t=search&q=b&apikey=d')   # ERROR
        after = int(time.time() * 1000)
        _, pbase = self.standin('replay', port=0, cfg={'indexers': {}})
        p = self.last
        fetch(f'{pbase}/fake/api?t=search&q=never&apikey=d')  # MISS
        lines = s.state.log_lines + p.state.log_lines
        kinds = {}
        for line in lines:
            m = re.match(r'^(HIT|MISS|RECORD|ERROR) .* from=(\S+) t=(\d+)$', line)
            if m:
                kinds[m.group(1)] = (m.group(2), int(m.group(3)))
        self.assertEqual(set(kinds), {'HIT', 'MISS', 'RECORD', 'ERROR'}, lines)
        for ip, t in kinds.values():
            self.assertEqual(ip, '127.0.0.1')
            self.assertTrue(before - 1000 <= t <= after + 1000)

    # ---- what is stored (review fix 5)
    def stored_bodies(self):
        out = []
        for root, _, files in os.walk(self.store):
            out += [f for f in files if f.endswith('.body')]
        return out

    def test_server_errors_are_passed_on_not_stored_and_asked_again_later(self):
        s, base = self.standin('record')
        FakeIndexer.force_status = 503
        st, _ = fetch(f'{base}/fake/api?t=search&q=a&apikey=d')
        self.assertEqual(st, 503)
        self.assertEqual(self.stored_bodies(), [])
        self.assertTrue(any(re.match(r'^ERROR fake api .* -> 503 from=\S+ t=\d+$', x) for x in s.state.log_lines), s.state.log_lines)
        self.assertEqual(s.state.errors, 1)
        FakeIndexer.force_status = None
        hits = FakeIndexer.hits
        self.assertEqual(fetch(f'{base}/fake/api?t=search&q=a&apikey=d')[0], 200)
        self.assertEqual(FakeIndexer.hits, hits + 1)  # the top-up asked again
        self.assertEqual(len(self.stored_bodies()), 1)

    def test_other_4xx_and_newznab_errors_are_not_stored_but_gone_is_kept(self):
        s, base = self.standin('record')
        FakeIndexer.force_status = 403
        fetch(f'{base}/fake/api?t=search&q=a&apikey=d')
        FakeIndexer.force_status = None
        FakeIndexer.error_body = b'{"error":{"@attributes":{"code":"100","description":"Incorrect user credentials"}}}'
        fetch(f'{base}/fake/api?t=search&q=b&apikey=d')
        FakeIndexer.error_body = None
        self.assertEqual(self.stored_bodies(), [])
        self.assertEqual(s.state.errors, 2)
        for code in (404, 410):
            FakeIndexer.force_status = code
            self.assertEqual(fetch(f'{base}/fake/api?t=search&q=gone{code}&apikey=d')[0], code)
        self.assertEqual(len(self.stored_bodies()), 2)  # an NZB that is gone stays gone

    def test_a_network_error_is_an_error_answer_not_a_crash(self):
        s, base = self.standin('record')
        self.fake.shutdown()
        self.fake.server_close()
        st, _ = fetch(f'{base}/fake/api?t=search&q=a&apikey=d')
        self.assertGreaterEqual(st, 500)
        self.assertEqual(self.stored_bodies(), [])
        self.assertTrue(any(x.startswith('ERROR fake ') for x in s.state.log_lines))

    # ---- two identical requests together (review fix 6)
    def test_two_identical_requests_together_reach_the_indexer_once(self):
        FakeIndexer.delay = 0.4
        s, base = self.standin('record')
        out = []
        ts = [threading.Thread(target=lambda: out.append(fetch(f'{base}/fake/api?t=search&q=same&apikey=d'))) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(FakeIndexer.hits, 1)
        self.assertEqual([o[0] for o in out], [200, 200])
        self.assertBytes(out[0][1], out[1][1])

    # ---- the dropped-parameter setting is fixed once answers exist (review fix 7)
    def test_a_different_dropped_parameter_setting_stops_with_one_sentence(self):
        s, base = self.standin('record', cfg=self.drop_cfg())
        fetch(f'{base}/fake/api?t=search&q=x&o=json&apikey=dummy')
        for cfg in (self.cfg, {'indexers': {'fake': dict(self.cfg['indexers']['fake'], drop_params=['o', 'x'])}}):
            problems = indexer_standin.setting_conflicts(cfg, self.store, 'list-a')
            self.assertEqual(len(problems), 1, problems)
            self.assertIn('new list name', problems[0])
            with self.assertRaises(ValueError):
                indexer_standin.make_server(cfg, self.store, 'record', 'list-a', port=0, bind='127.0.0.1')
        self.assertEqual(indexer_standin.setting_conflicts(self.drop_cfg(), self.store, 'list-a'), [])
        self.assertEqual(indexer_standin.setting_conflicts(self.cfg, self.store, 'list-new'), [])
        saved = json.load(open(os.path.join(self.store, 'list-a', 'fake', 'indexer.json')))
        self.assertEqual(saved, {'drop_params': ['o']})  # nothing deleted, nothing asked again


GB = 1024 ** 3


def posts(n, extra=()):
    """(title, size) of n ordinary 5 GB posts, plus the given ones up front."""
    return list(extra) + [(f'Film.2023.2160p.WEB-DL.DDP5.1.HEVC-G{i}', 5 * GB) for i in range(n)]


def xml_answer(items, base):
    """A search answer in NinjaCentral's XML layout (newznab size attribute and enclosure length, as captured on Brain)."""
    body = ''.join(
        f'<item>\n\t<title>{t.replace("&", "&amp;")}</title>\n\t<link>{base}/getnzb/{i}.nzb&amp;r={REAL_KEY}</link>\n'
        f'\t<enclosure url="{base}/getnzb/{i}.nzb&amp;r={REAL_KEY}" length="{s}" type="application/x-nzb" />\n'
        f'\t<newznab:attr name="category" value="2040" />\n\t\t<newznab:attr name="size" value="{s}" />\n</item>\n'
        for i, (t, s) in enumerate(items))
    return (f'<?xml version="1.0" encoding="utf-8" ?> \n<rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">\n'
            f'<channel>\n<title>NinjaCentral</title>\n<newznab:response offset="0" total="{len(items)}" />\n{body}</channel>\n</rss>\n').encode()


def json_answer(items, base):
    """A search answer in NinjaCentral's o=json layout (channel.item, attr list of @attributes, as captured on Brain)."""
    return json.dumps({'@attributes': {'version': '2.0'}, 'channel': {'title': 'NinjaCentral', 'response': {
        '@attributes': {'offset': '0', 'total': str(len(items))}}, 'item': [
        {'title': t, 'link': f'{base}/getnzb/{i}.nzb&r={REAL_KEY}',
         'enclosure': {'@attributes': {'url': f'{base}/getnzb/{i}.nzb&r={REAL_KEY}', 'length': str(s), 'type': 'application/x-nzb'}},
         'attr': [{'@attributes': {'name': 'category', 'value': '2040'}}, {'@attributes': {'name': 'size', 'value': str(s)}}]}
        for i, (t, s) in enumerate(items)]}}, separators=(',', ':')).encode()


class ListIndexer(http.server.BaseHTTPRequestHandler):
    """A fake indexer that answers every search with `items` in the format asked for (o=json or XML)."""
    items = []
    hits = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        type(self).hits += 1
        base = f'http://127.0.0.1:{self.server.server_port}'
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        body = json_answer(self.items, base) if q.get('o') == 'json' else xml_answer(self.items, base)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json' if q.get('o') == 'json' else 'text/xml')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def titles(fmt, body):
    if fmt == 'json':
        items = json.loads(body)['channel'].get('item', [])
        return [i['title'] for i in (items if isinstance(items, list) else [items])]
    return [t.decode() for t in re.findall(rb'<title>([^<]*)</title>', body) if t != b'NinjaCentral']


class UntouchedTest(unittest.TestCase):
    """#185: the stand-in passes every answer on as the indexer sent it (KaijuFlow's own filters do the rest, as at home),
    and a later page is asked of the indexer and recorded like any other request."""

    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.store = os.path.join(tmp, 'store')
        ListIndexer.items, ListIndexer.hits = [], 0
        self.fake = serve(http.server.ThreadingHTTPServer(('127.0.0.1', 0), ListIndexer))
        self.addCleanup(self.fake.server_close)
        self.addCleanup(self.fake.shutdown)
        self.cfg = {'indexers': {'fake': {'url': f'http://127.0.0.1:{self.fake.server_port}', 'apikey': REAL_KEY}}}

    def standin(self, mode, port=0, **kw):
        s = serve(indexer_standin.make_server(self.cfg, self.store, mode, 'l', port=port, bind='127.0.0.1', wait=False, **kw))
        self.addCleanup(s.server_close)
        self.addCleanup(s.shutdown)
        return s, f'http://127.0.0.1:{s.server_port}'

    def test_every_post_goes_out_as_the_indexer_sent_it_oversize_disc_images_and_past_the_first_100_included(self):
        ListIndexer.items = posts(118, [('Film.2023.2160p.BluRay.REMUX.HEVC-BIG', 40 * GB),
                                        ('Film.2023.COMPLETE.UHD.BLURAY-DISC', 20 * GB), ('Film 2023 BDMV 1080p', 20 * GB)])
        for fmt, ask in (('xml', 't=movie&imdbid=1&cat=2000'), ('json', 't=movie&imdbid=1&cat=2000&o=json&limit=100')):
            with self.subTest(fmt):
                _, base = self.standin('record')
                st, body = fetch(f'{base}/fake/api?{ask}&apikey=dummy')
                self.assertEqual(st, 200)
                self.assertEqual(len(titles(fmt, body)), 121)
                self.assertEqual(titles(fmt, body)[:3], ['Film.2023.2160p.BluRay.REMUX.HEVC-BIG',
                                                         'Film.2023.COMPLETE.UHD.BLURAY-DISC', 'Film 2023 BDMV 1080p'])
                self.assertNotIn(REAL_KEY.encode(), body)

    def test_a_later_page_is_recorded_from_the_indexer_and_replayed_byte_identical_without_it(self):
        ListIndexer.items = posts(5)
        rec, base = self.standin('record')
        ask = '/fake/api?t=search&q=Film%202023&cat=2000&offset=100&apikey=dummy'
        st, recorded = fetch(base + ask)
        self.assertEqual((st, len(titles('xml', recorded))), (200, 5))
        self.assertEqual(ListIndexer.hits, 1)  # asked of the indexer, not answered empty
        self.assertTrue(any(x.startswith('RECORD fake api cat=2000&offset=100&') for x in rec.state.log_lines), rec.state.log_lines)
        rec.shutdown()
        rec.server_close()
        self.fake.shutdown()  # replay never needs the indexer
        rep, rbase = self.standin('replay', port=rec.server_port)
        st, replayed = fetch(rbase + ask)
        self.assertEqual(st, 200)
        self.assertTrue(replayed == recorded, 'replay serves the later page as it was recorded')
        self.assertEqual(ListIndexer.hits, 1)
        self.assertTrue(rep.state.log_lines[-1].startswith('HIT fake api cat=2000&offset=100&'), rep.state.log_lines)


if __name__ == '__main__':
    unittest.main()
