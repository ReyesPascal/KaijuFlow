"""The Drill-down (#272, spec #279): one failed title played again, live, to prove its cause fixed.

    python3 -I tools/brain/brainrun.py drill --title <imdb id> [--episode S01E02] [--entry ID ...] [--tickets-dry-run]

It runs the quick check's own path (brainrun.play_check: the preflight, the reset, the stand-in live on the check's own
empty store, the list, the Browse pause, one press of Best, the same verdict and report) on that one title, which is not
drawn and not added to the draw ledger again. Its play always keeps an evidence folder (evidence.save), a play that
went fine too, and Diagnosis runs on it as after a check. The suspected causes are the Casebook entries proved on this
title's earlier evidence folders under the runs root (and its archive/), and every entry `--entry` names. Each one's
confirming recipe of Clues runs on every failure of the drill's play (diagnosis.prove), and the entry is marked:

- **proved fixed**: the title played with no failure (no fail, no fallback, no slow play);
- **reopened**: a failure appeared, its cause proved again by the recipe, or a new one (a fix that moved the problem
  does not count);
- **not marked**: the entry has no fix to prove (`fix: none yet`), or no confirming test that runs (`proved fixed` and
  `reopened` claim proof, casebook/README.md); its History still gets the Drill-down's line.

A drill with no verdict (the cap rule, a stop, a failure) marks nothing. The marks go into the drill folder's
`diagnosis.json` (`drill`); `diagnosis.py record <drill folder>` writes them onto the entries (fixing.record_drill), as
a check's fixes are, so the repository stays clean for the next preflight. Formats: tools/brain/docs/formats.md,
"Drill-down".
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import casebook  # noqa: E402
import clues  # noqa: E402
import diagnosis  # noqa: E402
import evidence  # noqa: E402
import pool  # noqa: E402

KIND = 'drill-down'  # the check's kind, in its meta.json, its evidence folder and its report
EPISODE = re.compile(r'^S(\d{1,3})E(\d{1,4})$', re.I)
IMDB = re.compile(r'^tt\d+$')
PROOF = ('proved fixed', 'reopened')


def title_id(imdb, episode=None):
    """The title's id as KaijuFlow's list address names it: `tt123`, or `tt123:1:2` for S01E02. ValueError when the
    IMDb id or the episode is not written that way."""
    if not IMDB.match(imdb or ''):
        raise ValueError(f'--title must be an IMDb id (tt and digits), not {imdb!r}')
    if not episode:
        return imdb
    m = EPISODE.match(episode)
    if not m:
        raise ValueError(f'--episode must be written S01E02, not {episode!r}')
    return f'{imdb}:{int(m.group(1))}:{int(m.group(2))}'


def earlier(runs_root, vid):
    """The diagnosed evidence folders of this title under the runs root and its archive/, newest check first: each
    {'evidence' (relative to the runs root), 'meta', 'diagnosis'}. A folder that cannot be read is left out."""
    out = []
    for run_dir in diagnosis.stored_checks(runs_root):
        for folder in diagnosis.evidence_folders(run_dir):
            try:
                meta = evidence.read(folder).meta
            except (OSError, ValueError, evidence.FormatUnknown):
                continue
            said = diagnosis._read_json(os.path.join(folder, diagnosis.STORED))
            title = meta.get('title') or []
            if said is not None and len(title) > 1 and title[1] == vid:
                out.append({'evidence': os.path.relpath(folder, runs_root), 'meta': meta, 'diagnosis': said,
                            'check': os.path.basename(run_dir)})
    return sorted(out, key=lambda e: e['check'], reverse=True)


def suspects(found, named=()):
    """The entries to mark: every one `--entry` named (`from` empty), then every entry a lead was proved for on the
    title's earlier evidence folders, each once, with the folders it was proved in."""
    out = {i: {'entry': i, 'from': []} for i in named}
    for e in found:
        for f in e['diagnosis'].get('failures') or []:
            for lead in f.get('leads') or []:
                if lead.get('result') == 'proved':
                    row = out.setdefault(lead['id'], {'entry': lead['id'], 'from': []})
                    if e['evidence'] not in row['from']:
                        row['from'].append(e['evidence'])
    return list(out.values())


def tmdb_title(get, imdb, episode=None):
    """The title ([type, id, label, kind, date], as the draw writes it) from TMDB by its IMDb id, for a title no earlier
    evidence folder names: a film's name and release date, an episode's show name with `S01E02` and its air date.
    pool.TmdbError when TMDB did not answer or does not know it."""
    vid = title_id(imdb, episode)

    def answer(path):
        status, data = get(path)
        if status != 200:
            raise pool.TmdbError(f'TMDB answered HTTP {status} to {path.split("?")[0]}')
        return data or {}
    found = answer(f'/find/{imdb}?external_source=imdb_id')
    if not episode:
        hit = (found.get('movie_results') or [None])[0]
        if not hit:
            raise pool.TmdbError(f'TMDB knows no film {imdb}' + (' (it is a show: name the episode with --episode)'
                                                                 if found.get('tv_results') else ''))
        return ['movie', vid, hit.get('title') or '', KIND, hit.get('release_date') or None]
    hit = (found.get('tv_results') or [None])[0]
    if not hit:
        raise pool.TmdbError(f'TMDB knows no show {imdb}')
    _, season, number = vid.split(':')
    ep = answer(f"/tv/{hit['id']}/season/{season}/episode/{number}")
    return ['series', vid, f"{hit.get('name') or ''} S{int(season):02d}E{int(number):02d}", KIND, ep.get('air_date') or None]


