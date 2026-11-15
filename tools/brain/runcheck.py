"""Check a finished run folder: can it serve as a baseline?

    python3 -I tools/brain/brainrun.py check --run <run folder>

Prints about a dozen plain lines and exits 0 when the run is usable, 1 when it is not
(a request the recording did not hold, a planned side that is absent, a null, stopped or failed run,
a recording folder, or a run folder that cannot be read). For a finished run it then prints one line per
target of targets.json (the target, the measured values, met or not met); for any other run one line
says why the targets are not judged (brainreport.targets_not_judged, the gate the report uses too).
The targets do not change the exit code.
The run command prints the same lines at its end and stores them in the run folder as CHECK.txt.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402

CHECK_FILE = 'CHECK.txt'
GAP_S = 0.5  # a visit whose step times and measured start differ by more than this is listed


def _load(run_dir, name):
    try:
        with open(os.path.join(run_dir, name)) as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, f'{name} is missing'
    except (OSError, ValueError) as e:
        return None, f'{name} cannot be read ({type(e).__name__})'


def _side(s):
    return br.SIDE_NAMES.get(s, s)


def _visit_name(v):
    return f"{_side(v['side'])}, {v['phase']} {v['round']}, {v['title']}"


def _step_gap(v):
    """Seconds between the step times a visit reports and its measured start; None when the visit has no such steps."""
    if not any(s.get('step') == 'first_byte' for s in v.get('steps') or []):
        return None
    if v.get('start_s') is None:
        return None
    m = br.visit_metrics(v)
    total = sum(m[k] or 0 for k in ('nzb_fetch_s', 'unscramble_s', 'import_s', 'probe_s'))
    return round(abs(total - v['start_s']), 2)


def check_run(run_dir):
    """Returns (usable, lines) for one run folder."""
    meta, err = _load(run_dir, 'meta.json')
    if err:
        return False, [f'Not usable as a baseline: {err}.']
    raw, err = _load(run_dir, 'raw.json')
    visits = (raw or {}).get('visits') or []
    status = meta.get('status')
    reasons, lines = [], []
    recording = meta.get('mode') == 'record'
    if recording:
        reasons.append('the folder holds a recording, not a timed run')
    if status == 'null':
        n = meta.get('null') or {}
        reasons.append(f"the run is null ({n.get('indexer', 'an indexer')} said its limit was reached at {n.get('time', 'an unknown time')})")
    elif status == 'stopped':
        reasons.append(f"the {'recording' if recording else 'run'} was {br.stopped_text(meta.get('stopped'))}")
    elif status != 'ok' and not recording:  # a recording's own status (recorded, failed) is no run's
        reasons.append(f"the run did not finish ({meta.get('error') or 'status ' + str(status)})")
    elif err and not recording:
        reasons.append(err)
    if br.is_archived(run_dir):
        reasons.append(f'{br.ARCHIVED_TEXT}: the folder is in the archive')
    if meta.get('short'):  # last: the reasons that say what went wrong with a plan that was played come first
        reasons.append(f"short run ({meta['short']})")
    lines.append(f"Run: {meta.get('name')}, status: {status}.")
    sides = meta.get('sides') or []
    seen = {v['side'] for v in visits}
    absent = [s for s in sides if s not in seen]
    if absent and status == 'ok':
        reasons.append('planned side absent: ' + ', '.join(_side(s) for s in absent))
    # top picks played per side, cold and warm (a top pick "played" when its visit served video on the first try, br.plays)
    for s in sides:
        parts = []
        for phase in ('cold', 'warm'):
            vs = [v for v in visits if v['side'] == s and v['phase'] == phase]
            parts.append(f"{phase} {sum(1 for v in vs if br.plays(v))} of {len(vs)}")
        lines.append(f"Top picks played, {_side(s)}: " + ', '.join(parts) + '.')
    # missed requests: requests the indexer stand-in did not hold, per round and side
    missed = [v for v in visits if v.get('misses')]
    if missed:
        per = {}
        for v in missed:
            k = (v['side'], f"{v['phase']} {v['round']}")
            per[k] = per.get(k, 0) + len(v['misses'])
        lines.append('Missed requests (a side asked for something the recording does not hold), per side and round: ' +
                     '; '.join(f'{_side(s)} {r}: {n}' for (s, r), n in sorted(per.items())) + '.')
        for phase in ('warm', 'cold'):
            by = {}
            for v in missed:
                if v['phase'] == phase:
                    by.setdefault((_side(v['side']), v['title']), []).append(str(v['round']))
            if by:
                lines.append(f'Missed in {phase} rounds (side, title, round): ' +
                             '; '.join(f"{s} {t} ({'+'.join(sorted(r))})" for (s, t), r in sorted(by.items())) + '.')
        reasons.append(f"{sum(len(v['misses']) for v in missed)} requests missed the recording in {len(missed)} visits")
    elif meta.get('standin_misses'):
        lines.append(f"Missed requests: the stand-in logged {meta['standin_misses']}, but no visit shows which.")
        reasons.append(f"{meta['standin_misses']} requests missed the recording")
    else:
        lines.append('Missed requests: none.')
    # sides with no import time (cold visits only; warm visits import nothing)
    no_import = [s for s in sides if s in seen and all(
        br.visit_metrics(v)['import_s'] is None for v in visits if v['side'] == s and v['phase'] == 'cold' and v.get('ok'))]
    lines.append('Sides with no import time: ' + (', '.join(_side(s) for s in no_import) if no_import else 'none') + '.')
    gaps = [(v, g) for v in visits for g in [_step_gap(v)] if g is not None and g > GAP_S]
    head = f'Visits whose step times and measured start differ by more than {GAP_S} s: '
    if gaps:
        lines.append(head + '; '.join(f'{_visit_name(v)} ({g} s)' for v, g in gaps[:5]) +
                     (f' and {len(gaps) - 5} more' if len(gaps) > 5 else '') + '.')
    else:
        lines.append(head + 'none.')
    failed = [v for v in visits if not v.get('ok')]
    if failed:
        lines.append(f'Failures ({len(failed)}), each with its cause:')
        for v in failed:
            cause = v.get('note') or '; '.join(t.get('note') or 'did not play' for t in v.get('tries') or []) or 'unknown'
            lines.append(f"- {_visit_name(v)}: {cause}" + (' (a missed request can be the cause)' if v.get('not_recorded') else ''))
    else:
        lines.append('Failures: none.')
    fell_back = [v for v in visits if br.fallbacks(v)]
    if fell_back:
        lines.append(f'Played after a fallback ({len(fell_back)}), not counted as played:')
        lines += [f'- {_visit_name(v)}: {br.failed_result(v, "fallback")}' for v in fell_back]
    lines += br.like_for_like_lines(visits)
    if not (err and status == 'ok'):  # the report's gate decides which runs get target verdicts; they never decide the baseline verdict
        lines += br.target_lines({'status': status, 'visits': visits})
    if reasons:
        lines.insert(0, 'Not usable as a baseline: ' + '; '.join(reasons) + '.')
    else:
        lines.insert(0, 'Usable as a baseline: no missed request, every planned side is there, the run is complete.')
    return not reasons, lines


def check_and_store(run_dir):
    """Check a run folder, save the lines as CHECK.txt in it, return (usable, lines)."""
    usable, lines = check_run(run_dir)
    try:
        with open(os.path.join(run_dir, CHECK_FILE), 'w') as f:
            f.write('\n'.join(lines) + '\n')
    except OSError:
        pass
    return usable, lines


def check_command(run_dir, store=False):
    """Prints the lines; returns the exit code (0 usable, 1 not). The check command only reads the folder; the run command stores."""
    usable, lines = (check_and_store if store else check_run)(run_dir)
    print('\n'.join(lines))
    return 0 if usable else 1
