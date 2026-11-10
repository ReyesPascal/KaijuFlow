"""Tests for the settings reader and the settings table command in testbed.py (spec #72, ticket #74).

Fixture test copies in a temporary folder with planted secrets; nothing real is read.
    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest

import brainrun
import testbed

SECRET = 'PLANTED-SECRET-9f3'
NAMES = {'ninjacentral': 'NinjaCentral', 'drunkenslug': 'DrunkenSlug', 'althub': 'altHUB'}
SHORT = {'ninjacentral': 'ninja', 'drunkenslug': 'drunkenslug', 'althub': 'althub'}


def _put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def make_copies(base=None, enabled=('ninjacentral', 'drunkenslug'), disabled=('althub',), caps=(12, 12, 25, 25, 25),
                url=lambda slug: 'http://host.docker.internal:1340/%s/api' % slug, key_mode=0o600, key_slugs=None, addon_off=(), backup_host='backup.example'):
    """A fake kaijuflow-test folder: KaijuFlow, UU, NzbDAV and both AltMounts, plus the key file."""
    base = base or tempfile.mkdtemp()
    td = os.path.join(base, 'kaijuflow-test')
    kf_cap, uu_cap, nz_cap, addon_cap, altkf_cap = caps
    for rel, cap in (('config/config.json', kf_cap), ('uu/config/config.json', uu_cap)):
        _put(os.path.join(td, rel), json.dumps({
            'indexers': [{'name': NAMES[s], 'url': url(s), 'apiKey': SECRET, 'enabled': s in enabled, 'maxPages': 3, 'timeout': 15}
                         for s in list(enabled) + list(disabled)],
            'healthChecks': {'sampleCount': 3, 'nzbsToInspect': 6, 'maxConnections': cap, 'inspectionMethod': 'smart',
                             'smartBatchSize': 3, 'smartAdditionalRuns': 1, 'smartMinHealthy': 1, 'archiveInspection': True,
                             'providers': [{'name': 'p', 'host': 'h', 'username': SECRET, 'password': SECRET}]},
            'searchConfig': {'seasonPackAdditionalPages': 2, 'seriesPackAdditionalPages': 2},
            'cacheTTL': 9000, 'altmountApiKey': SECRET, 'easynewsEnabled': False}))
    for side, cap in (('altmount-addon', addon_cap), ('altmount-kf', altkf_cap)):
        lines = ['import:', '    max_processor_workers: 2', '    segment_sample_percentage: 1',
                 'stremio:', '    indexers:', '        newsnab:']
        for s in list(enabled) + list(disabled):
            lines += ['            - id: x_%s' % s, '              name: %s' % SHORT[s], '              url: %s' % url(s).replace('/api', ''),
                      '              api_key: ' + SECRET, '              timeout_seconds: 15',
                      '              enabled: %s' % ('true' if s in enabled and not (side == 'altmount-addon' and s in addon_off) else 'false')]
        lines += ['providers:', '    - id: provider_1', '      host: news.example', '      username: ' + SECRET, '      password: ' + SECRET,
                  '      max_connections: %d' % cap, '      enabled: true', '      is_backup_provider: false',
                  '    - id: provider_2', '      host: ' + backup_host, '      max_connections: 99', '      enabled: true', '      is_backup_provider: true']
        _put(os.path.join(td, side, 'config/config.yaml'), '\n'.join(lines) + '\n')
    p = os.path.join(td, 'nzbdav/config/db.sqlite')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    db = sqlite3.connect(p)
    db.execute('create table ConfigItems (ConfigName text, ConfigValue text)')
    db.execute("insert into ConfigItems values ('api.key', ?)", (SECRET,))
    db.execute("insert into ConfigItems values ('usenet.max-download-connections', '25')")
    db.execute("insert into ConfigItems values ('usenet.providers', ?)", (json.dumps({'Providers': [
        {'Type': 1, 'Host': 'news.example', 'User': SECRET, 'Pass': SECRET, 'MaxConnections': nz_cap},
        {'Type': 3, 'Host': backup_host, 'User': SECRET, 'Pass': SECRET, 'MaxConnections': 15}]}),))
    db.commit()
    db.close()
    kp = os.path.join(td, 'indexers.json')
    _put(kp, json.dumps({'indexers': {s: {'url': 'https://real.example/api', 'apikey': SECRET} for s in (key_slugs or enabled)}}))
    os.chmod(kp, key_mode)
    return td


class ReaderTest(unittest.TestCase):
    def test_caps_sum_per_copy_and_no_secret_anywhere(self):
        td = make_copies()
        rep = testbed.settings_report(td, limit=100)
        self.assertEqual(rep['caps'], {'kaijuflow': 12, 'uu': 12, 'nzbdav': 25, 'altmount-addon': 25, 'altmount-kf': 25})
        self.assertEqual(rep['total'], 99)
        self.assertEqual(rep['limit'], 100)
        self.assertNotIn(SECRET, json.dumps(rep))
        self.assertNotIn(SECRET, testbed.render_settings(rep))

    def test_every_entry_on_the_main_providers_host_counts_backup_flag_or_not(self):
        td = make_copies(backup_host='news.example')  # the backup entries use the same Usenet host as the main provider
        rep = testbed.settings_report(td, limit=100)
        self.assertEqual(rep['caps']['altmount-addon'], 25 + 99)
        self.assertEqual(rep['caps']['altmount-kf'], 25 + 99)
        self.assertEqual(rep['caps']['nzbdav'], 25 + 15)

    def test_an_entry_on_another_host_is_shown_beside_and_not_counted(self):
        td = make_copies()  # backup entries on backup.example
        rep = testbed.settings_report(td, limit=100)
        self.assertEqual(rep['caps']['nzbdav'], 25)
        text = testbed.render_settings(rep)
        self.assertIn('max 25 (+ other host max 15, own limit)', text)
        self.assertIn('max 25 (+ other host max 99, own limit)', text)

    def test_enabled_indexers_are_slugs_from_each_copys_own_config(self):
        rep = testbed.settings_report(make_copies())
        for side in ('kaijuflow', 'uu', 'altmount-addon', 'altmount-kf'):
            self.assertEqual(rep['enabled'][side], ['drunkenslug', 'ninjacentral'], side)
        self.assertEqual(rep['enabled']['nzbdav'], [])

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
        code, text = self.run_cmd(make_copies())
        self.assertEqual(code, 0)
        self.assertNotIn(SECRET, text)
        self.assertIn('| Setting | KaijuFlow', text)
        self.assertIn('drunkenslug, ninjacentral', text)
        self.assertIn('Total: 99 of 100', text)
        self.assertIn('KaijuFlow 12', text)

    def test_per_indexer_rows_list_only_switched_on_indexers(self):
        _code, text = self.run_cmd(make_copies())
        self.assertIn('NinjaCentral 3', text)
        self.assertNotIn('altHUB', text)

    def test_limit_option_changes_the_verdict_sentence(self):
        _code, text = self.run_cmd(make_copies(), '--limit', '60')
        self.assertIn('Total: 99 of 60', text)
        self.assertIn('over the provider limit', text)

    def test_snapshot_of_the_runner_is_the_readers_output(self):
        td = make_copies()
        self.assertEqual(brainrun.snapshot_settings(td), testbed.settings_report(td)['settings'])


if __name__ == '__main__':
    unittest.main()
