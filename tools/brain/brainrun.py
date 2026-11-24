"""Real-use checks on the test copies (spec #268, ADR 0010): the quick check, the Drill-down, their preflight and the allowance.

    python3 -I tools/brain/brainrun.py check --quick [--name quick-check] [--runs-root DIR] [--ledger FILE] [--key-file PATH]
           [--cases DIR] [--rebuild-image]   (the quick check, #270: 5 new titles, live, one cold press of Best each; exit 0 pass, 4 fail)
    python3 -I tools/brain/brainrun.py drill --title <imdb id> [--episode S01E02] [--entry ID ...] [--casebook DIR]
           [--cases DIR] [--tickets-dry-run] [--rebuild-image]   (the Drill-down, #272: one failed title again, as a quick
           check plays it; its suspected causes marked proved fixed or reopened, drill.py)
    python3 -I tools/brain/brainrun.py preflight [--rebuild-image] [--provider-limit 100] [--key-file PATH]
           (the setup check alone; a check starts with it)
    python3 -I tools/brain/brainrun.py usage   (the indexer allowance: used, limit and left per indexer)

A check starts the indexer stand-in in record mode on the check's own empty store, so every answer comes from the live
indexer and the cap rule and the allowance count it, resets the test copies with testbed.py, plays each title once (its
list, the Browse pause, one press of Best), reads KaijuFlow's [KF-STEP] lines and AltMount's imports from the test
containers' logs, and writes a check folder, one INDEX.md row and report.md (quickcheck.py). The first "limit reached"
from any indexer stops the check with no verdict. Ctrl-C or SIGTERM (what `timeout` sends) stops it too: the titles that
finished are kept, and a second stop is ignored until the ending is written. Only test containers are touched; secrets
never reach the check folder.

The replayed Recording's commands (run, record and its top-ups, smoke, preflight --for run|record, check --run) are
retired by ADR 0010 and archived (retired.py, archive/README.md): they stop unless run with --revive.
"""
import argparse
import contextlib
import datetime
import ipaddress
import json
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import allowance  # noqa: E402
import brainreport as br  # noqa: E402
import common  # noqa: E402
import draw  # noqa: E402
import drill  # noqa: E402
import caselog  # noqa: E402
import diagnosis  # noqa: E402
import evidence  # noqa: E402
import fixing  # noqa: E402
import nntp  # noqa: E402
import pool  # noqa: E402
import quickcheck  # noqa: E402
import retired  # noqa: E402
import testbed  # noqa: E402
from common import DEFAULT_TEST_DIR  # noqa: E402

DEFAULT_RUNS_ROOT = os.path.expanduser('~/kaijuflow-notes/brain-runs')
MAIN_SIDES = ['kaijuflow']  # one setup (#185): KaijuFlow with its AltMount copy; the other test copies stay stopped
ALL_TESTBED = ['altmount-kf', 'kaijuflow']  # the test copies a check resets: the setup's own
# every side's containers: KaijuFlow's, with the [KF-STEP] lines, and its AltMount's, whose log holds the imports
KF_CONTAINER, ALTMOUNT_CONTAINER = br.CLIENT_CONTAINER, 'altmount-kf-test'
GRACE_S = 5
BROWSE_PAUSE_S = 5  # the Browse pause of every run (#205): a viewer reading the page between the list and the play
EXIT_INTERRUPTED = 130  # a check: stopped by Ctrl-C or SIGTERM (130 is the shell's own code for Ctrl-C)


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

