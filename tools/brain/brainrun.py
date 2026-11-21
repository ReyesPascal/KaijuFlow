"""The one command that runs the setup (KaijuFlow with its AltMount copy, #185) cold, then warm, twice, and writes the run record (spec #58, ticket #62).

    python3 -I tools/brain/brainrun.py run --name baseline --store <standin-store> --list <title-list>
           [--runs-root DIR] [--one-page | --quick | --sides LIST --rounds 1|2] [--titles-file titles.json] [--user-id ID] [--tries 1]
           [--rebuild-image] [--provider-limit 100] [--no-wait]
    python3 -I tools/brain/brainrun.py record --name baseline --store <standin-store> --list <title-list> [--key-file PATH]
           [--runs-root DIR] [--one-page] [--titles-file titles.json] [--tries 1] [--rebuild-image]   (record, or top up)
    python3 -I tools/brain/brainrun.py preflight [--for run|record] --store <standin-store> --list <title-list>
           [--rebuild-image] [--provider-limit 100] [--key-file PATH]   (the setup check alone; a run starts with it)
    python3 -I tools/brain/brainrun.py smoke --store <EMPTY dir> --list smoke [--one-page]   (stand-in reachability check, see README)

A run starts the indexer stand-in in REPLAY mode (never record, so no real indexer is contacted; it waits the recorded
indexer time for every answer unless --no-wait; every visit waits the fixed Browse pause between its list and
its play, #205; the stand-in's lines say which test container asked and when, so the report
matches them to the right side and visit) and resets the test copies with
testbed.py before each cold round, plays the top pick of every title on every side one side at a time, reads KaijuFlow's
[KF-STEP] lines and the Backends' import start/end from the test containers' logs, and writes a run folder, one INDEX.md
row and the report. The first "limit reached" from any indexer aborts the run and records it as null. Ctrl-C or SIGTERM
(what `timeout` sends) stops the pass too: the run is recorded as stopped, from the plays that finished, and a second
stop is ignored until that record is written (#110).
Every line of a play or a reset starts with the UTC time and a count (`05:46:35 [61/160] ...`), and the run's meta.json
and report say where its wall-clock time went: each pass, round and reset, the pauses (--settle), the failed plays and
the rest (#112).
The record command resets the test copies, starts the stand-in in RECORD mode (this spends real indexer requests), sends
every side through every title in a cold round and then a warm round, then proves the recording: the stand-in in REPLAY mode with the wait off
(no indexer contacted), test copies reset, the same two rounds again. No miss = state complete; any miss = incomplete (listed); and resets again; running it again only asks for what is not stored yet. Its timings never
reach a report. Only test containers are touched. Secrets never reach the run folder (settings are scrubbed, logs are scrubbed).
"""
import argparse
import contextlib
import copy
import datetime
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import allowance  # noqa: E402
import brainreport as br  # noqa: E402
import common  # noqa: E402
import indexer_standin  # noqa: E402
import runcheck  # noqa: E402
import testbed  # noqa: E402
from common import DEFAULT_TEST_DIR  # noqa: E402

DEFAULT_RUNS_ROOT = os.path.expanduser('~/kaijuflow-notes/brain-runs')
PLAN = [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)]
RECORD_ROUNDS = ('cold', 'warm')  # a record pass: a cold round, then a warm round on the same state (#79)
MAIN_SIDES = ['kaijuflow']  # one setup (#185): KaijuFlow with its AltMount copy; the other test copies stay stopped
ALL_TESTBED = ['altmount-kf', 'kaijuflow']  # the test copies a record or a run resets, the one-page side's too: the setup's own
# every side's containers: KaijuFlow's, with the [KF-STEP] lines, and its AltMount's, whose log holds the imports
KF_CONTAINER, ALTMOUNT_CONTAINER = br.CLIENT_CONTAINER, 'altmount-kf-test'
GRACE_S = 5
BROWSE_PAUSE_S = 5  # the Browse pause of every run (#205): a viewer reading the page between the list and the play
RECORDING_FILE = 'RECORDING.json'  # next to a list's answers: {"state": "complete"|"incomplete"|"stopped", "why", "when", "errors", "misses"}
EXIT_STOPPED, EXIT_INCOMPLETE = 2, 3  # the record command's own exit codes (0 complete, 1 setup problem or failure)
EXIT_INTERRUPTED = 130  # run and record: stopped by Ctrl-C or SIGTERM (130 is the shell's own code for Ctrl-C)


class CapReached(Exception):
    def __init__(self, indexer, time_, where):
        super().__init__(f'{indexer} limit reached at {time_} ({where})')
        self.indexer, self.time, self.where = indexer, time_, where


class Stop(KeyboardInterrupt):
    """A stop signal other than Ctrl-C (SIGTERM, which `timeout` sends), raised where the command is, so it takes the same
    path as Ctrl-C's KeyboardInterrupt and the command ends the normal way, with status `stopped`."""

    def __init__(self, signal_name):
        super().__init__(signal_name)
        self.signal_name = signal_name


@contextlib.contextmanager
def sigterm_stops():
    """While a run or a record goes, SIGTERM stops it the way Ctrl-C does (raises Stop); the earlier handler comes back after."""
    def stop(signum, frame):
        raise Stop(signal.Signals(signum).name)
    earlier = signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, earlier)


def stop_note(io, stopped_by, stage, plays_done, plays_planned, playing):
    """How a run or a record was stopped, in the one shape both keep (meta.json's `stopped`; brainreport.stopped_text says
    it in words): when, by which signal (from the KeyboardInterrupt or Stop that `stopped_by` is), in which stage, the plays
    done out of those planned as the play lines count them, and the play that was cut off (None between two plays)."""
    return {'time': br.iso(io.now()), 'signal': getattr(stopped_by, 'signal_name', 'SIGINT'), 'stage': stage,
            'plays_done': plays_done, 'plays_planned': plays_planned, 'during': playing}


def finish_after_stop(stopped, command, files):
    """After the first stop: one line says the command is finishing its record, and further Ctrl-C and SIGTERM are ignored
    until it is written. Returns the function that puts the earlier handlers back (it does nothing off the main thread,
    where no handler can be set)."""
    print(f"Stopped by {br.STOP_SIGNALS.get(stopped['signal'], stopped['signal'])}: the {command} is finishing its record "
          f"({files}); a second Ctrl-C is ignored until it is written.", flush=True)
    try:
        earlier = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGTERM)}
    except ValueError:
        return lambda: None
    return lambda: [signal.signal(s, h) for s, h in earlier.items()]


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


ALL_SIDES = MAIN_SIDES + ['kaijuflow-1page']


def run_sides(cfg):
    """The sides a run plays: the ones `--sides` names (in the plan's order), else the planned sides."""
    named = cfg.get('sides')
    return planned_sides(cfg) if named is None else [s for s in ALL_SIDES if s in named]


def run_plan(cfg):
    """The rounds a run plays: PLAN, or its first pairs of cold and warm rounds when `--rounds 1`."""
    return PLAN[:2 * cfg.get('rounds', 2)]


