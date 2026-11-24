"""The retired commands of brainrun.py (ADR 0010, #273), archived, not deleted: run (the four cold and warm rounds on a
replayed Recording, short runs), record (the cold and warm record pass, its top-ups and its proof replay), smoke (the
stand-in reachability check), the run and record preflights with their recording checks (the recording complete, no
request missed by the last run on it), and check --run (runcheck.py: a run usable as a baseline, and the judgement
against the previous run).

They run only through retired.py's gate, with --revive (`python3 -I tools/brain/brainrun.py run ... --revive`); the
live parts they share (the preflight's other checks, RealIO, the stand-in, the reset, the cap rule) are brainrun's own.
How they worked: README.md and run-and-record.md next to this file. This folder is out of npm run check:brain, so a
revived command may need fixing first.
"""
import argparse
import contextlib
import copy
import datetime
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]  # python3 -I leaves them off sys.path
import allowance  # noqa: E402
import brainreport as br  # noqa: E402
import brainrun  # noqa: E402
import caselog  # noqa: E402
import common  # noqa: E402
import drill  # noqa: E402
import indexer_standin  # noqa: E402
import runcheck  # noqa: E402
import runs  # noqa: E402
import testbed  # noqa: E402
from brainrun import (ALL_TESTBED, ALTMOUNT_CONTAINER, BROWSE_PAUSE_S, DEFAULT_RUNS_ROOT, DEFAULT_TEST_DIR,  # noqa: E402,F401
                      EXIT_INTERRUPTED, GRACE_S, KF_CONTAINER, MAIN_SIDES, CapReached, PreflightFailed, RealIO,
                      _check_cap, _key_path, _list, _read_text, _write, drill_command, finish_after_stop, line_prefix, list_base,
                      progress_log, quick_check_command, read_key_file, read_list,
                      sigterm_stops, stop_note)


PLAN = [('cold', 1), ('warm', 1), ('cold', 2), ('warm', 2)]


RECORD_ROUNDS = ('cold', 'warm')  # a record pass: a cold round, then a warm round on the same state (#79)


RECORDING_FILE = 'RECORDING.json'  # next to a list's answers: {"state": "complete"|"incomplete"|"stopped", "why", "when", "errors", "misses"}


EXIT_STOPPED, EXIT_INCOMPLETE = 2, 3  # the record command's own exit codes (0 complete, 1 setup problem or failure)


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
    out, streams = read_list(got)
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


CPU_CONTAINERS = {'kaijuflow_ms': KF_CONTAINER, 'altmount_ms': ALTMOUNT_CONTAINER}


_container_ids = {}


def _container_cpu_us(container, run=subprocess.run, root='/sys/fs/cgroup/system.slice'):
    """CPU a test container has used since it started, microseconds, from its cgroup (`usage_usec` of cpu.stat); None when
    it is not up. Its id is looked up with `docker inspect` (read-only) once, and again after a reset gave it a new one."""
    if container not in testbed.TEST_CONTAINERS:
        raise ValueError('not a test container: ' + container)
    for fresh in (False, True):
        if fresh or container not in _container_ids:
            r = run(['docker', 'inspect', '-f', '{{.Id}}', container], capture_output=True, text=True, timeout=30)
            _container_ids[container] = r.stdout.strip() if r.returncode == 0 else ''
        try:
            with open(os.path.join(root, f'docker-{_container_ids[container]}.scope', 'cpu.stat')) as f:
                return next(int(line.split()[1]) for line in f if line.startswith('usage_usec '))
        except (OSError, StopIteration, ValueError, IndexError):
            continue
    return None


def _machine_busy_ms(path='/proc/stat'):
    """CPU the whole machine has used since boot, every core added up, in ms: /proc/stat's first line less idle and iowait
    (clock ticks of 10 ms)."""
    try:
        with open(path) as f:
            ticks = [int(x) for x in f.readline().split()[1:9]]
        return (sum(ticks) - ticks[3] - ticks[4]) * 10
    except (OSError, ValueError, IndexError):
        return None


def cpu_sample(container_cpu=_container_cpu_us, machine=_machine_busy_ms):
    """One reading of the CPU used so far (#249): each test container's in microseconds and the machine's in ms."""
    out = {k: container_cpu(c) for k, c in CPU_CONTAINERS.items()}
    out['machine_ms'] = machine()
    return out


