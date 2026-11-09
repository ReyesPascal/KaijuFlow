"""Test for indexer_standin.py: record a fake indexer on loopback, replay it with the indexer gone, compare bytes.

Run: python3 -m unittest discover -s tools/brain -p 'test_*.py'  (CI runs it). No real indexer is contacted.
"""
import http.server, json, os, re, shutil, sys, tempfile, threading, unittest, urllib.error, urllib.request
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indexer_standin  # noqa: E402

REAL_KEY = 'REALSECRETKEY123'
PAGE = 3  # items per search page


def nzb_bytes(n):
    """Binary-ish NZB payload: CRLF, a NUL and high bytes, so any text re-encoding would show."""
    return b'<?xml version="1.0"?>\r\n<nzb id="%d">\x00\xff\xfe\r\n</nzb>\n' % n + bytes(range(256)) * 3


class FakeIndexer(http.server.BaseHTTPRequestHandler):
    hits = 0
    limit = False

    def log_message(self, *a):
        pass

    def do_GET(self):
        cls = type(self)
        cls.hits += 1
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if q.get('apikey') != REAL_KEY:
            return self.send(200, 'text/xml', b'<error code="100" description="Incorrect user credentials"/>')
        if cls.limit:
            return self.send(200, 'text/xml', b'<error code="500" description="Request limit reached"/>')
        if q.get('t') == 'get':
            return self.send(200, 'application/x-nzb', nzb_bytes(int(q['id'])))
        off = int(q.get('offset', 0))
        base = f'http://127.0.0.1:{self.server.server_port}'
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
        FakeIndexer.hits, FakeIndexer.limit = 0, False
        self.fake = serve(http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeIndexer))
        self.cfg = {'indexers': {'fake': {'url': f'http://127.0.0.1:{self.fake.server_port}', 'apikey': REAL_KEY}}}
        self.store = os.path.join(self.tmp, 'store')

    def standin(self, mode, listname='list-a', port=0):
        s = serve(indexer_standin.make_server(self.cfg, self.store, mode, listname, port=port, bind='127.0.0.1'))
        self.addCleanup(s.server_close)
        self.addCleanup(s.shutdown)
        return s, f'http://127.0.0.1:{s.server_port}'

    def crawl(self, base):
        """What a side does: all search pages with a dummy key, then every NZB link it was handed."""
        out = []
        for off in (0, 3, 6):
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
        self.assertEqual(len(recorded), 3 + 7)  # 3 pages + 7 NZBs
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


if __name__ == '__main__':
    unittest.main()
