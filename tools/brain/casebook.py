"""The Casebook: one Markdown file per known cause of a play going wrong, and the index generated from them (#281, spec #279).

    python3 -I tools/brain/casebook.py index [folder]   write <folder>/index.json from the entry files
    python3 -I tools/brain/casebook.py check [folder]   list every problem; exit 1 when there is one

The folder defaults to tools/brain/casebook/. The format (front matter fields, the seven sections, the values each
field takes) is in tools/brain/casebook/README.md. `check` finds an entry that breaks the format, an index that
disagrees with the files (never edit index.json by hand), and an entry that claims proved without a confirming test
that runs: status `proved fixed` or `reopened` needs a `confirm` recipe whose every Clue is in the Clue library
(`clues.CLUES`). `npm run check:brain` runs the check on the repo's Casebook (`test_casebook.py`).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import clues  # noqa: E402

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'casebook')
INDEX = 'index.json'
REGENERATE = 'run python3 -I tools/brain/casebook.py index'

FIELDS = ('id', 'title', 'kind', 'step', 'whose', 'status', 'match', 'confirm', 'fix', 'seen')
SECTIONS = ('What the viewer saw', 'Signs', 'Cause', 'How it was proved', 'Ruled out', 'Fix', 'History')
KINDS = ('fail', 'fallback', 'check miss', 'slow play', 'wrong title', 'nothing to play')
# Where a play went wrong: KaijuFlow's step-line names (tools/brain/docs/formats.md, "Step lines"), `search` (#279)
# and the list-time check's old `health_batch`.
STEPS = ('search', 'indexer_page', 'list', 'list_filter', 'list_sort', 'fallback_group', 'list_build', 'head_start',
         'health_batch', 'play_check', 'nzb_fetch', 'unscramble', 'upload', 'import_wait', 'first_byte', 'played',
         'play_failed')
WHOSE = ('KaijuFlow', 'AltMount', 'indexer', 'Usenet', 'test-only', 'unknown')
STATUSES = ('open', 'fix in progress', 'fixed awaiting proof', 'proved fixed', 'reopened')
PROVED = ('proved fixed', 'reopened')
NO_EVIDENCE = 'none (no evidence kept)'
ANSWERS = ('yes', 'no')
NAME = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
DATE = re.compile(r'^\d{4}-\d\d-\d\d$')
# A value written without quotes may not hold what YAML would read otherwise.
PLAIN_BAD = re.compile(r'(^["\'\[\]{}&*!|>%@`#,?-]|: | #|:$)')


class FormatError(Exception):
    pass


def scalar(text, where):
    """One value: a JSON string in double quotes, or plain text."""
    text = text.strip()
    if not text:
        raise FormatError(f'{where}: empty value')
    if text.startswith('"'):
        try:
            value = json.loads(text)
        except ValueError:
            raise FormatError(f'{where}: bad quoted value {text}') from None
        if not isinstance(value, str):
            raise FormatError(f'{where}: bad quoted value {text}')
        return value
    if PLAIN_BAD.search(text):
        raise FormatError(f'{where}: put {text!r} in double quotes')
    return text


def front_matter(lines, name):
    """The front matter's fields, in the small YAML subset the README gives: `key: value`, and lists of values or of
    flat mappings under `key:` (items `  - `, a mapping's further keys `    key: value`)."""
    fields, key, item = {}, None, None
    for n, line in enumerate(lines, 2):
        where = f'{name}:{n}'
        if not line.strip():
            continue
        if not line.startswith(' '):
            m = re.match(r'^([a-z_]+):(.*)$', line)
            if not m:
                raise FormatError(f'{where}: expected `field: value`')
            key, rest = m.group(1), m.group(2)
            if key in fields:
                raise FormatError(f'{where}: {key} given twice')
            fields[key] = scalar(rest, where) if rest.strip() else []
            item = None
            continue
        if key is None or not isinstance(fields[key], list):
            raise FormatError(f'{where}: indented line outside a list')
        m = re.match(r'^  - (.*)$', line)
        if m:
            km = re.match(r'^([a-z_]+): (.*)$', m.group(1))
            item = {km.group(1): scalar(km.group(2), where)} if km else None
            fields[key].append(item if km else scalar(m.group(1), where))
            continue
        m = re.match(r'^    ([a-z_]+): (.*)$', line)
        if not m or item is None:
            raise FormatError(f'{where}: expected `  - item` or `    key: value` under {key}')
        if m.group(1) in item:
            raise FormatError(f'{where}: {m.group(1)} given twice')
        item[m.group(1)] = scalar(m.group(2), where)
    return fields


def sections(lines, name):
    """The body's `## ` sections as {heading: text}, in the fixed order, none empty, nothing before the first."""
    found, current = {}, None
    for line in lines:
        if line.startswith('## '):
            current = line[3:].strip()
            if current in found:
                raise FormatError(f'{name}: section {current!r} given twice')
            found[current] = []
        elif current is None:
            if line.strip():
                raise FormatError(f'{name}: text before the first section')
        else:
            found[current].append(line)
    if tuple(found) != SECTIONS:
        raise FormatError(f'{name}: the sections must be {", ".join(SECTIONS)} in that order (found: {", ".join(found) or "none"})')
    for heading, body in found.items():
        if not ''.join(body).strip():
            raise FormatError(f'{name}: section {heading!r} is empty')
    return {heading: '\n'.join(body).strip() for heading, body in found.items()}


def mapping(item, where, order, optional=()):
    """An item of `key: value` pairs, in `order`, all present but the `optional` ones."""
    if not isinstance(item, dict):
        raise FormatError(f'{where}: expected `key: value` items')
    required = [k for k in order if k not in optional]
    if tuple(item) != tuple(k for k in order if k in item) or not set(required) <= set(item):
        raise FormatError(f'{where}: an item takes {", ".join(order)} in that order'
                          + (f' ({", ".join(optional)} may be left out)' if optional else ''))


def check_fields(fields, name):
    """Raises FormatError for a front matter that breaks the format."""
    if tuple(fields) != FIELDS:
        missing = [f for f in FIELDS if f not in fields]
        extra = [f for f in fields if f not in FIELDS]
        detail = (f'missing {", ".join(missing)}' if missing else '') + ('; ' if missing and extra else '') + \
            (f'unknown {", ".join(extra)}' if extra else '')
        raise FormatError(f'{name}: the fields must be {", ".join(FIELDS)} in that order'
                          + (f' ({detail})' if detail else ''))
    for key in ('id', 'title', 'kind', 'step', 'whose', 'status', 'fix'):
        if not isinstance(fields[key], str):
            raise FormatError(f'{name}: {key} must be one value')
    stem = os.path.splitext(name)[0]
    if not NAME.match(fields['id']) or fields['id'] != stem:
        raise FormatError(f'{name}: id must be the file name without .md, in lower-case words joined by -')
    for key, allowed in (('kind', KINDS), ('step', STEPS), ('whose', WHOSE), ('status', STATUSES)):
        if fields[key] not in allowed:
            raise FormatError(f'{name}: {key} {fields[key]!r} is not one of: {", ".join(allowed)}')
    if fields['whose'] == 'unknown' and fields['status'] != 'open':
        raise FormatError(f'{name}: whose unknown is only for an open entry')
    if not isinstance(fields['match'], list) or not fields['match']:
        raise FormatError(f'{name}: match must list at least one sign')
    for item in fields['match']:
        mapping(item, f'{name}: match', ('rules', 'sign'))
        if not re.match(r'^[1-9][0-9]*$', item['rules']):
            raise FormatError(f'{name}: match rules must be the masking rules version, a whole number from 1')
        item['rules'] = int(item['rules'])
        check_sign(item['sign'], name)
    confirm = fields['confirm']
    if confirm != NO_EVIDENCE:
        if not isinstance(confirm, list) or not confirm:
            raise FormatError(f'{name}: confirm must list Clues, or be {NO_EVIDENCE!r}')
        for item in confirm:
            mapping(item, f'{name}: confirm', ('clue', 'answer'))
            if not isinstance(item['clue'], str) or not NAME.match(item['clue']):
                raise FormatError(f'{name}: confirm clue {item["clue"]!r} must be a Clue name in lower-case words joined by -')
            if item['answer'] not in ANSWERS:
                raise FormatError(f'{name}: confirm answer must be yes or no')
    if not isinstance(fields['seen'], list):
        raise FormatError(f'{name}: seen must list occurrences')
    for item in fields['seen']:
        mapping(item, f'{name}: seen', ('check', 'title', 'play', 'date'), ('play',))
        if not isinstance(item['date'], str) or not DATE.match(item['date']):
            raise FormatError(f'{name}: seen date {item["date"]!r} must be YYYY-MM-DD')


def check_sign(sign, name):
    """A sign is a fingerprint pattern: `<kind> | <step> ok|not ok | <reason>`; `*` stands for anything."""
    parts = sign.split(' | ') if isinstance(sign, str) else []
    if len(parts) != 3:
        raise FormatError(f'{name}: sign {sign!r} must be `<kind> | <step> ok|not ok | <reason>`')
    kind, where, reason = parts
    if kind not in KINDS + ('*',):
        raise FormatError(f'{name}: sign kind {kind!r} is not one of: {", ".join(KINDS)}, *')
    m = re.match(r'^([a-z_]+) (ok|not ok)$', where)
    if where != '*' and not (m and m.group(1) in STEPS):
        raise FormatError(f'{name}: sign step {where!r} must be `<step> ok`, `<step> not ok` or *')
    if not reason.strip():
        raise FormatError(f'{name}: sign reason is empty (write * for any)')


def read_entry(path):
    """(fields, sections) of one entry file; FormatError when it breaks the format."""
    name = os.path.basename(path)
    with open(path) as f:
        lines = f.read().split('\n')
    if lines[0] != '---' or '---' not in lines[1:]:
        raise FormatError(f'{name}: must start with front matter between two --- lines')
    end = lines.index('---', 1)
    fields = front_matter(lines[1:end], name)
    check_fields(fields, name)
    return fields, sections(lines[end + 1:], name)


def entry_files(folder):
    return sorted(n for n in os.listdir(folder) if n.endswith('.md') and n != 'README.md')


def load(folder=FOLDER):
    """({id: fields} of the entries that keep the format, [problems] of those that don't)."""
    entries, problems = {}, []
    for name in entry_files(folder):
        try:
            fields, _ = read_entry(os.path.join(folder, name))
        except FormatError as e:
            problems.append(str(e))
            continue
        entries[fields['id']] = dict(fields, file=name)
    return entries, problems


def index_row(fields):
    """What programs need from one entry."""
    dates = sorted(s['date'] for s in fields['seen'])
    return {
        'id': fields['id'], 'file': fields['file'], 'title': fields['title'], 'kind': fields['kind'],
        'step': fields['step'], 'whose': fields['whose'], 'status': fields['status'], 'match': fields['match'],
        'confirm': fields['confirm'], 'occurrences': len(fields['seen']),
        'first_seen': dates[0] if dates else None, 'last_seen': dates[-1] if dates else None,
    }


def index_text(entries):
    index = {
        'generated_by': 'python3 -I tools/brain/casebook.py index, from the entry files; never edit by hand',
        'entries': [index_row(entries[i]) for i in sorted(entries)],
    }
    return json.dumps(index, indent=2, ensure_ascii=False) + '\n'


def write_index(folder=FOLDER):
    """Writes <folder>/index.json; FormatError (listing every problem) when an entry breaks the format."""
    entries, problems = load(folder)
    if problems:
        raise FormatError('\n'.join(problems))
    with open(os.path.join(folder, INDEX), 'w') as f:
        f.write(index_text(entries))
    return len(entries)


def index_problems(folder, entries):
    try:
        with open(os.path.join(folder, INDEX)) as f:
            text = f.read()
    except FileNotFoundError:
        return [f'{INDEX}: missing; {REGENERATE}']
    if text == index_text(entries):
        return []
    try:
        rows = {row['id']: row for row in json.loads(text)['entries']}
    except (ValueError, KeyError, TypeError):
        return [f'{INDEX}: not a Casebook index; {REGENERATE}']
    out = []
    for i in sorted(set(rows) | set(entries)):
        if i not in rows:
            out.append(f'{INDEX}: {i} is not in the index; {REGENERATE}')
        elif i not in entries:
            out.append(f'{INDEX}: {i} has no entry file; {REGENERATE}')
        else:
            want = index_row(entries[i])
            differ = sorted(k for k in set(want) | set(rows[i]) if want.get(k) != rows[i].get(k))
            if differ:
                out.append(f'{INDEX}: {i} differs from its file ({", ".join(differ)}); {REGENERATE}')
    return out or [f'{INDEX}: not written the way the index command writes it; {REGENERATE}']


def known_clues():
    """The Clue library's names (`clues.CLUES`)."""
    return set(clues.CLUES)


def proof_problems(entries, clues):
    out = []
    for i in sorted(entries):
        fields = entries[i]
        if fields['status'] not in PROVED:
            continue
        confirm = fields['confirm']
        if confirm == NO_EVIDENCE:
            out.append(f'{fields["file"]}: status {fields["status"]} needs a confirming test that runs; confirm is {NO_EVIDENCE}')
            continue
        missing = [item['clue'] for item in confirm if item['clue'] not in clues]
        if missing:
            out.append(f'{fields["file"]}: status {fields["status"]} needs a confirming test that runs; '
                       f'not in the Clue library: {", ".join(missing)}')
    return out


def problems(folder=FOLDER, clues=None):
    """Every problem with the Casebook in `folder`: entries that break the format, an index that disagrees with the
    files, entries that claim proved without a runnable confirm. `clues` is the set of Clue names that exist
    (default: the Clue library's)."""
    entries, out = load(folder)
    out += index_problems(folder, entries)
    out += proof_problems(entries, known_clues() if clues is None else clues)
    return out


def main(argv):
    if len(argv) not in (2, 3) or argv[1] not in ('index', 'check'):
        print(__doc__.strip().split('\n\n')[1], file=sys.stderr)
        return 2
    folder = argv[2] if len(argv) == 3 else FOLDER
    if argv[1] == 'index':
        try:
            n = write_index(folder)
        except FormatError as e:
            print(f'{e}\nindex.json not written', file=sys.stderr)
            return 1
        print(f'wrote {os.path.join(folder, INDEX)}: {n} entries')
        return 0
    found = problems(folder)
    for line in found:
        print(line)
    if not found:
        print(f'Casebook: {len(load(folder)[0])} entries, no problems')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