def short_run(cfg):
    """What a short run played (see brainreport.short_run_text), or None when the run is the full plan: the setup,
    two rounds and every title of the list."""
    sides, rounds = run_sides(cfg), cfg.get('rounds', 2)
    if all(s in sides for s in MAIN_SIDES) and rounds == 2 and not cfg.get('partial_titles'):
        return None
    return br.short_run_text(sides, rounds, cfg['titles'])


def planned_sides(cfg):
    """The sides a run, a record pass or a smoke check uses: KaijuFlow, then the one-page side when asked for."""
    return list(MAIN_SIDES) + (['kaijuflow-1page'] if cfg['one_page'] else [])


def switch_to_one_page(io, log=print):
    """The one step that turns KaijuFlow's test copy into the fourth side; the run, the record pass and the smoke check share
    it. The config is patched while the copy is stopped, then KaijuFlow and its AltMount are reset and come up again (cold).
    io.restore_config() undoes it. `log` gets the reset's lines."""
    io.apply_one_page()
    io.reset(ALL_TESTBED, log)


def visit_answer(got, tries, play=None, seek=None, pause_s=0, sleep=time.sleep):
    """One visit's result from one common.get() of a side's list address (status None: the copy did not answer), then the
    top `tries` Streams played. The real world and the fakes both build a visit here, so a copy that is down looks the same.
    A list with something to play is read for `pause_s` seconds first, the Browse pause (#205, rules.md "Browse pause"):
    `browse_pause_s` says how long it waited; it is in neither `list_s` nor `start_s`, so title to video leaves it out."""
    play, seek = play or common.play_stream, seek or common.seek_reads
    st, h, body, t = got
    out = {'list_status': st, 'list_s': round(t.get('total', t['ready']), 2), 'note': None}
    try:
        streams = json.loads(body or b'{}').get('streams', []) if st == 200 else []
    except ValueError as e:
        streams, out['note'] = [], f'bad JSON: {e}'[:120]
    if st != 200:
        out['note'] = h.get('error') or f'HTTP {st}'
    out['sources'] = len(streams)
    out['browse_pause_s'] = pause_s if streams[:tries] and pause_s else 0
    if out['browse_pause_s']:
        sleep(pause_s)
    plays = [play(s) for s in streams[:tries]]
    out['tries'] = plays
    top = plays[0] if plays else None
    out['first_try_plays'] = bool(top and top['plays'])
    out['start_s'] = top['first_byte_s'] if out['first_try_plays'] else None
    out['seeks'] = seek(streams[0]['url'], top['size']) if out['first_try_plays'] else {}
    if top and not top['plays']:
        out['note'] = top.get('note')
    elif not streams and not out['note']:
        out['note'] = 'no Sources'
    return out


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
        self.repo = REPO
        self.backup = os.path.join(cfg['test_dir'], 'config', 'config.json.pre-brainrun')

    def now(self):
        return datetime.datetime.now(datetime.timezone.utc)

    def sleep(self, s):
        time.sleep(s)

    def git_info(self):
        commit = subprocess.check_output(['git', '-C', self.repo, 'rev-parse', 'HEAD'], text=True).strip()
        dirty = bool(subprocess.check_output(['git', '-C', self.repo, 'status', '--porcelain', '--untracked-files=no'], text=True).strip())
        return commit, dirty

    def build_inputs_changed(self, since):
        return build_inputs_changed(self.repo, since)

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
        build_image(commit, self.repo)

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

    def load_average(self):
        return os.getloadavg()[0]

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

    def reset(self, sides, log=print):
        self.testbed.reset(self.cfg['test_dir'], sides, log=log)
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

    def visit_http(self, side, kind, vid, tries, browse_pause_s=0):
        base = list_base(self.cfg)
        return visit_answer(common.get(f'{base}/stream/{kind}/{vid}.json', timeout=180, limit=0), tries,
                            pause_s=browse_pause_s, sleep=self.sleep)

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


def build_inputs_changed(repo, since, run=subprocess.run):
    """Whether a build input differs between the commit `since` and HEAD: True or False, or None when git cannot say
    (`since` is not a commit id, or the repository does not have that commit)."""
    if not re.fullmatch(r'[0-9a-f]{7,40}', since or ''):
        return None
    r = run(['git', '-C', repo, 'diff', '--quiet', since + '^{commit}', 'HEAD', '--', *BUILD_INPUTS],
            capture_output=True, text=True, timeout=60)
    return {0: False, 1: True}.get(r.returncode)


def read_addresses(run=subprocess.run):
    """{test container: its address on the test network}, read with `docker inspect` (read-only); a container that is not up
    or has no address is left out."""
    out = {}
    for container in [KF_CONTAINER]:
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


def list_base(cfg):
    """The address every side's list is asked of: KaijuFlow's test copy (the one-page side is the same copy, patched)."""
    return f"http://localhost:1338/{cfg['user_id']}"


# --------------------------------------------------------------------------- the preflight (spec #72, ticket #74)

IMAGE = 'kaijuflow:test'
IMAGE_LABEL = 'kaijuflow.commit'
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The build inputs: every path the Dockerfile copies into the image (test_preflight.py holds the two in line), the Dockerfile,
# and the two files that can change what a build gets to see (the image is built from `git archive HEAD`, see build_image).
BUILD_INPUTS = ('Dockerfile', '.dockerignore', '.gitattributes', 'package.json', 'package-lock.json', 'tsconfig.json',
                'src', 'ui', 'scripts/docker-entrypoint.sh')
# The settings every test copy is expected to have (sort and filter rules); the preflight compares each copy with it (#109).
EXPECTED_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'expected-settings.json')


# A timed run starts only on an idle machine (#217): a busy one made the #205 re-run's cold lists 30-70% slower.
BUSY_LOAD = 1.0  # the 1-minute load average at or above which the machine is busy


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


def image_state(label, head, inputs_changed):
    """Whether the test image holds the code of the commit `head`, given the commit its label names.

    'current': it does (same commit, or no build input changed in between); 'stale': a build input changed since the image's
    commit; 'unknown': git cannot compare the two (the repository does not have the image's commit); 'missing': no image, or
    no label on it. `inputs_changed(commit)` answers True, False or None and is only asked when the two commits differ.
    """
    if not label:
        return 'missing'
    if label == head:
        return 'current'
    return {False: 'current', True: 'stale'}.get(inputs_changed(label), 'unknown')


def load_expected_settings(path=EXPECTED_SETTINGS_FILE):
    """The entries of the expected settings file: [{'copies': [side, ...], 'settings': {setting name: value}}].
    ValueError with a plain reason when the file or one of its entries cannot be used."""
    name = os.path.basename(path)
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f'{name} cannot be read: {type(e).__name__}') from None
    entries = data.get('expected') if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f'{name} cannot be read: it has no "expected" list')
    for i, entry in enumerate(entries, 1):
        copies, wanted = (entry.get('copies'), entry.get('settings')) if isinstance(entry, dict) else (None, None)
        unknown_copy = next((c for c in copies if not isinstance(c, str) or c not in testbed.SETTINGS), None) if isinstance(copies, list) else None
        # the file is in the repository: the settings reader's own test for a secret name keeps keys and logins out of it
        secret = next((k for k, v in br.flatten(wanted).items() if v == '***'), None) if isinstance(wanted, dict) else None
        if not isinstance(copies, list) or not copies:
            why = 'it names no copies'
        elif unknown_copy is not None:
            why = f'"{unknown_copy}" is not a test copy ({_list(testbed.SETTINGS_SIDES)})'
        elif not isinstance(wanted, dict) or not wanted:
            why = 'it names no settings'
        elif secret:
            why = f'{secret} is a key, a login or a password, which does not belong in this file'
        else:
            continue
        raise ValueError(f'{name}, entry {i}: {why}')
    return entries


