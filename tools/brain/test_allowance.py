"""Tests for the indexer allowance (spec #77, ticket #87): the usage command and the record preflight's table.

Fixture key files with limits (#302), counter files (stats.json) and record folders in a temporary folder; no indexer, no Docker.
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
from test_preflight import FakeWorld, make_cfg, record, run_command
from test_settings import make_copies, put_limits, tempdir

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


def stats_file(path, searches=(), grabs=(), name='NinjaCentral'):
    stamp = '%Y-%m-%dT%H:%M:%S.000Z'
    write(path, json.dumps({'indexers': {name: {
        'queryHistory': [{'timestamp': t.strftime(stamp), 'success': True} for t in searches],
        'grabHistory': [{'timestamp': t.strftime(stamp), 'title': 'x'} for t in grabs]}}}))


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
        self.stats = os.path.join(base, 'stats.json')

    def lines(self, **kw):
        return allowance.usage_lines(self.cfg, NOW, **kw)

    def test_missing_key_file_is_one_plain_sentence_naming_the_command(self):
        out = self.lines(stats_files=[])
        self.assertEqual(len(out), 1)
        self.assertIn('no key file', out[0])
        self.assertIn(self.limits, out[0])
        self.assertIn('testbed.py indexer add', out[0])

    def test_a_key_file_without_limits_says_so_and_names_the_command(self):
        write(self.limits, json.dumps({'indexers': {'ninjacentral': {'url': 'https://real.example', 'apikey': 'K-123'}}}))
        out = self.lines(stats_files=[])
        self.assertEqual(len(out), 1)
        self.assertIn('no daily limits', out[0])
        self.assertIn('testbed.py indexer add', out[0])
        self.assertNotIn('K-123', out[0])

    def test_the_limits_are_read_from_the_key_file_named_by_key_file(self):
        self.cfg['key_file'] = os.path.join(self.base, 'elsewhere', 'keys.json')
        limits_file(self.cfg['key_file'], search=77)
        limits_file(self.limits, search=2000)  # the test folder's key file is not the one named
        self.assertIn('searches       0      77      77', '\n'.join(self.lines(stats_files=[])))

    def test_a_limits_file_beside_the_key_file_is_not_read(self):
        write(os.path.join(self.td, 'limits.json'), json.dumps({'indexers': {'ninjacentral': {
            'search_per_day': 2000, 'download_per_day': 450, 'reset': 'rolling-24h'}}}))
        self.assertIn('no key file', self.lines(stats_files=[])[0])

    def test_broken_limits_say_what_to_fix_and_show_no_key(self):
        write(self.limits, json.dumps({'indexers': {'ninjacentral': {'apikey': 'K-123', 'search_per_day': 'many'}}}))
        out = self.lines(stats_files=[])
        self.assertEqual(len(out), 1)
        self.assertIn('wrong limits for ninjacentral', out[0])
        self.assertNotIn('K-123', out[0])

    def test_the_example_key_file_is_valid(self):
        here = os.path.dirname(os.path.abspath(__file__))
        limits, problem = allowance.load_limits(os.path.join(here, 'indexers.example.json'))
        self.assertIsNone(problem)
        self.assertEqual((limits['ninjacentral']['search'], limits['ninjacentral']['download']), (2000, 450))
        self.assertEqual((limits['drunkenslug']['search'], limits['drunkenslug']['download']), (1000, 100))

    def test_adds_standin_requests_and_copy_counts_since_the_reset(self):
        limits_file(self.limits)
        record_folder(self.runs, 'a-record', 'l', [
            api('RECORD', hours_ago(1)), api('RECORD', hours_ago(2)), api('ERROR', hours_ago(3)),
            api('RECORD', hours_ago(30)),  # before the reset: not counted
            api('HIT', hours_ago(1)),  # a replay costs the indexer nothing
            api('RECORD', hours_ago(1), slug='drunkenslug'),  # no limits in the key file
            nzb('RECORD', hours_ago(1))])
        stats_file(self.stats, searches=[hours_ago(5), hours_ago(40)], grabs=[hours_ago(4), hours_ago(6)])
        text = '\n'.join(self.lines(stats_files=[self.stats]))
        # searches: 3 from the stand-in (2 RECORD + 1 ERROR) + 1 from the copy; downloads: 1 + 2
        self.assertIn('searches       4    2000    1996', text)
        self.assertIn('downloads      3     450     447', text)
        self.assertIn('this machine only', text)
        self.assertIn('latest hundred', text)

    def test_default_counter_files_are_the_live_copy_only(self):
        self.assertEqual(allowance.default_stats_files(self.cfg), [allowance.DEFAULT_LIVE_STATS])

    def test_clock_time_reset_counts_from_the_latest_reset(self):
        limits_file(self.limits, reset='10:00')
        stats_file(self.stats, searches=[hours_ago(1), hours_ago(3)])
        text = '\n'.join(self.lines(stats_files=[self.stats]))
        self.assertIn('searches       1    2000    1999', text)  # since 10:00 today: only the 11:00 entry counts
        self.assertEqual(allowance.last_reset({'reset': '15:00', 'timezone': 'UTC'}, NOW), NOW.replace(hour=15) - datetime.timedelta(days=1))

    def test_missing_or_unreadable_counter_files_count_as_nothing(self):
        limits_file(self.limits)
        write(self.stats, 'not json')
        text = '\n'.join(self.lines(stats_files=[self.stats, os.path.join(self.td, 'none.json')]))
        self.assertIn('searches       0    2000    2000', text)

    def test_indexer_names_match_however_they_are_written(self):
        limits_file(self.limits)
        stats_file(self.stats, searches=[hours_ago(1)], name='Ninja Central')
        self.assertIn('searches       1', '\n'.join(self.lines(stats_files=[self.stats])))

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

    # --- the record preflight

    def test_last_complete_recording_of_the_same_list_only(self):
        record_folder(self.runs, '1-record', 'l', [api('RECORD', hours_ago(9))] * 2)
        record_folder(self.runs, '2-record', 'l', [api('RECORD', hours_ago(8))] * 5, status='null')  # stopped early
        record_folder(self.runs, '3-record', 'other', [api('RECORD', hours_ago(7))] * 7)
        name, counts = allowance.last_complete_recording(self.runs, 'l')
        self.assertEqual(name, '1-record')
        self.assertEqual(counts, {'ninjacentral': {'search': 2, 'download': 0}})
        self.assertIsNone(allowance.last_complete_recording(self.runs, 'none'))

    def test_record_preflight_shows_table_and_last_count_and_warns_when_short(self):
        limits_file(self.limits)
        record_folder(self.runs, '1-record', 'l', [api('RECORD', hours_ago(30))] * 2100)
        text = '\n'.join(allowance.record_preflight_lines(self.cfg, NOW, stats_files=[]))
        self.assertIn('searches       0    2000    2000', text)
        self.assertIn('sent 2100 requests', text)
        self.assertIn('Warning: ninjacentral has 2000 searches left but the last full recording needed 2100', text)

    def test_record_preflight_has_no_warning_when_it_fits(self):
        limits_file(self.limits)
        record_folder(self.runs, '1-record', 'l', [api('RECORD', hours_ago(30))] * 10)
        text = '\n'.join(allowance.record_preflight_lines(self.cfg, NOW, stats_files=[]))
        self.assertIn('sent 10 requests', text)
        self.assertNotIn('Warning', text)

    def test_record_preflight_without_limits_file_or_earlier_recording_says_so(self):
        text = '\n'.join(allowance.record_preflight_lines(self.cfg, NOW, stats_files=[]))
        self.assertIn('no key file', text)
        self.assertIn('no earlier complete recording', text)

    def test_preflight_for_record_warns_but_does_not_block(self):
        copies = make_copies(self)
        cfg = make_cfg(copies, runs_root=self.runs)
        record(cfg)
        limits_file(os.path.join(copies, 'indexers.json'), search=1)
        record_folder(self.runs, '1-record', 'l', [api('RECORD', hours_ago(30))] * 50)
        code, text = run_command('record', cfg, FakeWorld(cfg))
        self.assertEqual(code, 0, text)
        self.assertIn('Warning: ninjacentral', text)
        self.assertIn('sent 50 requests', text)
        self.assertIn('Setup is right for a record', text)


if __name__ == '__main__':
    unittest.main()
