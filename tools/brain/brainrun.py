"""The one command that runs every side cold, then warm, twice, and writes the run record (spec #58, ticket #62).

    python3 -I tools/brain/brainrun.py run --name baseline --store <standin-store> --list <title-list>
           [--runs-root DIR] [--one-page] [--titles-file titles.json] [--user-id ID] [--tries 1]
           [--rebuild-image] [--provider-limit 100] [--no-wait]
    python3 -I tools/brain/brainrun.py record --name baseline --store <standin-store> --list <title-list> [--key-file PATH]
           [--runs-root DIR] [--one-page] [--titles-file titles.json] [--tries 1] [--rebuild-image]   (record, or top up)
    python3 -I tools/brain/brainrun.py preflight [--for run|record] --store <standin-store> --list <title-list>
           [--rebuild-image] [--provider-limit 100] [--key-file PATH]   (the setup check alone; a run starts with it)
    python3 -I tools/brain/brainrun.py smoke --store <EMPTY dir> --list smoke   (stand-in reachability check, see README)

A run starts the indexer stand-in in REPLAY mode (never record, so no real indexer is contacted; it waits the recorded
indexer time for every answer unless --no-wait; the stand-in's lines say which test container asked and when, so the report
matches them to the right side and visit) and resets the test copies with
testbed.py before each cold round, plays the top pick of every title on every side one side at a time, reads KaijuFlow's
[KF-STEP] lines and the Backends' import start/end from the test containers' logs, and writes a run folder, one INDEX.md
row and the report. The first "limit reached" from any indexer aborts the run and records it as null.
The record command resets the test copies, starts the stand-in in RECORD mode (this spends real indexer requests), sends
every side through every title once, and resets again; running it again only asks for what is not stored yet. Its timings never
reach a report. Only test containers are touched. Secrets never reach the run folder (settings are scrubbed, logs are scrubbed).
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
import common  # noqa: E402
import indexer_standin  # noqa: E402
import testbed  # noqa: E402
from common import DEFAULT_TEST_DIR  # noqa: E402

DEFAULT_RUNS_ROOT = '/home/ryan/kaijuflow-notes/brain-runs'
PLAN = [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)]
MAIN_SIDES = ['kaijuflow', 'uu', 'altmount-addon']
ALL_TESTBED = ['nzbdav', 'altmount-addon', 'altmount-kf', 'uu', 'kaijuflow']
# side -> (KaijuFlow container with [KF-STEP] lines or None, Backend container, how its log is read)
SIDE_LOGS = {
    'kaijuflow': ('kaijuflow-test', 'altmount-kf-test', 'altmount'),
    'kaijuflow-1page': ('kaijuflow-test', 'altmount-kf-test', 'altmount'),
    'uu': (None, 'nzbdav-test', 'nzbdav'),
    'altmount-addon': (None, 'altmount-addon-test', 'altmount'),
}
GRACE_S = 5
RECORDING_FILE = 'RECORDING.json'  # next to a list's answers: {"state": "complete"|"stopped", "why", "when", "errors"}


class CapReached(Exception):
    def __init__(self, indexer, time_, where):
        super().__init__(f'{indexer} limit reached at {time_} ({where})')
        self.indexer, self.time, self.where = indexer, time_, where


# --------------------------------------------------------------------------- settings

def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _read_text(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def snapshot_settings(test_dir):
    """Settings of every side with secrets removed: {side: {dotted key: value}}; the settings command's reader (testbed.py)."""
    return testbed.read_settings(test_dir)


def one_page_config(cfg):
    """KaijuFlow config for the fourth side: one page per indexer (config only)."""
    out = copy.deepcopy(cfg)
    for ix in out.get('indexers', []):
        ix['pagination'] = False
    sc = out.setdefault('searchConfig', {})
    sc['seasonPackPagination'] = False
    sc['seriesPackPagination'] = False
    return out


# --------------------------------------------------------------------------- the real world