def _settings_at(flat, name):
    """The settings at or below `name` in a flat settings map. A list of plain values (an order such as `sortOrder`, which the
    map holds as sortOrder[0], sortOrder[1], ...) is one setting, with the list as its value."""
    out = {}
    for k, v in flat.items():
        if k != name and not k.startswith((name + '.', name + '[')):
            continue
        entry = re.fullmatch(r'(.+)\[(\d+)\]', k)
        if entry and len(entry.group(1)) >= len(name):
            out.setdefault(entry.group(1), {})[int(entry.group(2))] = v
        else:
            out[k] = [] if v == '[]' else v  # the map's way of writing an empty list
    return {k: [v[i] for i in sorted(v)] if isinstance(v, dict) else v for k, v in out.items()}


EMPTY = ([], '{}')  # how a settings map writes an empty list or section


def _holds_nothing(settings):
    """True when a level of a settings map has no setting, or only an empty list or section (`custom_formats: []`)."""
    return all(v in EMPTY for v in settings.values())


def _whole_gap(key, name, other):
    """The highest level of the setting `key`, from `name` down, that `other` has nothing of: a section or a rule that is
    missing as a whole is named once, not once per value in it. a.b[c].d is tried as a, a.b, a.b[c], a.b[c].d."""
    ends = [m.end() for m in re.finditer(r'\[.*?\](?=[.\[]|$)|[^.\[]+', key)]
    return next((key[:e] for e in ends if e >= len(name) and _holds_nothing(_settings_at(other, key[:e]))), key)


# The copies whose config is YAML (AltMount's config.yaml), read by br.flatten_yaml: every value as text, list entries by position.
YAML_COPIES = testbed.YAML_CONFIGS


def _as_yaml_read(value, prefix):
    """An expected value as br.flatten_yaml reads the same setting from AltMount's config.yaml: list entries tagged by position
    ([0], [1], ...), numbers, true, false and null as text, `key: ""` left out (the reader skips it), [] and {} for empty ones."""
    out = {}
    if isinstance(value, (dict, list)):
        items = value.items() if isinstance(value, dict) else ((f'[{i}]', v) for i, v in enumerate(value))
        for k, v in items:
            out.update(_as_yaml_read(v, prefix + k if k.startswith('[') else f'{prefix}.{k}'))
        if not value:
            out[prefix] = '[]' if isinstance(value, list) else '{}'
    elif value != '':
        out[prefix] = value if isinstance(value, str) else json.dumps(value)
    return out


def _show(value):
    return json.dumps(value, ensure_ascii=False)


def setting_differences(expected, settings, file=None):
    """One sentence per setting of a test copy that differs from the expected settings; [] when every copy matches.

    expected: the entries of the expected settings file (load_expected_settings). settings: {side: {dotted name: value}}, as
    the settings reader gives them (testbed.read_settings). file: where the expected settings file is, for the first
    sentence, which also says what to do (the others stay short).
    """
    out = []

    def say(start, end):
        first = not out
        out.append(f"{start} the expected settings file{f' ({file})' if first and file else ''} {end}"
                   + (": change the test copy's config, or the file if the copy's value is the intended one." if first else '.'))

    for entry in expected:
        for side in entry['copies']:
            copy_name, have = testbed.SETTINGS[side]['short'], settings.get(side) or {}
            if not have or '(file missing)' in have:  # a config that cannot be read: the other preflight checks say so
                continue
            for name, value in entry['settings'].items():
                flat = _as_yaml_read(value, name) if side in YAML_COPIES else br.flatten(value, name)
                want, got = _settings_at(flat, name), _settings_at(have, name)
                gaps = []  # a setting, a rule or a section one of the two lacks as a whole, each named once
                for k in want:
                    if k not in got:
                        gap = (_whole_gap(k, name, got), 'missing')
                        if gap not in gaps:
                            gaps.append(gap)
                            say(f'{copy_name} has no {gap[0]} setting, but', 'has one')
                    elif got[k] != want[k] and isinstance(got[k], list) and isinstance(want[k], list):
                        copy_list, expected_list = got[k], want[k]
                        n = next((i for i, (a, b) in enumerate(zip(copy_list, expected_list)) if a != b), min(len(copy_list), len(expected_list)))
                        if n >= len(copy_list):
                            say(f'{copy_name} has no {k} entry {n + 1}, but', f'says {_show(expected_list[n])}')
                        elif n >= len(expected_list):
                            say(f'{copy_name} has {k} entry {n + 1} set to {_show(copy_list[n])}, but', f'has no entry {n + 1}')
                        else:
                            say(f'{copy_name} has {k} entry {n + 1} set to {_show(copy_list[n])}, but',
                                f'says {_show(expected_list[n])} (the first entry that differs)')
                    elif got[k] != want[k]:
                        say(f'{copy_name} has {k} set to {_show(got[k])}, but', f'says {_show(want[k])}')
                for k in got:
                    if got[k] in EMPTY and _settings_at(want, k):  # an empty list where the file has entries: named once above
                        continue
                    gap = (_whole_gap(k, name, want), 'extra')
                    if k not in want and gap not in gaps:
                        gaps.append(gap)
                        say(f'{copy_name} has a {gap[0]} setting that', 'does not have')
    return out