def cpu_used(before, after):
    """The CPU used between two readings, in ms (`kaijuflow_ms`, `altmount_ms`, `machine_ms`); a figure either reading
    lacks, or one that went back (a container restarted), is None."""
    out = {}
    for k in ('kaijuflow_ms', 'altmount_ms', 'machine_ms'):
        a, b = before.get(k), after.get(k)
        d = None if a is None or b is None or b < a else b - a
        out[k] = None if d is None else round(d / 1000) if k != 'machine_ms' else d
    return out


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
    marker = br.read_json(path) or {}
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
    play = br.read_play(kf_text, {'id': vid, 't_start': br.iso(t0)})
    played = play['played_source']
    steps = br.attribute_steps({'id': vid, 't_start': br.iso(t0), 'tries': http.get('tries', []), 'played_source': played},
                               br.parse_step_lines(kf_text))
    imports = [i for i in br.altmount_imports(be_text) if lo <= br.parse_ts(i['start']) <= hi]
    limit = br.limit_event(kf_text + '\n' + be_text, cfg['indexers'])
    ok = bool(http.get('first_try_plays'))
    return {'side': side, 'phase': phase, 'round': rnd, 'title': label, 'id': vid, 'kind': kind, 'ok': ok,
            't_start': br.iso(t0), 't_end': br.iso(t1), 'list_status': http.get('list_status'),
            'list_s': http.get('list_s'), 'sources': http.get('sources'), 'start_s': http.get('start_s'),
            'seeks': http.get('seeks', {}), 'note': http.get('note'), 'tries': http.get('tries', []),
            'browse_pause_s': http.get('browse_pause_s', 0), **({'list_cpu': http['list_cpu']} if http.get('list_cpu') else {}),
            'steps': steps, 'imports': imports, 'limit': limit, 'played_source': played,
            'cause': '' if ok else play['cause'], **({'list': title[3]} if len(title) > 3 else {})}


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


def planned_plays(cfg, rounds):
    """How many plays a command makes when nothing stops it: every title on every planned side in every round."""
    return len(rounds) * len(cfg['titles']) * len(run_sides(cfg))


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


def run_all(cfg, io):
    seen = {}
    problems = io.preflight('run', seen)
    if problems:
        raise PreflightFailed(problems)
    started = io.now()
    start_load = round(seen['load'], 2) if 'load' in seen else None  # the load the preflight judged, as the run starts (#217)
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
           'lists': title_lists(cfg['titles']), 'start_load': start_load,
           'machine': seen.get('machine')}  # the power state, CPU policy and CPU probe the preflight judged (#262)
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
    prev = runs.previous(run)  # the one Previous run, as CHECK.txt and the page take it (#241)
    run['previous'] = prev['folder'] if prev else None
    nulls = runs.nulls_between(run, prev)
    if prev and run['short']:  # a short run is held against its previous run, as far as it played
        run['changes'] = [f"Short run: compared with the previous run, {prev['folder']}, limited to {run['short']}."] + \
            br.diff_runs(br.limit_to_played(prev, run), run, nulls)
    else:
        run['changes'] = br.diff_runs(prev, run, nulls)
    shown = ([runs.against(prev) + '.'] if prev else []) + run['changes']  # the report and the INDEX.md row name the run
    if run['status'] == 'ok':
        report, result, headline = br.render_report(run, shown), 'ok', br.headline(run)
    elif run['status'] == 'null':
        report, result = br.render_null_report(run), 'NULL'
        headline = f"NULL: {run['null']['indexer']} limit reached at {run['null']['time']}; no numbers"
    elif run['status'] == 'stopped':
        report, result, headline = br.render_stopped_report(run, shown), 'stopped', br.stopped_text(run['stopped'])
    else:
        report, result, headline = f"This run failed before it finished: {run['error']}\n", 'failed', f"failed: {run['error']}"
    if run['short']:
        report = f"Short run, not a baseline: {run['short']}.\n\n{report}"
        result = f"short: {run['short']}" if result == 'ok' else f"{result} (short: {run['short']})"
    _write(os.path.join(run_dir, 'report.md'), report)
    _write(os.path.join(run_dir, 'raw.json'), json.dumps({'status': run['status'], 'visits': run['visits']}, indent=1))
    meta = {k: run.get(k) for k in ('name', 'status', 'started', 'finished', 'commit', 'head', 'dirty', 'recording', 'titles', 'indexers',
                                    'sides', 'rounds', 'short', 'settings', 'facts', 'addresses', 'standin_unmatched', 'null', 'stopped', 'error',
                                    'standin_misses', 'changes', 'previous', 'timing', 'browse_pause_s', 'start_load', 'machine')}
    if run.get('lists'):  # a run on a tagged title list (#167); a run without tags keeps its meta.json as before
        meta['lists'] = run['lists']
    _write(os.path.join(run_dir, 'meta.json'), json.dumps(meta, indent=1, sort_keys=True))
    br.append_index_row(os.path.join(root, 'INDEX.md'), {
        'date': run['started'], 'name': cfg['name'], 'result': result, 'changed': shown,
        'headline': headline, 'folder': os.path.basename(run_dir)})


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
    io = io or RetiredIO(cfg)
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
    ap.add_argument('cmd', choices=['run', 'record', 'smoke', 'preflight', 'check', 'drill', 'usage'])
    ap.add_argument('--run', dest='run_dir', help='check only: the run folder to check; exits non-zero when it cannot serve as a baseline')
    ap.add_argument('--no-wait', action='store_true', help='run only: replay indexer answers at once instead of waiting the recorded indexer time')
    ap.add_argument('--for', dest='mode', choices=['run', 'record', 'check'], default='run',
                    help='preflight only: check the setup for a run, a record pass or a quick check')
    ap.add_argument('--name', help='the run folder\'s label: run, or quick-check for check --quick')
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
    ap.add_argument('--quick', action='store_true', help='check: the quick check, 5 new titles played live (#270); run: shorthand for '
                    '--sides kaijuflow --rounds 1 (a short run; does not imply --no-wait)')
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
    ap.add_argument('--titles-file')
    ap.add_argument('--tries', type=int, default=1)
    ap.add_argument('--settle', type=float, default=3, help='seconds to pause after every play (default 3)')
    return ap


