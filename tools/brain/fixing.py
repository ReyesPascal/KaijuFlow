"""Fixing (#288, spec #279): what a cause Diagnosis proved in a check does next.

A proved KaijuFlow cause with no fix under way (its entry `open` or `reopened`) becomes a fix ticket under the map
(#183), `ready-for-agent`, with the cause, its proof (every Clue of its recipe, on this failure's own evidence) and the
Drill-down command that proves the fix; it is built and reviewed the usual way and merged on green. The ticket's text is
always written into the check's folder (`fix-tickets/<entry id>.md`); it is filed unless the check is a dry run, and
never twice: an open ticket whose title names the entry is named instead. A cause that is AltMount's, an indexer's,
Usenet's or the test machine's gets its entry and its workaround (the entry's `fix`), no ticket. A failure that proves
a `proved fixed` entry is a comeback: it gets its ticket (a KaijuFlow cause) and `diagnosis.py record` reopens the
entry. The check itself leaves the Casebook alone (the repository stays clean for the next check's preflight);
`record` writes the comeback and the filed ticket onto the entry. Formats: tools/brain/docs/formats.md, "Fixing".
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
import casebook  # noqa: E402

MAP = 183  # the map every ticket is a sub-issue of (docs/agents/issue-tracker.md)
LABEL = 'ready-for-agent'
DIR = 'fix-tickets'  # in the check's folder
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TICKET_WHEN = ('open', 'reopened')  # a KaijuFlow cause with no fix under way; `proved fixed` is a comeback
COMEBACK = 'proved fixed'
NOTE = '(Diagnosis, #288)'


def marker(entry_id):
    """What a fix ticket's title ends with, so an open one is found again."""
    return f'(Casebook {entry_id})'


def drill_command(meta):
    """The Drill-down (#272) on the play's title: `--title <imdb id>`, and `--episode SxxEyy` for an episode."""
    title = meta.get('title') or []
    tid = title[1] if len(title) > 1 and title[1] else None
    if not tid:
        return None
    imdb, *episode = str(tid).split(':')
    cmd = f'python3 -I tools/brain/brainrun.py drill --title {imdb}'
    if len(episode) == 2 and all(p.isdigit() for p in episode):
        cmd += f' --episode S{int(episode[0]):02d}E{int(episode[1]):02d}'
    return cmd


def _action(fields):
    if fields['whose'] != 'KaijuFlow':
        return 'workaround'
    return 'ticket' if fields['status'] in TICKET_WHEN or fields['status'] == COMEBACK else 'under way'


def plan(plays, book):
    """One row per Casebook entry a lead was proved for in the check's plays (`{'evidence', 'meta', 'diagnosis'}`), in
    the order they were proved: `entry`, `title`, `whose`, `status` (before the check), `fix`, `comeback`, `action`
    (`ticket`, `under way`: its fix is in progress or awaits its Drill-down, `workaround`: not KaijuFlow's) and
    `proved_in` (each play and Source it was proved on, with the Clues that proved it)."""
    rows, sections = {}, {}
    for p in plays:
        meta = p['meta']
        for f in p['diagnosis']['failures']:
            for lead in f['leads']:
                if lead['result'] != 'proved':
                    continue
                if lead['id'] not in rows:
                    path = os.path.join(book, lead['id'] + '.md')
                    if not os.path.exists(path):
                        continue
                    fields, sections[lead['id']] = casebook.read_entry(path)
                    rows[lead['id']] = {'entry': fields['id'], 'title': fields['title'], 'whose': fields['whose'],
                                        'status': fields['status'], 'fix': fields['fix'], 'file': os.path.basename(path),
                                        'comeback': fields['status'] == COMEBACK, 'action': _action(fields), 'proved_in': []}
                rows[lead['id']]['proved_in'].append({
                    'evidence': p['evidence'], 'label': meta.get('label'), 'release': f['release'], 'kind': f['kind'],
                    'date': (meta.get('t_start') or '')[:10], 'commit': meta.get('commit'), 'drill': drill_command(meta),
                    'clues': [{'clue': c['clue'], 'answer': c['answer'], 'wanted': c['wanted'],
                               'fact': (c.get('facts') or [''])[0]} for c in lead['clues']]})
    return list(rows.values()), sections


