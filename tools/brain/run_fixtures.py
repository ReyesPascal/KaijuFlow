"""The one fixture builder for the brain tools' tests (#241): run folders in a temp directory, laid out as brainrun leaves
them (archive/formats-retired.md, "Run records"). The brainreport tests and the archived ones (archive/) make theirs here.
"""
import json
import os

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def fixture(name):
    """The path of a run folder kept under fixtures/ ('run-usable', 'run-2026-11-13')."""
    return os.path.join(FIXTURES, name)


def _read(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _write(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def run_folder(root, name, meta=None, visits=None, like=None, edit_visits=None):
    """root/name as a run folder: meta.json, and raw.json holding the visits. `like` is a run folder (a fixture, or one
    made here) whose meta.json and visits it starts from; `meta` is laid over that meta.json, `visits` replaces its
    visits, and `edit_visits(visits)` changes them in place. A folder with no visits given and none in `like` gets no
    raw.json, as a recording or a run that broke off has none. Returns the folder's path."""
    folder = os.path.join(root, name)
    os.makedirs(folder)
    base, base_visits = {}, None
    if like:
        base = _read(os.path.join(like, 'meta.json'))
        if os.path.exists(os.path.join(like, 'raw.json')):
            base_visits = _read(os.path.join(like, 'raw.json')).get('visits')
    m = {**base, **(meta or {})}
    vs = visits if visits is not None else base_visits
    _write(os.path.join(folder, 'meta.json'), m)
    if vs is not None:
        vs = json.loads(json.dumps(vs))  # a copy: the caller's list and the fixture stay as they were
        if edit_visits:
            edit_visits(vs)
        _write(os.path.join(folder, 'raw.json'), {'status': m.get('status'), 'visits': vs})
    return folder


def edit(folder, name, fn):
    """Change one JSON file of a run folder in place: fn(data) edits what folder/name holds."""
    path = os.path.join(folder, name)
    data = _read(path)
    fn(data)
    _write(path, data)
