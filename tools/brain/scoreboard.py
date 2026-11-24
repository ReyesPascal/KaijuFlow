"""The scoreboard (#288, spec #279, story 58): what a check's Diagnosis section shows of the system learning, beside the
five numbers (`diagnosis.counts`).

- **Clues reused against new**: the Clues this check's confirming tests ran, each *reused* (in the library the last
  check with a failure kept) or *new* (joined the library since), and the Clues that joined since.
- **Fixes proved and comebacks**: the Casebook's entries `proved fixed` (less this check's comebacks), its comebacks in
  all (entries `reopened`, and this check's), this check's comebacks and the fix tickets it filed.
- **Failures per check over time by cause**: for the last 10 checks with a failure under the runs root, how many
  failures each had, by the cause proved (`unexplained` when none was).
- **Research count and usage**: the research written in the Case logs, how much of it shaped a hypothesis or a Clue
  (`used`), and in how many Case logs.

`score` is a pure function of what Diagnosis gathers (diagnosis.after_check); `report_lines` writes it.
"""
OVER_TIME = 10  # checks shown in the failures per check
UNEXPLAINED = 'unexplained'


def clue_numbers(plays, library, earlier):
    """`plays`: this check's stored plays (diagnosis.stored_plays); `library`: the Clue names now; `earlier`: [(check
    folder name, summary)] of the earlier checks, oldest first."""
    ran = sorted({c['clue'] for p in plays for f in p['diagnosis']['failures'] for lead in f['leads']
                  for c in lead.get('clues') or []})
    since = next(((name, s['library']) for name, s in reversed(earlier) if isinstance(s.get('library'), list)), None)
    out = {'ran': len(ran), 'library': len(library), 'since': None, 'reused': None, 'new': None, 'joined': None}
    if since:
        before = set(since[1])
        out.update(since=since[0], reused=sum(1 for c in ran if c in before), new=[c for c in ran if c not in before],
                   joined=sorted(set(library) - before))
    return out


def fix_numbers(entries, fixes):
    """`entries`: {id: fields} of the Casebook; `fixes`: this check's (fixing.after_check)."""
    back = sorted(f['entry'] for f in fixes if f['comeback'])
    status = {i: e['status'] for i, e in entries.items()}
    return {'proved_fixed': sum(1 for i, s in status.items() if s == 'proved fixed' and i not in back),
            'comebacks': sum(1 for i, s in status.items() if s == 'reopened' and i not in back) + len(back),
            'this_check': back,
            'tickets': sum(1 for f in fixes if (f.get('ticket') or {}).get('filed') and not f['ticket'].get('already'))}


def by_cause(checks):
    """`checks`: [(check folder name, summary)], oldest first, this check last."""
    out = []
    for name, s in checks:
        fs = [f for p in s.get('plays') or [] for f in p.get('failures') or []]
        if not fs:
            continue
        causes = {}
        for f in fs:
            key = f.get('cause') if f.get('verdict') == 'found' and f.get('cause') else UNEXPLAINED
            causes[key] = causes.get(key, 0) + 1
        out.append({'check': name, 'failures': len(fs), 'causes': dict(sorted(causes.items()))})
    return out[-OVER_TIME:]


def research_numbers(logs):
    """`logs`: {id: Case log} under the cases folder, or None when no Case logs are kept."""
    if logs is None:
        return None
    items = [(cid, r) for cid, log in logs.items() for r in log.get('research') or []]
    return {'count': len(items), 'used': sum(1 for _, r in items if r.get('used')), 'logs': len({cid for cid, _ in items})}


def score(name, summary, plays, library, earlier, entries, logs):
    return {'clues': clue_numbers(plays, library, earlier),
            'fixes': fix_numbers(entries, summary.get('fixes') or []),
            'by_cause': by_cause(list(earlier) + [(name, summary)]),
            'research': research_numbers(logs)}


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _names(names):
    return f" ({', '.join(names)})" if names else ''


def report_lines(board):
    c, f, r = board['clues'], board['fixes'], board['research']
    if c['since'] is None:
        clue = f"Clues: the confirming tests ran {c['ran']}; the library holds {c['library']} (no earlier check kept its " \
               "library, so none is told new)."
    else:
        clue = f"Clues: the confirming tests ran {c['ran']}: {c['reused']} reused, {len(c['new'])} new since the check " \
               f"{c['since']}{_names(c['new'])}; the library holds {c['library']}, {len(c['joined'])} joined since" \
               f"{_names(c['joined'])}."
    fix = f"Fixes: {f['proved_fixed']} proved fixed, {_plural(f['comebacks'], 'comeback')} in all; this check: " \
          f"{_plural(len(f['this_check']), 'comeback')}{_names(f['this_check'])}, {_plural(f['tickets'], 'fix ticket')} filed."
    research = 'Research: not kept (no Case logs folder).' if r is None else \
        f"Research: {r['count']} looked up in {_plural(r['logs'], 'Case log')}, {r['used']} used."
    lines = [clue, fix, research, '', f'Failures per check by cause (the last {OVER_TIME} checks with a failure):', '']
    lines += [f"- {b['check']}: {_plural(b['failures'], 'failure')}: " + ', '.join(f'{k} {n}' for k, n in b['causes'].items())
              for b in board['by_cause']]
    return lines