def _read_text(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def _key_path(cfg):
    """The key file: --key-file, else the test folder's indexers.json."""
    return cfg.get('key_file') or os.path.join(cfg['test_dir'], 'indexers.json')


def snapshot_settings(test_dir):
    """Settings of every side with secrets removed: {side: {dotted key: value}}; the settings command's reader (testbed.py)."""
    return testbed.read_settings(test_dir)


def is_best_entry(stream):
    """Whether a Stream of KaijuFlow's list is the Best entry on top (#190): it plays one of the Sources below it, so it is
    no Source itself. Told by its play address, /play/stream/ultimate-fallback."""
    return '/play/stream/ultimate-fallback' in str(stream.get('url', ''))


def read_list(got):
    """One common.get() of a side's list address read as a list: ({'list_status', 'list_s', 'note', 'sources'}, the
    Streams). A copy that did not answer, or answered with an error or bad JSON, has no Streams and a note saying why;
    `sources` leaves the Best entry out. A run's visit and a check's visit both read their list here."""
    st, h, body, t = got
    out = {'list_status': st, 'list_s': round(t.get('total', t['ready']), 2), 'note': None}
    try:
        streams = json.loads(body or b'{}').get('streams', []) if st == 200 else []
    except ValueError as e:
        streams, out['note'] = [], f'bad JSON: {e}'[:120]
    if st != 200:
        out['note'] = h.get('error') or f'HTTP {st}'
    out['sources'] = sum(1 for s in streams if not is_best_entry(s))
    return out, streams


# --------------------------------------------------------------------------- the real world

class RealIO:
    def __init__(self, cfg):
        self.cfg = cfg
        self.testbed = testbed
        self.repo = REPO

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

    def altmount_image(self):
        """{'image', 'id'} of AltMount's test copy as it runs (docker inspect, read-only), or None when it is not up."""
        r = subprocess.run(['docker', 'inspect', '-f', '{{.Config.Image}} {{.Image}}', ALTMOUNT_CONTAINER],
                           capture_output=True, text=True, timeout=60)
        parts = r.stdout.split()
        return {'image': parts[0], 'id': parts[1]} if r.returncode == 0 and len(parts) == 2 else None

    def rebuild_image(self, commit):
        build_image(commit, self.repo)


    def load_average(self):
        return os.getloadavg()[0]

    def power(self):
        return read_power()

    def cpu_policy(self):
        return read_cpu_policy()

    def cpu_probe_ms(self):
        return cpu_probe_ms()

    def machine_addresses(self):
        return read_machine_addresses()

    def pinned_addresses(self):
        return read_pinned(self.cfg['test_dir'])

    def dns_answer(self, name, server):
        return read_dns(name, server)

    def port_free(self, port):
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('0.0.0.0', port))
            except OSError:
                return False
        return True


    def preflight(self, mode, seen=None):
        return preflight(mode, self.cfg, self, seen)

    def marker(self):
        return br.read_json(os.path.join(self.cfg['store'], 'LIMIT_REACHED.json'))

    def start_standin(self, logpath, mode='replay', wait=True):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'indexer_standin.py')
        port = self.cfg.get('standin_port', 1340)
        self.standin_log = logpath
        log = open(logpath, 'w')
        cmd = [sys.executable, '-I', script, '--mode', mode, '--store', self.cfg['store'],
               '--list', self.cfg['listname'], '--port', str(port), '--bind', '0.0.0.0']
        if mode == 'record':
            cmd += ['--config', _key_path(self.cfg)]
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


    def check_visit(self, kind, vid, browse_pause_s):
        got = common.get(f'{list_base(self.cfg)}/stream/{kind}/{vid}.json', timeout=180, limit=0)
        return check_visit_answer(got, lambda s: common.play_stream(s, timeout=quickcheck.PLAY_TIMEOUT_S), browse_pause_s, self.sleep)

    def draw_titles(self, check, kinds):
        """New titles of the kinds from TMDB (draw.draw), written to the ledger before they are played."""
        today = self.now()
        titles = draw.draw(pool.tmdb_getter(self.cfg['test_dir']), draw.read_ledger(self.cfg['ledger']), kinds,
                           random.Random(), today.date().isoformat(), say=lambda line: print(f'drawn {line}', flush=True))
        draw.add_to_ledger(self.cfg['ledger'], titles, check, today.isoformat(timespec='seconds'))
        return titles

    def drill_title(self, imdb, episode):
        """A Drill-down's title from TMDB, when no earlier evidence folder names it (#272)."""
        return drill.tmdb_title(pool.tmdb_getter(self.cfg['test_dir']), imdb, episode)

    def title_names(self, title):
        return quickcheck.tmdb_names(pool.tmdb_getter(self.cfg['test_dir']), title)

    def allowance_left(self):
        return allowance.left(self.cfg)

    def open_check_store(self, run_dir):
        """The check's own empty store for the stand-in, in the test folder; the stand-in and the cap rule read it from cfg."""
        path = os.path.join(self.cfg['test_dir'], CHECK_STORE_DIR, os.path.basename(run_dir))
        os.makedirs(path)
        self.cfg['store'], self.cfg['listname'] = path, CHECK_LIST

    def check_answers(self):
        """The folder of the check's stored answers (the stand-in's list in the check's own store), or None outside a check."""
        store = self.cfg.get('store') or ''
        if os.path.basename(os.path.dirname(store)) != CHECK_STORE_DIR:
            return None
        return os.path.join(store, self.cfg['listname'])

    def altmount_file(self, path):
        """The bytes of one of AltMount's failed NZBs, named by its container path (`/config/.nzbs/failed/<category>/<name>.nzb`,
        as its "Moved failed NZB" line names it), read from its test copy's config folder; None for any other path or a file
        that is gone (the one narrow exception to the guard, #280)."""
        rel = os.path.normpath(path)
        parts = rel.split(os.sep)
        if parts[:4] != ['', 'config', '.nzbs', 'failed'] or len(parts) < 5 or not rel.endswith('.nzb') or '..' in parts:
            return None
        full = os.path.join(self.cfg['test_dir'], 'altmount-kf', rel.lstrip(os.sep))
        root = os.path.realpath(os.path.join(self.cfg['test_dir'], 'altmount-kf', 'config', '.nzbs', 'failed'))
        if not os.path.realpath(full).startswith(root + os.sep):
            return None
        try:
            with open(full, 'rb') as f:
                return f.read()
        except OSError:
            return None

    def usenet(self):
        """The live Clues' one read-only connection to the test copy's AltMount provider (#284), opened at its first
        command."""
        return nntp.Usenet(login=nntp.provider(test_dir=self.cfg['test_dir']))

    def start_diagnosing_agent(self, cases, ids, run_dir):
        """The diagnosing agent on the check's open Case logs (#287): a herdr agent in the agents tab, else claude -p."""
        return caselog.start_agent(cases, ids, run_dir)

    def tracker(self):
        """The issue tracker a check files its fix tickets with (#288): this repo's GitHub Issues through gh."""
        return fixing.GitHub()

    def alert(self, line):
        """The owner told in one line, the usual alert (kf-alert returns at once; its voice runs detached)."""
        subprocess.run([os.path.expanduser('~/.local/bin/kf-alert'), line], timeout=30, check=False)

    def secret_values(self):
        """The test copies' secret values (key files, logins, keys), for scrubbing what a check keeps; never shown."""
        return testbed.secret_values(self.cfg['test_dir'])

    def close_check_store(self):
        store = self.cfg.get('store') or ''
        if os.path.basename(os.path.dirname(store)) == CHECK_STORE_DIR:
            shutil.rmtree(store, ignore_errors=True)

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


class LookupFailed(Exception):
    """A reader of the machine's own state (#217) got no answer; the message says how, to finish a sentence."""


