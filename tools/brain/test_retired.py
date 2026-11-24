"""Tests for the retired recording path (#273, ADR 0010): each retired command says "retired by ADR 0010" and stops,
touching nothing, unless it is run with --revive, which hands it to the archive (tools/brain/archive/).
    python3 -I -m unittest discover -s tools/brain -p 'test_retired.py'
"""
import contextlib
import io
import unittest
from unittest import mock

import brainrun
import pool
import retired
from test_settings import tempdir


def said(main, argv):
    """(exit code, what was printed) of a command's main(argv)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = main(argv)
    return code, out.getvalue()


RETIRED = [
    (brainrun.main, ['record', '--name', 'r', '--store', 'S', '--list', 'kf-265']),
    (brainrun.main, ['run', '--name', 'r', '--store', 'S', '--list', 'kf-265']),
    (brainrun.main, ['run', '--quick', '--store', 'S', '--list', 'kf-265']),
    (brainrun.main, ['smoke', '--store', 'S', '--list', 'smoke']),
    (brainrun.main, ['preflight', '--for', 'run', '--store', 'S', '--list', 'kf-265']),
    (brainrun.main, ['preflight', '--for', 'record', '--store', 'S', '--list', 'kf-265']),
    (brainrun.main, ['check', '--run', 'some-run-folder']),
    (pool.main, ['draw', '--test', 'test-3', '--out', 'titles.json']),
    (pool.main, ['check-ids']),
]


class RetiredCommandTest(unittest.TestCase):
    def test_each_retired_command_says_it_is_retired_and_stops_without_touching_anything(self):
        for main, argv in RETIRED:
            with self.subTest(argv=argv), mock.patch.object(retired, 'revive') as revive:
                code, text = said(main, argv)
                self.assertEqual(code, retired.EXIT_RETIRED)
                self.assertIn('retired by ADR 0010', text)
                self.assertIn('--revive', text)
                revive.assert_not_called()

    def test_with_revive_the_command_goes_to_the_archive_with_its_arguments_and_its_exit_code(self):
        for main, argv in RETIRED:
            with self.subTest(argv=argv), mock.patch.object(retired, 'revive', return_value=7) as revive:
                code, _ = said(main, argv + ['--revive'])
                self.assertEqual(code, 7)
                revive.assert_called_once()
                self.assertEqual(revive.call_args.args[1], argv)

    def test_the_live_commands_are_not_retired(self):
        tmp = tempdir(self)
        with mock.patch.object(retired, 'revive') as revive:
            code, text = said(brainrun.main, ['usage', '--runs-root', tmp, '--test-dir', tmp])
        revive.assert_not_called()
        self.assertNotIn('retired', text)
        self.assertEqual(code, 0)

    def test_the_archive_holds_every_retired_command(self):
        for name in retired.ARCHIVED.values():
            with self.subTest(module=name):
                self.assertIsNotNone(retired.archived_main(name))


if __name__ == '__main__':
    unittest.main()
