"""Tests for unreported.py: INDEX.md rows newer than the handoff note."""
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
    def test_the_note_is_dated_in_utc_like_the_index(self):
        stamp = unreported.note_time(unreported.os.path.dirname(unreported.os.path.dirname(unreported.os.path.dirname(
            unreported.os.path.abspath(unreported.__file__)))))
        self.assertRegex(stamp or '', r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')


if __name__ == '__main__':
    unittest.main()