def _ask(argv, run=None):
    """The output of a read-only command, or LookupFailed saying how it failed. `run` stands in for subprocess.run."""
    try:
        r = (run or subprocess.run)(argv, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise LookupFailed(f'{argv[0]} is not installed') from None
    except OSError as e:
        raise LookupFailed(f'{argv[0]} could not start: {e.strerror or e}') from None
    except subprocess.TimeoutExpired:
        raise LookupFailed(f'{argv[0]} gave no answer within 30 s') from None
    if r.returncode != 0:
        said = [line.strip() for line in f'{r.stdout or ""}\n{getattr(r, "stderr", "") or ""}'.splitlines() if line.strip()]
        raise LookupFailed(f'{argv[0]} stopped with exit code {r.returncode}' + (f': "{said[-1]}"' if said else ''))
    return r.stdout


def read_machine_addresses(run=None):
    """Every address this machine has now, on any interface, read with `ip -j addr show` (read-only), as ipaddress objects.
    LookupFailed when ip is missing, fails, or lists no address."""
    out = _ask(['ip', '-j', 'addr', 'show'], run)
    try:
        found = [_address(a.get('local')) for link in json.loads(out) for a in link.get('addr_info', [])]
    except (ValueError, TypeError, AttributeError):
        raise LookupFailed('ip -j addr show printed nothing readable') from None
    if not any(found):
        raise LookupFailed('ip -j addr show lists no address')
    return [a for a in found if a]


def read_dns(name, server, run=None):
    """The addresses `server` answers for `name`, read with `dig +short` (the CNAMEs it prints first are left out), as
    ipaddress objects; [] when the server has none. LookupFailed when dig is missing, fails or times out."""
    out = _ask(['dig', '+short', '+time=3', '+tries=2', name, '@' + server], run)
    return [a for a in map(_address, out.split()) if a]


def _sys_text(path):
    """The first line of a /sys file, stripped; None when it cannot be read."""
    try:
        with open(path) as f:
            return f.readline().strip()
    except OSError:
        return None


def read_power(root=None):
    """'battery' when the machine has a Mains supply (the AC adapter) and none of its Mains supplies is online, else 'ac' (#262).
    A machine with no Mains supply listed (a desktop) is 'ac'. A Mains supply whose `online` cannot be read counts as not online."""
    root = root or POWER_SUPPLY_ROOT
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return 'ac'
    mains = [n for n in names if _sys_text(os.path.join(root, n, 'type')) == 'Mains']
    if mains and not any(_sys_text(os.path.join(root, n, 'online')) == '1' for n in mains):
        return 'battery'
    return 'ac'


def read_cpu_policy(root=None):
    """The first CPU's frequency policy (#262): {'governor', 'energy_preference'}, each only when it can be read."""
    root, out = root or CPUFREQ_ROOT, {}
    for key, name in (('governor', 'scaling_governor'), ('energy_preference', 'energy_performance_preference')):
        value = _sys_text(os.path.join(root, name))
        if value:
            out[key] = value
    return out


def probe_work(rounds):
    """The CPU probe's work: `rounds` steps of integer arithmetic in one thread, the same every time."""
    x = 0
    for i in range(rounds):
        x = (x * 1103515245 + 12345 + i) & 0xFFFFFFFF
    return x


def cpu_probe_ms(rounds=None, clock=time.perf_counter, work=probe_work):
    """How long the CPU probe's fixed work took, in whole milliseconds (#262): about 1 s on Brain plugged in; more on a slower CPU."""
    start = clock()
    work(rounds or PROBE_ROUNDS)
    return round((clock() - start) * 1000)


def _env_value(path, key):
    """The value of `key` in a compose .env file (KEY=VALUE lines, quotes taken off); None when the file or the key is missing.
    Only that key is kept: the file holds secrets."""
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines:
        name, eq, value = line.strip().removeprefix('export ').partition('=')
        if eq and name.strip() == key:
            value = value.strip()
            return value[1:-1] if len(value) > 1 and value[0] == value[-1] and value[0] in '"\'' else value
    return None


def read_pinned(test_dir):
    """The two addresses the test setup pins (#217), and nothing else of the files they are in: `HOST_IP` from the test
    folder's .env, and the host of KaijuFlow's `altmountUrl` (its login, if any, left out). `altmount_url` says whether that
    URL is 'set', 'missing', or set but naming 'no host' (no http:// in front, say). `HOST_IP` and `altmount_host` are None
    when there is none."""
    url = (br.read_json(os.path.join(test_dir, 'config', 'config.json')) or {}).get('altmountUrl')
    try:
        host = urllib.parse.urlsplit(url).hostname if isinstance(url, str) else None
    except ValueError:
        host = None
    return {'HOST_IP': _env_value(os.path.join(test_dir, '.env'), 'HOST_IP') or None, 'altmount_host': host or None,
            'altmount_url': 'missing' if url in (None, '') else 'set' if host else 'no host'}


def _address(text):
    """`text` as an ipaddress object, so 2001:DB8::1 and 2001:db8:0::1 are one address; None when it is not an address."""
    try:
        return ipaddress.ip_address(text)
    except (ValueError, TypeError):
        return None


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


# A timed run starts only on an idle machine (#217): a busy one made the cold lists of #205's baseline with the Browse pause
# 30-70% slower.
BUSY_LOAD = 1.0  # the 1-minute load average at or above which the machine is busy
# An image build by this preflight loads the machine itself: the load check then waits up to this long for it to settle.
SETTLE_AFTER_BUILD_S, SETTLE_POLL_S = 180, 10
# A run on battery is slower (#249: the same code's warm lists 20-25% slower): a run or a record starts plugged in (#262).
POWER_SUPPLY_ROOT = '/sys/class/power_supply'
CPUFREQ_ROOT = '/sys/devices/system/cpu/cpu0/cpufreq'
# The CPU probe's fixed work (#262), run by a run's preflight after the load check: about 1 s on Brain, the same every run.
PROBE_ROUNDS = 12_000_000
# The router has answered Newshosting's name with a dead 10.x address (2026-11-17): every Usenet read then fails.
NEWS_HOST, ROUTER, SINKHOLE = 'news.newshosting.com', '192.168.4.1', ipaddress.ip_network('10.0.0.0/8')


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
    data = br.read_json(path)
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


def expand_names(name, flat):
    """A setting name of the expected settings file as the copy's settings name it: `indexers[*].timeout` is one
    name per entry the copy has (`indexers[NinjaCentral].timeout`, ...), so a rule holds for every indexer without
    the file naming one; any other name is itself."""
    if '[*]' not in name:
        return [name]
    head, _, tail = name.partition('[*]')
    found = re.compile(re.escape(head) + r'\[([^\]]+)\]')
    entries = sorted({m.group(1) for k in flat for m in [found.match(k)] if m})
    return [f'{head}[{e}]{tail}' for e in entries]


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
            for name, value in ((n, v) for wild, v in entry['settings'].items() for n in expand_names(wild, have)):
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


def preflight(mode, cfg, io, seen=None):
    """Checks the setup before a real-use check ('check', #270; a Drill-down too). Returns plain sentences, one per problem;
    [] means go.

    The modes 'record' and 'run' are the retired commands' (ADR 0010, #273), used only by the archive with --revive
    (archive/retired_run.py adds their recording checks): record and check check the key file (the stand-in asks the real
    indexers); run and check that the machine is idle; check only that the indexer allowance holds what the check may ask
    (allowance.left). Everything else is checked in all three.
    `seen`, when given, gets the readings the checks judged: 'load', and 'machine', the power state, the CPU policy and the
    CPU probe taken after the load check ({'power', 'governor', 'energy_preference', 'cpu_probe_ms'}, #262), so the check
    keeps what was judged.
    """
    if mode not in ('record', 'run', 'check'):
        raise ValueError("preflight mode must be 'record', 'run' or 'check'")
    problems, rebuilt = [], False
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
            rebuilt = True
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

    # 2. (record and check) the key file names exactly the indexers every test copy has switched on
    if mode in ('record', 'check'):
        path = _key_path(cfg)
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

    # 7. (run and check) the machine is idle (#217); after an image build by this preflight, once the build's own load has settled
    if mode in ('run', 'check'):
        load = io.load_average()
        if rebuilt and load >= BUSY_LOAD:
            print(f"Waiting up to {SETTLE_AFTER_BUILD_S // 60} minutes for the image build's load to settle (1-minute load average "
                  f'{load:.2f}).', flush=True)
            waited = 0
            while load >= BUSY_LOAD and waited < SETTLE_AFTER_BUILD_S:
                io.sleep(SETTLE_POLL_S)
                waited += SETTLE_POLL_S
                load = io.load_average()
        probe = io.cpu_probe_ms()  # once the load is judged, so an image build's own load has settled first (#262)
        if seen is not None:
            seen['load'] = load
        if load >= BUSY_LOAD:
            after = f' {SETTLE_AFTER_BUILD_S // 60} minutes after the image build' if rebuilt else ''
            problems.append(f'The machine is busy: its 1-minute load average is {load:.2f}{after}, at or above {BUSY_LOAD:.2f}, which slows '
                            'a timed run: stop what keeps it busy (other agents, test suites, builds) and wait until it is idle.')

    # 8. the pinned addresses are this machine's (#217): a stale altmountUrl made every play fail on 2026-11-20
    pinned, env = io.pinned_addresses(), os.path.join(cfg['test_dir'], '.env')
    try:
        mine, unread = io.machine_addresses(), None
    except LookupFailed as e:
        mine, unread = [], str(e)
        problems.append(f"This machine's addresses cannot be read ({unread}), so HOST_IP in {env} and KaijuFlow's altmountUrl cannot "
                        'be checked: check that ip -j addr show works.')
    others = [str(a) for a in mine if not a.is_loopback and not a.is_link_local]
    shown = _list(others) if others else 'only loopback and link-local ones'
    if not pinned['HOST_IP']:
        problems.append(f"The test folder's {env} has no HOST_IP: set it to this machine's address" + ('.' if unread else f' ({shown}).'))
    elif not unread and _address(pinned['HOST_IP']) not in mine:
        problems.append(f'HOST_IP in {env} is {pinned["HOST_IP"]}, which is not an address this machine has now ({shown}): '
                        'set it to the current one, then start the test copies again.')
    host = pinned['altmount_host']
    if pinned['altmount_url'] == 'missing':
        problems.append("KaijuFlow's config has no altmountUrl, so it cannot reach its AltMount: set it, with the owner's go.")
    elif pinned['altmount_url'] == 'no host':
        problems.append("KaijuFlow's altmountUrl names no host (it needs the form http://<address>:<port>), so it cannot reach its "
                        "AltMount: fix it, with the owner's go.")
    elif not unread and _address(host) and _address(host) not in mine:
        problems.append(f"KaijuFlow's altmountUrl points at {host}, which is not an address this machine has now ({shown}), so "
                        "every play would fail: change it to the current address, with the owner's go.")

    # 9. the router answers Newshosting's name with a real address, not its sinkhole (#217)
    try:
        answer, failed = io.dns_answer(NEWS_HOST, ROUTER), None
    except LookupFailed as e:
        answer, failed = [], str(e)
    sunk = [str(a) for a in answer if a in SINKHOLE]
    if failed:
        problems.append(f'The lookup of {NEWS_HOST} at the router ({ROUTER}) failed ({failed}), so nothing says the health check and '
                        f'AltMount can reach Usenet: run dig +short {NEWS_HOST} @{ROUTER} and fix what it shows.')
    elif not answer:
        problems.append(f'The router ({ROUTER}) gives no address for {NEWS_HOST}, so the health check and AltMount cannot reach '
                        f'Usenet: check the network (dig +short {NEWS_HOST} @{ROUTER}).')
    elif sunk:
        problems.append(f'The router ({ROUTER}) answers {NEWS_HOST} with {_list(sunk)}, its sinkhole, so every Usenet read would fail: '
                        f"fix the router's DNS until dig +short {NEWS_HOST} @{ROUTER} gives no 10.x address.")

    # 11. run and record: the machine is plugged in (#262): on battery the same code listed 20-25% slower (#249)
    power = io.power()
    if power == 'battery':
        problems.append(f'The machine runs on battery (no Mains supply in {POWER_SUPPLY_ROOT} is online), which slows the CPU and a '
                        'timed run with it: plug it in and run the preflight again.')
    if mode in ('run', 'check') and seen is not None:
        seen['machine'] = {'power': power, **io.cpu_policy(), 'cpu_probe_ms': probe}

    # 12. (check only, #270) every switched-on indexer has what the check may ask of it left in its daily allowance
    if mode == 'check':
        left, problem = io.allowance_left()
        want = quickcheck.need(cfg.get('check_titles') or sum(quickcheck.QUICK_KINDS.values()))
        if problem:
            problems.append(problem)  # the limits file is missing or wrong: the sentence says what to fill in
        else:
            # Every title is searched on every indexer, so each needs the check's searches; the Walk's grabs are shared
            # (at most 30 per title in all, from whichever indexer has the Source), so the indexers together must hold the
            # check's downloads (owner's pick on #286, 2026-11-24, when DrunkenSlug's 100 a day joined NinjaCentral).
            downloads = {}
            for slug in sorted({slug for s in readable for slug in rep['enabled'][s]}):
                have = left.get(allowance.norm(slug))
                if have is None:
                    problems.append(f'The limits file has no entry for {slug}, so its allowance cannot be checked: add one.')
                    continue
                downloads[slug] = have['download']
                for kind in allowance.KINDS:
                    if kind != 'download' and have[kind] < want[kind]:
                        problems.append(f'{slug} has {have[kind]} {allowance.KIND_NAMES[kind]} left today, and the check may need '
                                        f'{want[kind]}: wait for its reset (brainrun.py usage shows the allowance).')
            if downloads and sum(downloads.values()) < want['download']:
                name, each = allowance.KIND_NAMES['download'], ', '.join(f'{s} {n}' for s, n in downloads.items())
                if len(downloads) == 1:
                    problems.append(f'{next(iter(downloads))} has {sum(downloads.values())} {name} left today, and the check may need '
                                    f"{want['download']}: wait for its reset (brainrun.py usage shows the allowance).")
                else:
                    problems.append(f'The indexers have {sum(downloads.values())} {name} left today between them ({each}), and the '
                                    f"check may need {want['download']}: wait for a reset (brainrun.py usage shows the allowance).")
    return problems


def preflight_command(mode, cfg, io):
    """Prints the preflight result in plain sentences; exit code 0 when the setup is right, 1 otherwise."""
    seen = {}
    problems = preflight(mode, cfg, io, seen)
    for p in problems:
        print(p)
    if not problems:
        idle = f' and idle (1-minute load below {BUSY_LOAD:.2f})' if mode in ('run', 'check') else ''
        machine = (f'; the machine is plugged in{idle}, HOST_IP and altmountUrl are its addresses, {NEWS_HOST} resolves outside 10.x'
                   + {'check': " and the indexer allowance holds the check's requests"}.get(mode, ''))
        print(f'Setup is right for a {mode}: image, indexers, addresses, connection caps, sort and filter settings and port all check out{machine}.')
        if 'machine' in seen:
            print(f"CPU probe: {br.probe_text(seen['machine'])}.")
    return 1 if problems else 0


# --------------------------------------------------------------------------- what every check shares


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


def line_prefix(io, done, planned, proof=False):
    """How every line starts that a run or a record prints while it plays: the UTC time and the plays done out of those
    planned (`05:46:35 [61/160]`), so the last line of the log says how far the command is. The proof of a record counts
    on its own and says `proof`."""
    return f"{io.now():%H:%M:%S} [{done}/{planned}]{' proof' if proof else ''}"


def progress_log(io, done, planned, proof=False):
    """A log function for what happens between two plays (a reset): its lines start the way the play lines do."""
    return lambda msg: print(f'{line_prefix(io, done, planned, proof)} {msg}', flush=True)


def _write(path, text):
    with open(path, 'w') as f:
        f.write(text)


# --------------------------------------------------------------------------- the quick check (#270, spec #268, ADR 0010)

CHECK_LIST = 'check'  # the stand-in's list name for a check's live answers, in the check's own store (emptied after it)
CHECK_STORE_DIR = 'check-answers'  # in the test folder: never in the run folder, which backup.sh pushes
EXIT_FAILS, EXIT_NO_VERDICT = 4, 2  # check --quick: a play failed; the cap rule stopped it (0 pass, 1 setup problem or failure)


def check_visit_answer(got, play, pause_s=0, sleep=time.sleep):
    """What a check saw of one title: its list (one common.get() of the list address), then, when the list has the Best
    entry, the Browse pause and one press of Best (`play(stream)`, common.play_stream's result), nothing else played.
    The real world and the fakes both build a visit here, so a copy that is down looks the same."""
    out, streams = read_list(got)
    best = next((s for s in streams if is_best_entry(s)), None)
    out.update(play=None, browse_pause_s=0, best=best is not None)
    if best is not None:
        if pause_s:
            sleep(pause_s)
            out['browse_pause_s'] = pause_s
        out['play'] = play(best)
    return out


def collect_check_visit(cfg, io, title, logbuf, plays=None, secrets=()):
    """One title of a check: its list, the Browse pause, one press of Best; then KaijuFlow's play step lines for it
    (quickcheck.visit_steps), its AltMount imports and any "limit reached" line in either log. Both containers' lines go
    to `logbuf` scrubbed (evidence.scrub, with the test copies' `secrets`) and, unscrubbed, to `plays` for the evidence
    folder of a play that fails (write_check_ending)."""
    kind, vid, label = title[:3]
    t0 = io.now()
    http = io.check_visit(kind, vid, cfg['browse_pause'])
    t1 = io.now()
    since = br.iso(t0 - datetime.timedelta(seconds=1))
    kf_text, be_text = io.logs(KF_CONTAINER, since), io.logs(ALTMOUNT_CONTAINER, since)
    for c, text in ((KF_CONTAINER, kf_text), (ALTMOUNT_CONTAINER, be_text)):
        logbuf.setdefault(c, []).append(f'--- {label} {br.iso(t0)}\n{evidence.scrub(text, secrets)}')
    if plays is not None:
        plays.append({'kf_text': kf_text, 'be_text': be_text})
    lo, hi = t0 - datetime.timedelta(seconds=1), t1 + datetime.timedelta(seconds=GRACE_S)
    return {'title': list(title), 'label': label, 'id': vid, 't_start': br.iso(t0), 't_end': br.iso(t1), **http,
            'steps': quickcheck.visit_steps(br.parse_step_lines(kf_text), vid, since),
            'imports': [i for i in br.altmount_imports(be_text) if lo <= br.parse_ts(i['start']) <= hi],
            'limit': br.limit_event(kf_text + '\n' + be_text, cfg['indexers'])}


def quick_check_all(cfg, io):
    """The quick check (#270): play_check on 5 new titles drawn (and written to the ledger first)."""
    return play_check(cfg, io, 'quick check', lambda check: io.draw_titles(f"quick check {check['folder']}",
                                                                           quickcheck.QUICK_KINDS))


def drill_all(cfg, io):
    """The Drill-down (#272): play_check on one failed title (`drill_title`, `drill_episode`), not drawn and not added
    to the ledger again; its suspected causes (drill.prepare) are marked after Diagnosis (write_check_ending)."""
    def title(check):
        t, check['drill_suspects'] = drill.prepare(cfg['runs_root'], cfg['drill_title'], cfg.get('drill_episode'),
                                                   cfg.get('drill_entries') or (),
                                                   lambda imdb, episode: io.drill_title(imdb, episode))
        return [t]
    return play_check(cfg, io, drill.KIND, title)


def play_check(cfg, io, kind, titles):
    """A real-use check of `kind` (the quick check, a Drill-down): the preflight for a check, a run folder, its titles
    (`titles(check)`), the test copies reset, the stand-in in record mode on the check's own empty store (so every answer
    comes from the live indexer, and its LIMIT_REACHED marker and RECORD lines work as in a record: the cap rule and the
    allowance count it), then each title once: its list, the Browse pause, one press of Best, stopped at the first video.
    The first "limit reached" stops the check with no verdict. Ctrl-C or SIGTERM stops it as it stops a run. The ending is
    written however it ends (write_check_ending)."""
    seen = {}
    problems = io.preflight('check', seen)
    if problems:
        raise PreflightFailed(problems)
    started = io.now()
    run_dir = br.create_run_dir(cfg['runs_root'], cfg['name'], started)
    os.makedirs(os.path.join(run_dir, 'logs'))
    check = {'kind': kind, 'name': cfg['name'], 'status': 'ok', 'started': br.iso(started), 'dir': run_dir,
             'folder': os.path.basename(run_dir), 'titles': [], 'visits': [], 'null': None, 'stopped': None, 'error': None,
             'indexers': list(cfg['indexers']), 'browse_pause_s': cfg['browse_pause'], 'settings': {}, 'commit': None,
             'head': None, 'dirty': None, 'altmount': None, 'start_load': round(seen['load'], 2) if 'load' in seen else None,
             'machine': seen.get('machine'), 'stage': 'the draw', 'playing': None}
    logbuf, handle, failure, restore_signals = {}, None, None, lambda: None
    check['plays'] = []  # both containers' lines per visit, for the evidence folders (never in raw.json)
    try:
        try:
            secrets = io.secret_values()
            check['settings'] = io.snapshot()
            check['head'], check['dirty'] = io.git_info()
            check['commit'] = io.image_label()
            _write(os.path.join(run_dir, 'settings.json'), json.dumps(check['settings'], indent=1, sort_keys=True))
            check['titles'] = [list(t) for t in titles(check)]
            _write(os.path.join(run_dir, 'titles.json'), json.dumps(check['titles'], indent=1))
            planned = len(check['titles'])
            check['stage'] = 'the reset'
            io.reset(ALL_TESTBED, progress_log(io, 0, planned))
            check['altmount'] = io.altmount_image()  # after the reset, which starts the copy (#287: what changed)
            io.open_check_store(run_dir)
            handle = io.start_standin(os.path.join(run_dir, 'logs', 'standin.log'), mode='record')
            check['stage'] = 'the plays'
            for title in check['titles']:
                check['playing'] = {'side': 'kaijuflow', 'phase': 'cold', 'round': None, 'title': title[2]}  # stop_note's shape
                v = collect_check_visit(cfg, io, title, logbuf, check['plays'], secrets)
                check['visits'].append(v)
                check['playing'] = None
                play = v['play'] or {}
                print(f"{line_prefix(io, len(check['visits']), planned)} {title[2]}: "
                      f"{'video' if play.get('plays') else 'no video'} list {v['list_s']} s start {play.get('first_byte_s')} s", flush=True)
                _check_cap(io, {'limit': v['limit'], 'side': 'KaijuFlow', 'title': title[2], 't_end': v['t_end']}, since=started)
                io.sleep(cfg['settle'])
        except CapReached as e:
            check['status'], check['null'] = 'null', {'indexer': e.indexer, 'time': e.time, 'where': e.where}
            if check['visits']:  # the play the limit cut says nothing of KaijuFlow: kept in raw.json, not judged
                check['visits'][-1]['cut_by_limit'] = True
        except KeyboardInterrupt as e:  # Ctrl-C or SIGTERM: the titles that finished are kept and judged, no verdict
            check['status'] = 'stopped'
            check['stopped'] = stop_note(io, e, check['stage'], len(check['visits']), len(check['titles']), check['playing'])
            check['stopped_text'] = br.stopped_text(check['stopped'])
            restore_signals = finish_after_stop(check['stopped'], 'check', 'report.md, raw.json, meta.json and the INDEX.md row')
        finally:
            try:
                if handle:
                    handle.stop()
                    late = io.marker()  # a limit after the last title's check (a late grab of the Walk) still stops it
                    if late and check['status'] == 'ok':
                        check['status'] = 'null'
                        check['null'] = {'indexer': late.get('indexer', 'unknown'), 'time': late.get('time', '?'),
                                         'where': 'indexer stand-in LIMIT_REACHED.json, after the last title'}
            finally:
                io.stop_all()
    except (draw.Refused, pool.TmdbError) as e:  # the draw could not be made: its one sentence, no traceback
        check['status'], check['error'] = 'failed', str(e)
    except Exception as e:  # noqa: BLE001
        check['status'], check['error'] = 'failed', br.scrub_text(f'{type(e).__name__}: {e}')
        failure = e
    try:
        write_check_ending(cfg, io, check, started, logbuf)
    finally:
        try:
            io.close_check_store()  # after the ending: the evidence folders keep a failed play's answers first
        finally:
            restore_signals()
    if failure:
        raise failure
    return check


def write_check_ending(cfg, io, check, started, logbuf):
    """The ending of every check, finished or not: the logs, report.md (quickcheck.render_report), raw.json (the visits
    and each one's outcome), meta.json and the INDEX.md row. A check names no recording, so no run is ever judged
    against it (runs.previous)."""
    run_dir = check['dir']
    finished = io.now()
    check['finished'], check['seconds'] = br.iso(finished), round((finished - started).total_seconds(), 3)
    for c, parts in logbuf.items():
        _write(os.path.join(run_dir, 'logs', c + '.log'), '\n'.join(parts) + '\n')

    def names(title):
        try:
            return io.title_names(title)
        except Exception:  # noqa: BLE001  (TMDB down: judge says the other names could not be read)
            return None
    check['outcomes'] = [quickcheck.judge(v, names=lambda t=v['title']: names(t)) for v in quickcheck.judged(check)]
    save_evidence(io, check, every=check['kind'] == drill.KIND)  # a Drill-down keeps its play's folder however it went
    try:  # Diagnosis runs by itself on a check with a failure (#283), the live read-only Clues first (#284); its report
        # section says if it could not
        # a proved KaijuFlow cause files its fix ticket, unless the check is a dry run (#288)
        check['diagnosis'] = diagnosis.after_check(run_dir, cfg['runs_root'], usenet=io.usenet, cases=cfg.get('cases'),
                                                   agent=io.start_diagnosing_agent, alert=io.alert, book=cfg.get('casebook'),
                                                   tracker=None if cfg.get('tickets_dry_run') else io.tracker())
    except Exception as e:  # noqa: BLE001  (the check's report and verdict come first)
        check['diagnosis'] = None
        check['diagnosis_error'] = br.scrub_text(f'{type(e).__name__}: {e}')
    check['verdict'] = quickcheck.verdict(check, check['outcomes'])
    if check['kind'] == drill.KIND and check['verdict'] is not None:
        if check.get('diagnosis_error'):
            check['drill_error'] = 'Diagnosis could not run'
        else:
            try:  # the suspected causes marked proved fixed or reopened (#272)
                check['drill'] = drill.mark(run_dir, check.get('drill_suspects') or [], cfg.get('casebook'))
            except Exception as e:  # noqa: BLE001  (the report and verdict come first)
                check['drill_error'] = br.scrub_text(f'{type(e).__name__}: {e}')
    check['headline'] = quickcheck.headline(check, check['outcomes'])
    _write(os.path.join(run_dir, 'report.md'), quickcheck.render_report(check, check['outcomes']))
    _write(os.path.join(run_dir, 'raw.json'), json.dumps({'status': check['status'], 'visits': check['visits'],
                                                          'outcomes': check['outcomes']}, indent=1))
    meta = {k: check.get(k) for k in ('kind', 'name', 'status', 'verdict', 'headline', 'started', 'finished', 'seconds', 'commit',
                                      'head', 'dirty', 'altmount', 'titles', 'indexers', 'null', 'stopped', 'error', 'browse_pause_s',
                                      'start_load', 'machine')}
    _write(os.path.join(run_dir, 'meta.json'), json.dumps(meta, indent=1, sort_keys=True))
    result = {'pass': 'pass', 'fail': 'FAIL'}.get(check['verdict']) or {'null': 'NULL'}.get(check['status'], check['status'])
    br.append_index_row(os.path.join(cfg['runs_root'], 'INDEX.md'), {
        'date': check['started'], 'name': cfg['name'], 'result': result, 'changed': [], 'headline': check['headline'],
        'folder': check['folder']})


def save_evidence(io, check, every=False):
    """An evidence folder (evidence.save) for every judged play that failed or fell back (`every`: every judged play), its
    path in the play's outcome as `evidence`; a play that went fine gets none. A folder that cannot be written is said in `evidence_error` and the
    check's ending goes on."""
    visits, plays = check.get('visits') or [], check.get('plays') or []
    judged = [(i, v) for i, v in enumerate(visits) if not v.get('cut_by_limit')]
    for (i, v), outcome in zip(judged, check.get('outcomes') or []):
        if not (every or evidence.kept_because(outcome)) or i >= len(plays):
            continue
        nxt = visits[i + 1]['t_start'] if i + 1 < len(visits) else br.iso(br.parse_ts(v['t_end']) + datetime.timedelta(seconds=GRACE_S))
        play = {'check': check['folder'], 'kind': check['kind'], 'visit': v, 'outcome': outcome, **plays[i],
                'settings': check.get('settings') or {}, 'until': nxt,
                **{k: check.get(k) for k in ('commit', 'head', 'dirty', 'altmount')}}
        try:
            outcome['evidence'] = evidence.save(check['dir'], i + 1, play, io)
        except Exception as e:  # noqa: BLE001  (the check's report and verdict come first)
            outcome['evidence_error'] = br.scrub_text(f'{type(e).__name__}: {e}')


# --------------------------------------------------------------------------- the command line


def quick_check_command(cfg, io, run=quick_check_all):
    """`check --quick` (and `drill`, run=drill_all): runs the check and prints its verdict line and folder. Exit 0 pass,
    4 a play failed, 2 the cap rule stopped it, 130 stopped by Ctrl-C or SIGTERM, 1 a setup problem or a failure."""
    try:
        with sigterm_stops():
            check = run(cfg, io)
    except PreflightFailed as e:
        for p in e.problems:
            print(p)
        return 1
    print(check['headline'])
    print(f"Folder: {check['dir']}")
    if check['verdict']:
        return 0 if check['verdict'] == 'pass' else EXIT_FAILS
    return {'null': EXIT_NO_VERDICT, 'stopped': EXIT_INTERRUPTED}.get(check['status'], 1)


def drill_command(cfg, io):
    """`drill`: the Drill-down (#272), with the quick check's exit codes."""
    return quick_check_command(cfg, io, drill_all)


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['check', 'drill', 'preflight', 'usage'])
    ap.add_argument('--for', dest='mode', choices=['check'], default='check',
                    help='preflight only: the setup check for a real-use check (the only one left; run and record are retired)')
    ap.add_argument('--name', help="the check folder's label (default quick-check, or drill-down)")
    ap.add_argument('--runs-root', default=DEFAULT_RUNS_ROOT)
    ap.add_argument('--rebuild-image', action='store_true', help='build kaijuflow:test again from the current commit when the code that goes into the image has changed since it was built')
    ap.add_argument('--provider-limit', type=int, default=testbed.PROVIDER_LIMIT)
    ap.add_argument('--key-file')
    ap.add_argument('--test-dir', default=os.environ.get('TEST_DIR', DEFAULT_TEST_DIR))
    ap.add_argument('--user-id')
    ap.add_argument('--quick', action='store_true', help='check: the quick check, 5 new titles played live (#270)')
    ap.add_argument('--title', dest='drill_title', help='drill only: the IMDb id of the failed title to play again (#272)')
    ap.add_argument('--episode', help='drill only: the episode of a show, written S01E02')
    ap.add_argument('--entry', action='append', default=[],
                    help='drill only: a Casebook entry to mark besides the ones proved on the title before (repeatable)')
    ap.add_argument('--full', action='store_true', help="drill only: watch the play as the full check does (#271)")
    ap.add_argument('--casebook', help="check --quick and drill: the Casebook folder Diagnosis reads (default the repo's)")
    ap.add_argument('--cases', default=caselog.CASES,
                    help='check --quick and drill: the Case logs of failures with no proved cause (default %(default)s, #287)')
    ap.add_argument('--tickets-dry-run', action='store_true',
                    help='check --quick and drill: write the fix tickets of proved KaijuFlow causes into the check folder, file none (#288)')
    ap.add_argument('--ledger', help='check --quick only: the titles already played (default <runs root>/titles-played.json)')
    ap.add_argument('--settle', type=float, default=3, help='seconds to pause after every play (default 3)')
    return ap


