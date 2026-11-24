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


BROKEN = {
    'a field left out': (ENTRY.replace('step: unscramble\n', ''),
                         'unscramble-read-error.md: the fields must be id, title, kind, step, whose, status, match, '
                         'confirm, fix, seen in that order (missing step)'),
    'an unknown field': (ENTRY.replace('fix: ', 'ticket: "#245"\nfix: '),
                         'unscramble-read-error.md: the fields must be id, title, kind, step, whose, status, match, '
                         'confirm, fix, seen in that order (unknown ticket)'),
    'fields out of order': (ENTRY.replace('kind: fallback\nstep: unscramble\n', 'step: unscramble\nkind: fallback\n'),
                            'unscramble-read-error.md: the fields must be id, title, kind, step, whose, status, match, '
                            'confirm, fix, seen in that order'),
    'an id that is not the file name': (ENTRY.replace('id: unscramble-read-error', 'id: read-error'),
                                        'unscramble-read-error.md: id must be the file name without .md, '
                                        'in lower-case words joined by -'),
    'a status outside the five': (ENTRY.replace('status: fixed awaiting proof', 'status: proved'),
                                  "unscramble-read-error.md: status 'proved' is not one of: open, fix in progress, "
                                  'fixed awaiting proof, proved fixed, reopened'),
    'whose outside the list': (ENTRY.replace('whose: KaijuFlow', 'whose: Newshosting'),
                               "unscramble-read-error.md: whose 'Newshosting' is not one of: KaijuFlow, AltMount, "
                               'indexer, Usenet, test-only, unknown'),
    'whose unknown on a fixed entry': (ENTRY.replace('whose: KaijuFlow', 'whose: unknown'),
                                       'unscramble-read-error.md: whose unknown is only for an open entry'),
    'a kind outside the list': (ENTRY.replace('kind: fallback', 'kind: crash'),
                                "unscramble-read-error.md: kind 'crash' is not one of: fail, fallback, check miss, "
                                'slow play, wrong title, nothing to play'),
    'a step that is no step line': (ENTRY.replace('step: unscramble', 'step: unpack'),
                                    "unscramble-read-error.md: step 'unpack' is not one of: " + ', '.join(casebook.STEPS)),
    'a sign without three parts': (ENTRY.replace('fallback | import_wait not ok | ', 'fallback | '),
                                   "unscramble-read-error.md: sign 'fallback | *all files failed validation*' must be "
                                   '`<kind> | <step> ok|not ok | <reason>`'),
    'a sign whose step says neither ok nor not ok': (ENTRY.replace('import_wait not ok', 'import_wait failed'),
                                                     "unscramble-read-error.md: sign step 'import_wait failed' must be "
                                                     '`<step> ok`, `<step> not ok` or *'),
    'a match without its rules version': (ENTRY.replace('  - rules: 1\n    sign:', '  - sign:'),
                                          'unscramble-read-error.md: match: an item takes rules, sign in that order'),
    'confirm as free text': (ENTRY.replace('confirm:\n  - clue: unscramble-read-error\n    answer: yes\n'
                                           '  - clue: altmount-missing-volumes\n    answer: yes\n',
                                           'confirm: read the logs\n'),
                             "unscramble-read-error.md: confirm must list Clues, or be 'none (no evidence kept)'"),
    'a Clue answer of maybe': (ENTRY.replace('    answer: yes\n  - clue: alt', '    answer: maybe\n  - clue: alt'),
                               'unscramble-read-error.md: confirm answer must be yes or no'),
    'a seen date that is no date': (ENTRY.replace('    date: 2026-11-23\n---', '    date: 23 Nov\n---'),
                                    "unscramble-read-error.md: seen date '23 Nov' must be YYYY-MM-DD"),
    'a value YAML would read otherwise': (ENTRY.replace('fix: "#245 (PR #252', 'fix: #245 (PR #252').replace(
        'then the Source is not uploaded"', 'then the Source is not uploaded'),
        "unscramble-read-error.md:16: put '#245 (PR #252, 6efbc7c): a read-error is retried once, then the Source is "
        "not uploaded' in double quotes"),
    'no front matter': (ENTRY.split('---\n', 2)[2],
                        'unscramble-read-error.md: must start with front matter between two --- lines'),
    'a section left out': (ENTRY.replace('## Ruled out\n\nKaijuFlow going over its own connection cap (#245\'s first test).\n\n', ''),
                           'unscramble-read-error.md: the sections must be What the viewer saw, Signs, Cause, How it was '
                           'proved, Ruled out, Fix, History in that order (found: What the viewer saw, Signs, Cause, '
                           'How it was proved, Fix, History)'),
    'an empty section': (ENTRY.replace('A fallback: video from the next Source, 2 to 8 s late.\n', ''),
                         "unscramble-read-error.md: section 'What the viewer saw' is empty"),
    'text before the first section': (ENTRY.replace('---\n\n## What', '---\n\nSome words.\n\n## What'),
                                      'unscramble-read-error.md: text before the first section'),
}


class FormatTest(unittest.TestCase):
    def test_an_entry_that_breaks_the_format_is_a_problem(self):
        for case, (text, problem) in BROKEN.items():
            with self.subTest(case):
                folder = casebook_with({'unscramble-read-error.md': ENTRY})
                self.addCleanup(shutil.rmtree, folder, True)
                with open(os.path.join(folder, 'unscramble-read-error.md'), 'w') as f:
                    f.write(text)
                self.assertEqual(casebook.problems(folder, clues=set()), [problem])

    def test_the_index_command_refuses_a_casebook_with_a_broken_entry(self):
        folder = casebook_with({'unscramble-read-error.md': ENTRY.replace('kind: fallback', 'kind: crash')}, index=False)
        self.addCleanup(shutil.rmtree, folder, True)
        with self.assertRaises(casebook.FormatError):
            casebook.write_index(folder)
        self.assertFalse(os.path.exists(os.path.join(folder, 'index.json')))

    def test_an_entry_without_evidence_says_so_in_confirm(self):
        text = ENTRY.replace('confirm:\n  - clue: unscramble-read-error\n    answer: yes\n'
                             '  - clue: altmount-missing-volumes\n    answer: yes\n',
                             'confirm: none (no evidence kept)\n')
        folder = casebook_with({'unscramble-read-error.md': text})
        self.addCleanup(shutil.rmtree, folder, True)
        self.assertEqual(casebook.problems(folder, clues=set()), [])


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
