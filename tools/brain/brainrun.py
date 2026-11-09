"""The one command that runs every side cold, then warm, twice, and writes the run record (spec #58, ticket #62).

    python3 -I tools/brain/brainrun.py run --name baseline --store <standin-store> --list <title-list>
           [--runs-root DIR] [--one-page] [--titles-file titles.json] [--user-id ID] [--tries 1]
    python3 -I tools/brain/brainrun.py smoke --store <EMPTY dir> --list smoke   (stand-in reachability check, see README)

It starts the indexer stand-in in REPLAY mode (never record, so no real indexer is contacted), resets the test copies with
testbed.py before each cold round, plays the top pick of every title on every side one side at a time, reads KaijuFlow's
[KF-STEP] lines and the Backends' import start/end from the test containers' logs, and writes a run folder, one INDEX.md
row and the report. The first "limit reached" from any indexer aborts the run and records it as null.
Only test containers are touched. Secrets never reach the run folder (settings are scrubbed, logs are scrubbed).
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
import common  # noqa: E402

DEFAULT_RUNS_ROOT = '/home/ryan/kaijuflow-notes/brain-runs'
DEFAULT_TEST_DIR = '/home/ryan/kaijuflow-test'
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


def nzbdav_settings(db_path):
    """NzbDAV's stored settings (ConfigItems), secrets replaced by ***."""
    if not os.path.exists(db_path):
        return {}
    db = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
    try:
        rows = db.execute('select ConfigName, ConfigValue from ConfigItems').fetchall()
    except sqlite3.Error:
        return {}
    finally:
        db.close()
    out = {}
    for name, value in rows:
        try:
            parsed = json.loads(value) if value and value.strip()[:1] in '{[' else None
        except ValueError:
            parsed = None
        if parsed is not None:
            out.update(br.flatten(parsed, name))
        else:
            out[name] = br._scrub_value(name, value)
    return out


def snapshot_settings(test_dir):
    """Settings of every side with secrets removed: {side: {dotted key: value}}."""
    td = test_dir
    snap = {}
    for side, rel in (('kaijuflow', 'config/config.json'), ('uu', 'uu/config/config.json')):
        data = _read_json(os.path.join(td, rel))
        snap[side] = br.flatten(data) if data is not None else {'(file missing)': rel}
    snap['nzbdav'] = nzbdav_settings(os.path.join(td, 'nzbdav/config/db.sqlite'))
    for side in ('altmount-addon', 'altmount-kf'):
        text = _read_text(os.path.join(td, side, 'config/config.yaml'))
        snap[side] = br.flatten_yaml(text) if text is not None else {'(file missing)': side}
    return snap


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
        import testbed
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

    def marker(self):
        return _read_json(os.path.join(self.cfg['store'], 'LIMIT_REACHED.json'))

    def start_standin(self, logpath):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'indexer_standin.py')
        port = self.cfg.get('standin_port', 1340)
        log = open(logpath, 'w')
        proc = subprocess.Popen([sys.executable, '-I', script, '--mode', 'replay', '--store', self.cfg['store'],
                                 '--list', self.cfg['listname'], '--port', str(port), '--bind', '0.0.0.0'],
                                stderr=log, stdout=subprocess.DEVNULL)
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


def side_base(cfg, side):
    u = cfg['user_id']
    return {'kaijuflow': f'http://localhost:1338/{u}', 'kaijuflow-1page': f'http://localhost:1338/{u}',
            'uu': f'http://localhost:1339/{u}',
            'altmount-addon': f"http://localhost:8086/stremio/{cfg['download_key']}"}[side]


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
    steps = []
    for s in br.parse_step_lines(kf_text):
        try:
            if lo <= br.parse_ts(s['t']) <= hi:
                steps.append(s)
        except (KeyError, ValueError):
            pass
    parse = br.altmount_imports if be_kind == 'altmount' else br.nzbdav_imports
    imports = [i for i in parse(be_text) if lo <= br.parse_ts(i['start']) <= hi]
    limit = br.limit_event(kf_text + '\n' + be_text, cfg['indexers'])
    ok = bool(http.get('first_try_plays'))
    return {'side': side, 'phase': phase, 'round': rnd, 'title': label, 'id': vid, 'kind': kind, 'ok': ok,
            't_start': br.iso(t0), 't_end': br.iso(t1), 'list_status': http.get('list_status'),
            'list_s': http.get('list_s'), 'sources': http.get('sources'), 'start_s': http.get('start_s'),
            'seeks': http.get('seeks', {}), 'note': http.get('note'), 'tries': http.get('tries', []),
            'steps': steps, 'imports': imports, 'limit': limit}


def _check_cap(io, visit=None):
    m = io.marker()
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
        for i, title in enumerate(cfg['titles']):
            k = i % len(sides)
            for side in sides[k:] + sides[:k]:
                v = collect_visit(cfg, io, side, phase, rnd, title, logbuf)
                run['visits'].append(v)
                print(f"{side} {phase} {rnd} {title[2]}: {'plays' if v['ok'] else 'FAILS'} list {v['list_s']} s start {v['start_s']} s", flush=True)
                _check_cap(io, v)
                io.sleep(cfg['settle'])


