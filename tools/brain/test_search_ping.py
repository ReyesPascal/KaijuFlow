"""Tests for the check preflight's search (#303, spec #298's review P3): one one-result `t=search` per switched-on indexer,
sent through the real stand-in code to a fake indexer on loopback that answers with replies captured from the real indexers
(a search answer, tests/fixtures/indexer-answers/, and DrunkenSlug's answer to a search with a wrong key,
tests/fixtures/indexer-caps/), counted by the allowance as one search each, and judged by the preflight. A caps request
would not do: indexers answer `t=caps` without a key, so a wrong key would pass.

    python3 -I -m unittest discover -s tools/brain -p 'test_search_ping.py'
"""
import datetime
import http.server
import json
import os
import threading
import unittest
from urllib.parse import parse_qs, urlparse

import allowance
import brainrun
from test_preflight import FakeWorld, make_cfg, run_command
from test_settings import SECRET, make_copies, put_limits, tempdir

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tests', 'fixtures')
SEARCH_ANSWER = 'indexer-answers/ninjacentral-search-girlfriends-s04e04.xml'
WRONG_KEY = 'indexer-caps/drunkenslug-error-wrong-key.xml'
UTC = datetime.timezone.utc


def captured(name):
    with open(os.path.join(FIXTURES, name), 'rb') as f:
        return f.read()


class FakeIndexer(http.server.BaseHTTPRequestHandler):
    """An indexer on loopback: a search answer (NinjaCentral's captured one) for the right key, and DrunkenSlug's captured
    wrong-key error, sent with HTTP 200 as DrunkenSlug sends it, for any other key."""
    key = 'right-key'
    asked = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        type(self).asked.append((q.get('t'), q.get('limit')))
        body = captured(SEARCH_ANSWER) if q.get('apikey') == self.key else captured(WRONG_KEY)
        self.send_response(200)
        self.send_header('Content-Type', 'text/xml;charset=UTF-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def free_port():
    import socket
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class PingSearchTest(unittest.TestCase):
    def setUp(self):
        FakeIndexer.asked = []
        self.real = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeIndexer)
        threading.Thread(target=self.real.serve_forever, daemon=True).start()
        self.addCleanup(self.real.server_close)
        self.addCleanup(self.real.shutdown)
        self.root = tempdir(self)
        self.key_file = os.path.join(self.root, 'indexers.json')
        url = 'http://127.0.0.1:%d' % self.real.server_port
        with open(self.key_file, 'w') as f:
            json.dump({'indexers': {'ninjacentral': {'url': url, 'apikey': 'right-key'},
                                    'drunkenslug': {'url': url, 'apikey': 'wrong-' + SECRET, 'drop_params': ['o']}}}, f)
        self.runs_root = os.path.join(self.root, 'runs')

    def ping(self, slugs):
        return brainrun.ping_search(self.key_file, slugs, free_port(), self.runs_root)

    def test_each_indexer_is_asked_one_one_result_search_through_the_stand_in(self):
        got = self.ping(['ninjacentral', 'drunkenslug'])
        self.assertEqual(FakeIndexer.asked, [('search', '1'), ('search', '1')])
        self.assertEqual(got['ninjacentral'][0], 200)
        self.assertIn(b'<rss', got['ninjacentral'][1])
        self.assertEqual(got['drunkenslug'], (200, captured(WRONG_KEY)))

    def test_the_search_counts_as_one_search_of_each_indexer(self):
        put_limits(self.key_file, {'ninjacentral': (2000, 450), 'drunkenslug': (1000, 100)})
        self.ping(['ninjacentral', 'drunkenslug'])
        left, problem = allowance.left({'key_file': self.key_file, 'runs_root': self.runs_root, 'test_dir': self.root})
        self.assertIsNone(problem)
        self.assertEqual((left['ninjacentral']['search'], left['ninjacentral']['download']), (1999, 450))
        self.assertEqual(left['drunkenslug']['search'], 999)  # an error answer is a search the indexer counted too

    def test_no_key_reaches_the_log_the_allowance_reads(self):
        self.ping(['ninjacentral', 'drunkenslug'])
        with open(os.path.join(self.runs_root, brainrun.PING_LOG)) as f:
            text = f.read()
        self.assertNotIn('right-key', text)
        self.assertNotIn(SECRET, text)

    def test_an_indexer_that_does_not_answer_gives_no_answer(self):
        with open(self.key_file) as f:
            data = json.load(f)
        data['indexers']['ninjacentral']['url'] = 'http://127.0.0.1:%d' % free_port()  # nothing listens there
        with open(self.key_file, 'w') as f:
            json.dump(data, f)
        self.assertIsNone(self.ping(['ninjacentral'])['ninjacentral'])


