"""Tests for unreported.py: INDEX.md rows newer than the handoff note."""
import os
import subprocess
import tempfile
import unittest

import unreported

INDEX = """# Brain runs

| Date (UTC) | Name | Result | What changed from the previous run | Headline numbers | Folder |
|---|---|---|---|---|---|
| 2026-11-20T22:38:14.219Z | baseline-189 | ok | No earlier run to compare with: this is the first one. | fails 0 | [2026-11-20T223814Z-baseline-189](2026-11-20T223814Z-baseline-189/) |
| 2026-11-21T05:09:27.546Z | baseline-218-wifi | stopped | No earlier run. | stopped by SIGTERM | [2026-11-21T050927Z-baseline-218-wifi](2026-11-21T050927Z-baseline-218-wifi/) |
"""


class RowsAfterTest(unittest.TestCase):
    def test_only_rows_after_the_note_are_given(self):
        self.assertEqual(unreported.rows_after(INDEX, '2026-11-21T03:00:00Z'),
                         [('2026-11-21T05:09:27.546Z', 'baseline-218-wifi', 'stopped', '2026-11-21T050927Z-baseline-218-wifi')])

    def test_no_row_after_the_note_gives_none(self):
        self.assertEqual(unreported.rows_after(INDEX, '2026-11-22T00:00:00Z'), [])

    def test_the_header_and_other_lines_are_not_rows(self):
        self.assertEqual(len(unreported.rows_after(INDEX, '2000-01-01T00:00:00Z')), 2)


class NoteTimeTest(unittest.TestCase):
    def test_the_note_is_dated_by_its_last_commit_in_utc_like_the_index(self):
        with tempfile.TemporaryDirectory() as repo:
            note = os.path.join(repo, 'NEXT_SESSION.md')
            open(note, 'w').write('# Handoff\n')
            env = {**os.environ, 'GIT_COMMITTER_DATE': '2026-11-24T01:02:03-06:00', 'GIT_AUTHOR_NAME': 't',
                   'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}
            for cmd in (['init', '-q'], ['add', 'NEXT_SESSION.md'], ['commit', '-qm', 'note']):
                subprocess.run(['git', '-C', repo, *cmd], check=True, env=env)
            self.assertEqual(unreported.note_time(note), '2026-11-24T07:02:03Z')

    def test_a_note_git_cannot_date_gives_none(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(unreported.note_time(os.path.join(folder, 'NEXT_SESSION.md')))


if __name__ == '__main__':
    unittest.main()