def _write(path, text):
    with open(path, 'w') as f:
        f.write(text)


def run_all(cfg, io):
    started = io.now()
    root = cfg['runs_root']
    run_dir = br.create_run_dir(root, cfg['name'], started)
    logs_dir = os.path.join(run_dir, 'logs')
    os.makedirs(logs_dir)
    run = {'name': cfg['name'], 'status': 'ok', 'started': br.iso(started), 'dir': run_dir, 'visits': [], 'null': None,
           'error': None, 'titles': [t[2] for t in cfg['titles']], 'indexers': list(cfg['indexers']),
           'sides': MAIN_SIDES + (['kaijuflow-1page'] if cfg['one_page'] else []), 'standin_misses': 0,
           'settings': {}, 'commit': None, 'dirty': None}
    logbuf, handle, failure = {}, None, None
    try:
        run['settings'] = io.snapshot()
        run['commit'], run['dirty'] = io.git_info()
        _write(os.path.join(run_dir, 'settings.json'), json.dumps(run['settings'], indent=1, sort_keys=True))
        try:
            _check_cap(io)
            handle = io.start_standin(os.path.join(logs_dir, 'standin.log'))
            do_pass(cfg, io, run, logbuf, list(MAIN_SIDES), ALL_TESTBED)
            if cfg['one_page']:
                run['settings'].update(io.apply_one_page())
                do_pass(cfg, io, run, logbuf, ['kaijuflow-1page'], ['kaijuflow', 'altmount-kf'])
        except CapReached as e:
            run['status'] = 'null'
            run['null'] = {'indexer': e.indexer, 'time': e.time, 'where': e.where}
        finally:
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
    run['changes'] = br.diff_runs(prev, run)
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
                                    'sides', 'settings', 'null', 'error', 'standin_misses', 'changes')}
    _write(os.path.join(run_dir, 'meta.json'), json.dumps(meta, indent=1, sort_keys=True))
    br.append_index_row(os.path.join(root, 'INDEX.md'), {
        'date': run['started'], 'name': cfg['name'], 'result': result, 'changed': run['changes'],
        'headline': headline, 'folder': os.path.basename(run_dir)})
    if failure:
        raise failure
    return run


# --------------------------------------------------------------------------- smoke and CLI

def smoke(cfg, port=1340):
    """One search per side against the stand-in on an EMPTY store (every request a MISS); prints which side reached it."""
    store = cfg['store']
    if os.path.isdir(store) and os.listdir(store):
        sys.exit('smoke needs an EMPTY store folder so that every request is a MISS and nothing can be read from Usenet')
    os.makedirs(store, exist_ok=True)
    io = RealIO(cfg)
    log = os.path.join(store, '..', os.path.basename(store.rstrip('/')) + '.smoke.log')
    handle = io.start_standin(log)
    results = {}
    try:
        for side in ('kaijuflow', 'uu', 'altmount-addon'):
            before = sum(1 for line in open(log) if line.startswith('MISS '))
            st, h, body, t = common.get(f"{side_base(cfg, side)}/stream/movie/tt0133093.json", timeout=120, limit=0)
            time.sleep(1)
            lines = [line.strip() for line in open(log) if line.startswith('MISS ')]
            results[side] = {'http': st, 'standin_requests': len(lines) - before, 'sample': lines[before:before + 1]}
    finally:
        handle.stop()
    print(json.dumps(results, indent=1))
    return results


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('cmd', choices=['run', 'smoke'])
    ap.add_argument('--name', default='run')
    ap.add_argument('--runs-root', default=DEFAULT_RUNS_ROOT)
    ap.add_argument('--store', required=True)
    ap.add_argument('--list', required=True, dest='listname')
    ap.add_argument('--test-dir', default=os.environ.get('TEST_DIR', DEFAULT_TEST_DIR))
    ap.add_argument('--user-id')
    ap.add_argument('--one-page', action='store_true', help='add the fourth side: KaijuFlow, one page per indexer')
    ap.add_argument('--titles-file')
    ap.add_argument('--tries', type=int, default=1)
    ap.add_argument('--settle', type=float, default=3)
    a = ap.parse_args(argv)
    td = a.test_dir
    users = (_read_json(os.path.join(td, 'config/users.json')) or {}).get('users') or [{}]
    key = (_read_text(os.path.join(td, 'templates/altmount.key')) or '').strip()
    pool = [tuple(t) for t in _read_json(a.titles_file)] if a.titles_file else common.TITLES
    listdir = os.path.join(a.store, a.listname)
    cfg = dict(name=a.name, runs_root=a.runs_root, store=a.store, listname=a.listname, test_dir=td,
               user_id=a.user_id or users[0].get('id', ''), download_key=hashlib.sha256(key.encode()).hexdigest(),
               one_page=a.one_page, titles=pool, tries=a.tries, settle=a.settle,
               indexers=sorted(os.listdir(listdir)) if os.path.isdir(listdir) else [])
    started = time.time()
    if a.cmd == 'smoke':
        smoke(cfg)
    else:
        run = run_all(cfg, RealIO(cfg))
        print(f"{run['status']}: {run['dir']}")
    common.finish(started)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