def topup_command(a):
    """The record command that tops up this recording, as a line the owner can paste."""
    parts = ['python3', '-I', 'tools/brain/brainrun.py', 'record', '--name', a.name or 'run', '--store', a.store or '', '--list', a.listname or '']
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
        if a.sides is not None or a.rounds is not None or (a.quick and a.cmd != 'check'):
            return None, 2, '--sides and --rounds are only for run, --quick for run and check'
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
    if a.cmd == 'check' and not a.quick:
        if not a.run_dir:
            ap.error('--run is needed (or --quick for a quick check)')
        return runcheck.check_command(a.run_dir)
    if a.cmd == 'check' and a.run_dir:
        ap.error('--run is for checking a run folder; a quick check (--quick) plays new titles and takes no --run')
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
    if a.cmd not in ('preflight', 'usage', 'check', 'drill') or (a.cmd == 'preflight' and a.mode == 'run'):
        if not a.store or not a.listname:
            ap.error('--store and --list are needed')
    td = a.test_dir
    users = (br.read_json(os.path.join(td, 'config/users.json')) or {}).get('users') or [{}]
    titles = [tuple(t) for t in br.read_json(a.titles_file)] if a.titles_file else common.TITLES
    listdir = os.path.join(a.store or '', a.listname or '')
    cfg = dict(name=a.name or 'run', runs_root=a.runs_root, store=a.store, listname=a.listname, test_dir=td,
               user_id=a.user_id or ((users[0].get('manifests') or [{}])[0].get('id') or users[0].get('id', '')),
               one_page=a.one_page, sides=sides, rounds=rounds, titles=titles,
               partial_titles=partial_titles(titles, a.titles_file), tries=a.tries, settle=a.settle, browse_pause=BROWSE_PAUSE_S,
               indexers=sorted(d for d in os.listdir(listdir) if os.path.isdir(os.path.join(listdir, d))) if a.store and os.path.isdir(listdir) else [],
               rebuild_image=a.rebuild_image, limit=a.provider_limit, key_file=a.key_file, standin_port=testbed.STANDIN_PORT,
               wait=not a.no_wait, topup_command=topup_command(a))
    if a.cmd in ('check', 'drill') or (a.cmd == 'preflight' and a.mode == 'check'):
        cfg.update(name=a.name or 'quick-check', indexers=read_key_file(_key_path(cfg))[1], cases=a.cases,
                   tickets_dry_run=a.tickets_dry_run, casebook=a.casebook,
                   ledger=a.ledger or os.path.join(a.runs_root, 'titles-played.json'))
    if a.cmd == 'drill':  # one title, not drawn: the preflight's allowance is one title's (#272)
        cfg.update(name=a.name or 'drill-down', drill_title=a.drill_title, drill_episode=a.episode, drill_entries=a.entry,
                   check_titles=1)
        return drill_command(cfg, RetiredIO(cfg))
    started = time.time()
    if a.cmd == 'check':
        return quick_check_command(cfg, RetiredIO(cfg))
    if a.cmd == 'usage':
        print('\n'.join(allowance.usage_lines(cfg)))
        return 0
    if a.cmd == 'preflight':
        return preflight_command(a.mode, cfg, RetiredIO(cfg))
    if a.cmd == 'smoke':
        smoke(cfg)
    elif a.cmd == 'record':
        try:
            with sigterm_stops():
                rec = record_all(cfg, RetiredIO(cfg))
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
                run = run_all(cfg, RetiredIO(cfg))
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


