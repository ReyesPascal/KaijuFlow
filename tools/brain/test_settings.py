"""Tests for the settings reader and the settings table command in testbed.py (spec #72, ticket #74).

Fixture test copies in a temporary folder with planted secrets; nothing real is read.
    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
import unittest.mock

import brainrun
import testbed

SECRET = 'PLANTED-SECRET-9f3'
NAMES = {'ninjacentral': 'NinjaCentral', 'drunkenslug': 'DrunkenSlug', 'althub': 'altHUB'}
HOST_IP = '192.0.2.10'  # the fixture machine's LAN address (a documentation address)
SHORT = {'ninjacentral': 'ninja', 'drunkenslug': 'drunkenslug', 'althub': 'althub'}


def tempdir(case):
    """A temporary folder that is removed when the test is over."""
    d = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, d, True)
    return d


def _put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def rules(films=3000, episodes=1000):
    """Sort and filter rules in the shape KaijuFlow keeps them (`movieFilters`, `tvFilters`), cut short:
    an order, switches, a size cap and one named drop rule."""
    def one(cap):
        return {'sortOrder': ['quality', 'size', 'language'], 'enabledSorts': {'quality': True, 'size': True, 'language': False},
                'enabledPriorities': {'resolution': {}, 'visualTag': {'3D': False}}, 'maxFileSize': cap,
                'rules': {'rankedRegexPatterns': [{'id': 'r-1', 'name': 'No disc images', 'pattern': r'\bBDMV\b|\bBD(25|50)\b',
                                                   'flags': 'i', 'mode': 'drop', 'score': 0, 'enabled': True}]}}
    return {'movieFilters': one(films), 'tvFilters': one(episodes)}


# The Play-time check's settings of the committed expected settings file (#190; its Head start on, #206), as an applied
# copy holds them.
PLAY_TIME_CHECK = {'candidateCount': 3, 'preferenceMode': 'priority', 'whenToResolve': 'on-results'}


SEARCH_METHODS = {f'{kind}SearchMethod': ['text'] for kind in ('movie', 'tv', 'animeMovie', 'animeTv')}  # Ultimate Text Search (#270)


def make_copies(case, base=None, enabled=('ninjacentral', 'drunkenslug'), disabled=('althub',), caps=(12, 25),
                url=lambda slug: 'http://host.docker.internal:1340/%s/api' % slug, key_mode=0o600, key_slugs=None,
                altkf_off=(), backup_host='backup.example', kf_rules=None, kf_fallback=True, host_ip=HOST_IP,
                altmount_url='http://%s:8087' % HOST_IP):
    """A fake kaijuflow-test folder: KaijuFlow and its AltMount, the one setup (#187), plus the key file. KaijuFlow holds
    the sort and filter rules of rules() unless others are given (kf_rules: what goes into the config; {} for none), and its
    fallback is on (ultimateFallback.enabled, #185) unless kf_fallback is False, with the Play-time check's settings (#190). caps: KaijuFlow's and its AltMount's
    connection caps (KaijuFlow's None: its config names none); altkf_off: indexers its AltMount has switched off. host_ip:
    HOST_IP in the folder's .env, beside a secret; altmount_url: KaijuFlow's altmountUrl (None leaves either out)."""
    base = base or tempdir(case)
    td = os.path.join(base, 'kaijuflow-test')
    kf_cap, altkf_cap = caps
    for rel, cap, own in (('config/config.json', kf_cap, kf_rules),):
        _put(os.path.join(td, rel), json.dumps({
            **(rules() if own is None else own),
            'indexers': [{'name': NAMES[s], 'url': url(s), 'apiKey': SECRET, 'enabled': s in enabled, 'maxPages': 3, 'timeout': 15,
                          **SEARCH_METHODS} for s in list(enabled) + list(disabled)],
            'healthChecks': {**({} if cap is None else {'maxTotalConnections': cap}),
                             'providers': [{'name': 'p', 'host': 'h', 'username': SECRET, 'password': SECRET}]},
            'searchConfig': {'seasonPackAdditionalPages': 2, 'seriesPackAdditionalPages': 2},
            'cacheTTL': 9000, 'altmountApiKey': SECRET, 'easynewsEnabled': False,
            'ultimateFallback': {'enabled': kf_fallback, **PLAY_TIME_CHECK},
            **({} if altmount_url is None else {'altmountUrl': altmount_url})}))
    _put(os.path.join(td, '.env'), f'JWT_SECRET={SECRET}\nTEST_DIR={td}\n' + ('' if host_ip is None else f'HOST_IP={host_ip}\n'))
    for side, cap in (('altmount-kf', altkf_cap),):
        lines = ['import:', '    max_processor_workers: 2', '    segment_sample_percentage: 1',
                 'stremio:', '    indexers:', '        newsnab:']
        for s in list(enabled) + list(disabled):
            lines += ['            - id: x_%s' % s, '              name: %s' % SHORT[s], '              url: %s' % url(s).replace('/api', ''),
                      '              api_key: ' + SECRET, '              timeout_seconds: 15',
                      '              enabled: %s' % ('true' if s in enabled and s not in altkf_off else 'false')]
        lines += ['providers:', '    - id: provider_1', '      host: news.example', '      username: ' + SECRET, '      password: ' + SECRET,
                  '      max_connections: %d' % cap, '      enabled: true', '      is_backup_provider: false',
                  '    - id: provider_2', '      host: ' + backup_host, '      max_connections: 99', '      enabled: true', '      is_backup_provider: true']
        _put(os.path.join(td, side, 'config/config.yaml'), '\n'.join(lines) + '\n')
    kp = os.path.join(td, 'indexers.json')
    _put(kp, json.dumps({'indexers': {s: {'url': 'https://real.example/api', 'apikey': SECRET} for s in (key_slugs or enabled)}}))
    os.chmod(kp, key_mode)
    return td


class ReaderTest(unittest.TestCase):
    def test_caps_sum_per_copy_and_no_secret_anywhere(self):
        td = make_copies(self)
        rep = testbed.settings_report(td, limit=100)
        self.assertEqual(rep['caps'], {'kaijuflow': 12, 'altmount-kf': 25})
        self.assertEqual(rep['total'], 37)
        self.assertEqual(rep['limit'], 100)
        self.assertNotIn(SECRET, json.dumps(rep))
        self.assertNotIn(SECRET, testbed.render_settings(rep))

    def test_kaijuflows_cap_is_its_total_connection_cap_and_its_default_when_unnamed(self):
        # #191: the worker count (maxConnections) went with the list-time check; the cap every check shares stays.
        self.assertEqual(testbed.settings_report(make_copies(self, caps=(9, 25)), limit=100)['caps']['kaijuflow'], 9)
        rep = testbed.settings_report(make_copies(self, caps=(None, 25)), limit=100)
        self.assertEqual(rep['caps']['kaijuflow'], 8)  # KaijuFlow's default (src/health/nntpConnection.ts)
        self.assertEqual(rep['total'], 33)

    def test_every_entry_on_the_main_providers_host_counts_backup_flag_or_not(self):
        td = make_copies(self, backup_host='news.example')  # the backup entries use the same Usenet host as the main provider
        rep = testbed.settings_report(td, limit=100)
        self.assertEqual(rep['caps']['altmount-kf'], 25 + 99)

    def test_an_entry_on_another_host_is_shown_beside_and_not_counted(self):
        td = make_copies(self)  # backup entries on backup.example
        rep = testbed.settings_report(td, limit=100)
        self.assertEqual(rep['caps']['altmount-kf'], 25)
        self.assertIn('max 25 (+ other host max 99, own limit)', testbed.render_settings(rep))

    def test_enabled_indexers_are_slugs_from_each_copys_own_config(self):
        rep = testbed.settings_report(make_copies(self))
        for side in ('kaijuflow', 'altmount-kf'):
            self.assertEqual(rep['enabled'][side], ['drunkenslug', 'ninjacentral'], side)
        self.assertEqual(set(rep['enabled']), {'kaijuflow', 'altmount-kf'})  # the one setup (#187)

    def test_slug_ignores_api_suffix_and_rejects_other_hosts(self):
        self.assertEqual(testbed.standin_slug('http://host.docker.internal:1340/ninjacentral'), 'ninjacentral')
        self.assertEqual(testbed.standin_slug('http://host.docker.internal:1340/ninjacentral/api'), 'ninjacentral')
        self.assertEqual(testbed.standin_slug('http://host.docker.internal:1340/ninjacentral/api/'), 'ninjacentral')
        self.assertIsNone(testbed.standin_slug('https://api.ninjacentral.co.za/api'))
        self.assertIsNone(testbed.standin_slug('http://host.docker.internal:1341/x/api'))
        self.assertEqual(testbed.standin_slug('http://host.docker.internal:1400/x', port=1400), 'x')


class CommandTest(unittest.TestCase):
    def run_cmd(self, td, *args):
        out = io.StringIO()
        old = os.environ.get('TEST_DIR')
        os.environ['TEST_DIR'] = td
        try:
            with contextlib.redirect_stdout(out):
                code = testbed.main(['testbed.py', 'settings'] + list(args))
        finally:
            if old is None:
                del os.environ['TEST_DIR']
            else:
                os.environ['TEST_DIR'] = old
        return code, out.getvalue()

    def test_table_and_budget_are_printed_without_secrets(self):
        code, text = self.run_cmd(make_copies(self))
        self.assertEqual(code, 0)
        self.assertNotIn(SECRET, text)
        self.assertIn('| Setting | KaijuFlow', text)
        self.assertIn('drunkenslug, ninjacentral', text)
        self.assertIn('Total: 37 of 100', text)
        self.assertIn('KaijuFlow 12', text)

    def test_per_indexer_rows_list_only_switched_on_indexers(self):
        _code, text = self.run_cmd(make_copies(self))
        self.assertIn('NinjaCentral 3', text)
        self.assertNotIn('altHUB', text)

    def test_limit_option_changes_the_verdict_sentence(self):
        _code, text = self.run_cmd(make_copies(self), '--limit', '30')
        self.assertIn('Total: 37 of 30', text)
        self.assertIn('over the provider limit', text)

    def test_snapshot_of_the_runner_is_the_readers_output(self):
        td = make_copies(self)
        self.assertEqual(brainrun.snapshot_settings(td), testbed.settings_report(td)['settings'])


class ShowCommandTest(unittest.TestCase):
    """`testbed.py read-settings [side]`: the reader's output as JSON, the command the secret hook points to (#161)."""

    def run_cmd(self, td, *args):
        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ, {'TEST_DIR': td}), contextlib.redirect_stdout(out):
            code = testbed.main(['testbed.py', 'read-settings'] + list(args))
        return code, out.getvalue()

    def test_prints_every_copys_settings_and_no_secret(self):
        td = make_copies(self)
        code, text = self.run_cmd(td)
        self.assertEqual(code, 0)
        self.assertNotIn(SECRET, text)
        self.assertEqual(json.loads(text), testbed.read_settings(td))
        self.assertIn('***', text)

    def test_prints_one_copy_when_named(self):
        code, text = self.run_cmd(make_copies(self), 'altmount-kf')
        self.assertEqual((code, list(json.loads(text))), (0, ['altmount-kf']))
        self.assertNotIn(SECRET, text)

    def test_an_unknown_copy_says_which_exist_and_exits_2(self):
        code, text = self.run_cmd(make_copies(self), 'nope')
        self.assertEqual(code, 2)
        self.assertIn('nope', text)
        self.assertIn('kaijuflow', text)


if __name__ == '__main__':
    unittest.main()