class RealIO:
    def __init__(self, cfg):
        self.cfg = cfg
        self.testbed = testbed
        self.backup = os.path.join(cfg['test_dir'], 'config', 'config.json.pre-brainrun')

    def now(self):
        return datetime.datetime.now(datetime.timezone.utc)

    def sleep(self, s):
        time.sleep(s)

    def git_info(self):
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        commit = subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'], text=True).strip()
        dirty = bool(subprocess.check_output(['git', '-C', repo, 'status', '--porcelain', '--untracked-files=no'], text=True).strip())
        return commit, dirty

    def snapshot(self):
        return snapshot_settings(self.cfg['test_dir'])

    def setup_report(self, limit):
        return testbed.settings_report(self.cfg['test_dir'], limit)

    def key_state(self, path):
        return read_key_file(path)

    def image_label(self):
        r = subprocess.run(['docker', 'image', 'inspect', IMAGE, '--format', '{{index .Config.Labels "%s"}}' % IMAGE_LABEL],
                           capture_output=True, text=True, timeout=60)
        label = r.stdout.strip()
        return label if r.returncode == 0 and label and label != '<no value>' else None

    def rebuild_image(self, commit):
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        build_image(commit, repo)

    def addresses(self):
        return read_addresses()

    def shelve_marker(self):
        return shelve_marker(self.cfg['store'])

    def setting_conflicts(self):
        """Sentences for a key file whose dropped-parameter setting differs from the one the list was recorded with."""
        key = self.cfg.get('key_file') or os.path.join(self.cfg['test_dir'], 'indexers.json')
        return indexer_standin.setting_conflicts(_read_json(key) or {}, self.cfg['store'], self.cfg['listname'])

    def recording_state(self):
        return _read_json(os.path.join(self.cfg['store'], self.cfg['listname'], RECORDING_FILE))

    def port_free(self, port):
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('0.0.0.0', port))
            except OSError:
                return False
        return True

    def recording(self):
        """{indexer slug: number of stored answers} for the title list; {} when there is no such folder."""
        d = os.path.join(self.cfg['store'], self.cfg['listname'])
        if not os.path.isdir(d):
            return {}
        return {slug: sum(1 for f in os.listdir(os.path.join(d, slug)) if f.endswith('.body'))
                for slug in os.listdir(d) if os.path.isdir(os.path.join(d, slug))}

    def preflight(self, mode):
        return preflight(mode, self.cfg, self)

    def marker(self):
        return _read_json(os.path.join(self.cfg['store'], 'LIMIT_REACHED.json'))

    def start_standin(self, logpath, mode='replay', wait=True):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'indexer_standin.py')
        port = self.cfg.get('standin_port', 1340)
        self.standin_log = logpath
        log = open(logpath, 'w')
        cmd = [sys.executable, '-I', script, '--mode', mode, '--store', self.cfg['store'],
               '--list', self.cfg['listname'], '--port', str(port), '--bind', '0.0.0.0']
        if mode == 'record':
            cmd += ['--config', self.cfg.get('key_file') or os.path.join(self.cfg['test_dir'], 'indexers.json')]
        elif not wait:
            cmd.append('--no-wait')
        proc = subprocess.Popen(cmd, stderr=log, stdout=subprocess.DEVNULL)
        end = time.time() + 20
        while time.time() < end:
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/_standin/status' % port, timeout=2)
                break
            except OSError:
                time.sleep(0.3)
        else:
            proc.terminate()
            raise RuntimeError('indexer stand-in did not start')

        class Handle:
            def stop(self):
                proc.terminate()
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                log.close()
        return Handle()

    def standin_lines(self):
        """The stand-in's log so far, one entry per line."""
        return (_read_text(self.standin_log) or '').splitlines()

    def standin_line_count(self):
        return len(self.standin_lines())

    def reset(self, sides):
        self.testbed.reset(self.cfg['test_dir'], sides, log=print)
        problems = self.testbed.check_empty(self.cfg['test_dir'], sides)
        if problems:
            raise RuntimeError('a test Backend is not empty after reset: ' + '; '.join(problems[:3]))

    def _compose(self, verb, *services):
        return self.testbed._run(self.testbed.compose_cmd(self.cfg['test_dir'], verb, *services))

    def stop_all(self):
        self._compose('stop')

    def apply_one_page(self):
        path = os.path.join(self.cfg['test_dir'], 'config', 'config.json')
        if os.path.exists(self.backup):
            raise RuntimeError(f'{self.backup} exists: an earlier run did not restore the KaijuFlow config; restore it by hand')
        self._compose('stop', 'kaijuflow')
        shutil.copyfile(path, self.backup)
        patched = one_page_config(_read_json(path))
        with open(path, 'w') as f:
            json.dump(patched, f, indent=2)
        return {'kaijuflow-1page': br.flatten(patched)}

    def restore_config(self):
        if os.path.exists(self.backup):
            self._compose('stop', 'kaijuflow')
            shutil.copyfile(self.backup, os.path.join(self.cfg['test_dir'], 'config', 'config.json'))
            os.remove(self.backup)

    def visit_http(self, side, kind, vid, tries):
        base = side_base(self.cfg, side)
        st, h, body, t = common.get(f'{base}/stream/{kind}/{vid}.json', timeout=180, limit=0)
        out = {'list_status': st, 'list_s': round(t.get('total', t['ready']), 2), 'note': None}
        try:
            streams = json.loads(body or b'{}').get('streams', []) if st == 200 else []
        except ValueError as e:
            streams, out['note'] = [], f'bad JSON: {e}'[:120]
        if st != 200:
            out['note'] = h.get('error') or f'HTTP {st}'
        out['sources'] = len(streams)
        plays = [common.play_stream(s) for s in streams[:tries]]
        out['tries'] = plays
        top = plays[0] if plays else None
        out['first_try_plays'] = bool(top and top['plays'])
        out['start_s'] = top['first_byte_s'] if out['first_try_plays'] else None
        out['seeks'] = common.seek_reads(streams[0]['url'], top['size']) if out['first_try_plays'] else {}
        if top and not top['plays']:
            out['note'] = top.get('note')
        elif not streams and not out['note']:
            out['note'] = 'no Sources'
        return out

    def logs(self, container, since):
        if container not in self.testbed.TEST_CONTAINERS:
            raise ValueError('not a test container: ' + container)
        r = subprocess.run(['docker', 'logs', '--timestamps', '--since', since, container], capture_output=True, text=True, timeout=60)
        return r.stdout + r.stderr


