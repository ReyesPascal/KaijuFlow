"""The evidence folder (#280, spec #279): what a failed or fallen-back play leaves for Diagnosis, saved by one shared part.

The quick check calls `save` for every play `kept_because` names (and the full check and the Drill-down will call the same
part), so all three write one format: tools/brain/docs/formats.md, "Evidence folder". A play that went fine gets none.
`save` reads only what it is handed and what the io gives (the check's stored indexer answers, the stand-in's request
lines, AltMount's copy of a failed import, the test copies' secret values for scrubbing); it never asks an indexer.
"""
import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
import indexer_standin  # noqa: E402

FORMAT = 1  # the evidence folder's format version; a reader refuses a version it does not know
DIR = 'evidence'  # in the check's run folder: <run folder>/evidence/<NN>-<label>/
ANSWERS = 'answers'  # the kept indexer answers, a stand-in list: --store <evidence folder> --list answers replays them
_SECOND = datetime.timedelta(seconds=1)
MIN_SECRET = 6  # a secret value shorter than this is not scrubbed by value (it would blank ordinary words)

# AltMount's line when a failed import's NZB is moved, as its log writes it (fixtures/2026-11-23-failed-play/):
#   msg="Moved failed NZB to failed directory" component=importer-service new_path=/config/.nzbs/failed/kaijuflow/<name>.nzb
MOVED_FAILED = re.compile(r'msg="Moved failed NZB to failed directory".*?\bnew_path=(?:"((?:[^"\\]|\\.)*)"|(\S+))')


def kept_because(outcome):
    """Why a judged play gets an evidence folder: 'fail', 'nothing to play', 'fallback', 'slow play', or None for a play
    that went fine (played, on time, with no fallback)."""
    if outcome.get('outcome') != 'played':
        return outcome.get('outcome')
    if outcome.get('fallbacks'):
        return 'fallback'
    if outcome.get('slow'):
        return 'slow play'
    return None


def scrub(text, secrets=()):
    """`text` as a run folder may keep it: brainreport.scrub_text (key=, password=, logins in links), then every known
    secret value (the test copies' keys and logins) replaced by ***, longest first."""
    text = br.scrub_text(text)
    for value in sorted({v for v in secrets if v and len(v) >= MIN_SECRET}, key=len, reverse=True):
        text = text.replace(value, '***')
    return text


def play_steps(kf_text, vid, since):
    """Every KaijuFlow step line of one play: its own title's (`ref` the title's id) or with no ref, from `since` on."""
    lo = br.parse_ts(since)

    def from_then(s):
        try:
            return br.parse_ts(s['t']) >= lo
        except (KeyError, TypeError, ValueError):
            return False
    return [s for s in br.parse_step_lines(kf_text) if s.get('ref') in (None, vid) and from_then(s)]


def failed_sources(steps):
    """The Sources that failed in a play, each once, in the order they first failed: a Play-time check that did not pass
    ('check', its status), a Source AltMount refused or that failed after its check ('play' from `play_failed`, or
    'import' from a failed `import_wait` in builds without it)."""
    out, seen = [], set()
    for s in steps:
        if s.get('ok') or not s.get('title'):
            continue
        how = {'play_check': 'check', 'play_failed': 'play', 'import_wait': 'import'}.get(s.get('step'))
        if how and s['title'] not in seen:
            seen.add(s['title'])
            out.append({'release': s['title'], 'failed': how, 'status': s.get('status') if how == 'check' else None})
    return out


def altmount_failed_nzbs(be_text):
    """The container paths of the NZBs AltMount moved to its failed folder in this log, in order, each once."""
    out = []
    for m in MOVED_FAILED.finditer(be_text):
        path = m.group(1).replace('\\"', '"') if m.group(1) is not None else m.group(2)
        if path not in out:
            out.append(path)
    return out