# --------------------------------------------------------------------------- the recording checks of the run's preflight

def recording_problems(cfg, io):
    """Check 10 of the run's preflight, archived with it: the recording exists, holds an answer for every switched-on
    indexer, and the last run on it missed nothing (#229). Plain sentences, one per problem."""
    problems = []
    rep = io.setup_report(cfg.get('limit', testbed.PROVIDER_LIMIT))
    readable = [s for s in brainrun.INDEXER_SIDES if rep['indexers'].get(s) is not None]
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
        missed = io.missed_since(state.get('when'))
        if missed and missed[1]:
            problems.append(f"The last run on '{cfg.get('listname')}' ({missed[0]}) missed {missed[1]} requests the recording does not hold, "
                            f"so a run now would miss them too: top it up with the record command: {top_up}")
    return problems


def preflight(mode, cfg, io, seen=None):
    """The retired run and record preflights: brainrun's preflight, then (a run) the recording checks."""
    problems = brainrun.preflight(mode, cfg, io, seen)
    if mode == 'run':
        problems += recording_problems(cfg, io)
    return problems


def preflight_command(mode, cfg, io):
    """Prints the run or record preflight's result in plain sentences; exit code 0 when the setup is right, 1 otherwise."""
    seen = {}
    problems = preflight(mode, cfg, io, seen)
    for p in problems:
        print(p)
    if mode == 'record' and cfg.get('runs_root'):  # the allowance: warns only, never blocks
        print('\n'.join(record_preflight_lines(cfg)))
    if not problems:
        idle = f' and idle (1-minute load below {brainrun.BUSY_LOAD:.2f})' if mode == 'run' else ''
        machine = (f'; the machine is plugged in{idle}, HOST_IP and altmountUrl are its addresses, {brainrun.NEWS_HOST} resolves '
                   'outside 10.x' + (' and the recording is complete' if mode == 'run' else ''))
        print(f'Setup is right for a {mode}: image, indexers, addresses, connection caps, sort and filter settings and port all '
              f'check out{machine}.')
        if 'machine' in seen:
            print(f"CPU probe: {br.probe_text(seen['machine'])}.")
    return 1 if problems else 0


def last_complete_recording(runs_root, listname):
    """(folder name, {indexer slug: {'search': n, 'download': n}}) of the newest complete record folder of this list, or None.

    Complete: its meta.json says status "recorded". The list comes from the first line of its stand-in log."""
    for folder in sorted(glob.glob(os.path.join(runs_root, '*-record')), reverse=True):
        try:
            meta = runs.load(folder)
        except runs.Unreadable:
            continue
        if meta.get('status') != 'recorded':
            continue
        log = os.path.join(folder, 'logs', 'standin.log')
        try:
            with open(log, errors='replace') as f:
                head = f.readline()
        except OSError:
            continue
        m = re.match(r'stand-in record list=(\S+)', head)
        if not m or m.group(1) != listname:
            continue
        counts = {}
        for slug, kind, _ in allowance.requests_in(log):
            counts.setdefault(slug, dict.fromkeys(allowance.KINDS, 0))[kind] += 1
        return os.path.basename(folder), counts
    return None


