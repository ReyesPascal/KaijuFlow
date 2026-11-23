"""The runs root (#241): the one reader of a run folder, and the run rules the measuring tools share.

    load(folder)          a run folder as the tools read it: its meta.json, its visits from raw.json
    why_not_judged(run)   why a run's lists are not judged against its previous run, or None
    previous(run)         the glossary's Previous run, used by CHECK.txt, report.md, the INDEX.md row and the page
    nulls_between(run, prev)  the null runs that lie between a run and its previous run
    missed_since(root, recording, when)  the preflight's own question: did the last run on a Recording since its top-up miss?

The rules are in docs/rules.md ("Judged against the previous run", "Preflight"). A run folder is described in
docs/formats.md.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402

META, RAW = 'meta.json', 'raw.json'


class Unreadable(Exception):
    """A run folder whose meta.json is missing or cannot be read; the message says which ('meta.json is missing')."""


def _read(folder, name):
    """(the JSON in folder/name, None) or (None, why it cannot be read)."""
    try:
        with open(os.path.join(folder, name), encoding='utf-8') as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, f'{name} is missing'
    except (OSError, ValueError) as e:
        return None, f'{name} cannot be read ({type(e).__name__})'


def load(folder):
    """A run folder as the tools read a run: its meta.json, with the visits of its raw.json under 'visits', its path
    under 'dir' and its name under 'folder'. A folder without a readable raw.json (a recording, or a run that broke off)
    has no visits and says why under 'raw_error'. Raises Unreadable when meta.json cannot be read."""
    meta, err = _read(folder, META)
    if err:
        raise Unreadable(err)
    if not isinstance(meta, dict):
        raise Unreadable(f'{META} cannot be read (not an object)')
    raw, raw_err = _read(folder, RAW)
    visits = raw.get('visits') if isinstance(raw, dict) else None
    if raw_err is None and not isinstance(visits, list):
        raw_err, visits = f'{RAW} holds no visits', None
    return {**meta, 'visits': visits or [], 'raw_error': raw_err, 'dir': folder,
            'folder': os.path.basename(os.path.abspath(folder).rstrip(os.sep))}


def _metas(root):
    """(folder name, meta.json) of every run folder in the runs root whose meta.json can be read, newest first."""
    for d in reversed(br.run_folders(root)):
        meta, err = _read(os.path.join(root, d), META)
        if err is None and isinstance(meta, dict):
            yield d, meta


def why_not_judged(run):
    """Why this run's lists cannot be judged (a run that did not finish, or a short run, played fewer plays than the
    previous run, so fewer fails says nothing), or None when they can (spec #183)."""
    status = run.get('status')
    if status == 'stopped':
        return 'this run was stopped'
    if status != 'ok':
        return f'this run did not finish (status {status})'
    if run.get('short'):
        return f"this run is short ({run['short']})"
    return None


def _comparable(meta, recording):
    return (meta.get('recording') == recording and meta.get('status') == 'ok' and not meta.get('short')
            and not br.never_compared(meta))


def previous(run):
    """The run a run is judged against (GLOSSARY "Previous run", rules.md "Judged against the previous run"): the newest
    earlier finished run in the same runs root on the same Recording, not archived, not short and not marked never
    compared with, as load() reads it. None when there is none or the run names no Recording (a run from before #186).
    `run` needs its 'dir' and 'recording'; its own meta.json need not be written yet."""
    recording = run.get('recording')
    if recording is None:
        return None
    root, name = os.path.split(os.path.abspath(run['dir']).rstrip(os.sep))
    if br.is_archived(run['dir']):
        return None
    for d, meta in _metas(root):
        if d >= name or not _comparable(meta, recording):
            continue
        prev = load(os.path.join(root, d))
        if prev['raw_error'] is None:
            return prev
    return None


def against(prev):
    """'Against the previous run on the same recording (kf-189): <folder>': how CHECK.txt, report.md and the INDEX.md row
    name the previous run."""
    return f"Against the previous run on the same recording ({prev['recording']}): {prev['folder']}"


def nulls_between(run, prev):
    """meta.json of every null run in the runs root that started after `prev` (ISO time), oldest first; [] without one."""
    if not prev or not prev.get('started'):
        return []
    root, name = os.path.split(os.path.abspath(run['dir']).rstrip(os.sep))
    since = br.parse_ts(prev['started'])
    found = [m for d, m in _metas(root) if d != name and m.get('status') == 'null' and m.get('started')
             and br.parse_ts(m['started']) > since]
    return sorted(found, key=lambda m: m['started'])


def missed_since(root, recording, when):
    """(run folder, missed requests) of the newest run on this Recording that started after `when` (its last record, as
    RECORDING.json says), of any status, a stopped or short one too; None when there is none (#229). A grab of a release
    the visit never played does not count (#235), when the run folder's raw.json shows the visits."""
    if not root or not when:
        return None
    for d, meta in _metas(root):
        if meta.get('recording') != recording or 'standin_misses' not in meta:
            continue
        if (meta.get('started') or '') <= when:
            return None
        run = load(os.path.join(root, d))
        if run['raw_error'] is None:  # the misses that count, as check counts them (#235)
            return d, sum(len(br.counted_misses(v)) for v in run['visits'])
        return d, meta.get('standin_misses') or 0
    return None
