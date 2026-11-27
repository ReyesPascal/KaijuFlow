"""The live docs describe real-use checks only (#273, ADR 0010): no live doc tells a session to record, top up, replay a
Recording, run a timed or grouped run, or use another retired command (retired.py; they live in tools/brain/archive/).
    python3 -I -m unittest discover -s tools/brain -p 'test_live_docs.py'
"""
import os
import unittest

import retired

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


class RetiredWordsTest(unittest.TestCase):
    def test_a_retired_command_is_found_with_its_file_and_line(self):
        text = 'Intro.\nThen run `python3 -I tools/brain/brainrun.py record --name x --store s --list l`.\nDone.\n'
        self.assertEqual(retired.retired_lines('RUNBOOK.md', text),
                         ['RUNBOOK.md:2: brainrun.py record (a retired command)'])

    def test_each_retired_command_and_step_is_found(self):
        for line in ('brainrun.py run --name baseline', 'brainrun.py smoke --store x', 'preflight --for record',
                     'preflight --for run --store s', 'check --run <run folder>', 'pool.py draw --test t',
                     'pool.py check-ids', 'build_page.py <run folder>', 'Top it up with the record command',
                     'a top-up asks again', 'one grouped run', 'each halving run', 'run --no-wait'):
            with self.subTest(line=line):
                self.assertEqual(len(retired.retired_lines('d.md', line)), 1, line)

    def test_the_live_commands_and_the_archive_pointer_pass(self):
        text = ('Run `brainrun.py check --quick --rebuild-image`, `brainrun.py drill --title tt1`, `brainrun.py preflight`.\n'
                'The retired recording path is in tools/brain/archive/README.md (ADR 0010).\n'
                'A run of a quick check, the runs root and run folders stay.\n')
        self.assertEqual(retired.retired_lines('d.md', text), [])


class LiveDocsTest(unittest.TestCase):
    def test_no_live_doc_describes_a_retired_command(self):
        found = []
        for rel in retired.LIVE_DOCS:
            with open(os.path.join(REPO, rel)) as f:
                found += retired.retired_lines(rel, f.read())
        self.assertEqual(found, [], 'a live doc describes a retired command again (ADR 0010; the archive keeps them):\n'
                         + '\n'.join(found))


if __name__ == '__main__':
    unittest.main()