def record_preflight_lines(cfg, now=None, stats_files=None):
    """What `preflight --for record` adds: the allowance allowance.table, the last complete recording's request count, and a warning
    when that many requests may not fit in what is left. Warns only; never blocks."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    limits, used, problem = allowance._compute(cfg, now, stats_files)
    lines = [problem] if problem else allowance.table(limits, used) + [allowance.COLUMNS, allowance.CAVEAT]
    last = last_complete_recording(cfg['runs_root'], cfg.get('listname')) if cfg.get('runs_root') else None
    if last is None:
        lines.append(f"There is no earlier complete recording of the list '{cfg.get('listname')}', so the request count of a full pass is not known yet.")
        return lines
    folder, counts = last
    total = sum(sum(c.values()) for c in counts.values())
    parts = ', '.join(f'{slug}: {c["search"]} searches and {c["download"]} downloads' for slug, c in sorted(counts.items()))
    lines.append(f"The last complete recording of the list '{cfg.get('listname')}' ({folder}) sent {total} requests to the indexers ({parts}). "
                 'A top-up sends fewer, because stored answers are not asked for again.')
    for slug, c in sorted(counts.items()):
        lim = (limits or {}).get(slug)
        if not lim:
            continue
        for kind in allowance.KINDS:
            left = lim[kind] - used[slug]['standin'][kind] - used[slug]['copies'][kind]
            if c[kind] > left:
                lines.append(f'Warning: {lim["name"]} has {left} {allowance.KIND_NAMES[kind]} left but the last full recording needed {c[kind]}. '
                             'The recording may stop at the limit; it can be topped up after the reset.')
    return lines


# --------------------------------------------------------------------------- the real world, with the recording's parts

class RetiredIO(RealIO):
    """brainrun's real world plus what only the retired commands ask: the recording, the one-page side, the run's visit."""

    def __init__(self, cfg):
        super().__init__(cfg)
        self.backup = os.path.join(cfg['test_dir'], 'config', 'config.json.pre-brainrun')

    def preflight(self, mode, seen=None):
        return preflight(mode, self.cfg, self, seen)

    def addresses(self):
        return read_addresses()


    def shelve_marker(self):
        return shelve_marker(self.cfg['store'])


    def setting_conflicts(self):
        """Sentences for a key file whose dropped-parameter setting differs from the one the list was recorded with."""
        key = _key_path(self.cfg)
        return indexer_standin.setting_conflicts(br.read_json(key) or {}, self.cfg['store'], self.cfg['listname'])


    def recording_state(self):
        return br.read_json(os.path.join(self.cfg['store'], self.cfg['listname'], RECORDING_FILE))


    def missed_since(self, when):
        """(run folder, missed requests) of the newest run on this recording that started after `when` (the recording's
        last record, as RECORDING.json says), or None when there is none or the runs root is not known. #229. A grab of a release
        the visit never played does not count (#235), when the run folder's raw.json shows the visits."""
        return runs.missed_since(self.cfg.get('runs_root'), self.cfg['listname'], when)


    def recording(self):
        """{indexer slug: number of stored answers} for the title list; {} when there is no such folder."""
        d = os.path.join(self.cfg['store'], self.cfg['listname'])
        if not os.path.isdir(d):
            return {}
        return {slug: sum(1 for f in os.listdir(os.path.join(d, slug)) if f.endswith('.body'))
                for slug in os.listdir(d) if os.path.isdir(os.path.join(d, slug))}


    def apply_one_page(self):
        path = os.path.join(self.cfg['test_dir'], 'config', 'config.json')
        if os.path.exists(self.backup):
            raise RuntimeError(f'{self.backup} exists: an earlier run did not restore the KaijuFlow config; restore it by hand')
        self._compose('stop', 'kaijuflow')
        shutil.copyfile(path, self.backup)
        patched = one_page_config(br.read_json(path))
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
        before = cpu_sample()
        got = common.get(f'{base}/stream/{kind}/{vid}.json', timeout=180, limit=0)
        list_cpu = cpu_used(before, cpu_sample())
        out = visit_answer(got, tries, pause_s=browse_pause_s, sleep=self.sleep)
        return {**out, 'list_cpu': list_cpu}


if __name__ == '__main__':
    import retired  # noqa: E402
    sys.exit(retired.gate('brainrun', 'brainrun.py ' + (sys.argv[1] if len(sys.argv) > 1 else ''), sys.argv[1:]))