def ticket_text(row, sections, check):
    """(title, body) of one fix ticket."""
    title = ('Fix, a comeback: ' if row['comeback'] else 'Fix: ') + row['title'].rstrip('.') + ' ' + marker(row['entry'])
    lines = ['## Parent', f"#{MAP} (the map). Filed by Diagnosis (spec #279) after the check `{check}`: a proved "
             f"KaijuFlow cause, `{LABEL}`. Build it and review it the usual way; it merges on green.", '',
             '## The cause', '', row['title'], '', sections['Cause'], '',
             '## What the viewer saw', '', sections['What the viewer saw'], '']
    if row['comeback']:
        lines += ['## A comeback', '', f"This cause was proved fixed ({row['fix']}), and this check proved it again.", '']
    lines += ['## Its proof', '', "The entry's confirming test, a recipe of Clues, passed on this failure's own evidence "
              f"(the evidence folders are in the check's folder, `{check}`, under the runs root):", '']
    for p in row['proved_in']:
        lines.append(f"- {p['label']}: {p['release'] or 'the play itself'} ({p['kind']}, commit "
                     f"{str(p['commit'] or '?')[:7]}), evidence folder `{p['evidence']}`:")
        lines += [f"  - `{c['clue']}` answered {c['answer']} (wanted {c['wanted']})" + (f": {c['fact']}" if c['fact'] else '')
                  for c in p['clues']]
    drills = list(dict.fromkeys(p['drill'] for p in row['proved_in'] if p['drill']))
    labels = ', '.join(dict.fromkeys(str(p['label']) for p in row['proved_in']))
    lines += ['', f"The Casebook entry: `tools/brain/casebook/{row['file']}`.", '',
              '## Proving the fix', '', 'Once the fix is merged, a Drill-down on the failed title proves it (#272); the '
              'entry moves to `proved fixed` only after the Drill-down plays with no new failure:', '']
    lines += [f'    {d}' for d in drills] or ['(the evidence names no title id)']
    lines += ['', '## Acceptance criteria', '',
              '- [ ] The cause is fixed, with a test that reaches the code that uses the change.',
              f'- [ ] A Drill-down on {labels} plays with no new failure.']
    return title, '\n'.join(lines) + '\n'


def file_ticket(title, body, mark, tracker):
    """What happened to one ticket: `filed` (its number), `already` (an open ticket names the entry), `error`."""
    out = {'filed': None, 'dry_run': tracker is None}
    if tracker is None:
        return out
    try:
        have = tracker.find(mark)
        if have:
            return dict(out, filed=have, already=True)
        ref, problem = tracker.file(title, body)
        out['filed'] = ref
        if problem:
            out['error'] = problem
    except Exception as e:  # noqa: BLE001  (the tracker down: the text is kept, the report says so)
        out['error'] = br.scrub_text(f'{type(e).__name__}: {e}')
    return out


def after_check(run_dir, plays, book=casebook.FOLDER, tracker=None):
    """The fixes of one diagnosed check: the rows of `plan`, each `ticket` row with its text written into
    `<run folder>/fix-tickets/` and `ticket` (`title`, `file`, `filed`, `dry_run`, and `already` or `error`); filed
    through `tracker` (`find(text)` and `file(title, body)`), or not at all when it is None (a dry run)."""
    rows, sections = plan(plays, book)
    check = os.path.basename(os.path.normpath(run_dir))
    for row in rows:
        if row['action'] != 'ticket':
            continue
        title, body = ticket_text(row, sections[row['entry']], check)
        rel = os.path.join(DIR, row['entry'] + '.md')
        os.makedirs(os.path.join(run_dir, DIR), exist_ok=True)
        with open(os.path.join(run_dir, rel), 'w') as f:
            f.write(f'# {title}\n\n{body}')
        row['ticket'] = dict(title=title, file=rel, **file_ticket(title, body, marker(row['entry']), tracker))
    return rows


def report_lines(fixes):
    """The Diagnosis section's line for each proved cause: its ticket, its fix under way, or its workaround."""
    out = []
    for f in fixes:
        said = 'a comeback (it was proved fixed); `diagnosis.py record` reopens it; ' if f['comeback'] else ''
        if f['action'] == 'workaround':
            said += "not KaijuFlow's, no ticket; " + ('no workaround written yet' if f['fix'] == 'none yet' else f['fix'])
        elif f['action'] == 'under way':
            said += f"its fix is under way ({f['status']}: {f['fix']}); no new ticket"
        else:
            t = f['ticket']
            if t['filed'] and t.get('already'):
                said += f"fix ticket {t['filed']} is open already (`{t['file']}`)"
            elif t['filed']:
                said += f"fix ticket {t['filed']} filed (`{t['file']}`)" + (f"; {t['error']}" if t.get('error') else '')
            elif t['dry_run']:
                said += f"fix ticket text written, not filed (a dry run): `{t['file']}`"
            else:
                said += f"fix ticket text written, not filed ({t['error']}): `{t['file']}`"
        out.append(f"- {f['entry']} ({f['whose']}): {said}.")
    return out


# --------------------------------------------------------------------------- onto the Casebook (`diagnosis.py record`)

def _set(lines, end, key, value):
    for i in range(1, end):
        if lines[i].startswith(key + ': '):
            lines[i] = f'{key}: {casebook.written(value)}'
            return
    raise casebook.FormatError(f'no {key} in the front matter')


def _history(lines, line):
    at = lines.index('## History')
    nxt = next((i for i in range(at + 1, len(lines)) if lines[i].startswith('## ')), len(lines))
    body = [x for x in lines[at + 1:nxt] if x.strip()]
    lines[at + 1:nxt] = [''] + body + [line, '']


