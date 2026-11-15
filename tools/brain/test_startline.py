"""Tests for startline.py, the Starting line design of the Speed Check page: where the marks of a ruler go, and the
colours the design promises. No Docker, no network.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
"""
import re
import unittest

import startline as sl


def contrast(a, b):
    """WCAG contrast ratio of two #rrggbb colours."""
    def lum(hex_):
        c = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class Scale(unittest.TestCase):
    """A ruler runs from 0 to a round number just past the longest mark, in at most 8 equal steps."""

    def test_the_scales_of_the_mock_up(self):
        # CONTENT.md: cold start on 0 to 6 s, warm start on 0 to 0.5 s, cold list on 0 to 12 s, the titles on 0 to 20 s
        self.assertEqual(sl.scale(5.47), (6, [0, 1, 2, 3, 4, 5, 6]))
        self.assertEqual(sl.scale(0.44), (0.5, [0, 0.1, 0.2, 0.3, 0.4, 0.5]))
        self.assertEqual(sl.scale(10.08), (12, [0, 2, 4, 6, 8, 10, 12]))
        self.assertEqual(sl.scale(17.65), (20, [0, 5, 10, 15, 20]))

    def test_the_scales_of_the_2026_11_13_baseline(self):
        self.assertEqual(sl.scale(6.73)[0], 7)
        self.assertEqual(sl.scale(0.46)[0], 0.5)
        self.assertEqual(sl.scale(50.49), (60, [0, 10, 20, 30, 40, 50, 60]))

    def test_a_mark_on_a_round_number_ends_the_ruler_there(self):
        self.assertEqual(sl.scale(4.0)[0], 4)

    def test_nothing_to_draw_still_gives_a_ruler(self):
        self.assertEqual(sl.scale(0), (1, [0, 1]))


class Positions(unittest.TestCase):
    def test_a_value_sits_at_its_share_of_the_ruler(self):
        self.assertEqual(sl.pct(4.82, 6), 80.33)
        self.assertEqual(sl.pct(0, 6), 0)
        self.assertEqual(sl.pct(6, 6), 100)

    def ruler(self):
        return sl.ruler([('AltMount direct', 3.61, False, ''), ('KaijuFlow', 4.82, True, ''), ('Usenet Ultimate', 5.47, False, '')],
                        limits=[(5.47, 'Limit 5.47 s: Usenet Ultimate', ''), (4.61, 'Limit 4.61 s: AltMount direct + 1 s', '')])

    def test_bars_and_limit_lines_are_placed_on_the_same_scale(self):
        html = self.ruler()
        self.assertEqual(re.findall(r'class="sl-bar[^"]*" style="width:([\d.]+)%', html), ['60.17', '80.33', '91.17'])
        self.assertEqual(re.findall(r'class="sl-lim" style="grid-row:\d+ / \d+;left:([\d.]+)%', html), ['91.17', '76.83'])
        self.assertEqual(re.findall(r'<span class="sl-tick[^"]*" style="left:([\d.]+)%', html),
                         ['0', '16.67', '33.33', '50', '66.67', '83.33', '100'])

    def test_each_limit_line_runs_from_its_own_label_down_through_every_lane(self):
        html = self.ruler()
        # two label rows, then the lanes in row 3: the lines end where the lanes end
        self.assertEqual(re.findall(r'class="sl-lim" style="grid-row:(\d+ / \d+)', html), ['1 / 4', '2 / 4'])
        self.assertIn('class="sl-lanes" style="grid-row:3"', html)

    def test_kaijuflow_is_the_highlighted_lane_and_every_bar_carries_its_time(self):
        html = self.ruler()
        self.assertEqual(re.findall(r'<li class="sl-lane( sl-kf)?">', html), ['', ' sl-kf', ''])
        self.assertEqual(re.findall(r'<b>([\d.]+ s)</b>', html), ['3.61 s', '4.82 s', '5.47 s'])


class DesignPromises(unittest.TestCase):
    """The two fixes over the mock-up (#132): a limit line crosses KaijuFlow's bar instead of hiding behind it, and the
    grey lanes stand out from the paper."""

    def tokens(self, block):
        return dict(re.findall(r'--([\w-]+):\s*(#[0-9A-Fa-f]{6})', block))

    def themes(self):
        light = re.search(r'\.sl\s*\{([^}]*)\}', sl.CSS).group(1)
        dark = re.search(r'@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\) \.sl\s*\{([^}]*)\}', sl.CSS).group(1)
        forced = re.search(r':root\[data-theme="dark"\] \.sl\s*\{([^}]*)\}', sl.CSS).group(1)
        self.assertEqual(self.tokens(dark), self.tokens(forced))
        report = re.search(r'\.sl\.sl-rep\s*\{([^}]*)\}', sl.REPORT_CSS).group(1)   # the one-page report's white sheet (#133)
        return {'light': self.tokens(light), 'dark': {**self.tokens(light), **self.tokens(dark)}, 'report': self.tokens(report)}

    def test_grey_lanes_are_at_least_3_to_1_against_the_paper_in_both_themes(self):
        for name, t in self.themes().items():
            self.assertGreaterEqual(contrast(t['lane'], t['paper']), 3, name)

    def test_text_is_at_least_4_5_to_1_against_the_paper_in_both_themes(self):
        for name, t in self.themes().items():
            for token in ('ink', 'slate'):
                self.assertGreaterEqual(contrast(t[token], t['paper']), 4.5, (name, token))
            self.assertGreaterEqual(contrast(t['on-yellow'], t['yellow']), 4.5, name)

    def z(self, selector):
        rule = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', sl.CSS).group(1)
        return int(re.search(r'z-index:\s*(\d+)', rule).group(1))

    def test_a_limit_line_is_drawn_over_the_bars_and_under_their_times(self):
        self.assertGreater(self.z('.sl .sl-lim'), self.z('.sl .sl-bar'))
        self.assertGreater(self.z('.sl .sl-val'), self.z('.sl .sl-lim'))
        # the lanes make no stacking layer of their own, which would put every bar above the lines again
        lanes = re.search(r'\.sl \.sl-lanes\s*\{([^}]*)\}', sl.CSS).group(1)
        self.assertNotIn('z-index', lanes)


if __name__ == '__main__':
    unittest.main()
