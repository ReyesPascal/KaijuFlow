"""Check a finished run folder: can it serve as a baseline?

    python3 -I tools/brain/brainrun.py check --run <run folder>

Prints about a dozen plain lines and exits 0 when the run is usable, 1 when it is not
(a request the recording did not hold, a planned side that is absent, a null, stopped or failed run,
a recording folder, or a run folder that cannot be read). It then prints one line per side and list (list_lines) and
judges KaijuFlow's run per list against the previous run on the same recording, kept or not kept (judged_lines, rules.md
"Judged against the previous run"); the verdict does not change the exit code.
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


def _round_title(v):
    return f"{v['phase'].capitalize()} {v['round']} {v['title']}"


def _line_head(side, lst):
    """'KaijuFlow, hard list', or 'KaijuFlow, every title' for a run without tags: how a per-list line starts."""
    return f"{_side(side)}, {f'{lst} list' if lst else 'every title'}"


def list_lines(visits, sides):
    """Per side and list (#185), one line: the fails (titles and plays, each failed play named), the fallbacks (each named
    with its extra seconds) and the median cold and warm title to video. A run without tags gets one line for every title."""
    out = []
    for s in sides:
        for x in br.run_lists(visits) or [None]:
            vs = [v for v in visits if v['side'] == s and x in (None, v.get('list'))]
            if not vs:
                continue
            failed = [_round_title(v) for v in br.fail_visits(vs, s)]
            fell_back = [f'{_round_title(v)}, {br.fallback_text(v)}' for v in vs if br.fallbacks(v)]
            out.append(f"{_line_head(s, x)}: fails {br.fails_words(br.fail_figure(vs, s))}"
                       + (f" ({'; '.join(failed)})" if failed else '')
                       + (f"; fallbacks {len(fell_back)} ({'; '.join(fell_back)})" if fell_back else '; fallbacks none')
                       + ''.join(f'; {phase} title to video {br.secs_text(br.side_time(vs, s, phase, "video"))}' for phase in ('cold', 'warm'))
                       + '.')
    return out


KEPT, NOT_KEPT, NOT_JUDGED = 'kept', 'not kept', 'not judged'


def _against(now, was):
    """'better', 'same' or 'worse' for a figure where less is better (failed plays, seconds), or None when either is
    missing. Seconds are compared as printed, to the hundredth."""
    if now is None or was is None:
        return None
    now, was = round(now, 2), round(was, 2)
    return 'better' if now < was else 'worse' if now > was else 'same'


def _fallback_secs(x):
    return 'unknown' if x is None else f'{x:.2f} s'


def _why_not_judged(meta):
    """Why this run's lists cannot be judged (a run that did not finish, or a short run, played fewer plays than the
    previous run, so fewer fails says nothing), or None when they can (spec #183)."""
    status = meta.get('status')
    if status == 'stopped':
        return 'this run was stopped'
    if status != 'ok':
        return f'this run did not finish (status {status})'
    if meta.get('short'):
        return f"this run is short ({meta['short']})"
    return None


def _compared(name, now, was, words, by):
    """'cold title to video 1.50 s (was 2.00 s), better': one figure of this run against the previous run's."""
    return f"{name} {words(now)} (was {words(was)}), {by or 'not compared'}"


def judged_lines(run_dir, meta, visits):
    """KaijuFlow's run judged against its previous run on the same recording (#186, rules.md "Judged against the previous
    run"): per list, the fails and the median cold title to video, each better, same or worse than the previous run's,
    and kept or not kept; then the verdict over every list. Each list's line also shows, against the previous run's, its
    median warm title to video (spec #183) and its fallback time (the fallbacks' extra seconds added up,
    brainreport.fallback_total_s, #187); the verdict leaves those out. A previous run with another Browse pause is not
    compared, with why (#205, rules.md "Browse pause")."""
    side, recording = br.JUDGED, meta.get('recording')
    prev = br.run_before(run_dir, recording)
    if prev is None:
        return [f'Against the previous run: not compared, no earlier run on the same recording ({recording}).']
    was, now = (br.browse_pause_of(m) for m in (prev, meta))
    if was != now:  # #205: the pause lets work begun at list time show in the start, so it is no like for like
        return [f"Against the previous run on the same recording ({recording}): {prev['folder']}: not compared, its Browse pause "
                f"was {br.pause_text(was)} and this run's is {br.pause_text(now)}; a run is judged only against a run with the same pause."]
    out, verdicts = [f"Against the previous run on the same recording ({recording}): {prev['folder']}."], []
    why_not = _why_not_judged(meta)
    for x in br.run_lists(visits) or [None]:
        fails = [br.fail_figure(vs, side, lst=x) for vs in (visits, prev['visits'])]
        cold, warm = ([br.side_time(vs, side, phase, 'video', lst=x) for vs in (visits, prev['visits'])]
                      for phase in ('cold', 'warm'))
        by_fails = _against(*[f['fails'] if f['counted'] else None for f in fails])
        by_cold = _against(*cold)
        fell_back = [br.fallback_count(vs, side, lst=x) for vs in (visits, prev['visits'])]
        fallback_secs = [br.fallback_total_s(vs, side, lst=x) for vs in (visits, prev['visits'])]
        if why_not:
            verdict = NOT_JUDGED
        elif by_fails == 'worse':
            verdict = NOT_KEPT
        elif by_fails is None or by_cold is None:
            verdict = NOT_JUDGED
        else:
            verdict = KEPT if by_cold != 'worse' else NOT_KEPT
        verdicts.append(verdict)
        figures = [_compared('fails', *fails, br.fails_words, by_fails),
                   _compared('cold title to video', *cold, br.secs_text, by_cold),
                   # shown, never part of the verdict (spec #183; owner, 2026-11-20, #187)
                   _compared('warm title to video', *warm, br.secs_text, _against(*warm)),
                   _compared('fallbacks', *fell_back, str, _against(*fell_back)),
                   _compared('fallback time', *fallback_secs, _fallback_secs, _against(*fallback_secs))]
        out.append(f"{_line_head(side, x)}: {'; '.join(figures)}. {verdict.capitalize()}"
                   + (f': {why_not}.' if why_not else '.'))
    if why_not:
        return out + [f'Verdict against the previous run: {NOT_JUDGED}, {why_not}.']
    overall = NOT_KEPT if NOT_KEPT in verdicts else NOT_JUDGED if NOT_JUDGED in verdicts else KEPT
    return out + [f'Verdict against the previous run: {overall}.']


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
    if br.never_compared(meta):
        reasons.append(f"marked never compared with ({meta.get('label') or meta.get('name')})")
    if meta.get('short'):  # last: the reasons that say what went wrong with a plan that was played come first
        reasons.append(f"short run ({meta['short']})")
    lines.append(f"Run: {meta.get('name')}, status: {status}.")
    sides = meta.get('sides') or []
    seen = {v['side'] for v in visits}
    absent = [s for s in sides if s not in seen]
    if absent and status == 'ok':
        reasons.append('planned side absent: ' + ', '.join(_side(s) for s in absent))
    # top picks played per side, cold and warm (a top pick "played" when its visit served video, a fallback too: br.plays)
    for s in sides:
        by = {}
        for phase in ('cold', 'warm'):
            vs = [v for v in visits if v['side'] == s and v['phase'] == phase]
            by[phase] = (sum(1 for v in vs if br.plays(v)), len(vs))
        lines.append(br.top_picks_played([(s, by)]))
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
    if fell_back:  # a fallback counts as played, its extra seconds in its title to video (#185)
        lines.append(f'Played after a fallback ({len(fell_back)}), counted as played:')
        lines += [f'- {_visit_name(v)}: {br.fallback_text(v)}' for v in fell_back]
    lines += list_lines(visits, sides)
    lines += judged_lines(run_dir, meta, visits)
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