def request_lines(lines, lo_ms, hi_ms):
    """The stand-in's request lines (brainreport.LINE_RE) sent between lo_ms and hi_ms (epoch ms): [(line, kind, slug,
    request)], the request as the stand-in names it (`api <query>` or `nzb <12 characters of its stored key>`)."""
    out = []
    for line in lines:
        m = br.LINE_RE.match(line.strip())
        if not m or not lo_ms <= int(m.group(6)) <= hi_ms:
            continue
        kind, slug, request = m.group(1), m.group(2), m.group(3)
        request = re.sub(r' -> \d+.*$', '', request)  # RECORD/ERROR: the status and size after the request
        if request.startswith('nzb '):
            request = ' '.join(request.split(' ')[:2])  # a MISS adds the release title after the key
        out.append((line.strip(), kind, slug, request))
    return out


def _stored(list_dir, slug, request):
    """The stored answer's key (its file name) for one request, or None: an NZB by its key's first 12 characters, a
    search by the request its .meta.json names."""
    d = os.path.join(list_dir, slug)
    try:
        names = sorted(n[:-len('.meta.json')] for n in os.listdir(d) if n.endswith('.meta.json'))
    except OSError:
        return None
    if request.startswith('nzb '):
        hit = [n for n in names if n.startswith(request[4:])]
        return hit[0] if len(hit) == 1 else None
    for n in names:
        try:
            with open(os.path.join(d, n + '.meta.json')) as f:
                if json.load(f).get('request') == request:
                    return n
        except (OSError, ValueError):
            continue
    return None


def _safe_name(name):
    """A release or file name as a file name: no folder separators, no leading dot."""
    return re.sub(r'[/\\\0]', '_', name).lstrip('.') or 'unnamed'


def _slug(label):
    return '-'.join(re.findall(r'[a-z0-9]+', label.lower())) or 'title'


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb' if isinstance(data, bytes) else 'w') as f:
        f.write(data)


def save(run_dir, n, play, io):
    """Write the evidence folder of the n-th play (1-based) of a check into `run_dir`/evidence/ and return its path
    relative to `run_dir`. `play` holds: 'check' (the run folder's name), 'kind' ('quick check'), 'visit' (as raw.json
    keeps it), 'outcome' (quickcheck.judge's), 'kf_text' and 'be_text' (both containers' lines for the play, unscrubbed),
    'settings', 'commit', 'head', 'dirty', and 'until' (the end of the play's window: the next play's start, or its end
    plus the grace). `io` gives check_answers() (the folder of the check's stored answers, or None), standin_lines(),
    altmount_file(container path) (bytes or None) and secret_values()."""
    visit, outcome = play['visit'], play['outcome']
    rel = os.path.join(DIR, f'{n:02d}-{_slug(visit["label"])}')
    out = os.path.join(run_dir, rel)
    secrets = io.secret_values()
    steps = play_steps(play['kf_text'], visit['id'], br.iso(br.parse_ts(visit['t_start']) - _SECOND))
    _write(os.path.join(out, 'steps.jsonl'), ''.join(json.dumps(s) + '\n' for s in steps))
    _write(os.path.join(out, 'logs', 'kaijuflow-test.log'), scrub(play['kf_text'], secrets))
    _write(os.path.join(out, 'logs', 'altmount-kf-test.log'), scrub(play['be_text'], secrets))
    _write(os.path.join(out, 'settings.json'), json.dumps(play['settings'], indent=1, sort_keys=True))

    lo_ms = int((br.parse_ts(visit['t_start']) - _SECOND).timestamp() * 1000)
    hi_ms = int(br.parse_ts(play['until']).timestamp() * 1000)
    lines = request_lines(io.standin_lines(), lo_ms, hi_ms)
    _write(os.path.join(out, 'logs', 'standin.log'), scrub(''.join(line + '\n' for line, *_ in lines), secrets))
    list_dir = io.check_answers()
    kept, not_stored = set(), []
    for line, kind, slug, request in lines:
        key = _stored(list_dir, slug, request) if list_dir and kind != 'MISS' else None
        if key is None:
            not_stored.append(scrub(line, secrets))
            continue
        if (slug, key) not in kept:
            kept.add((slug, key))
            for ext in ('.body', '.meta.json'):
                _write(os.path.join(out, ANSWERS, slug, key + ext), _read_bytes(os.path.join(list_dir, slug, key + ext)))
            setting = os.path.join(list_dir, slug, indexer_standin.SETTINGS_FILE)
            if os.path.exists(setting):
                shutil.copyfile(setting, os.path.join(out, ANSWERS, slug, indexer_standin.SETTINGS_FILE))

    failed = failed_sources(steps)
    for f in failed:
        body = _source_nzb(out, kept, f['release'])
        if body is not None:
            f['nzb'] = f'nzbs/{_safe_name(f["release"])}.nzb'
            _write(os.path.join(out, f['nzb']), body)
        else:
            f['nzb'] = None
    altmount = []
    for path in altmount_failed_nzbs(play['be_text']):
        body = io.altmount_file(path)
        entry = {'from': path, 'nzb': None}
        if body is not None:
            entry['nzb'] = f'nzbs/altmount/{_safe_name(os.path.basename(path))}'
            _write(os.path.join(out, entry['nzb']), body)
        altmount.append(entry)

    setting = (play['settings'].get('kaijuflow') or {}).get('devDiagnostics')
    meta = {'format': FORMAT, 'check': play['check'], 'kind': play['kind'], 'title': visit['title'], 'label': visit['label'],
            'id': visit['id'], 'kept_because': kept_because(outcome), 'outcome': outcome, 't_start': visit['t_start'],
            't_end': visit['t_end'], 'commit': play['commit'], 'head': play['head'], 'dirty': play['dirty'],
            'dev_switch': {'setting': setting is True, 'step_lines': sum(1 for s in steps if s.get('dev') is True), 'of': len(steps)},
            'failed_sources': failed, 'altmount_nzbs': altmount,
            'answers': {'list': ANSWERS, 'kept': len(kept), 'not_stored': not_stored}}
    _write(os.path.join(out, 'evidence.json'), json.dumps(meta, indent=1))
    return rel