def preflight(mode, cfg, io):
    """Checks the setup before a record ('record') or a run ('run'). Returns plain sentences, one per problem; [] means go.

    Record only: the key file. Run only: the recording exists. Everything else is checked in both.
    """
    if mode not in ('record', 'run'):
        raise ValueError("preflight mode must be 'record' or 'run'")
    problems = []
    port = cfg.get('standin_port', 1340)

    # 1. the test image holds the code of the commit being tested
    commit, dirty = io.git_info()
    label = io.image_label()
    if dirty:
        problems.append('The repository has uncommitted changes, so the test image cannot name the code that runs: commit them first.')
    else:
        state = image_state(label, commit, io.build_inputs_changed)
        if cfg.get('rebuild_image') and state != 'current':
            io.rebuild_image(commit)
            label = io.image_label()
            state = image_state(label, commit, io.build_inputs_changed)
        if state == 'missing':
            problems.append(f'The test image {IMAGE} is missing or does not say which commit it was built from: build it again with --rebuild-image.')
        elif state == 'stale':
            problems.append(f'The test image was built from commit {label[:7]}, and the code that goes into the image has changed '
                            f'since then (the repository is at {commit[:7]}): build it again with --rebuild-image.')
        elif state == 'unknown':
            problems.append(f'The test image was built from commit {label[:7]}, which this repository does not have, so nothing says '
                            f'whether it holds the code at {commit[:7]}: build it again with --rebuild-image.')

    rep = io.setup_report(cfg.get('limit', testbed.PROVIDER_LIMIT))
    titles = {side: v['short'] for side, v in testbed.SETTINGS.items()}
    indexer_sides = testbed.SETTINGS_SIDES
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

    # 5. every test copy has the sort and filter settings of the expected settings file
    path = cfg.get('expected_settings') or EXPECTED_SETTINGS_FILE
    shown = os.path.relpath(path, REPO) if os.path.abspath(path).startswith(REPO + os.sep) else path
    try:
        problems += setting_differences(load_expected_settings(path), rep['settings'], shown)
    except ValueError as e:
        problems.append(f'The expected settings file cannot be used ({e}): fix the file.')

    # 6. the stand-in's port is free
    if not io.port_free(port):
        problems.append(f"The indexer stand-in's port {port} is already in use: stop whatever listens there (an earlier indexer stand-in?) and try again.")

    # 7. (run only) the machine is idle (#217)
    if mode == 'run':
        load = io.load_average()
        if load >= BUSY_LOAD:
            problems.append(f'The machine is busy: its 1-minute load average is {load:.2f}, at or above {BUSY_LOAD:.2f}, which slows a timed '
                            'run: stop what keeps it busy (other agents, test suites, builds) and wait until it is idle.')

    # 8. (run only) the recording exists and holds an answer for every enabled indexer
    if mode == 'run':
        have = io.recording()
        need = sorted({slug for s in readable for slug in rep['enabled'][s]})
        state = io.recording_state()
        top_up = cfg.get('topup_command') or 'the record command with the same title list'
        if not have:
            problems.append(f"There is no recording for the title list '{cfg.get('listname')}' in {cfg.get('store')}: run the record command first.")
        elif not state:
            problems.append(f"The recording for '{cfg.get('listname')}' does not say whether it is complete: top it up with the record command: {top_up}")
        elif state.get('state') == 'incomplete':
            problems.append(f"The recording for '{cfg.get('listname')}' is incomplete: {state.get('why') or 'the proof replay missed answers'}. "
                            f"Top it up with the record command: {top_up}")
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
    if mode == 'record' and cfg.get('runs_root'):  # the allowance: warns only, never blocks
        print('\n'.join(allowance.record_preflight_lines(cfg)))
    if not problems:
        print(f'Setup is right for a {mode}: image, indexers, addresses, connection caps, sort and filter settings and port all check out.')
    return 1 if problems else 0


# --------------------------------------------------------------------------- the run

def title_lists(titles):
    """{label: list} of a tagged title list (#165's [type, id, label, list], list 'easy' or 'hard'); None for a list
    without tags, whose run folder keeps no list (#167)."""
    lists = {t[2]: t[3] for t in titles if len(t) > 3}
    return lists or None


def partial_titles(titles, titles_file):
    """Whether a run plays part of the built-in title list (a short run): a --titles-file that leaves out one of its
    titles. A tagged title list is a speed test's whole list of new titles (#165), never a part."""
    return bool(titles_file) and not title_lists(titles) and not {t[2] for t in common.TITLES} <= {t[2] for t in titles}


def collect_visit(cfg, io, side, phase, rnd, title, logbuf):
    kind, vid, label = title[:3]
    kf_c, be_c = KF_CONTAINER, ALTMOUNT_CONTAINER
    t0 = io.now()
    http = io.visit_http(side, kind, vid, cfg['tries'], browse_pause_s=cfg['browse_pause'])
    t1 = io.now()
    since = br.iso(t0 - datetime.timedelta(seconds=1))
    lo, hi = t0 - datetime.timedelta(seconds=1), t1 + datetime.timedelta(seconds=GRACE_S)
    kf_text = io.logs(kf_c, since)
    be_text = io.logs(be_c, since)
    for c, text in ((kf_c, kf_text), (be_c, be_text)):
        logbuf.setdefault(c, []).append(f'--- {side} {phase} {rnd} {label} {br.iso(t0)}\n{br.scrub_text(text)}')
    # provisional; finalize_steps() re-attributes once the whole run is read (late lines, next visit of the side)
    played = br.played_source(kf_text)
    steps = br.attribute_steps({'id': vid, 't_start': br.iso(t0), 'tries': http.get('tries', []), 'played_source': played},
                               br.parse_step_lines(kf_text))
    imports = [i for i in br.altmount_imports(be_text) if lo <= br.parse_ts(i['start']) <= hi]
    limit = br.limit_event(kf_text + '\n' + be_text, cfg['indexers'])
    ok = bool(http.get('first_try_plays'))
    return {'side': side, 'phase': phase, 'round': rnd, 'title': label, 'id': vid, 'kind': kind, 'ok': ok,
            't_start': br.iso(t0), 't_end': br.iso(t1), 'list_status': http.get('list_status'),
            'list_s': http.get('list_s'), 'sources': http.get('sources'), 'start_s': http.get('start_s'),
            'seeks': http.get('seeks', {}), 'note': http.get('note'), 'tries': http.get('tries', []),
            'browse_pause_s': http.get('browse_pause_s', 0),
            'steps': steps, 'imports': imports, 'limit': limit, 'played_source': played,
            'cause': '' if ok else br.failure_cause(kf_text), **({'list': title[3]} if len(title) > 3 else {})}


def finalize_steps(io, visits):
    """Attribute every KaijuFlow step line to a visit, from the container's whole log.

    Search-side lines go by `ref` to the visit of that title until the next visit that used the same KaijuFlow container
    starts (no fixed cut-off, so a late health_batch is kept); prepare-side lines go to the Source that was played.
    """
    by_container = {}
    for v in visits:
        by_container.setdefault(KF_CONTAINER, []).append(v)
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


def planned_plays(cfg, rounds):
    """How many plays a command makes when nothing stops it: every title on every planned side in every round."""
    return len(rounds) * len(cfg['titles']) * len(run_sides(cfg))


def line_prefix(io, done, planned, proof=False):
    """How every line starts that a run or a record prints while it plays: the UTC time and the plays done out of those
    planned (`05:46:35 [61/160]`), so the last line of the log says how far the command is. The proof of a record counts
    on its own and says `proof`."""
    return f"{io.now():%H:%M:%S} [{done}/{planned}]{' proof' if proof else ''}"


def progress_log(io, done, planned, proof=False):
    """A log function for what happens between two plays (a reset): its lines start the way the play lines do."""
    return lambda msg: print(f'{line_prefix(io, done, planned, proof)} {msg}', flush=True)


@contextlib.contextmanager
def clocked(io, rows, **what):
    """Times one stretch of a run (a pass, a round, a reset) by the io's clock. Its row is in `rows` from the start and gets
    its end and its seconds however the stretch ends, so a stretch cut short by Ctrl-C, the cap rule or an error is kept."""
    t0 = io.now()
    row = dict(what, start=br.iso(t0), end=None, seconds=None)
    rows.append(row)
    try:
        yield row
    finally:
        t1 = io.now()
        row.update(end=br.iso(t1), seconds=round((t1 - t0).total_seconds(), 3))