def _option(argv, name):
    """The value argv gives the option `name` (`--for run` or `--for=run`), or None."""
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + '='):
            return a.split('=', 1)[1]
    return None


def retired_command(argv):
    """The retired command (ADR 0010, #273) that argv names, as its one line names it, or None for a live command."""
    cmd = argv[0] if argv else None
    if cmd in ('run', 'record', 'smoke'):
        return cmd
    if cmd == 'preflight' and _option(argv, '--for') in ('run', 'record'):
        return f"preflight --for {_option(argv, '--for')}"
    if cmd == 'check' and _option(argv, '--run') is not None:
        return 'check --run'
    return None


def main(argv):
    command = retired_command(argv)
    if command:
        return retired.gate('brainrun', command, argv)
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.cmd == 'check' and not a.quick:
        ap.error('--quick is needed: the quick check is the one check built (the full check comes with #271)')
    if a.cmd == 'drill':
        if not a.drill_title:
            ap.error('--title is needed: the IMDb id of the title to drill down on')
        if a.full:
            ap.error("--full watches the play as the full check does, and the full check's watch (#271) is not built yet; "
                     'it wires --full in here')
        try:
            drill.title_id(a.drill_title, a.episode)
        except ValueError as e:
            ap.error(str(e))
    td = a.test_dir
    users = (br.read_json(os.path.join(td, 'config/users.json')) or {}).get('users') or [{}]
    cfg = dict(name=a.name or 'quick-check', runs_root=a.runs_root, store=None, listname=None, test_dir=td,
               user_id=a.user_id or ((users[0].get('manifests') or [{}])[0].get('id') or users[0].get('id', '')),
               settle=a.settle, browse_pause=BROWSE_PAUSE_S, rebuild_image=a.rebuild_image, limit=a.provider_limit,
               key_file=a.key_file, standin_port=testbed.STANDIN_PORT, cases=a.cases, tickets_dry_run=a.tickets_dry_run,
               casebook=a.casebook, ledger=a.ledger or os.path.join(a.runs_root, 'titles-played.json'))
    if a.cmd == 'usage':
        print('\n'.join(allowance.usage_lines(cfg)))
        return 0
    cfg['indexers'] = read_key_file(_key_path(cfg))[1]
    if a.cmd == 'preflight':
        return preflight_command('check', cfg, RealIO(cfg))
    if a.cmd == 'drill':  # one title, not drawn: the preflight's allowance is one title's (#272)
        cfg.update(name=a.name or 'drill-down', drill_title=a.drill_title, drill_episode=a.episode, drill_entries=a.entry,
                   check_titles=1)
        return drill_command(cfg, RealIO(cfg))
    return quick_check_command(cfg, RealIO(cfg))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