def build_image(commit, repo, popen=subprocess.Popen, run=subprocess.run):
    """Builds kaijuflow:test from the commit itself (an archive of HEAD piped into `docker build -`), so a file that is untracked
    or ignored can never get into an image whose label names that commit."""
    archive = popen(['git', '-C', repo, 'archive', 'HEAD'], stdout=subprocess.PIPE)
    try:
        run(['docker', 'build', '--label', f'{IMAGE_LABEL}={commit}', '-t', IMAGE, '-'], stdin=archive.stdout, check=True, timeout=1800)
    finally:
        archive.stdout.close()
        archive.wait()


def read_addresses(run=subprocess.run):
    """{test container: its address on the test network}, read with `docker inspect` (read-only); a container that is not up
    or has no address is left out."""
    out = {}
    for container in sorted(set(br.CLIENT_CONTAINER.values())):
        if container not in testbed.TEST_CONTAINERS:
            raise ValueError('not a test container: ' + container)
        fmt = '{{with index .NetworkSettings.Networks "%s"}}{{.IPAddress}}{{end}}' % testbed.NETWORK
        r = run(['docker', 'inspect', '-f', fmt, container], capture_output=True, text=True, timeout=60)
        ip = r.stdout.strip() if r.returncode == 0 else ''
        if ip:
            out[container] = ip
    return out


def note_addresses(io, run):
    """Adds the containers' current addresses to the run (they can change when a container is started again)."""
    for container, ip in io.addresses().items():
        known = run['addresses'].setdefault(container, [])
        if ip not in known:
            known.append(ip)


def shelve_marker(store):
    """Moves a limit marker left by an earlier command aside (kept, renamed with its time); returns the new name or None."""
    path = os.path.join(store, 'LIMIT_REACHED.json')
    if not os.path.exists(path):
        return None
    marker = _read_json(path) or {}
    try:
        when = br.parse_ts(marker['time'])
    except (TypeError, KeyError, ValueError):
        when = datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc)
    new = os.path.join(store, f'LIMIT_REACHED.{when:%Y%m%dT%H%M%SZ}.json')
    n = 1
    while os.path.exists(new):
        new = os.path.join(store, f'LIMIT_REACHED.{when:%Y%m%dT%H%M%SZ}-{n}.json')
        n += 1
    os.rename(path, new)
    return new


def side_base(cfg, side):
    u = cfg['user_id']
    return {'kaijuflow': f'http://localhost:1338/{u}', 'kaijuflow-1page': f'http://localhost:1338/{u}',
            'uu': f'http://localhost:1339/{u}',
            'altmount-addon': f"http://localhost:8086/stremio/{cfg['download_key']}"}[side]


# --------------------------------------------------------------------------- the preflight (spec #72, ticket #74)

IMAGE = 'kaijuflow:test'
IMAGE_LABEL = 'kaijuflow.commit'


class PreflightFailed(Exception):
    def __init__(self, problems):
        super().__init__(' '.join(problems))
        self.problems = problems


def read_key_file(path):
    """(state, indexer slugs) of the key file. Only the indexer names are read, so new per-indexer settings do no harm.

    state: 'missing', 'open' (readable by others), 'unreadable' or 'ok'.
    """
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return 'missing', []
    if mode & 0o077:
        return 'open', []
    data = _read_json(path)
    names = data.get('indexers') if isinstance(data, dict) else None
    if not isinstance(names, dict):
        return 'unreadable', []
    return 'ok', sorted(str(k) for k in names)


def _list(items):
    return ', '.join(items) if items else 'none'