def do_pass(cfg, io, run, logbuf, name, sides, reset_sides, first_reset=None):
    """One pass: every side of `sides` through every title in each round of PLAN. Each cold round starts with a reset of
    `reset_sides`; `first_reset(io, log)` takes the place of the first one (the switch to one page, which resets too).
    The pass, each of its rounds and each of its resets are timed into run['timing'] (#112)."""
    timing = run['timing']
    run['stage'] = f'the pass of the {name}'
    with clocked(io, timing['passes'], name=name, sides=list(sides)):
        for n, (phase, rnd) in enumerate(run_plan(cfg)):
            round_key = {'pass': name, 'phase': phase, 'round': rnd}
            if phase == 'cold':
                log = progress_log(io, len(run['visits']), planned_plays(cfg, run_plan(cfg)))
                with clocked(io, timing['resets'], **round_key):
                    if first_reset and n == 0:
                        first_reset(io, log)
                    else:
                        io.reset(reset_sides, log)
                note_addresses(io, run)  # a container gets its address when it starts
            with clocked(io, timing['rounds'], **round_key, plays=0, pause_s=0.0) as round_row:
                do_round(cfg, io, run, logbuf, sides, phase, rnd, round_row)


def do_round(cfg, io, run, logbuf, sides, phase, rnd, round_row):
    """One round of a pass: every title on every side of `sides`, the first side rotating per title, a pause of
    cfg['settle'] seconds after each play. `round_row` counts the plays and adds up the pauses as the clock saw them."""
    for i, title in enumerate(cfg['titles']):
        k = i % len(sides)
        for side in sides[k:] + sides[:k]:
            run['playing'] = {'side': side, 'phase': phase, 'round': rnd, 'title': title[2]}
            v = collect_visit(cfg, io, side, phase, rnd, title, logbuf)
            run['visits'].append(v)
            run['playing'] = None
            round_row['plays'] += 1
            print(f"{line_prefix(io, len(run['visits']), planned_plays(cfg, run_plan(cfg)))} {side} {phase} {rnd} {title[2]}: "
                  f"{'plays' if v['ok'] else 'FAILS'} list {v['list_s']} s start {v['start_s']} s", flush=True)
            _check_cap(io, v, since=run['started_at'])
            paused = io.now()
            try:
                io.sleep(cfg['settle'])
            finally:  # a pause cut short by Ctrl-C counts for as long as it lasted
                round_row['pause_s'] = round(round_row['pause_s'] + (io.now() - paused).total_seconds(), 3)


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
           'error': None, 'recording': cfg['listname'], 'titles': [t[2] for t in cfg['titles']], 'indexers': list(cfg['indexers']),
           'sides': run_sides(cfg), 'rounds': cfg.get('rounds', 2), 'short': short_run(cfg), 'standin_misses': 0,
           'settings': {}, 'commit': None, 'head': None, 'dirty': None, 'topup_command': cfg.get('topup_command'),
           'started_at': started, 'addresses': {}, 'standin_unmatched': 0, 'browse_pause_s': cfg['browse_pause'],
           'facts': {'stand-in replay wait': 'on' if cfg.get('wait', True) else 'off', 'browse pause': br.pause_text(cfg['browse_pause']),
                     'one-page side': 'yes' if 'kaijuflow-1page' in run_sides(cfg) else 'no'},
           'timing': {'seconds': None, 'settle_s': cfg['settle'], 'passes': [], 'rounds': [], 'resets': []},
           'lists': title_lists(cfg['titles'])}
    wait = cfg.get('wait', True)
    logbuf, handle, failure, restore_signals = {}, None, None, lambda: None
    try:
        run['settings'] = io.snapshot()
        run['head'], run['dirty'] = io.git_info()  # the repository's commit; it differs from the image's after a docs-only commit
        run['commit'] = io.image_label()  # the commit the test image was built from: the code that runs
        _write(os.path.join(run_dir, 'settings.json'), json.dumps(run['settings'], indent=1, sort_keys=True))
        try:
            _check_cap(io, since=started)
            handle = io.start_standin(os.path.join(logs_dir, 'standin.log'), mode='replay', wait=wait)
            main_sides = [s for s in run_sides(cfg) if s in MAIN_SIDES]
            if main_sides:
                do_pass(cfg, io, run, logbuf, 'main sides', main_sides, ALL_TESTBED)
            if 'kaijuflow-1page' in run_sides(cfg):
                do_pass(cfg, io, run, logbuf, 'one-page side', ['kaijuflow-1page'], ALL_TESTBED,
                        first_reset=switch_to_one_page)
        except CapReached as e:
            run['status'] = 'null'
            run['null'] = {'indexer': e.indexer, 'time': e.time, 'where': e.where}
        except KeyboardInterrupt as e:  # Ctrl-C or SIGTERM: the pass stops, the plays that finished are kept, the ending is the normal one (#110)
            run['status'] = 'stopped'
            run['stopped'] = stop_note(io, e, run.get('stage'), len(run['visits']), planned_plays(cfg, run_plan(cfg)), run.get('playing'))
            restore_signals = finish_after_stop(run['stopped'], 'run', 'report.md, raw.json, meta.json and the INDEX.md row')
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
    try:
        write_run_ending(cfg, io, run, started, logbuf)
    finally:
        restore_signals()
    if failure:
        raise failure
    return run


def write_run_ending(cfg, io, run, started, logbuf):
    """The ending of every run, finished or not: its time, the logs, report.md, raw.json, meta.json and the INDEX.md row."""
    root, run_dir = cfg['runs_root'], run['dir']
    logs_dir = os.path.join(run_dir, 'logs')
    finished = io.now()
    run['finished'] = br.iso(finished)
    run['timing']['seconds'] = round((finished - started).total_seconds(), 3)
    run['timing']['parts'] = br.time_parts(run)
    sl = os.path.join(logs_dir, 'standin.log')
    if os.path.exists(sl):
        run['standin_misses'] = sum(1 for line in _read_text(sl).splitlines() if line.startswith('MISS '))
    for c, parts in logbuf.items():
        _write(os.path.join(logs_dir, c + '.log'), '\n'.join(parts) + '\n')
    prev = br.previous_run(root, exclude=os.path.basename(run_dir), usable=(lambda d: runcheck.check_run(d)[0]) if run['short'] else None)
    nulls = br.null_runs_between(root, prev['started'], exclude=os.path.basename(run_dir)) if prev and prev.get('started') else None
    if prev and run['short']:  # a short run is held against the last baseline, as far as it played
        run['changes'] = [f"Short run: compared with the last baseline, {prev['folder']}, limited to {run['short']}."] + \
            br.diff_runs(br.limit_to_played(prev, run), run, nulls)
    else:
        run['changes'] = br.diff_runs(prev, run, nulls)
    if run['status'] == 'ok':
        report, result, headline = br.render_report(run, run['changes']), 'ok', br.headline(run)
    elif run['status'] == 'null':
        report, result = br.render_null_report(run), 'NULL'
        headline = f"NULL: {run['null']['indexer']} limit reached at {run['null']['time']}; no numbers"
    elif run['status'] == 'stopped':
        report, result, headline = br.render_stopped_report(run, run['changes']), 'stopped', br.stopped_text(run['stopped'])
    else:
        report, result, headline = f"This run failed before it finished: {run['error']}\n", 'failed', f"failed: {run['error']}"
    if run['short']:
        report = f"Short run, not a baseline: {run['short']}.\n\n{report}"
        result = f"short: {run['short']}" if result == 'ok' else f"{result} (short: {run['short']})"
    _write(os.path.join(run_dir, 'report.md'), report)
    _write(os.path.join(run_dir, 'raw.json'), json.dumps({'status': run['status'], 'visits': run['visits']}, indent=1))
    meta = {k: run.get(k) for k in ('name', 'status', 'started', 'finished', 'commit', 'head', 'dirty', 'recording', 'titles', 'indexers',
                                    'sides', 'rounds', 'short', 'settings', 'facts', 'addresses', 'standin_unmatched', 'null', 'stopped', 'error',
                                    'standin_misses', 'changes', 'timing', 'browse_pause_s')}
    if run.get('lists'):  # a run on a tagged title list (#167); a run without tags keeps its meta.json as before
        meta['lists'] = run['lists']
    _write(os.path.join(run_dir, 'meta.json'), json.dumps(meta, indent=1, sort_keys=True))
    br.append_index_row(os.path.join(root, 'INDEX.md'), {
        'date': run['started'], 'name': cfg['name'], 'result': result, 'changed': run['changes'],
        'headline': headline, 'folder': os.path.basename(run_dir)})