def prepare(runs_root, imdb, episode, named, tmdb):
    """(title, suspects) of a Drill-down, before it plays: the title as its newest earlier evidence folder names it
    (else `tmdb(imdb, episode)`), and the entries to mark."""
    found = earlier(runs_root, title_id(imdb, episode))
    title = list(found[0]['meta']['title']) if found else tmdb(imdb, episode)
    return title, suspects(found, named)


def _runnable(fields, library):
    confirm = fields['confirm']
    return confirm != casebook.NO_EVIDENCE and all(c['clue'] in library for c in confirm)


def mark(run_dir, suspected, book=None, library=None):
    """Marks each suspected entry from the drill's own evidence folder (its first), after Diagnosis ran on it: the
    entry's recipe run on every failure of the play, and `result` proved fixed, reopened or not marked (module doc).
    Returns {'evidence', 'check', 'date', 'label', 'marks'}; also kept in the drill folder's diagnosis.json (`drill`)."""
    book = casebook.FOLDER if book is None else book
    library = clues.CLUES if library is None else library
    folders = diagnosis.evidence_folders(run_dir)
    out = {'check': os.path.basename(os.path.normpath(run_dir)), 'suspects': suspected, 'marks': []}
    if not folders:
        out['error'] = 'the play left no evidence folder'
        return _keep(run_dir, out)
    folder = folders[0]
    ev = evidence.read(folder)
    rel = os.path.relpath(folder, run_dir)
    said = (diagnosis._read_json(os.path.join(folder, diagnosis.STORED)) or {}).get('failures') or []
    out.update(evidence=rel, date=(ev.meta.get('t_start') or '')[:10], label=ev.meta.get('label'))
    entries, _ = casebook.load(book)
    index = {e['id']: e for e in diagnosis.load_index(book)}
    fails = diagnosis.failures(ev)
    for s in suspected:
        fields = entries.get(s['entry'])
        row = {'entry': s['entry'], 'from': s['from'], 'before': fields and fields['status'], 'recipe': []}
        if fields is None or s['entry'] not in index:
            out['marks'].append(dict(row, result='not marked', would=None, why='no such Casebook entry'))
            continue
        row['file'] = fields['file']
        for f in fails:
            tried = diagnosis.prove(index[s['entry']], ev, f, library)
            row['recipe'].append({'release': f['release'], 'kind': f['kind'], 'result': tried['result'],
                                  'why': tried.get('why'), 'clues': tried['clues']})
        if not fails:
            would, why = 'proved fixed', f"{out['label']} played with no failure ({rel})"
        else:
            proved = next((r for r in row['recipe'] if r['result'] == 'proved'), None)
            if proved:
                why = (f"its cause was proved again on {proved['release'] or 'the play'} by Clues "
                       f"{', '.join(c['clue'] for c in proved['clues'])} ({rel})")
            else:
                first = said[0] if said else {}
                why = (f"a new failure appeared: {(first.get('release') or fails[0]['release'] or 'the play')}: "
                       f"{first.get('says') or fails[0]['kind']} ({rel})")
            would = 'reopened'
        if fields['fix'] == 'none yet':
            row.update(result='not marked', would=would, why=why + '; it has no fix to prove (fix: none yet)')
        elif not _runnable(fields, library):
            row.update(result='not marked', would=would,
                       why=why + f"; {would} claims proof, and it has no confirming test that runs")
        else:
            row.update(result=would, would=None, why=why)
        out['marks'].append(row)
    return _keep(run_dir, out)


def _keep(run_dir, out):
    path = os.path.join(run_dir, diagnosis.STORED)
    summary = diagnosis._read_json(path) or {}
    summary['drill'] = out
    diagnosis._write_json(path, summary)
    return out


def report_lines(drill, error=None):
    """The drill report's Drill-down section: one line per suspected entry and its mark."""
    lines = ['## Drill-down', '']
    if error:
        return lines + [f'No entry marked: {error}.']
    if not drill or 'marks' not in drill:
        return lines + ['No entry marked: the Drill-down has no verdict.']
    if drill.get('error'):
        return lines + [f"No entry marked: {drill['error']}."]
    if not drill['marks']:
        return lines + ['No Casebook entry to mark: no earlier evidence folder of this title has a proved cause '
                        '(name one with --entry).']
    for m in drill['marks']:
        if m['result'] == 'not marked':
            lines.append(f"- {m['entry']}: not marked{' ' + m['would'] if m.get('would') else ''}: {m['why']}.")
        else:
            lines.append(f"- {m['entry']}: {m['result']}: {m['why']}.")
    lines += ['', "`python3 -I tools/brain/diagnosis.py record <this folder>` writes the marks on the entries; commit them."]
    return lines