class PingJudgeTest(unittest.TestCase):
    """The preflight's reading of a search answer, on the captured replies."""

    def test_a_search_answer_is_no_problem(self):
        self.assertIsNone(brainrun.ping_problem('ninjacentral', (200, captured(SEARCH_ANSWER))))
        self.assertIsNone(brainrun.ping_problem('drunkenslug', (200, captured('indexer-answers/drunkenslug-search-girlfriends-s04e04.xml'))))

    def test_a_caps_reply_is_not_a_search_answer(self):
        # DrunkenSlug answers t=caps the same with or without a valid key: what the caps request let pass
        self.assertIn('not a search answer', brainrun.ping_problem('drunkenslug', (200, captured('indexer-caps/drunkenslug-caps.xml'))))

    def test_the_wrong_key_reply_is_an_error_that_names_its_fix(self):
        said = brainrun.ping_problem('drunkenslug', (200, captured(WRONG_KEY)))
        self.assertIn('drunkenslug answered the search with an error (403: Incorrect user credentials (wrong API key))', said)
        self.assertIn('python3 -I tools/brain/testbed.py indexer add drunkenslug --stash <entry>', said)
        self.assertIn('python3 -I tools/brain/testbed.py indexer off drunkenslug', said)

    def test_no_answer_and_a_refused_request_are_problems(self):
        self.assertIn('did not answer the search', brainrun.ping_problem('ninjacentral', None))
        self.assertIn('did not answer the search', brainrun.ping_problem('ninjacentral', (502, b'indexer not reachable')))
        self.assertIn('HTTP 401', brainrun.ping_problem('ninjacentral', (401, b'Unauthorized')))
        self.assertIn('not a search answer', brainrun.ping_problem('ninjacentral', (200, b'<html>login</html>')))


class CheckPreflightSearchTest(unittest.TestCase):
    """The check's preflight sends its search last, and refuses on an error or no answer."""

    def setUp(self):
        self.td = make_copies(self)
        self.cfg = make_cfg(self.td, runs_root=tempdir(self))
        put_limits(os.path.join(self.td, 'indexers.json'), {'ninjacentral': (2000, 450), 'drunkenslug': (1000, 300)})

    def test_the_wrong_key_reply_refuses_a_check(self):
        world = FakeWorld(self.cfg, pings={'drunkenslug': (200, captured(WRONG_KEY))})
        code, text = run_command('check', self.cfg, world)
        self.assertEqual(code, 1, text)
        self.assertIn('drunkenslug answered the search with an error', text)
        self.assertEqual(world.pinged, [['drunkenslug', 'ninjacentral']])

    def test_an_indexer_with_no_answer_refuses_a_check(self):
        code, text = run_command('check', self.cfg, FakeWorld(self.cfg, pings={'ninjacentral': None}))
        self.assertEqual(code, 1, text)
        self.assertIn('ninjacentral did not answer the search', text)

    def test_a_record_and_a_run_send_no_search(self):
        world = FakeWorld(self.cfg)
        brainrun.preflight('record', self.cfg, world)
        self.assertEqual(world.pinged, [])

    def test_no_search_is_sent_while_another_check_fails(self):
        world = FakeWorld(self.cfg, free=False)  # the stand-in's port is taken
        code, text = run_command('check', self.cfg, world)
        self.assertEqual(code, 1, text)
        self.assertEqual(world.pinged, [])

    def test_the_allowance_check_counts_the_preflight_search_as_one_more(self):
        put_limits(os.path.join(self.td, 'indexers.json'), {'ninjacentral': (2000, 450), 'drunkenslug': (60, 300)})
        world = FakeWorld(self.cfg)
        code, text = run_command('check', self.cfg, world)
        self.assertEqual(code, 1, text)
        self.assertIn('drunkenslug has 60 searches left today, and the check may need 61', text)
        self.assertEqual(world.pinged, [])


if __name__ == '__main__':
    unittest.main()