# --------------------------------------------------------------------------- the record command (spec #72, ticket #75)

def record_all(cfg, io):
    """Preflight, reset, stand-in in record mode, every side through every title in a cold round and then a warm round
    (no reset between, so the warm round's own requests, such as health-check replacements, are stored too), reset again.

    Running it again is a top-up: record mode serves what is stored instead of asking the indexer. The first "limit reached"
    stops the pass and the recording is NULL (what was stored stays). Nothing from the pass is a measurement: it gets a folder
    with the stand-in's log and a meta.json, and an INDEX.md row only when it is NULL, stopped or failed. Ctrl-C in the pass
    or in the proof ends it the normal way with status `stopped` (#110).
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
           'error': None, 'titles': [t[2] for t in cfg['titles']], 'sides': planned_sides(cfg),
           'commit': None, 'new_answers': 0, 'stored_answers': 0, 'errors': 0, 'visits': 0,
           'listed': {side: 0 for side in planned_sides(cfg)}, 'rounds': list(RECORD_ROUNDS), 'misses': []}
    if title_lists(cfg['titles']):  # a recording of a tagged title list (#167) keeps each title's list
        rec['lists'] = title_lists(cfg['titles'])
    handle, failure, restore_signals = None, None, lambda: None
    planned = planned_plays(cfg, RECORD_ROUNDS)
    stage, counts = 'the record pass', rec  # the proof counts its plays on its own
    proof = {'visits': 0, 'listed': {side: 0 for side in planned_sides(cfg)}}
    try:
        rec['commit'] = io.image_label()
        try:
            try:  # the opening reset and the stand-in's start are inside, so a stop there ends the normal way too
                io.reset(ALL_TESTBED, progress_log(io, 0, planned))
                handle = io.start_standin(logpath, mode='record')
                record_pass(cfg, io, rec, list(MAIN_SIDES))
                if cfg['one_page']:
                    switch_to_one_page(io, progress_log(io, rec['visits'], planned))
                    record_pass(cfg, io, rec, ['kaijuflow-1page'])
            except CapReached as e:
                rec['status'] = 'null'
                rec['null'] = {'indexer': e.indexer, 'time': e.time, 'where': e.where}
            finally:
                try:
                    if handle:
                        handle.stop()
                finally:
                    io.restore_config()
            if rec['status'] == 'recorded':
                stage, counts = 'the proof replay', proof
                rec['misses'] = prove_recording(cfg, io, os.path.join(logs_dir, 'standin-proof.log'), proof)
        except KeyboardInterrupt as e:  # Ctrl-C or SIGTERM in the pass or the proof: what was stored is kept, the ending is the normal one (#110)
            rec['status'] = 'stopped'
            rec['stopped'] = stop_note(io, e, stage, counts['visits'], planned, counts.get('playing'))
            restore_signals = finish_after_stop(rec['stopped'], 'record command', 'RECORDING.json, meta.json and the INDEX.md row')
        finally:  # the cleanup runs even when stopping the stand-in fails
            io.reset(ALL_TESTBED, progress_log(io, rec['visits'], planned))
            io.stop_all()
    except Exception as e:  # noqa: BLE001
        rec['status'], rec['error'] = 'failed', br.scrub_text(f'{type(e).__name__}: {e}')
        failure = e
    try:
        write_record_ending(cfg, io, rec, logpath)
    finally:
        restore_signals()
    if failure:
        raise failure
    return rec


def write_record_ending(cfg, io, rec, logpath):
    """The ending of every record command, finished or not: the counts from the stand-in's log, RECORDING.json, meta.json
    and, unless it is complete, the INDEX.md row."""
    root, run_dir = cfg['runs_root'], rec['dir']
    rec.pop('playing', None)
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
    elif rec['status'] == 'stopped':
        br.append_index_row(os.path.join(root, 'INDEX.md'), {
            'date': rec['started'], 'name': cfg['name'] + ' (record)', 'result': 'stopped',
            'changed': ['recording stopped; what was stored is kept, run the same record command again'],
            'headline': f"{br.stopped_text(rec['stopped'])}; no numbers",
            'folder': os.path.basename(run_dir)})
    elif rec['status'] == 'failed':
        br.append_index_row(os.path.join(root, 'INDEX.md'), {
            'date': rec['started'], 'name': cfg['name'] + ' (record)', 'result': 'failed', 'changed': ['record pass'],
            'headline': f"failed: {rec['error']}", 'folder': os.path.basename(run_dir)})


def write_recording_state(cfg, rec):
    """Writes the recording's state next to the list's answers: complete, or stopped early (why and when), and how many
    answers of this pass were errors (not stored). The preflight of a run reads it."""
    d = os.path.join(cfg['store'], cfg['listname'])
    os.makedirs(d, exist_ok=True)
    misses = rec.get('misses') or []
    if rec['status'] == 'recorded' and misses:
        first = '; '.join(f"{br.SIDE_NAMES.get(m['side'], m['side'])} asked {m['request']}" for m in misses[:3])
        state, why = 'incomplete', f"the proof replay missed {len(misses)} request{'' if len(misses) == 1 else 's'} ({first}{'; ...' if len(misses) > 3 else ''})"
    elif rec['status'] == 'recorded':
        state, why = 'complete', None
    elif rec['status'] == 'null':
        state, why = 'stopped', f"{rec['null']['indexer']} said its limit was reached"
    elif rec['status'] == 'stopped':
        state, why = 'stopped', f"the record command was {br.stopped_text(rec['stopped'])}"
    else:
        state, why = 'stopped', rec.get('error') or 'the record pass failed'
    _write(os.path.join(d, RECORDING_FILE), json.dumps({'state': state, 'why': why, 'when': rec['finished'], 'errors': rec['errors'], 'misses': misses}, indent=1))


def record_summary(rec):
    """The sentence(s) the record command ends with."""
    text = f"Recorded {rec['new_answers']} new answers; {rec['stored_answers']} were already stored."
    n = rec.get('errors') or 0
    if n:
        text += (f" {n} answer{' was an error' if n == 1 else 's were errors'} and {'was' if n == 1 else 'were'} not stored: "
                 "run record again to top them up.")
    total = len(rec.get('titles') or [])
    for side, n in (rec.get('listed') or {}).items():
        if total and n < total:
            text += f" {br.SIDE_NAMES.get(side, side)} listed no Sources for {total - n} of {total} titles."
    misses = rec.get('misses') or []
    if misses:
        text += (f" The proof replay missed {len(misses)} request{'' if len(misses) == 1 else 's'}, so the recording is INCOMPLETE "
                 "and a run will refuse it: run the same record command again.")
    plays = rec.get('plays') or {}
    if plays:  # last: the top picks of the record pass that played, in check's words
        text += ' ' + br.top_picks_played([(side, plays[side]) for side in rec.get('sides') or plays if side in plays])
    return text


def prove_recording(cfg, io, logpath, counts=None):
    """The proof that ends a record pass: test copies reset, the stand-in in REPLAY mode with the wait off (no indexer is
    contacted), every side through the same cold round and warm round as the record pass. Returns the requests it could not
    answer, one {'side', 'request'} each (the side that was visiting when the stand-in logged the MISS), without repeats.
    `counts` ({'visits', 'listed'}, as record_pass keeps them) is where the proof counts its plays; record_all reads it when
    the proof is stopped."""
    planned = planned_plays(cfg, RECORD_ROUNDS)
    io.reset(ALL_TESTBED, progress_log(io, 0, planned, proof=True))
    handle = io.start_standin(logpath, mode='replay', wait=False)
    windows = []  # (index of the stand-in's first new log line, side) at the start of every visit

    class Watch:  # notes where each visit starts in the stand-in's log
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def visit_http(self, side, kind, vid, tries):
            windows.append((self.inner.standin_line_count(), side))
            return self.inner.visit_http(side, kind, vid, tries)

    watched = Watch(io)
    scratch = counts if counts is not None else {'visits': 0, 'listed': {side: 0 for side in planned_sides(cfg)}}
    try:
        record_pass(cfg, watched, scratch, list(MAIN_SIDES), proof=True)
        if cfg['one_page']:
            switch_to_one_page(io, progress_log(io, scratch['visits'], planned, proof=True))
            record_pass(cfg, watched, scratch, ['kaijuflow-1page'], proof=True)
        lines = io.standin_lines()
    finally:
        try:
            handle.stop()
        finally:
            io.restore_config()
    misses, seen = [], set()
    for i, line in enumerate(lines):
        if not line.startswith('MISS '):
            continue
        side = next((w[1] for w in reversed(windows) if w[0] <= i), 'unknown')
        request = br.scrub_text(re.sub(r'\s+from=\S+(\s+t=\d+)?$', '', line[5:]))
        if (side, request) not in seen:
            seen.add((side, request))
            misses.append({'side': side, 'request': request})
    return misses


def record_pass(cfg, io, rec, sides, proof=False):
    """A cold round, then a warm round with no reset between: in each, every side lists every title and plays its top pick,
    sides one after another, order rotating per title. `listed` counts the titles a side listed Sources for in any round,
    and `playing` names the play in progress (a record's rounds have no number). The proof replay makes the same rounds
    with its own count, and its play lines say `proof`."""
    _check_cap(io)
    listed = {side: set() for side in sides}
    played = rec.setdefault('plays', {})  # {side: {round: [top picks that played, plays]}}, for the command's last sentence
    try:
        for phase in RECORD_ROUNDS:
            for i, title in enumerate(cfg['titles']):
                k = i % len(sides)
                for side in sides[k:] + sides[:k]:
                    kind, vid, label = title[:3]
                    rec['playing'] = {'side': side, 'phase': phase, 'round': None, 'title': label}
                    http = io.visit_http(side, kind, vid, cfg['tries'])
                    rec['visits'] += 1
                    rec['playing'] = None
                    if http.get('sources'):
                        listed[side].add(vid)
                    count = played.setdefault(side, {}).setdefault(phase, [0, 0])
                    count[0] += 1 if http.get('first_try_plays') else 0
                    count[1] += 1
                    print(f"{line_prefix(io, rec['visits'], planned_plays(cfg, RECORD_ROUNDS), proof)} "
                          f"{side} {phase} {label}: {http.get('sources')} Sources, top pick "
                          f"{'plays' if http.get('first_try_plays') else 'does not play'}", flush=True)
                    _check_cap(io)
                    io.sleep(cfg['settle'])
    finally:
        for side, got in listed.items():
            rec['listed'][side] = len(got)


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
    """One plain sentence on whether the sides arrive with their own addresses. Sides that share a test container (the
    one-page side uses KaijuFlow's) may share its address; two containers may not."""
    addrs = [tuple(r['came_from']) for r in results.values()]
    owners = {}
    for side, r in results.items():
        for ip in r['came_from']:
            owners.setdefault(ip, set()).add(r.get('container') or side)
    if all(r['matched'] for r in results.values()) and all(len(c) == 1 for c in owners.values()):
        return 'Every side reached the indexer stand-in from its own address, and each address matched what docker inspect gave.'
    if not any(addrs):
        return 'No side reached the indexer stand-in: nothing can be said about addresses.'
    return ('The sides do not all arrive with their own matching address: the runner must rely on the time window alone '
            'for the sides that did not match.')


def smoke(cfg, io=None):
    """One search per planned side (the run's side list, the one-page side included when asked for) against the stand-in
    on an EMPTY store (every request a MISS); prints which side reached it, from which address, and whether that matches the
    address docker inspect gives for the side's test container. The one-page side is switched on with the same step as in
    a run and switched off again at the end (KaijuFlow's test copy is left stopped then)."""
    store = cfg['store']
    if os.path.isdir(store) and os.listdir(store):
        sys.exit('smoke needs an EMPTY store folder so that every request is a MISS and nothing can be read from Usenet')
    os.makedirs(store, exist_ok=True)
    io = io or RealIO(cfg)
    log = os.path.join(store, '..', os.path.basename(store.rstrip('/')) + '.smoke.log')
    handle = io.start_standin(log)
    results, switched = {}, False
    try:
        addresses = io.addresses()
        for side in planned_sides(cfg):
            if side == 'kaijuflow-1page':
                switched = True
                switch_to_one_page(io)
                addresses = io.addresses()  # a container started again can get a new address
            before = len(io.standin_lines())
            http = io.visit_http(side, 'movie', os.environ.get('SMOKE_IMDB', 'tt0133093'), 0)
            io.sleep(1)
            new = [x for x in io.standin_lines()[before:] if x.startswith('MISS ')]
            container = KF_CONTAINER
            results[side] = dict(http=http.get('list_status'), container=container,
                                 **smoke_side_result(new, addresses.get(container)))
    finally:
        try:
            if switched:
                io.restore_config()
        finally:
            handle.stop()
    print(json.dumps(results, indent=1))
    print(smoke_verdict(results))
    return results


RECORD_EXIT_CODES = """exit codes of the record command:
  0  complete: every side was recorded and the proof replay (no indexer contacted) answered every request. A run may use it.
  1  nothing recorded: the setup check failed (the sentences say why) or the pass broke.
  2  stopped: an indexer said its limit was reached. What was stored is kept; run the same command again after the indexer reset.
  3  incomplete: the proof replay missed some requests (listed). Not an error: run the same record command again to top up.
  130  stopped by Ctrl-C or SIGTERM (what `timeout` sends). What was stored is kept; run the same command again. The run
       command uses 130 the same way: its folder keeps the plays that finished, and its report and INDEX.md row say stopped."""


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=RECORD_EXIT_CODES)
    ap.add_argument('cmd', choices=['run', 'record', 'smoke', 'preflight', 'check', 'usage'])
    ap.add_argument('--run', dest='run_dir', help='check only: the run folder to check; exits non-zero when it cannot serve as a baseline')
    ap.add_argument('--no-wait', action='store_true', help='run only: replay indexer answers at once instead of waiting the recorded indexer time')
    ap.add_argument('--for', dest='mode', choices=['run', 'record'], default='run', help='preflight only: check the setup for a run or for a record pass')
    ap.add_argument('--name', default='run')
    ap.add_argument('--runs-root', default=DEFAULT_RUNS_ROOT)
    ap.add_argument('--store')
    ap.add_argument('--list', dest='listname')
    ap.add_argument('--rebuild-image', action='store_true', help='build kaijuflow:test again from the current commit when the code that goes into the image has changed since it was built')
    ap.add_argument('--provider-limit', type=int, default=testbed.PROVIDER_LIMIT)
    ap.add_argument('--key-file')
    ap.add_argument('--test-dir', default=os.environ.get('TEST_DIR', DEFAULT_TEST_DIR))
    ap.add_argument('--user-id')
    ap.add_argument('--one-page', action='store_true', help='add the fourth side: KaijuFlow, one page per indexer')
    ap.add_argument('--sides', help='run only: play only these sides, comma-separated: ' + ', '.join(ALL_SIDES) + ' (a short run)')
    ap.add_argument('--rounds', type=int, help='run only: 1 plays cold 1 and warm 1 only, 2 (the default) the full plan (a short run)')
    ap.add_argument('--quick', action='store_true', help='run only: shorthand for --sides kaijuflow --rounds 1 (a short run; does not imply --no-wait)')
    ap.add_argument('--titles-file')
    ap.add_argument('--tries', type=int, default=1)
    ap.add_argument('--settle', type=float, default=3, help='seconds to pause after every play (default 3)')
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


def run_selection(a):
    """(sides or None, rounds) from the run's selectors, or a sentence that says what is wrong with them."""
    if a.cmd != 'run':
        if a.sides is not None or a.rounds is not None or a.quick:
            return None, 2, '--sides, --rounds and --quick are only for run'
        return None, 2, None
    if a.quick and (a.sides is not None or a.rounds is not None):
        return None, 2, '--quick is --sides kaijuflow --rounds 1 and cannot be combined with --sides or --rounds'
    if a.quick:
        return ['kaijuflow'], 1, None
    if a.one_page and a.sides is not None:
        return None, 2, '--one-page cannot be combined with --sides (name kaijuflow-1page in --sides instead)'
    if a.rounds not in (None, 1, 2):
        return None, 2, f'--rounds must be 1 or 2, not {a.rounds}'
    sides = None
    if a.sides is not None:
        sides = [x.strip() for x in a.sides.split(',') if x.strip()]
        unknown = [x for x in sides if x not in ALL_SIDES]
        if unknown or not sides:
            return None, 2, (f"unknown side {', '.join(unknown)} in --sides (use {', '.join(ALL_SIDES)})" if unknown else '--sides names no side')
    return sides, a.rounds or 2, None


def main(argv):
    ap = build_parser()
    a = ap.parse_args(argv)
    sides, rounds, problem = run_selection(a)
    if problem:
        ap.error(problem)
    if a.cmd == 'check':
        if not a.run_dir:
            ap.error('--run is needed')
        return runcheck.check_command(a.run_dir)
    if a.cmd not in ('preflight', 'usage') or (a.cmd == 'preflight' and a.mode == 'run'):
        if not a.store or not a.listname:
            ap.error('--store and --list are needed')
    td = a.test_dir
    users = (_read_json(os.path.join(td, 'config/users.json')) or {}).get('users') or [{}]
    titles = [tuple(t) for t in _read_json(a.titles_file)] if a.titles_file else common.TITLES
    listdir = os.path.join(a.store or '', a.listname or '')
    cfg = dict(name=a.name, runs_root=a.runs_root, store=a.store, listname=a.listname, test_dir=td,
               user_id=a.user_id or ((users[0].get('manifests') or [{}])[0].get('id') or users[0].get('id', '')),
               one_page=a.one_page, sides=sides, rounds=rounds, titles=titles,
               partial_titles=partial_titles(titles, a.titles_file), tries=a.tries, settle=a.settle, browse_pause=BROWSE_PAUSE_S,
               indexers=sorted(d for d in os.listdir(listdir) if os.path.isdir(os.path.join(listdir, d))) if a.store and os.path.isdir(listdir) else [],
               rebuild_image=a.rebuild_image, limit=a.provider_limit, key_file=a.key_file, standin_port=testbed.STANDIN_PORT,
               wait=not a.no_wait, topup_command=topup_command(a))
    started = time.time()
    if a.cmd == 'usage':
        print('\n'.join(allowance.usage_lines(cfg)))
        return 0
    if a.cmd == 'preflight':
        return preflight_command(a.mode, cfg, RealIO(cfg))
    if a.cmd == 'smoke':
        smoke(cfg)
    elif a.cmd == 'record':
        try:
            with sigterm_stops():
                rec = record_all(cfg, RealIO(cfg))
        except PreflightFailed as e:
            for p in e.problems:
                print(p)
            return 1
        if rec['status'] == 'null':
            print(f"The recording stopped: {rec['null']['indexer']} said its limit was reached. What was stored is kept; "
                  f"once the indexer has reset, run the same command again to top up. Folder: {rec['dir']}")
            return EXIT_STOPPED
        if rec['status'] == 'stopped':
            print(f"The recording was {br.stopped_text(rec['stopped'])}. What was stored is kept; "
                  f"run the same command again to top up. Folder: {rec['dir']}")
            return EXIT_INTERRUPTED
        print(f"Folder: {rec['dir']}")
        print(record_summary(rec))
        if rec.get('misses'):
            for m in rec['misses'][:10]:
                print(f"  missed: {br.SIDE_NAMES.get(m['side'], m['side'])} asked {m['request']}")
            return EXIT_INCOMPLETE
    else:
        try:
            with sigterm_stops():
                run = run_all(cfg, RealIO(cfg))
        except PreflightFailed as e:
            for p in e.problems:
                print(p)
            return 1
        print(f"{run['status']}: {run['dir']}")
        runcheck.check_command(run['dir'], store=True)  # the same lines `check` prints, kept in the run folder as CHECK.txt
        if run['status'] == 'stopped':
            return EXIT_INTERRUPTED
    common.finish(started)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