def preflight(mode, cfg, io):
    """Checks the setup before a record ('record') or a run ('run'). Returns plain sentences, one per problem; [] means go.

    Record only: the key file. Run only: the recording exists. Everything else is checked in both.
    """
    if mode not in ('record', 'run'):
        raise ValueError("preflight mode must be 'record' or 'run'")
    problems = []
    port = cfg.get('standin_port', 1340)

    # 1. the test image was built from the commit being tested
    commit, dirty = io.git_info()
    label = io.image_label()
    if dirty:
        problems.append('The repository has uncommitted changes, so the test image cannot name the code that runs: commit them first.')
    else:
        if cfg.get('rebuild_image') and label != commit:
            io.rebuild_image(commit)
            label = io.image_label()
        if not label:
            problems.append(f'The test image {IMAGE} is missing or does not say which commit it was built from: build it again with --rebuild-image.')
        elif label != commit:
            problems.append(f'The test image was built from commit {label[:7]} but the repository is at {commit[:7]}: '
                            'build it again with --rebuild-image.')

    rep = io.setup_report(cfg.get('limit', testbed.PROVIDER_LIMIT))
    titles = {side: v['short'] for side, v in testbed.SETTINGS.items()}
    indexer_sides = [s for s in testbed.SETTINGS_SIDES if s != 'nzbdav']
    unreadable = [s for s in indexer_sides if rep['indexers'].get(s) is None]
    for s in unreadable:
        problems.append(f"The config file of {titles[s]} cannot be read: check that it exists in the test folder.")
    readable = [s for s in indexer_sides if s not in unreadable]

    # 2. (record only) the key file names exactly the indexers every test copy has switched on
    if mode == 'record':
        path = cfg.get('key_file') or os.path.join(cfg['test_dir'], 'indexers.json')
        state, key = io.key_state(path)
        if state == 'missing':
            problems.append(f'The key file {path} is missing: create it with one entry per indexer before recording.')
        elif state == 'open':
            problems.append(f'The key file {path} can be read by others: make the key file readable only by you (run: chmod 600 {path}).')
        elif state == 'unreadable':
            problems.append(f'The key file {path} has no "indexers" list of names: fix the file.')
        else:
            differ = [f'{titles[s]} switches on {_list(rep["enabled"][s])}' for s in readable if rep['enabled'][s] != key]
            if differ:
                problems.append(f'The key file names {_list(key)}, but ' + '; '.join(differ) + ': make them the same.')

    # 3. every indexer address in every test copy is the indexer stand-in's (explained once, in the first sentence)
    what = ' (the local program that replays recorded indexer answers)'
    for s in readable:
        for r in rep['indexers'][s]:
            if testbed.standin_slug(r['url'], port) is None:
                problems.append(f'{r["name"]} in {titles[s]} points at {r["url"]}, not the indexer stand-in{what}: '
                                f'change the address to http://{testbed.STANDIN_HOST}:{port}/<indexer> so no test can reach a real indexer.')
                what = ''

    # 4. the connection caps fit the provider limit
    for s in testbed.SETTINGS_SIDES:
        if rep['caps'].get(s) is None:
            problems.append(f"The connection cap of {titles[s]} cannot be read from its config: check the file.")
    if rep['total'] > rep['limit']:
        per = ', '.join(f'{titles[s]} {rep["caps"][s]}' for s in testbed.SETTINGS_SIDES if rep['caps'].get(s) is not None)
        problems.append(f'The test copies may open {rep["total"]} connections together ({per}), over the provider limit of {rep["limit"]}: '
                        'lower the caps.')

    # 5. the stand-in's port is free
    if not io.port_free(port):
        problems.append(f"The indexer stand-in's port {port} is already in use: stop whatever listens there (an earlier indexer stand-in?) and try again.")

    # 6. (run only) the recording exists and holds an answer for every enabled indexer
    if mode == 'run':
        have = io.recording()
        need = sorted({slug for s in readable for slug in rep['enabled'][s]})
        state = io.recording_state()
        top_up = cfg.get('topup_command') or 'the record command with the same title list'
        if not have:
            problems.append(f"There is no recording for the title list '{cfg.get('listname')}' in {cfg.get('store')}: run the record command first.")
        elif not state:
            problems.append(f"The recording for '{cfg.get('listname')}' does not say whether it is complete: top it up with the record command: {top_up}")
        elif state.get('state') != 'complete':
            problems.append(f"The recording for '{cfg.get('listname')}' stopped early ({state.get('why') or 'no reason noted'}, "
                            f"{state.get('when') or 'at an unknown time'}): top it up with the record command: {top_up}")
        else:
            gaps = [slug for slug in need if not have.get(slug)]
            if gaps:
                problems.append(f"The recording for '{cfg.get('listname')}' holds no answer for {_list(gaps)}: top it up with the record command.")
    return problems


def preflight_command(mode, cfg, io):
    """Prints the preflight result in plain sentences; exit code 0 when the setup is right, 1 otherwise."""
    problems = preflight(mode, cfg, io)
    for p in problems:
        print(p)
    if not problems:
        print(f'Setup is right for a {mode}: image, indexers, addresses, connection caps and port all check out.')
    return 1 if problems else 0


# --------------------------------------------------------------------------- the run

def collect_visit(cfg, io, side, phase, rnd, title, logbuf):
    kind, vid, label = title
    kf_c, be_c, be_kind = SIDE_LOGS[side]
    t0 = io.now()
    http = io.visit_http(side, kind, vid, cfg['tries'])
    t1 = io.now()
    since = br.iso(t0 - datetime.timedelta(seconds=1))
    lo, hi = t0 - datetime.timedelta(seconds=1), t1 + datetime.timedelta(seconds=GRACE_S)
    kf_text = io.logs(kf_c, since) if kf_c else ''
    be_text = io.logs(be_c, since)
    for c, text in ((kf_c, kf_text), (be_c, be_text)):
        if c:
            logbuf.setdefault(c, []).append(f'--- {side} {phase} {rnd} {label} {br.iso(t0)}\n{br.scrub_text(text)}')
    # provisional; finalize_steps() re-attributes once the whole run is read (late lines, next visit of the side)
    steps = br.attribute_steps({'id': vid, 't_start': br.iso(t0), 'tries': http.get('tries', [])}, br.parse_step_lines(kf_text))
    parse = br.altmount_imports if be_kind == 'altmount' else br.nzbdav_imports
    imports = [i for i in parse(be_text) if lo <= br.parse_ts(i['start']) <= hi]
    limit = br.limit_event(kf_text + '\n' + be_text, cfg['indexers'])
    ok = bool(http.get('first_try_plays'))
    return {'side': side, 'phase': phase, 'round': rnd, 'title': label, 'id': vid, 'kind': kind, 'ok': ok,
            't_start': br.iso(t0), 't_end': br.iso(t1), 'list_status': http.get('list_status'),
            'list_s': http.get('list_s'), 'sources': http.get('sources'), 'start_s': http.get('start_s'),
            'seeks': http.get('seeks', {}), 'note': http.get('note'), 'tries': http.get('tries', []),
            'steps': steps, 'imports': imports, 'limit': limit}


