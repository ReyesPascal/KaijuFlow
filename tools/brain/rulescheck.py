"""The rules check (#309, spec #298 story 46), run by `npm run check:brain` through test_rules_check.py.

`tools/brain/docs/rules.md` is the one home of every rule: a `### Name` heading, one sentence, `- **Why:**` and
`- **Enforced by:**`. The check finds a rule whose Enforced by names no enforcer: a tool or test written as code
(`brainrun.preflight`, `test_guard.py`), or the words "by hand"; and a line of rules.md or the runbook that names a
specific indexer (which indexers are on, and their limits, are the key file's: `testbed.py indexer list`) or describes
a retired command (`retired.retired_lines`: record, run, top-up, proof replay, grouped or halving runs; ADR 0010).
"""
import re

import retired

ENFORCED_BY = re.compile(r'^- \*\*Enforced by:\*\*(.*)$', re.M)
ENFORCER = re.compile(r'`[^`]+`|\bby hand\b', re.I)
# Known Newznab indexers, each as its words; a doc may write them joined, spaced, dotted or hyphenated, in any case.
INDEXERS = (('ninja', 'central'), ('drunken', 'slug'), ('nzb', 'geek'), ('nzb', 'planet'), ('dog', 'nzb'),
            ('nzb', 'finder'), ('alt', 'hub'), ('nzb', 'su'), ('nzb', 'cat'), ('abnzb',), ('miatrix',), ('scenenzbs',),
            ('tabula', 'rasa'), ('nzb', 'life'))
INDEXER = re.compile('|'.join(r'\b' + r'[ ._-]?'.join(words) + r'\b' for words in INDEXERS), re.I)


def rules(text):
    """(name, body) for every `### ` rule in rules.md's text."""
    parts = re.split(r'^### +(.+?)\s*$', text, flags=re.M)
    return list(zip(parts[1::2], parts[2::2]))


def problems(rules_text, runbook_text):
    """One line per mistake in rules.md and the runbook; empty when both pass."""
    out = []
    for name, body in rules(rules_text):
        enforced = ENFORCED_BY.search(body)
        if not enforced or not ENFORCER.search(enforced.group(1)):
            out.append(f'rules.md: "{name}" names no enforcer')
    for doc, text in (('rules.md', rules_text), ('RUNBOOK.md', runbook_text)):
        for n, line in enumerate(text.splitlines(), 1):
            out += [f'{doc}:{n}: names the indexer "{m.group(0)}"' for m in INDEXER.finditer(line)]
        out += retired.retired_lines(doc, text)
    return out
