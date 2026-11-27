"""Tests for the indexer allowance (spec #77, ticket #87): the usage command and what a check has left.

Fixture key files with limits (#302) and record folders in a temporary folder; no indexer, no Docker.
    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import datetime
import io
import json
import os
import unittest

import allowance
import brainrun
from test_settings import put_limits, tempdir

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def ms(dt):
    return int(dt.timestamp() * 1000)


def hours_ago(h):
    return NOW - datetime.timedelta(hours=h)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def limits_file(path, reset='rolling-24h', search=2000):
    """The key file at `path` with ninjacentral's daily limits in its entry (#302)."""
    put_limits(path, {'ninjacentral': (search, 450)}, reset=reset)


def api(kind, when, slug='ninjacentral'):
    return f'{kind} {slug} api q=x&t=search -> 200 10 bytes from=1.2.3.4 t={ms(when)}'


def nzb(kind, when, slug='ninjacentral'):
    return f'{kind} {slug} nzb abc123 -> 200 10 bytes from=1.2.3.4 t={ms(when)}'


def record_folder(root, name, listname, lines, status='recorded'):
    d = os.path.join(root, name)
    write(os.path.join(d, 'logs', 'standin.log'), '\n'.join([f'stand-in record list={listname} on 0.0.0.0:1340'] + lines) + '\n')
    write(os.path.join(d, 'meta.json'), json.dumps({'status': status}))


class AllowanceTest(unittest.TestCase):
    def setUp(self):
        base = tempdir(self)
        self.base = base
        self.td = os.path.join(base, 'kaijuflow-test')
        self.runs = os.path.join(base, 'runs')
        os.makedirs(self.td)
        os.makedirs(self.runs)
        self.cfg = dict(test_dir=self.td, runs_root=self.runs, listname='l', store=os.path.join(base, 'store'))
        self.limits = os.path.join(self.td, 'indexers.json')

    def lines(self, **kw):
        return allowance.usage_lines(self.cfg, NOW, **kw)

    def test_missing_key_file_is_one_plain_sentence_naming_the_command(self):
        out = self.lines()
        self.assertEqual(len(out), 1)
        self.assertIn('no key file', out[0])
        self.assertIn(self.limits, out[0])
        self.assertIn('testbed.py indexer add', out[0])

    def test_a_key_file_without_limits_says_so_and_names_the_command(self):
        write(self.limits, json.dumps({'indexers': {'ninjacentral': {'url': 'https://real.example', 'apikey': 'K-123'}}}))
        out = self.lines()
        self.assertEqual(len(out), 1)
        self.assertIn('no daily limits', out[0])
        self.assertIn('testbed.py indexer add', out[0])
        self.assertNotIn('K-123', out[0])

    def test_the_limits_are_read_from_the_key_file_named_by_key_file(self):
        self.cfg['key_file'] = os.path.join(self.base, 'elsewhere', 'keys.json')
        limits_file(self.cfg['key_file'], search=77)
        limits_file(self.limits, search=2000)  # the test folder's key file is not the one named
        self.assertIn('searches       0      77      77', '\n'.join(self.lines()))

    def test_a_limits_file_beside_the_key_file_is_not_read(self):
        write(os.path.join(self.td, 'limits.json'), json.dumps({'indexers': {'ninjacentral': {
            'search_per_day': 2000, 'download_per_day': 450, 'reset': 'rolling-24h'}}}))
        self.assertIn('no key file', self.lines()[0])

    def test_broken_limits_say_what_to_fix_and_show_no_key(self):
        write(self.limits, json.dumps({'indexers': {'ninjacentral': {'apikey': 'K-123', 'search_per_day': 'many'}}}))
        out = self.lines()
        self.assertEqual(len(out), 1)
        self.assertIn('wrong limits for ninjacentral', out[0])
        self.assertNotIn('K-123', out[0])

    def test_the_example_key_file_is_valid(self):
        here = os.path.dirname(os.path.abspath(__file__))
        limits, problem = allowance.load_limits(os.path.join(here, 'indexers.example.json'))
        self.assertIsNone(problem)
        self.assertEqual((limits['ninjacentral']['search'], limits['ninjacentral']['download']), (2000, 450))
        self.assertEqual((limits['drunkenslug']['search'], limits['drunkenslug']['download']), (1000, 100))

    def test_adds_the_standin_requests_since_the_reset(self):
        limits_file(self.limits)
        record_folder(self.runs, 'a-record', 'l', [
            api('RECORD', hours_ago(1)), api('RECORD', hours_ago(2)), api('ERROR', hours_ago(3)),
            api('RECORD', hours_ago(30)),  # before the reset: not counted
            api('HIT', hours_ago(1)),  # a replay costs the indexer nothing
            api('RECORD', hours_ago(1), slug='drunkenslug'),  # no limits in the key file
            nzb('RECORD', hours_ago(1))])
        text = '\n'.join(self.lines())
        # searches: 2 RECORD + 1 ERROR; downloads: 1
        self.assertIn('searches       3    2000    1997', text)
        self.assertIn('downloads      1     450     449', text)
        self.assertIn('this machine only', text)

    def test_only_the_standin_is_counted(self):
        # spec #298's review (P8): no live Usenet Ultimate copy's counters, which this machine does not have
        limits_file(self.limits)
        record_folder(self.runs, 'a-record', 'l', [api('RECORD', hours_ago(1))])
        text = '\n'.join(self.lines())
        self.assertIn("since 2026-11-09 12:00 UTC; the stand-in's 1 searches, 0 downloads.", text)
        self.assertNotIn('Usenet Ultimate', text)
        self.assertNotIn('copies', text)

    def test_clock_time_reset_counts_from_the_latest_reset(self):
        limits_file(self.limits, reset='10:00')
        record_folder(self.runs, 'a-record', 'l', [api('RECORD', hours_ago(1)), api('RECORD', hours_ago(3))])
        text = '\n'.join(self.lines())
        self.assertIn('searches       1    2000    1999', text)  # since 10:00 today: only the 11:00 one counts
        self.assertEqual(allowance.last_reset({'reset': '15:00', 'timezone': 'UTC'}, NOW), NOW.replace(hour=15) - datetime.timedelta(days=1))

    def test_indexer_names_match_however_they_are_written(self):
        put_limits(self.limits, {'Ninja Central': (2000, 450)})
        record_folder(self.runs, 'a-record', 'l', [api('RECORD', hours_ago(1), slug='ninjacentral')])
        self.assertIn('searches       1', '\n'.join(self.lines()))

    def test_usage_command_prints_the_table_and_needs_no_store(self):
        limits_file(self.limits)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = brainrun.main(['usage', '--test-dir', self.td, '--runs-root', self.runs])
        self.assertEqual(code, 0)
        self.assertIn('Indexer', out.getvalue())
        self.assertIn('ninjacentral', out.getvalue())

    def test_usage_command_without_limits_file_prints_one_sentence(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = brainrun.main(['usage', '--test-dir', self.td, '--runs-root', self.runs])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.getvalue().strip().splitlines()), 1)


if __name__ == '__main__':
    unittest.main()