def record(run_dir, fixes, book=casebook.FOLDER):
    """Writes a diagnosed check's fixes onto their entries: a comeback reopens its entry (`reopened`, a History line),
    a filed ticket goes first in the entry's `fix` (an `open` entry is then `fix in progress`). Nothing is written twice.
    Returns {entry id: [what changed]}."""
    check = os.path.basename(os.path.normpath(run_dir))
    out = {}
    for f in fixes:
        path = os.path.join(book, f['file'])
        if not os.path.exists(path):
            continue
        fields, _ = casebook.read_entry(path)
        with open(path) as fh:
            lines = fh.read().split('\n')
        end = lines.index('---', 1)
        p = f['proved_in'][0]
        where = f"{check}, {p['label']} ({p['evidence']})"
        ref = (f.get('ticket') or {}).get('filed')
        changed = []
        if f['comeback'] and fields['status'] == COMEBACK:
            tail = f'fix ticket {ref}' if ref else ('its workaround no longer holds' if f['action'] == 'workaround'
                                                    else 'its fix ticket was not filed')
            _set(lines, end, 'status', 'reopened')
            _history(lines, f"- {p['date']}: reopened, a comeback: proved again in {where}; {tail}. {NOTE}")
            changed.append('reopened')
        if ref and ref not in re.findall(r'#\d+', fields['fix']):
            note = f"{ref} (fix ticket filed by Diagnosis{', a comeback' if f['comeback'] else ''})"
            _set(lines, end, 'fix', note if fields['fix'] == 'none yet' else f"{note}; {fields['fix']}")
            if fields['status'] == 'open':
                _set(lines, end, 'status', 'fix in progress')
            if not f['comeback']:
                _history(lines, f"- {p['date']}: fix ticket {ref} filed by Diagnosis, proved in {where}. {NOTE}")
            changed.append(f'fix ticket {ref}')
        if changed:
            with open(path, 'w') as fh:
                fh.write('\n'.join(lines))
            out[f['entry']] = changed
    return out


DRILL_NOTE = '(Drill-down, #272)'


def drill_history(drill, m):
    """The History line a Drill-down's mark writes on its entry."""
    head = f"- {drill['date']}: "
    if m['result'] == 'not marked':
        head += f"the Drill-down {drill['check']} did not mark it" + (f" {m['would']}" if m.get('would') else '')
    else:
        head += f"{m['result']} by the Drill-down {drill['check']}"
    return f"{head}: {m['why']}. {DRILL_NOTE}"


def record_drill(drill, book=casebook.FOLDER):
    """Writes a Drill-down's marks (drill.mark) onto their entries: `proved fixed` or `reopened` as the status, and a
    History line for every mark, the ones not marked too. Nothing is written twice. Returns {entry id: [what changed]}."""
    out = {}
    for m in (drill or {}).get('marks') or []:
        path = os.path.join(book, m.get('file') or '')
        if not m.get('file') or not os.path.exists(path):
            continue
        fields, _ = casebook.read_entry(path)
        with open(path) as fh:
            text = fh.read()
        line = drill_history(drill, m)
        if line in text:
            continue
        lines = text.split('\n')
        changed = []
        if m['result'] in ('proved fixed', 'reopened') and fields['status'] != m['result']:
            _set(lines, lines.index('---', 1), 'status', m['result'])
            changed.append(m['result'])
        _history(lines, line)
        changed.append('history')
        with open(path, 'w') as fh:
            fh.write('\n'.join(lines))
        out[m['entry']] = changed
    return out


# --------------------------------------------------------------------------- the real tracker

class GitHub:
    """This repo's GitHub Issues through `gh` (2.46: no `--parent`; a sub-issue is linked through the API,
    docs/agents/issue-tracker.md)."""

    def __init__(self, run=subprocess.run, cwd=REPO):
        self.run, self.cwd = run, cwd

    def _gh(self, *args):
        r = self.run(['gh', *args], cwd=self.cwd, capture_output=True, text=True, timeout=60, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"gh {' '.join(args[:2])}: {br.scrub_text((r.stderr or r.stdout or '').strip())}")
        return r.stdout

    def find(self, text):
        """The number (`#123`) of an open ticket whose title holds `text`, or None."""
        phrase = text.strip('()')  # GitHub's search drops the brackets; the title is matched on the whole text below
        found = json.loads(self._gh('issue', 'list', '--state', 'open', '--search', f'"{phrase}" in:title',
                                    '--json', 'number,title', '--limit', '100') or '[]')
        return next((f"#{i['number']}" for i in found if text in i['title']), None)

    def file(self, title, body):
        """Files one `ready-for-agent` ticket and puts it under the map: (`#123`, None), or (`#123`, the problem) when it
        was filed but not put under the map."""
        url = self._gh('issue', 'create', '--title', title, '--body', body, '--label', LABEL).strip().splitlines()[-1]
        n = int(url.rstrip('/').rsplit('/', 1)[1])
        try:
            db = self._gh('api', f'repos/{{owner}}/{{repo}}/issues/{n}', '--jq', '.id').strip()
            self._gh('api', '--method', 'POST', f'repos/{{owner}}/{{repo}}/issues/{MAP}/sub_issues', '-F', f'sub_issue_id={db}')
        except Exception as e:  # noqa: BLE001  (filed: say it is not under the map yet)
            return f'#{n}', br.scrub_text(f'filed, but not put under the map #{MAP}: {e}')
        return f'#{n}', None
