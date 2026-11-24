"""Tests for `testbed.py indexer add|on|off|remove|list` (#302): one command keeps KaijuFlow's test config, the stand-in's
key file (with the indexer's daily limits) and the test copy of AltMount in step, from the owner's stash.

Seam: testbed.main on a fixture test folder (test_settings.make_copies) and a fixture stash folder; the preflight and the
allowance then read what it wrote. No indexer, no Docker, no real test folder.
    python3 -I -m unittest discover -s tools/brain -p 'test_testbed_indexer.py'
"""
import contextlib
import io
import json
import os
import re
import stat
import unittest
import unittest.mock

import allowance
import brainrun
import brainreport as br
import testbed
from test_preflight import FakeWorld, make_cfg
from test_settings import SECRET, make_copies, tempdir

# The owner's two stash entries as they are written (2026-11-24), values replaced: a key line and an address line in
# either order, a heading line, and a note after the address.
STASH = {
    'drunkenslug': 'DrunkenSlug API key: DS-KEY-0a1b2c3d4e5f\n'
                   'API URL: https://api.slug.example/api (live AltMount reaches it through ds-xml-proxy, which drops o=json)\n',
    'ninja': 'NinjaCentral (NZB indexer)\nAPI URL: https://ninja.example\nAPI key: NC-KEY-9z8y7x6w5v\n',
    'newone': 'NewOne\nAPI URL: https://new.example/api/\nAPI key: NEW-KEY-1q2w3e4r5t\n',
    'nokey': 'Something\nAPI URL: https://nokey.example\n',
}
KEYS = ('DS-KEY-0a1b2c3d4e5f', 'NC-KEY-9z8y7x6w5v', 'NEW-KEY-1q2w3e4r5t', SECRET)
HOSTS = ('api.slug.example', 'ninja.example', 'new.example', 'real.example')
STAMP = '20261124T120000Z'


def read(path):
    with open(path) as f:
        return f.read()


