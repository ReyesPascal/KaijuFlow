"""The rules check (#309, spec #298 story 46): rules.md and the runbook pass, and a copy of them with one mistake fails.
    python3 -I -m unittest discover -s tools/brain -p 'test_rules_check.py'
"""
import os
import unittest

import rulescheck

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, 'docs', 'rules.md')
RUNBOOK = os.path.join(HERE, 'RUNBOOK.md')


def read(path):
    with open(path) as f:
        return f.read()


def with_rule(rules, block):
    """A copy of rules.md with one more rule at its end."""
    return rules.rstrip('\n') + '\n\n' + block


class RealDocsTest(unittest.TestCase):
    def test_rules_md_and_the_runbook_pass(self):
        found = rulescheck.problems(read(RULES), read(RUNBOOK))
        self.assertEqual(found, [], 'the rules check found:\n' + '\n'.join(found))


class EachMistakeFailsTest(unittest.TestCase):
    def setUp(self):
        self.rules, self.runbook = read(RULES), read(RUNBOOK)

    def test_a_rule_without_an_enforced_by_line_fails(self):
        rules = with_rule(self.rules, '### Lights off\n\nThe lights go off at night.\n\n- **Why:** owner, 2026-11-24.\n')
        self.assertEqual(rulescheck.problems(rules, self.runbook), ['rules.md: "Lights off" names no enforcer'])

    def test_a_rule_naming_an_indexer_fails(self):
        rules = with_rule(self.rules, '### Rare titles\n\nRare titles are searched on DrunkenSlug.\n\n'
                          '- **Why:** owner, 2026-11-24.\n- **Enforced by:** by hand.\n')
        found = rulescheck.problems(rules, self.runbook)
        self.assertEqual(len(found), 1, found)
        self.assertRegex(found[0], r'^rules\.md:\d+: names the indexer "DrunkenSlug"')

    def test_the_runbook_naming_an_indexer_fails(self):
        runbook = self.runbook + '\nIf ninja central is down, wait an hour.\n'
        found = rulescheck.problems(self.rules, runbook)
        self.assertEqual(found, [f'RUNBOOK.md:{len(runbook.splitlines())}: names the indexer "ninja central"'])

    def test_a_rule_describing_a_retired_command_fails(self):
        rules = with_rule(self.rules, '### Short Recordings\n\nA short Recording is topped up before the next run.\n\n'
                          '- **Why:** #140.\n- **Enforced by:** `brainrun.py record`.\n')
        found = rulescheck.problems(rules, self.runbook)
        self.assertEqual(len(found), 2, found)
        self.assertRegex(found[0], r'^rules\.md:\d+: topped up \(a retired step')
        self.assertRegex(found[1], r'^rules\.md:\d+: brainrun\.py record \(a retired command\)')

    def test_the_runbook_describing_a_proof_replay_fails(self):
        runbook = self.runbook + '\nAfter recording, run the proof replay.\n'
        self.assertEqual(rulescheck.problems(self.rules, runbook),
                         [f'RUNBOOK.md:{len(runbook.splitlines())}: proof replay (a retired step of the record command)'])


if __name__ == '__main__':
    unittest.main()
