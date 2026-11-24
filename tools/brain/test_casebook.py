"""Tests for casebook.py: the Casebook's entry files, their format and the generated index (#281)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import casebook

HERE = os.path.dirname(os.path.abspath(__file__))

ENTRY = """---
id: unscramble-read-error
title: Unscramble could not read the set, so the scrambled original went up and AltMount refused it.
kind: fallback
step: unscramble
whose: KaijuFlow
status: fixed awaiting proof
match:
  - rules: 1
    sign: "fallback | import_wait not ok | *all files failed validation*"
confirm:
  - clue: unscramble-read-error
    answer: yes
  - clue: altmount-missing-volumes
    answer: yes
fix: "#245 (PR #252, 6efbc7c): a read-error is retried once, then the Source is not uploaded"
seen:
  - check: 2026-11-23T183239Z-baseline-218
    title: The Witcher S01E01
    play: cold 1
    date: 2026-11-23
  - check: 2026-11-23T190950Z-grouped-219
    title: Joker
    play: cold 2
    date: 2026-11-23
---

## What the viewer saw

A fallback: video from the next Source, 2 to 8 s late.

## Signs

KaijuFlow's `unscramble` step ends `read-error`.

## Cause

Unscramble could not read the first articles it needs.

## How it was proved

The logs of every case, step by step.

## Ruled out

KaijuFlow going over its own connection cap (#245's first test).

## Fix

#245 (PR #252).

## History

- 2026-11-24: converted from the casebook sweep (draft A1).
"""


def casebook_with(entries, index=True):
    """A Casebook folder in a temp dir holding `entries` ({file name: text}), with its index written unless index=False."""
    folder = tempfile.mkdtemp()
    for name, text in entries.items():
        with open(os.path.join(folder, name), 'w') as f:
            f.write(text)
    if index:
        casebook.write_index(folder)
    return folder


class IndexTest(unittest.TestCase):
    def tearDown(self):
        shutil.rmtree(getattr(self, 'folder', ''), ignore_errors=True)

    def test_the_index_holds_what_programs_need_from_each_entry(self):
        self.folder = casebook_with({'unscramble-read-error.md': ENTRY})
        with open(os.path.join(self.folder, 'index.json')) as f:
            index = json.load(f)
        self.assertEqual(index['entries'], [{
            'id': 'unscramble-read-error',
            'file': 'unscramble-read-error.md',
            'title': 'Unscramble could not read the set, so the scrambled original went up and AltMount refused it.',
            'kind': 'fallback', 'step': 'unscramble', 'whose': 'KaijuFlow', 'status': 'fixed awaiting proof',
            'match': [{'rules': 1, 'sign': 'fallback | import_wait not ok | *all files failed validation*'}],
            'confirm': [{'clue': 'unscramble-read-error', 'answer': 'yes'},
                        {'clue': 'altmount-missing-volumes', 'answer': 'yes'}],
            'occurrences': 2, 'first_seen': '2026-11-23', 'last_seen': '2026-11-23',
        }])
        self.assertIn('casebook.py index', index['generated_by'])

    def test_a_casebook_whose_index_matches_its_files_has_no_problem(self):
        self.folder = casebook_with({'unscramble-read-error.md': ENTRY})
        self.assertEqual(casebook.problems(self.folder, clues=set()), [])

    def test_an_entry_changed_after_the_index_was_written_is_a_problem(self):
        self.folder = casebook_with({'unscramble-read-error.md': ENTRY})
        with open(os.path.join(self.folder, 'unscramble-read-error.md'), 'w') as f:
            f.write(ENTRY.replace('status: fixed awaiting proof', 'status: fix in progress'))
        self.assertEqual(casebook.problems(self.folder, clues=set()),
                         ['index.json: unscramble-read-error differs from its file (status); '
                          'run python3 -I tools/brain/casebook.py index'])

    def test_an_entry_missing_from_the_index_and_an_index_row_without_a_file_are_problems(self):
        self.folder = casebook_with({'unscramble-read-error.md': ENTRY})
        os.rename(os.path.join(self.folder, 'unscramble-read-error.md'), os.path.join(self.folder, 'other-cause.md'))
        with open(os.path.join(self.folder, 'other-cause.md'), 'w') as f:
            f.write(ENTRY.replace('id: unscramble-read-error', 'id: other-cause'))
        self.assertEqual(casebook.problems(self.folder, clues=set()), [
            'index.json: other-cause is not in the index; run python3 -I tools/brain/casebook.py index',
            'index.json: unscramble-read-error has no entry file; run python3 -I tools/brain/casebook.py index',
        ])

    def test_a_hand_edit_of_the_index_is_a_problem(self):
        self.folder = casebook_with({'unscramble-read-error.md': ENTRY})
        path = os.path.join(self.folder, 'index.json')
        with open(path) as f:
            text = f.read()
        with open(path, 'w') as f:
            f.write(text.replace('"occurrences": 2', '"occurrences": 3'))
        self.assertEqual(casebook.problems(self.folder, clues=set()),
                         ['index.json: unscramble-read-error differs from its file (occurrences); '
                          'run python3 -I tools/brain/casebook.py index'])

    def test_a_missing_index_is_a_problem(self):
        self.folder = casebook_with({'unscramble-read-error.md': ENTRY}, index=False)
        self.assertEqual(casebook.problems(self.folder, clues=set()),
                         ['index.json: missing; run python3 -I tools/brain/casebook.py index'])


class CommandTest(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run([sys.executable, '-I', os.path.join(HERE, 'casebook.py'), *args],
                              capture_output=True, text=True)

    def test_one_command_writes_the_index_and_check_then_passes_until_a_file_changes(self):
        folder = casebook_with({'unscramble-read-error.md': ENTRY}, index=False)
        self.addCleanup(shutil.rmtree, folder, True)
        self.assertEqual(self.run_tool('check', folder).returncode, 1)
        written = self.run_tool('index', folder)
        self.assertEqual((written.returncode, written.stdout), (0, f'wrote {folder}/index.json: 1 entries\n'))
        checked = self.run_tool('check', folder)
        self.assertEqual((checked.returncode, checked.stdout), (0, 'Casebook: 1 entries, no problems\n'))
        with open(os.path.join(folder, 'unscramble-read-error.md'), 'w') as f:
            f.write(ENTRY.replace('    date: 2026-11-23\n---', '    date: 2026-11-24\n---'))
        checked = self.run_tool('check', folder)
        self.assertEqual((checked.returncode, checked.stdout),
                         (1, 'index.json: unscramble-read-error differs from its file (last_seen); '
                             'run python3 -I tools/brain/casebook.py index\n'))


if __name__ == '__main__':
    unittest.main()