class IndexerCommandTest(unittest.TestCase):
    def setUp(self):
        self.td = make_copies(self)
        self.stash = os.path.join(tempdir(self), '.stash')
        os.makedirs(self.stash)
        for name, text in STASH.items():
            with open(os.path.join(self.stash, name), 'w') as f:
                f.write(text)
        self.key_path = os.path.join(self.td, 'indexers.json')
        self.kf_path = os.path.join(self.td, 'config', 'config.json')
        self.am_path = os.path.join(self.td, 'altmount-kf', 'config', 'config.yaml')

    def run_cmd(self, *args):
        out = io.StringIO()
        env = {'TEST_DIR': self.td, 'STASH_DIR': self.stash}
        with unittest.mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
            code = testbed.main(['testbed.py', 'indexer', *args])
        text = out.getvalue()
        for secret in KEYS + HOSTS:
            self.assertNotIn(secret, text)
        return code, text

    def files(self):
        return {p: read(p) for p in (self.key_path, self.kf_path, self.am_path)}

    def keys(self):
        return json.loads(read(self.key_path))['indexers']

    def kf(self):
        return {i['name']: i for i in json.loads(read(self.kf_path))['indexers']}

    def backups(self):
        d = os.path.join(self.td, testbed.BACKUP_DIR)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def am_flat(self):
        return br.flatten_yaml(read(self.am_path))

    # --- add

    def test_add_writes_the_key_file_entry_kaijuflows_entry_and_switches_altmounts_indexers_off(self):
        before = self.files()
        code, text = self.run_cmd('add', 'newone', '--stash', 'newone', '--searches', '500', '--downloads', '50',
                                  '--drop', 'o', '--name', 'NewOne')
        self.assertEqual(code, 0, text)
        keys = self.keys()
        self.assertEqual(keys['newone'], {'url': 'https://new.example', 'apikey': 'NEW-KEY-1q2w3e4r5t', 'enabled': True,
                                          'drop_params': ['o'], 'search_per_day': 500, 'download_per_day': 50,
                                          'reset': 'rolling-24h'})
        old = json.loads(before[self.key_path])['indexers']
        self.assertEqual({k: v for k, v in keys.items() if k != 'newone'}, old)  # the other entries as they were
        self.assertEqual(stat.S_IMODE(os.stat(self.key_path).st_mode), 0o600)

        kf, kf_old = self.kf(), {i['name']: i for i in json.loads(before[self.kf_path])['indexers']}
        self.assertEqual(kf['NewOne'], {'name': 'NewOne', 'url': 'http://host.docker.internal:1340/newone/api',
                                        'apiKey': testbed.STANDIN_API_KEY, 'enabled': True, 'maxPages': 3, 'timeout': 15})
        self.assertEqual({k: v for k, v in kf.items() if k != 'NewOne'}, kf_old)
        kf_rest = {k: v for k, v in json.loads(read(self.kf_path)).items() if k != 'indexers'}
        self.assertEqual(kf_rest, {k: v for k, v in json.loads(before[self.kf_path]).items() if k != 'indexers'})

        flat, flat_old = self.am_flat(), br.flatten_yaml(before[self.am_path])
        switches = {k: v for k, v in flat.items() if re.fullmatch(r'stremio\.indexers\.newsnab\[\d+\]\.enabled', k)}
        self.assertEqual(sorted(v for k, v in flat_old.items() if k in switches), ['false', 'true', 'true'])  # two were on
        self.assertEqual(set(switches.values()), {'false'})
        self.assertEqual({k: v for k, v in flat.items() if not k.endswith('].enabled')},
                         {k: v for k, v in flat_old.items() if not k.endswith('].enabled')})
        self.assertEqual(flat['providers[0].enabled'], 'true')  # only the indexers' switches

        # each changed file backed up, as it was before
        names = self.backups()
        self.assertEqual(len(names), 3, names)
        saved = {read(os.path.join(self.td, testbed.BACKUP_DIR, n)) for n in names}
        self.assertEqual(saved, set(before.values()))
        self.assertIn('newone: added, on; 500 searches and 50 downloads a day (reset rolling-24h); dropped parameters: o.', text)
        self.assertIn('backed up to backups/', text)

    def test_what_add_writes_is_what_the_preflight_and_the_allowance_read(self):
        code, text = self.run_cmd('add', 'newone', '--stash', 'newone', '--searches', '500', '--downloads', '50')
        self.assertEqual(code, 0, text)
        self.run_cmd('add', 'ninjacentral', '--stash', 'ninja', '--searches', '2000', '--downloads', '450')
        self.run_cmd('add', 'drunkenslug', '--stash', 'drunkenslug', '--searches', '1000', '--downloads', '100', '--drop', 'o')
        cfg = make_cfg(self.td, runs_root=tempdir(self))
        self.assertEqual(brainrun.preflight('check', cfg, FakeWorld(cfg)), [])
        limits, problem = allowance.load_limits(allowance.limits_path(cfg))
        self.assertIsNone(problem)
        self.assertEqual({s: (v['search'], v['download']) for s, v in limits.items()},
                         {'newone': (500, 50), 'ninjacentral': (2000, 450), 'drunkenslug': (1000, 100)})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            brainrun.main(['usage', '--test-dir', self.td, '--runs-root', cfg['runs_root']])
        self.assertIn('newone       searches       0     500     500', out.getvalue())

    def test_add_again_writes_that_entry_again_in_place_and_nothing_else(self):
        before = self.files()
        code, text = self.run_cmd('add', 'drunkenslug', '--stash', 'drunk', '--searches', '1000', '--downloads', '100',
                                  '--drop', 'o', '--reset', '04:00', '--timezone', 'Europe/Amsterdam')
        self.assertEqual(code, 0, text)
        keys, old = self.keys(), json.loads(before[self.key_path])['indexers']
        self.assertEqual(keys['drunkenslug'], {'url': 'https://api.slug.example', 'apikey': 'DS-KEY-0a1b2c3d4e5f', 'enabled': True,
                                               'drop_params': ['o'], 'search_per_day': 1000, 'download_per_day': 100,
                                               'reset': '04:00', 'timezone': 'Europe/Amsterdam'})
        self.assertEqual(keys['ninjacentral'], old['ninjacentral'])
        self.assertEqual(json.loads(read(self.kf_path)), json.loads(before[self.kf_path]))  # DrunkenSlug was there, on
        self.assertIn('drunkenslug: written again, on; 1000 searches and 100 downloads a day (reset 04:00 Europe/Amsterdam); '
                      'dropped parameters: o.', text)
        self.assertNotIn('config/config.json backed up', text)

    def test_off_and_on_switch_exactly_that_indexer_in_both_files(self):
        self.run_cmd('add', 'drunkenslug', '--stash', 'drunkenslug', '--searches', '1000', '--downloads', '100')
        before, saved = self.files(), len(self.backups())
        code, text = self.run_cmd('off', 'drunkenslug')
        self.assertEqual(code, 0, text)
        keys, old = self.keys(), json.loads(before[self.key_path])['indexers']
        self.assertEqual(keys['drunkenslug'], {**old['drunkenslug'], 'enabled': False})
        self.assertEqual(keys['ninjacentral'], old['ninjacentral'])
        kf, kf_old = self.kf(), {i['name']: i for i in json.loads(before[self.kf_path])['indexers']}
        self.assertEqual(kf['DrunkenSlug'], {**kf_old['DrunkenSlug'], 'enabled': False})
        self.assertEqual({k: v for k, v in kf.items() if k != 'DrunkenSlug'}, {k: v for k, v in kf_old.items() if k != 'DrunkenSlug'})
        self.assertEqual(read(self.am_path), before[self.am_path])  # already off since the add
        self.assertIn('drunkenslug: switched off, off; 1000 searches and 100 downloads a day (reset rolling-24h).', text)
        self.assertEqual(len(self.backups()), saved + 2)  # the key file and KaijuFlow's config
        cfg = make_cfg(self.td)
        self.assertEqual(brainrun.preflight('record', cfg, FakeWorld(cfg)), [])  # the two agree: drunkenslug is off in both

        code, text = self.run_cmd('on', 'drunkenslug')
        self.assertEqual(code, 0, text)
        self.assertEqual(json.loads(read(self.kf_path)), json.loads(before[self.kf_path]))
        self.assertEqual(read(self.am_path), before[self.am_path])
        self.assertEqual(self.keys(), json.loads(before[self.key_path])['indexers'])

    def test_a_switch_that_changes_nothing_writes_and_backs_up_nothing(self):
        self.run_cmd('off', 'drunkenslug')
        count, before = len(self.backups()), self.files()
        code, text = self.run_cmd('off', 'drunkenslug')
        self.assertEqual(code, 0, text)
        self.assertEqual((len(self.backups()), self.files()), (count, before))
        self.assertIn('Nothing changed', text)

    def test_remove_takes_the_indexer_out_of_both_files(self):
        before = self.files()
        code, text = self.run_cmd('remove', 'drunkenslug')
        self.assertEqual(code, 0, text)
        self.assertEqual(set(self.keys()), {'ninjacentral'})
        self.assertEqual(set(self.kf()), {'NinjaCentral', 'altHUB'})
        self.assertEqual(self.kf()['NinjaCentral'], {i['name']: i for i in json.loads(before[self.kf_path])['indexers']}['NinjaCentral'])
        self.assertIn('drunkenslug: removed.', text)
        cfg = make_cfg(self.td)
        self.assertEqual(brainrun.preflight('record', cfg, FakeWorld(cfg)), [])

    def test_remove_of_an_indexer_only_kaijuflow_has(self):
        code, text = self.run_cmd('remove', 'althub')  # in KaijuFlow's config (off), not in the key file
        self.assertEqual(code, 0, text)
        self.assertEqual(set(self.kf()), {'NinjaCentral', 'DrunkenSlug'})

    def test_refusals_write_nothing_and_name_what_to_do(self):
        before = self.files()
        for args, said in ((('add', 'newone', '--stash', 'nosuch', '--searches', '1', '--downloads', '1'), 'no stash entry matches'),
                           (('add', 'newone', '--stash', 'n', '--searches', '1', '--downloads', '1'), 'matches several stash entries'),
                           (('add', 'newone', '--stash', 'nokey', '--searches', '1', '--downloads', '1'), 'has no "API key:" line'),
                           (('add', 'newone', '--stash', 'newone', '--downloads', '1'), 'needs --searches'),
                           (('add', 'newone', '--stash', 'newone', '--searches', 'many', '--downloads', '1'), 'whole number'),
                           (('add', 'newone', '--stash', 'newone', '--searches', '1', '--downloads', '1', '--reset', 'noon'), '--reset'),
                           (('add', 'New One', '--stash', 'newone', '--searches', '1', '--downloads', '1'), 'slug'),
                           (('on', 'newone'), 'add it with testbed.py indexer add newone'),
                           (('on', 'althub'), 'not in the key file'),
                           (('remove', 'newone'), 'neither'),
                           (('rename', 'x'), 'choose add, on, off, remove or list')):
            code, text = self.run_cmd(*args)
            self.assertEqual(code, 1, (args, text))
            self.assertIn('Nothing changed', text)
            self.assertIn(said, text, args)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.backups(), [])

    def test_list_shows_names_switches_and_limits_only(self):
        self.run_cmd('add', 'ninjacentral', '--stash', 'ninja', '--searches', '2000', '--downloads', '450')
        code, text = self.run_cmd('list')
        self.assertEqual(code, 0, text)
        self.assertEqual(text.splitlines(), [
            'althub: not in the key file, KaijuFlow off; no daily limits.',
            'drunkenslug: key file on, KaijuFlow on; no daily limits.',
            'ninjacentral: key file on, KaijuFlow on; 2000 searches and 450 downloads a day (reset rolling-24h).'])

    def test_agents_may_run_it(self):
        import guard
        for cmd in ('python3 -I tools/brain/testbed.py indexer add drunkenslug --stash drunkenslug --searches 1000 --downloads 100 --drop o',
                    'python3 -I tools/brain/testbed.py indexer off drunkenslug', 'python3 -I tools/brain/testbed.py indexer list'):
            self.assertIsNone(guard.refusal('Bash', {'command': cmd}, os.getcwd()), cmd)


if __name__ == '__main__':
    unittest.main()