def _read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def _source_nzb(out, kept, release):
    """The NZB of one Source among the answers kept: its link's token found in a kept search answer (the stand-in names
    each link by the release before it, indexer_standin.nzb_titles), its stored NZB the kept answer with that key."""
    for slug in sorted({s for s, _ in kept}):
        d = os.path.join(out, ANSWERS, slug)
        for token, title in indexer_standin.nzb_titles(d).items():
            if title != release:
                continue
            key = indexer_standin.cache_key('nzb', [('token', token)])
            if (slug, key) in kept:
                return _read_bytes(os.path.join(d, key + '.body'))
    return None


# --------------------------------------------------------------------------- reading a saved folder (Diagnosis, #283)

class FormatUnknown(Exception):
    pass


class Saved:
    """One evidence folder as Diagnosis and the Clues read it: `meta` (evidence.json), `steps` (steps.jsonl), `kf_lines`
    and `am_lines` (both containers' log lines), `settings`, and `nzb(release)` (the bytes of a failed Source's NZB, or
    None)."""

    def __init__(self, folder):
        self.folder = folder
        with open(os.path.join(folder, 'evidence.json')) as f:
            self.meta = json.load(f)
        if self.meta.get('format') != FORMAT:
            raise FormatUnknown(f"{folder}: evidence format {self.meta.get('format')!r}, this reader knows {FORMAT}")
        with open(os.path.join(folder, 'steps.jsonl')) as f:
            self.steps = [json.loads(line) for line in f if line.strip()]
        self.kf_lines = self._lines('kaijuflow-test.log')
        self.am_lines = self._lines('altmount-kf-test.log')
        try:
            with open(os.path.join(folder, 'settings.json')) as f:
                self.settings = json.load(f)
        except (OSError, ValueError):
            self.settings = {}

    def _lines(self, name):
        try:
            with open(os.path.join(self.folder, 'logs', name), errors='replace') as f:
                return f.read().splitlines()
        except OSError:
            return []

    def nzb(self, release):
        for s in self.meta.get('failed_sources') or []:
            if s.get('release') == release and s.get('nzb'):
                return _read_bytes(os.path.join(self.folder, s['nzb']))
        return None


def read(folder):
    """The evidence folder at `folder` (Saved); FormatUnknown for a format this reader does not know."""
    return Saved(folder)