def finalize_steps(io, visits):
    """Attribute every KaijuFlow step line to a visit, from the container's whole log.

    Search-side lines go by `ref` to the visit of that title until the next visit that used the same KaijuFlow container
    starts (no fixed cut-off, so a late health_batch is kept); prepare-side lines go to the Source that was played.
    """
    by_container = {}
    for v in visits:
        kf = SIDE_LOGS[v['side']][0]
        if kf:
            by_container.setdefault(kf, []).append(v)
    for container, vs in by_container.items():
        vs.sort(key=lambda v: br.parse_ts(v['t_start']))
        first = br.parse_ts(vs[0]['t_start']) - datetime.timedelta(seconds=1)
        steps = br.parse_step_lines(io.logs(container, br.iso(first)))
        for i, v in enumerate(vs):
            end = br.parse_ts(vs[i + 1]['t_start']) - datetime.timedelta(seconds=1) if i + 1 < len(vs) else None
            v['steps'] = br.attribute_steps(v, steps, end)


def _marker_is_old(m, since):
    """True when a marker was written before `since` (the start of this command): replay never contacts an indexer, so it cannot be new."""
    try:
        return br.parse_ts(m['time']) < since.replace(microsecond=0)
    except (TypeError, KeyError, ValueError):
        return False


def _check_cap(io, visit=None, since=None):
    m = io.marker()
    if m and since is not None and _marker_is_old(m, since):
        m = None
    if m:
        raise CapReached(m.get('indexer', 'unknown'), m.get('time', '?'), 'indexer stand-in LIMIT_REACHED.json')
    if visit and visit.get('limit'):
        lim = visit['limit']
        raise CapReached(lim['indexer'], lim.get('time') or visit['t_end'],
                         f"{visit['side']} log during {visit['title']}")


def do_pass(cfg, io, run, logbuf, sides, reset_sides):
    for phase, rnd in PLAN:
        if phase == 'cold':
            io.reset(reset_sides)
            note_addresses(io, run)  # a container gets its address when it starts
        for i, title in enumerate(cfg['titles']):
            k = i % len(sides)
            for side in sides[k:] + sides[:k]:
                v = collect_visit(cfg, io, side, phase, rnd, title, logbuf)
                run['visits'].append(v)
                print(f"{side} {phase} {rnd} {title[2]}: {'plays' if v['ok'] else 'FAILS'} list {v['list_s']} s start {v['start_s']} s", flush=True)
                _check_cap(io, v, since=run['started_at'])
                io.sleep(cfg['settle'])


def _write(path, text):
    with open(path, 'w') as f:
        f.write(text)


def run_all(cfg, io):
    problems = io.preflight('run')
    if problems:
        raise PreflightFailed(problems)
    started = io.now()
    root = cfg['runs_root']
    run_dir = br.create_run_dir(root, cfg['name'], started)
    logs_dir = os.path.join(run_dir, 'logs')
    os.makedirs(logs_dir)
    run = {'name': cfg['name'], 'status': 'ok', 'started': br.iso(started), 'dir': run_dir, 'visits': [], 'null': None,
           'error': None, 'titles': [t[2] for t in cfg['titles']], 'indexers': list(cfg['indexers']),
           'sides': MAIN_SIDES + (['kaijuflow-1page'] if cfg['one_page'] else []), 'standin_misses': 0,
           'settings': {}, 'commit': None, 'dirty': None, 'topup_command': cfg.get('topup_command'),
           'started_at': started, 'addresses': {}, 'standin_unmatched': 0,
           'facts': {'stand-in replay wait': 'on' if cfg.get('wait', True) else 'off',
                     'one-page side': 'yes' if cfg['one_page'] else 'no'}}
    wait = cfg.get('wait', True)
    logbuf, handle, failure = {}, None, None
    try:
        run['settings'] = io.snapshot()
        run['dirty'] = io.git_info()[1]
        run['commit'] = io.image_label()  # the commit the test image was built from, not the repository's
        _write(os.path.join(run_dir, 'settings.json'), json.dumps(run['settings'], indent=1, sort_keys=True))
        try:
            _check_cap(io, since=started)
            handle = io.start_standin(os.path.join(logs_dir, 'standin.log'), mode='replay', wait=wait)
            do_pass(cfg, io, run, logbuf, list(MAIN_SIDES), ALL_TESTBED)
            if cfg['one_page']:
                io.apply_one_page()
                do_pass(cfg, io, run, logbuf, ['kaijuflow-1page'], ['kaijuflow', 'altmount-kf'])
        except CapReached as e:
            run['status'] = 'null'
            run['null'] = {'indexer': e.indexer, 'time': e.time, 'where': e.where}
        finally:
            try:
                finalize_steps(io, run['visits'])
                if handle:
                    run['standin_unmatched'] = br.assign_standin(run['visits'], io.standin_lines(), run['addresses'])
            finally:  # the cleanup runs even when reading the logs fails
                io.restore_config()
                if handle:
                    handle.stop()
                io.stop_all()
    except Exception as e:  # noqa: BLE001
        run['status'], run['error'] = 'failed', br.scrub_text(f'{type(e).__name__}: {e}')
        failure = e
    run['finished'] = br.iso(io.now())
    sl = os.path.join(logs_dir, 'standin.log')
    if os.path.exists(sl):
        run['standin_misses'] = sum(1 for line in _read_text(sl).splitlines() if line.startswith('MISS '))
    for c, parts in logbuf.items():
        _write(os.path.join(logs_dir, c + '.log'), '\n'.join(parts) + '\n')
    prev = br.previous_run(root, exclude=os.path.basename(run_dir))
    nulls = br.null_runs_between(root, prev['started'], exclude=os.path.basename(run_dir)) if prev and prev.get('started') else None
    run['changes'] = br.diff_runs(prev, run, nulls)
    if run['status'] == 'ok':
        report, result, headline = br.render_report(run, run['changes']), 'ok', br.headline(run)
    elif run['status'] == 'null':
        report, result = br.render_null_report(run), 'NULL'
        headline = f"NULL: {run['null']['indexer']} limit reached at {run['null']['time']}; no numbers"
    else:
        report, result, headline = f"This run failed before it finished: {run['error']}\n", 'failed', f"failed: {run['error']}"
    _write(os.path.join(run_dir, 'report.md'), report)
    _write(os.path.join(run_dir, 'raw.json'), json.dumps({'status': run['status'], 'visits': run['visits']}, indent=1))
    meta = {k: run.get(k) for k in ('name', 'status', 'started', 'finished', 'commit', 'dirty', 'titles', 'indexers',
                                    'sides', 'settings', 'facts', 'addresses', 'standin_unmatched', 'null', 'error',
                                    'standin_misses', 'changes')}
    _write(os.path.join(run_dir, 'meta.json'), json.dumps(meta, indent=1, sort_keys=True))
    br.append_index_row(os.path.join(root, 'INDEX.md'), {
        'date': run['started'], 'name': cfg['name'], 'result': result, 'changed': run['changes'],
        'headline': headline, 'folder': os.path.basename(run_dir)})
    if failure:
        raise failure
    return run


# --------------------------------------------------------------------------- the record command (spec #72, ticket #75)

def record_all(cfg, io):
    """Preflight, reset, stand-in in record mode, every side through every title once, reset again.

    Running it again is a top-up: record mode serves what is stored instead of asking the indexer. The first "limit reached"
    stops the pass and the recording is NULL (what was stored stays). Nothing from the pass is a measurement: it gets a folder
    with the stand-in's log and a meta.json, and an INDEX.md row only when it is NULL or failed.
    """
    problems = io.preflight('record') + io.setting_conflicts()
    if problems:
        raise PreflightFailed(problems)
    if io.marker():  # left by an earlier command: kept under another name; if the limit still holds, the first answer writes a new one
        io.shelve_marker()
    started = io.now()
    root = cfg['runs_root']
    run_dir = br.create_run_dir(root, cfg['name'] + '-record', started)
    logs_dir = os.path.join(run_dir, 'logs')
    os.makedirs(logs_dir)
    logpath = os.path.join(logs_dir, 'standin.log')
    rec = {'name': cfg['name'], 'mode': 'record', 'status': 'recorded', 'started': br.iso(started), 'dir': run_dir, 'null': None,
           'error': None, 'titles': [t[2] for t in cfg['titles']], 'sides': MAIN_SIDES + (['kaijuflow-1page'] if cfg['one_page'] else []),
           'commit': None, 'new_answers': 0, 'stored_answers': 0, 'errors': 0, 'visits': 0}
    handle, failure = None, None
    try:
        rec['commit'] = io.image_label()
        io.reset(ALL_TESTBED)
        handle = io.start_standin(logpath, mode='record')
        try:
            record_pass(cfg, io, rec, list(MAIN_SIDES))
            if cfg['one_page']:
                io.apply_one_page()
                record_pass(cfg, io, rec, ['kaijuflow-1page'])
        except CapReached as e:
            rec['status'] = 'null'
            rec['null'] = {'indexer': e.indexer, 'time': e.time, 'where': e.where}
        finally:
            try:
                if handle:
                    handle.stop()
            finally:  # the cleanup runs even when stopping the stand-in fails
                io.restore_config()
                io.reset(ALL_TESTBED)
                io.stop_all()
    except Exception as e:  # noqa: BLE001
        rec['status'], rec['error'] = 'failed', br.scrub_text(f'{type(e).__name__}: {e}')
        failure = e
    rec['finished'] = br.iso(io.now())
    text = _read_text(logpath) or ''
    rec['new_answers'] = sum(1 for line in text.splitlines() if line.startswith('RECORD '))
    rec['stored_answers'] = sum(1 for line in text.splitlines() if line.startswith('HIT '))
    rec['errors'] = sum(1 for line in text.splitlines() if line.startswith('ERROR '))
    write_recording_state(cfg, rec)
    _write(os.path.join(run_dir, 'meta.json'), json.dumps({k: rec.get(k) for k in rec if k != 'dir'}, indent=1, sort_keys=True))
    if rec['status'] == 'null':
        br.append_index_row(os.path.join(root, 'INDEX.md'), {
            'date': rec['started'], 'name': cfg['name'] + ' (record)', 'result': 'NULL',
            'changed': ['recording stopped; what was stored is kept, top it up after the reset'],
            'headline': f"NULL: {rec['null']['indexer']} limit reached at {rec['null']['time']}; no numbers",
            'folder': os.path.basename(run_dir)})
    elif rec['status'] == 'failed':
        br.append_index_row(os.path.join(root, 'INDEX.md'), {
            'date': rec['started'], 'name': cfg['name'] + ' (record)', 'result': 'failed', 'changed': ['record pass'],
            'headline': f"failed: {rec['error']}", 'folder': os.path.basename(run_dir)})
    if failure:
        raise failure
    return rec


def write_recording_state(cfg, rec):
    """Writes the recording's state next to the list's answers: complete, or stopped early (why and when), and how many
    answers of this pass were errors (not stored). The preflight of a run reads it."""
    d = os.path.join(cfg['store'], cfg['listname'])
    os.makedirs(d, exist_ok=True)
    if rec['status'] == 'recorded':
        state, why = 'complete', None
    elif rec['status'] == 'null':
        state, why = 'stopped', f"{rec['null']['indexer']} said its limit was reached"
    else:
        state, why = 'stopped', rec.get('error') or 'the record pass failed'
    _write(os.path.join(d, RECORDING_FILE), json.dumps({'state': state, 'why': why, 'when': rec['finished'], 'errors': rec['errors']}, indent=1))


def record_summary(rec):
    """The sentence(s) the record command ends with."""
    text = f"Recorded {rec['new_answers']} new answers; {rec['stored_answers']} were already stored."
    n = rec.get('errors') or 0
    if n:
        text += (f" {n} answer{' was an error' if n == 1 else 's were errors'} and {'was' if n == 1 else 'were'} not stored: "
                 "run record again to top them up.")
    return text


def record_pass(cfg, io, rec, sides):
    """Every side lists every title and plays its top pick once, sides one after another, order rotating per title."""
    _check_cap(io)
    for i, title in enumerate(cfg['titles']):
        k = i % len(sides)
        for side in sides[k:] + sides[:k]:
            kind, vid, label = title
            http = io.visit_http(side, kind, vid, cfg['tries'])
            rec['visits'] += 1
            print(f"{side} {label}: {http.get('sources')} Sources, top pick {'plays' if http.get('first_try_plays') else 'does not play'}", flush=True)
            _check_cap(io)
            io.sleep(cfg['settle'])


# --------------------------------------------------------------------------- smoke and CLI

def smoke_side_result(lines, expected_ip):
    """What one side's search caused at the stand-in: how many requests, from which address(es), and whether that is the
    address `docker inspect` gave for the side's container."""
    seen = [p for p in (br.parse_standin_line(x) for x in lines) if p]
    came_from = sorted({p['ip'] for p in seen})
    return {'standin_requests': len(seen), 'came_from': came_from, 'expected_from_docker_inspect': expected_ip,
            'matched': bool(came_from) and came_from == [expected_ip],
            'sample': [x.strip() for x in lines[:1]]}


def smoke_verdict(results):
    """One plain sentence on whether the sides arrive with their own addresses."""
    addrs = [tuple(r['came_from']) for r in results.values()]
    if all(r['matched'] for r in results.values()) and len(set(addrs)) == len(addrs):
        return 'Every side reached the indexer stand-in from its own address, and each address matched what docker inspect gave.'
    if not any(addrs):
        return 'No side reached the indexer stand-in: nothing can be said about addresses.'
    return ('The sides do not all arrive with their own matching address: the runner must rely on the time window alone '
            'for the sides that did not match.')


def smoke(cfg, port=1340):
    """One search per side against the stand-in on an EMPTY store (every request a MISS); prints which side reached it,
    from which address, and whether that matches the address docker inspect gives for the side's test container."""
    store = cfg['store']
    if os.path.isdir(store) and os.listdir(store):
        sys.exit('smoke needs an EMPTY store folder so that every request is a MISS and nothing can be read from Usenet')
    os.makedirs(store, exist_ok=True)
    io = RealIO(cfg)
    log = os.path.join(store, '..', os.path.basename(store.rstrip('/')) + '.smoke.log')
    handle = io.start_standin(log)
    results = {}
    try:
        addresses = io.addresses()
        for side in ('kaijuflow', 'uu', 'altmount-addon'):
            before = len((_read_text(log) or '').splitlines())
            st, h, body, t = common.get(f"{side_base(cfg, side)}/stream/movie/{os.environ.get('SMOKE_IMDB', 'tt0133093')}.json", timeout=120, limit=0)
            time.sleep(1)
            new = [x for x in (_read_text(log) or '').splitlines()[before:] if x.startswith('MISS ')]
            results[side] = dict(http=st, **smoke_side_result(new, addresses.get(br.CLIENT_CONTAINER[side])))
    finally:
        handle.stop()
    print(json.dumps(results, indent=1))
    print(smoke_verdict(results))
    return results


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('cmd', choices=['run', 'record', 'smoke', 'preflight'])
    ap.add_argument('--no-wait', action='store_true', help='run only: replay indexer answers at once instead of waiting the recorded indexer time')
    ap.add_argument('--for', dest='mode', choices=['run', 'record'], default='run', help='preflight only: check the setup for a run or for a record pass')
    ap.add_argument('--name', default='run')
    ap.add_argument('--runs-root', default=DEFAULT_RUNS_ROOT)
    ap.add_argument('--store')
    ap.add_argument('--list', dest='listname')
    ap.add_argument('--rebuild-image', action='store_true', help='build kaijuflow:test again from the current commit when the image is not from it')
    ap.add_argument('--provider-limit', type=int, default=testbed.PROVIDER_LIMIT)
    ap.add_argument('--key-file')
    ap.add_argument('--test-dir', default=os.environ.get('TEST_DIR', DEFAULT_TEST_DIR))
    ap.add_argument('--user-id')
    ap.add_argument('--one-page', action='store_true', help='add the fourth side: KaijuFlow, one page per indexer')
    ap.add_argument('--titles-file')
    ap.add_argument('--tries', type=int, default=1)
    ap.add_argument('--settle', type=float, default=3)
    return ap


def topup_command(a):
    """The record command that tops up this recording, as a line the owner can paste."""
    parts = ['python3', '-I', 'tools/brain/brainrun.py', 'record', '--name', a.name, '--store', a.store or '', '--list', a.listname or '']
    if a.key_file:
        parts += ['--key-file', a.key_file]
    if a.titles_file:
        parts += ['--titles-file', a.titles_file]
    if a.one_page:
        parts.append('--one-page')
    return ' '.join(shlex.quote(x) for x in parts)


def main(argv):
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.cmd != 'preflight' or a.mode == 'run':
        if not a.store or not a.listname:
            ap.error('--store and --list are needed')
    td = a.test_dir
    users = (_read_json(os.path.join(td, 'config/users.json')) or {}).get('users') or [{}]
    key = (_read_text(os.path.join(td, 'templates/altmount.key')) or '').strip()
    pool = [tuple(t) for t in _read_json(a.titles_file)] if a.titles_file else common.TITLES
    listdir = os.path.join(a.store or '', a.listname or '')
    cfg = dict(name=a.name, runs_root=a.runs_root, store=a.store, listname=a.listname, test_dir=td,
               user_id=a.user_id or ((users[0].get('manifests') or [{}])[0].get('id') or users[0].get('id', '')), download_key=hashlib.sha256(key.encode()).hexdigest(),
               one_page=a.one_page, titles=pool, tries=a.tries, settle=a.settle,
               indexers=sorted(d for d in os.listdir(listdir) if os.path.isdir(os.path.join(listdir, d))) if a.store and os.path.isdir(listdir) else [],
               rebuild_image=a.rebuild_image, limit=a.provider_limit, key_file=a.key_file, standin_port=testbed.STANDIN_PORT,
               wait=not a.no_wait, topup_command=topup_command(a))
    started = time.time()
    if a.cmd == 'preflight':
        return preflight_command(a.mode, cfg, RealIO(cfg))
    if a.cmd == 'smoke':
        smoke(cfg)
    elif a.cmd == 'record':
        try:
            rec = record_all(cfg, RealIO(cfg))
        except PreflightFailed as e:
            for p in e.problems:
                print(p)
            return 1
        if rec['status'] == 'null':
            print(f"The recording stopped: {rec['null']['indexer']} said its limit was reached. What was stored is kept; "
                  f"once the indexer has reset, run the same command again to top up. Folder: {rec['dir']}")
            return 2
        print(f"{record_summary(rec)} Folder: {rec['dir']}")
    else:
        try:
            run = run_all(cfg, RealIO(cfg))
        except PreflightFailed as e:
            for p in e.problems:
                print(p)
            return 1
        print(f"{run['status']}: {run['dir']}")
    common.finish(started)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
