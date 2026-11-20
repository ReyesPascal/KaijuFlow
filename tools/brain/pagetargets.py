"""The Speed Check page's judging of KaijuFlow against the other setups of a run: the targets of targets.json, a speed
test's targets, outcome and final bar, and like for like per title. Only build_page.py (the page code) uses it; the brain
tools no longer judge a run against other setups (#187): `check` judges it against the previous run (runcheck.judged_lines).
It goes with the page code when the page shows each run against the previous one (#195).

Pure logic: no Docker, no network.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
from brainreport import (  # noqa: E402
    JUDGED, LISTS, NO_FIGURE, RUN_ORDER, SIDE_NAMES, _plays, _run_label, _secs, _time, fail_figure, fails_words, run_lists,
    top_pick)

# The setups as the page's verdicts name them (GLOSSARY), the other setups of the runs before #185 among them.
SHORT_NAMES = {'kaijuflow': 'KaijuFlow', 'uu': 'Usenet Ultimate', 'altmount-addon': 'AltMount direct',
               'kaijuflow-1page': 'KaijuFlow with one page per indexer'}
EXPECTED_SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'expected-settings.json')
EPISODE = re.compile(r'\bS\d{1,3}[ ._-]?E\d{1,4}|\b\d{1,2}x\d{2}\b', re.I)  # a title that names an episode, not a whole season


# --------------------------------------------------------------------------- like for like

def like_for_like_rules(path=EXPECTED_SETTINGS):
    """{'film': cap, 'episode': cap, 'disc': compiled regex}: KaijuFlow's size caps (maxFileSize of movieFilters and tvFilters)
    and its "No disc images" drop rule, from the expected settings file. ValueError with a plain reason when they are not there.
    The stand-in no longer filters (#185); only the page's like-for-like comparison reads this."""
    try:
        with open(path) as f:
            entries = json.load(f)['expected']
        rules = next(e['settings'] for e in entries if 'kaijuflow' in e['copies'])
        drop = next(r for r in rules['movieFilters']['rules']['rankedRegexPatterns'] if r['name'] == 'No disc images')
        return {'film': int(rules['movieFilters']['maxFileSize']), 'episode': int(rules['tvFilters']['maxFileSize']),
                'disc': re.compile(drop['pattern'], re.I if 'i' in drop.get('flags', '') else 0)}
    except (OSError, ValueError, KeyError, TypeError, StopIteration, re.error) as e:
        raise ValueError(f'The like-for-like rules cannot be read from {os.path.basename(path)} ({type(e).__name__}): it needs '
                         'the KaijuFlow entry with movieFilters and tvFilters, their maxFileSize and the "No disc images" rule.') from None


def keep_post(title, size, kind, rules):
    """True when a post is on the like-for-like list: not a disc image, and not over the cap of its kind. In an episode search
    a post whose title names no episode is a season pack, which has no cap (KaijuFlow's maxFileSize leaves packs alone)."""
    if rules['disc'].search(title or ''):
        return False
    if size is None or (kind == 'episode' and not EPISODE.search(title or '')):
        return True
    return size <= rules[kind]


RESOLUTIONS = {'2160p': ('2160p', '4k|uhd'), '1080p': ('1080p', 'fhd'), '720p': ('720p', '')}  # (stated number, words)


def _first_of(text, pick):
    """The resolution whose pattern (pick: 0 the number, 1 the words) comes first in the text, or None."""
    words = '|'.join(f'(?P<r{res}>{w[pick]})' for res, w in RESOLUTIONS.items() if w[pick])
    m = re.search(rf'(?<![a-z0-9])(?:{words})(?![a-z0-9])', text)
    return m and m.lastgroup[1:]


def resolution(text):
    """The resolution a top pick's name or list text states ('2160p', '1080p', '720p'), or None when it states none (#154).
    A stated number wins over the words 4K, UHD (2160p) and FHD (1080p), which count only when no number is stated: "1080p
    UHD BluRay" is a 1080p encode from a 4K disc. A side's own label ("AltMount FHD - ... [1080p]", "4K BluRay") is read
    with the release name as one text, so the first stated number wins (tools/brain/docs/rules.md, "Like for like")."""
    text = str(text or '').lower()
    return _first_of(text, 0) or _first_of(text, 1)


def _rule_break(v, rules):
    """Why a visit's top pick is outside the like-for-like rules (#142), or None: a disc image, or a served file over the size
    cap of its kind. The served size is held to the cap the indexer's post size is held to; the file is never larger than
    its post, so a file over the cap means its post was over it too. Season packs have no cap (keep_post)."""
    pick = top_pick(v)
    kind = {'movie': 'film', 'series': 'episode'}.get(v.get('kind'))
    if not pick or not rules or not kind or keep_post(pick['name'], pick['size'], kind, rules):
        return None
    if rules['disc'].search(str(pick['name'] or '')):
        return 'a disc image'
    return f"{pick['size'] / 1e9:.1f} GB served, over the cap for {'a film' if kind == 'film' else 'an episode'} " \
           f"({rules[kind] / 1e9:.1f} GB)"


def unlike_titles(visits):
    """{side: {title: why}}: the titles whose top picks are not like for like between KaijuFlow and another setup (not a
    KaijuFlow variant such as one page per indexer, which no target is held against), with the first round that shows it.
    Not like for like: in one round the two top picks state different resolutions, or either one breaks the like-for-like
    rules (_rule_break). A title is left out of judging KaijuFlow against that side (#143)."""
    try:
        rules = like_for_like_rules()
    except ValueError:  # the expected settings file cannot be used: the preflight says so; resolutions are still compared
        rules = None
    by = {(v['side'], v['title'], _run_label(v['phase'], v['round'])): v for v in visits if v.get('tries')}
    labels = [_run_label(phase, rnd) for phase, rnd in RUN_ORDER]
    me = SIDE_NAMES[JUDGED]
    out = {}
    for side in [s for s in SIDE_NAMES if not s.startswith(JUDGED)]:
        for title in dict.fromkeys(v['title'] for v in visits):
            for label in labels:
                mine, theirs = by.get((JUDGED, title, label)), by.get((side, title, label))
                if not mine or not theirs:
                    continue
                a, b = (resolution((top_pick(x) or {}).get('name')) for x in (mine, theirs))
                if a and b and a != b:
                    why = f"{me}'s top pick is {a}, {SIDE_NAMES[side]}'s is {b} ({label})"
                else:
                    broken = [(x, r) for x in (mine, theirs) for r in [_rule_break(x, rules)] if r]
                    why = broken and (f"{SIDE_NAMES[broken[0][0]['side']]}'s top pick breaks the like-for-like rules "
                                      f"({label}): {broken[0][1]}")
                if why:
                    out.setdefault(side, {})[title] = why
                    break
    return out


# --------------------------------------------------------------------------- targets

TARGETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'targets.json')
# What each measure is held against: a fixed limit, another side (against), or either of the two.
TARGET_MEASURES = {'plays per round': 'limit', 'plays': 'against',
                   'cold start': 'either', 'warm start': 'either', 'cold list': 'either', 'warm list': 'either'}


def _plays_text(plays):
    """'p of n' for (top picks that played, top picks counted), or 'no figure' when none was counted."""
    return f'{plays[0]} of {plays[1]}' if plays[1] else NO_FIGURE


MET, NOT_MET, NOT_MEASURED = 'met', 'not met', 'not measured'


def _verdict(result, slower_s=None, noise=None, value=None, limit=None, **held):
    """A target's verdict as a value: the result (MET, NOT_MET or NOT_MEASURED); for a time target that is not met, how many
    seconds KaijuFlow is slower than what it is held against; the noise: None, or KaijuFlow's two rounds of the phase
    with how far the target is met or missed by, when those two rounds differ by more than that; and the two figures the
    result compares (None when not measured): KaijuFlow's value and the limit it is held to, both in seconds for a time
    target (the limit includes the margin), both (top picks that played, top picks counted) for a plays target, both fail
    figures (fail_figure) for a speed test's fails target. A speed test's verdict also names what the two figures were
    judged on (`held`): 'held_against', the setup the limit is from (None for a fixed limit), and 'left_out', how many
    titles were left out of both figures as not like for like."""
    return {'result': result, 'slower_s': slower_s, 'noise': noise, 'value': value, 'limit': limit, **held}


def verdict_text(verdict):
    """The Result words of a verdict, as the report's table and the check's lines show them."""
    text = verdict['result'].capitalize()
    if verdict['result'] == NOT_MET and verdict['slower_s'] is not None:
        text += f" ({_secs(verdict['slower_s'])} slower)"
    noise = verdict['noise']
    if noise:
        a, b = noise['rounds']
        text += (f", inside the noise: {SIDE_NAMES[JUDGED]}'s two {noise['phase']} rounds differ by {_secs(abs(a - b))} "
                 f"({a:.2f} and {b:.2f} s), more than the {_secs(noise['by'])} the target is "
                 f"{'missed' if verdict['result'] == NOT_MET else 'met'} by")
    return text


def _measure_target(visits, t, unlike=None):
    """(measured values, verdict) of one entry of the targets file. A target held against a side leaves out the titles that
    are not like for like between KaijuFlow and that side (`unlike`, as unlike_titles gives it), and says how many."""
    left_out = (unlike or {}).get(t.get('against'), {})
    if left_out:
        visits = [v for v in visits if v['title'] not in left_out]
        n = len(left_out)
        measured, verdict = _measure_target(visits, t)
        return f"{measured} ({n} title{'' if n == 1 else 's'} left out: not like for like)", verdict
    me, margin = SIDE_NAMES[JUDGED], t['margin']
    if t['measure'] == 'plays per round':  # every round the run holds, cold and warm
        rounds = {phase: [x for p, r in RUN_ORDER if p == phase for x in [_plays(visits, JUDGED, phase, r)] if x[1]]
                  for phase in ('cold', 'warm')}
        measured = ', '.join(f'{phase} ' + (' and '.join(_plays_text(x) for x in rs) or NO_FIGURE) for phase, rs in rounds.items())
        if not all(rounds.values()):
            return measured, _verdict(NOT_MEASURED)
        met = all(p >= t['limit'] - margin and n - p <= margin for rs in rounds.values() for p, n in rs)
        every = [x for rs in rounds.values() for x in rs]
        value = (sum(p for p, _ in every), sum(n for _, n in every))
        limit = (sum(t['limit'] - margin for _ in every), value[1])
        return measured, _verdict(MET if met else NOT_MET, value=value, limit=limit)
    if t['measure'] == 'plays':  # the share of top picks that played, every round together
        (p, n), (q, m) = _plays(visits, JUDGED), _plays(visits, t['against'])
        measured = f"{me} {_plays_text((p, n))}, {SIDE_NAMES[t['against']]} {_plays_text((q, m))}"
        if not n or not m:
            return measured, _verdict(NOT_MEASURED)
        # At least as often, and more often unless both play every time (spec #58; owner, 2026-11-15): a tie at the
        # maximum is met, any other tie is not.
        more_often = p * m > (q - margin * m) * n
        both_every_time = p == n and q == m
        return measured, _verdict(MET if more_often or both_every_time else NOT_MET, value=(p, n), limit=(q, m))
    phase, what = t['measure'].split()
    mine = _time(visits, JUDGED, phase, what)
    ref = t['limit'] if 'limit' in t else _time(visits, t['against'], phase, what)
    measured = f'{me} {_secs(mine)}' + ('' if 'limit' in t else f", {SIDE_NAMES[t['against']]} {_secs(ref)}")
    if mine is None or ref is None:
        return measured, _verdict(NOT_MEASURED)
    over = round(mine - ref - margin, 2)  # above 0: the target is missed by this much; below: met by this much
    a, b = (_time(visits, JUDGED, phase, what, r) for r in (1, 2))
    noise = ({'phase': phase, 'rounds': (a, b), 'by': abs(over)}
             if a is not None and b is not None and round(abs(a - b), 2) > abs(over) else None)
    figures = {'value': mine, 'limit': round(ref + margin, 2)}
    return measured, _verdict(MET, noise=noise, **figures) if over <= 0 else _verdict(NOT_MET, mine - ref, noise, **figures)


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def load_targets(path=TARGETS_FILE):
    """The entries of the targets file. ValueError with a plain reason when the file or one of its entries cannot be used."""
    name = os.path.basename(path)
    try:
        with open(path) as f:
            targets = json.load(f)['targets']
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f'{name} cannot be read: {type(e).__name__}') from None
    if not isinstance(targets, list):
        raise ValueError(f'{name} cannot be read: "targets" is not a list')
    for i, t in enumerate(targets, 1):
        if not isinstance(t, dict) or not isinstance(t.get('target'), str):
            why = 'it has no target text'
        elif t.get('measure') not in TARGET_MEASURES:
            why = f"the measure \"{t.get('measure')}\" is not known"
        elif not _is_number(t.get('margin')) or t['margin'] < 0:
            why = 'the margin is not a number from 0 up'
        elif 'against' in t and t['against'] not in SIDE_NAMES:
            why = f"the side \"{t['against']}\" is not known"
        elif TARGET_MEASURES[t['measure']] == 'limit' and ('against' in t or not _is_number(t.get('limit'))):
            why = f"\"{t['measure']}\" takes a fixed limit, not a side"
        elif TARGET_MEASURES[t['measure']] == 'against' and ('limit' in t or 'against' not in t):
            why = f"\"{t['measure']}\" takes a side (against), not a fixed limit"
        elif ('against' in t) == ('limit' in t) or ('limit' in t and not _is_number(t['limit'])):
            why = f"\"{t['measure']}\" takes a side (against) or a fixed limit, one of the two"
        else:
            continue
        raise ValueError(f'{name}, entry {i}: {why}')
    return targets


def target_results(visits, path=TARGETS_FILE):
    """[(target, measured values, verdict)] for every entry of the targets file, in its order."""
    unlike = unlike_titles(visits)
    return [(t['target'],) + _measure_target(visits, t, unlike) for t in load_targets(path)]


SPEED_MEASURES = ('fails', 'cold title to video', 'warm title to video')  # a speed test's measures (#169), judged per list


def load_speed_targets(path=TARGETS_FILE):
    """The speed test's part of the targets file: {'targets': [entry]}. ValueError with a plain reason when it cannot be used."""
    name = os.path.basename(path)
    try:
        with open(path) as f:
            speed = json.load(f)['speed_test']
        targets = speed['targets']
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f'{name} cannot be read: {type(e).__name__} in "speed_test"') from None
    for i, t in enumerate(targets, 1):
        if not isinstance(t, dict) or not isinstance(t.get('target'), str):
            why = 'it has no target text'
        elif t.get('measure') not in SPEED_MEASURES:
            why = f"the measure \"{t.get('measure')}\" is not known"
        elif t['measure'] == 'warm title to video' and not _is_number(t.get('limit')):
            why = '"warm title to video" takes a fixed limit'
        else:
            continue
        raise ValueError(f'{name}, speed test entry {i}: {why}')
    if not isinstance(speed.get('final_bar'), str):
        raise ValueError(f'{name}, speed test: the final bar has no text')
    return speed


def _others(visits):
    """The setups KaijuFlow is held against in a run: every side but KaijuFlow and its variants, in SIDE_NAMES order."""
    return [s for s in SIDE_NAMES if not s.startswith(JUDGED) and any(v['side'] == s for v in visits)]


def _pair(visits, side, lst, unlike):
    """KaijuFlow against one other setup on one list, on the titles that are like for like between the two:
    {'side', 'mine', 'theirs', 'left_out', 'rounds'}, where mine and theirs are fail figures (fail_figure) with 'video'
    added (the median cold title to video, None without a top pick that played), left_out is how many of the list's titles
    were left out of both, and rounds is KaijuFlow's cold title to video in each of its two cold rounds."""
    left_out = unlike.get(side, {})
    vs = [v for v in visits if v.get('list') == lst and v['title'] not in left_out]
    titles = {v['title'] for v in visits if v.get('list') == lst}

    def figures(s):
        return {**fail_figure(vs, s, lst=lst), 'video': _time(vs, s, 'cold', 'video', lst=lst)}
    return {'side': side, 'mine': figures(JUDGED), 'theirs': figures(side), 'left_out': len(titles & set(left_out)),
            'rounds': tuple(_time(vs, JUDGED, 'cold', 'video', r, lst) for r in (1, 2))}


def left_out_words(n):
    """'1 title left out: not like for like', or '' when none was."""
    return f"{n} title{'' if n == 1 else 's'} left out: not like for like" if n else ''


def _fails_part(f):
    return [fails_words(f)]


def _video_part(f):
    return [_secs(f['video']), fails_words(f)]


def _part_text(part):
    """'3.50 s (1 title failed · 1 of 8 plays; more failed plays: not held against it)' from [main, detail...]."""
    main, *details = part
    return main + (f" ({'; '.join(details)})" if details else '')


def _pairs_text(pairs, mine, part, note=None):
    """'KaijuFlow 1 title failed · 1 of 8 plays, Usenet Ultimate 2 titles failed · 2 of 8 plays, AltMount direct 1 title
    failed · 1 of 6 plays (KaijuFlow 1 title failed · 1 of 6 plays on the same titles; 1 title left out: not like for
    like)': KaijuFlow's figure, then each other setup's, with what note(pair) says of it and KaijuFlow's figure on the same
    titles when some were left out."""
    out = [f'{SHORT_NAMES[JUDGED]} {_part_text(part(mine))}']
    for p in pairs:
        main, *details = part(p['theirs'])
        details += [x for x in [note and note(p)] if x]
        if p['left_out']:
            details.append(f"{SHORT_NAMES[JUDGED]} {_part_text(part(p['mine']))} on the same titles; {left_out_words(p['left_out'])}")
        out.append(f"{SHORT_NAMES[p['side']]} {_part_text([main] + details)}")
    return ', '.join(out)


def _vs(p):
    """'KaijuFlow 1 title failed · 2 of 8 plays against Usenet Ultimate 0 titles failed · 0 of 8 plays', the two figures of
    a pair on the titles they were judged on, with how many were left out."""
    words = (f"{SHORT_NAMES[JUDGED]} {fails_words(p['mine'])} against {SHORT_NAMES[p['side']]} "
             f"{fails_words(p['theirs'])}")
    return words + (f"; {left_out_words(p['left_out'])}" if p['left_out'] else '')


def _time_verdict(mine, limit, rounds, phase, strict=False, **held):
    """The verdict of a time target: met when KaijuFlow's figure is no higher than the limit (lower, when strict), with
    the noise of KaijuFlow's two rounds of the phase (`rounds`) as the targets of before have it."""
    over = round(mine - limit, 2)  # above 0: missed by this much; below: met by this much
    a, b = rounds
    noise = ({'phase': phase, 'rounds': (a, b), 'by': abs(over)}
             if a is not None and b is not None and round(abs(a - b), 2) > abs(over) else None)
    if over < 0 or (over == 0 and not strict):
        return _verdict(MET, noise=noise, value=mine, limit=limit, **held)
    return _verdict(NOT_MET, over, noise, value=mine, limit=limit, **held)


def _judge_fails(visits, lst, pairs, entry):
    """Target 1 on one list: KaijuFlow fails no more plays than any other setup, and none on the easy list. Against a
    setup it is judged on the titles like for like with it; the no-fail rule of the easy list is a fixed limit and keeps
    every title. The verdict's figures are the ones the result was decided on: on the easy list KaijuFlow's against no
    fail, on the hard list KaijuFlow's against the setup it is closest to failing more than (on the same titles)."""
    mine = _pair(visits, JUDGED, lst, {})['mine']
    measured = _pairs_text(pairs, mine, _fails_part)
    if not mine['counted'] or not pairs:
        return measured, _verdict(NOT_MEASURED)
    met = all(p['mine']['fails'] <= p['theirs']['fails'] for p in pairs) and not (lst == 'easy' and mine['fails'])
    if lst == 'easy':
        none = {'titles': 0, 'fails': 0, 'counted': mine['counted']}
        return measured, _verdict(MET if met else NOT_MET, value=mine, limit=none, held_against=None, left_out=0)
    p = max(pairs, key=lambda p: (p['mine']['fails'] - p['theirs']['fails'], -p['left_out']))
    return measured, _verdict(MET if met else NOT_MET, value=p['mine'], limit=p['theirs'], held_against=p['side'],
                              left_out=p['left_out'])


def _judge_cold_video(visits, lst, pairs, entry):
    """Target 2 on one list: KaijuFlow's median cold title to video, over the titles it played, is no slower than that of
    any setup with as few fails or fewer (owner, 2026-11-15): a faster setup that fails more plays than KaijuFlow is not
    held against it (fails come first), nor is a setup with no title to video."""
    mine = _pair(visits, JUDGED, lst, {})['mine']
    measured = _pairs_text(pairs, mine, _video_part,
                           lambda p: 'more failed plays: not held against it' if p['theirs']['fails'] > p['mine']['fails'] else None)
    if mine['video'] is None or not pairs:
        return measured, _verdict(NOT_MEASURED)
    held = [p for p in pairs if p['theirs']['fails'] <= p['mine']['fails'] and None not in (p['mine']['video'], p['theirs']['video'])]
    if not held:
        return measured + '; every other setup fails more plays', _verdict(MET, value=mine['video'], held_against=None, left_out=0)
    p = max(held, key=lambda p: p['mine']['video'] - p['theirs']['video'])  # the setup KaijuFlow is furthest behind
    return measured, _time_verdict(p['mine']['video'], p['theirs']['video'], p['rounds'], 'cold', held_against=p['side'],
                                   left_out=p['left_out'])


def _judge_warm_video(visits, lst, pairs, entry):
    """Target 3 on one list: KaijuFlow's median warm title to video is under the limit (1.00 s is not under 1 s)."""
    mine = _time(visits, JUDGED, 'warm', 'video', lst=lst)
    measured = f'{SHORT_NAMES[JUDGED]} {_secs(mine)}'
    if mine is None:
        return measured, _verdict(NOT_MEASURED)
    rounds = tuple(_time(visits, JUDGED, 'warm', 'video', r, lst) for r in (1, 2))
    return measured, _time_verdict(mine, entry['limit'], rounds, 'warm', strict=True, held_against=None, left_out=0)


SPEED_JUDGES = {'fails': _judge_fails, 'cold title to video': _judge_cold_video, 'warm title to video': _judge_warm_video}


# The three outcomes of the hard list, decided before the first speed test (ADR 0007, spec #159), and what each says to do.
OUTCOME_TUNE, OUTCOME_NO_PRE_LIST_CHECK, OUTCOME_BUG = 'tune its speed', 'try without its pre-list check', 'find the bug'
OUTCOME_HEAD = 'Outcome on the hard list: '
ALTMOUNT = 'altmount-addon'  # the setup the outcome compares KaijuFlow with: AltMount direct


def _outcome(visits, unlike):
    """{'outcome', 'text'}: which outcome the hard list gave, KaijuFlow against AltMount direct on the titles like for
    like between the two (failed plays first, then the median cold title to video). The same fails with KaijuFlow no
    slower is "as reliable and no slower: tune its speed" (owner, 2026-11-15). Outcome None when it cannot be named."""
    if 'hard' not in run_lists(visits) or ALTMOUNT not in _others(visits):
        why = 'the run has no hard list' if 'hard' not in run_lists(visits) else f'{SHORT_NAMES[ALTMOUNT]} is not in the run'
        return {'outcome': None, 'text': f'{OUTCOME_HEAD}not named: {why}.'}
    p = _pair(visits, ALTMOUNT, 'hard', unlike)
    me, them, (a, b) = SHORT_NAMES[JUDGED], SHORT_NAMES[ALTMOUNT], (p['mine'], p['theirs'])
    if a['fails'] < b['fails']:
        return {'outcome': OUTCOME_TUNE, 'text': f'{OUTCOME_HEAD}{me} fails fewer plays than {them} ({_vs(p)}), so tune its speed.'}
    if a['fails'] > b['fails']:
        return {'outcome': OUTCOME_BUG, 'text': f"{OUTCOME_HEAD}{them} fails fewer plays than {me} ({_vs(p)}), so {me}'s "
                                                'checking has a bug to find first.'}
    if a['video'] is None or b['video'] is None:
        return {'outcome': None, 'text': f'{OUTCOME_HEAD}not named: {me} and {them} fail as many plays ({_vs(p)}), and one '
                                         'of them has no cold title to video.'}
    video = f"cold title to video {_secs(a['video'])} against {_secs(b['video'])}"
    if b['video'] < a['video']:
        return {'outcome': OUTCOME_NO_PRE_LIST_CHECK, 'text': (
            f"{OUTCOME_HEAD}{me} and {them} fail as many plays ({_vs(p)}) and {them} is faster (cold title to video "
            f"{_secs(b['video'])} against {_secs(a['video'])}), so try {me} without its own pre-list check, behind AltMount.")}
    return {'outcome': OUTCOME_TUNE, 'text': f'{OUTCOME_HEAD}{me} is as reliable and no slower: tune its speed ({_vs(p)}; {video}).'}


def _bar_on_list(visits, lst, pairs):
    """{'result', 'why'}: the final bar on one list. Fewest fails: no more failed plays than any other setup, any tie
    counting as fewest (owner, 2026-11-15); then strictly the fastest median cold title to video among the setups with as
    few. A setup that fails more is not held against KaijuFlow's speed. Each comparison is on the titles like for like."""
    me, mine = SHORT_NAMES[JUDGED], _pair(visits, JUDGED, lst, {})['mine']
    if not mine['counted'] or not pairs:
        return {'result': NOT_MEASURED, 'why': f'no {"figure" if pairs else "other setup"} to judge it on'}
    for p in pairs:
        if p['theirs']['fails'] < p['mine']['fails']:
            return {'result': NOT_MET, 'why': f"{SHORT_NAMES[p['side']]} fails fewer plays ({_vs(p)})"}
    tied = [p for p in pairs if p['theirs']['fails'] == p['mine']['fails']]
    for p in tied:
        a, b = p['mine'], p['theirs']
        if a['video'] is None or (b['video'] is not None and b['video'] <= a['video']):
            return {'result': NOT_MET, 'why': f"{SHORT_NAMES[p['side']]} fails as few plays ({_vs(p)}) and is as fast or "
                                              f"faster (cold title to video {_secs(b['video'])} against {me}'s {_secs(a['video'])})"}
    speed = ('; '.join(f"cold title to video {_secs(p['mine']['video'])} against {SHORT_NAMES[p['side']]}'s "
                       f"{_secs(p['theirs']['video'])}" for p in tied) if tied else 'no other setup fails as few plays')
    closest = min(pairs, key=lambda p: (p['theirs']['fails'] - p['mine']['fails'], p['left_out']))  # the next fewest
    return {'result': MET, 'why': f"{me} fails the fewest plays ({_vs(closest)}) and is the fastest among setups with as "
                                  f'few ({speed})'}


def _final_bar(visits, lists, text):
    """{'target', 'lists': {list: {'result', 'why'}}, 'verdict'}: the final bar on each list and on both together. Met
    when met on both lists; not measured when the run lacks a list or a list holds no figure for it."""
    results = [r['result'] for r in lists.values()]
    if set(run_lists(visits)) != set(LISTS) or NOT_MEASURED in results:
        result = NOT_MEASURED
    else:
        result = MET if all(r == MET for r in results) else NOT_MET
    return {'target': text, 'lists': lists, 'verdict': _verdict(result)}


def speed_test_judgement(visits, path=TARGETS_FILE):
    """The judgement of a tagged run (#169), for the check, the report and the page: {'targets': [{'number', 'target',
    'list', 'measured', 'verdict'}], 'outcome': {'outcome', 'text'}, 'final_bar': {'target', 'lists', 'verdict'}}: each
    target of the targets file's speed test part judged on each list of the run, list by list; the outcome of the hard
    list (_outcome); and the owner's final bar (_final_bar), which is shown apart and never counted with the targets.
    ValueError when the targets file cannot be used."""
    speed = load_speed_targets(path)
    unlike = unlike_titles(visits)
    rows, bar = [], {}
    for lst in run_lists(visits):
        pairs = [_pair(visits, s, lst, unlike) for s in _others(visits)]
        for n, t in enumerate(speed['targets'], 1):
            measured, verdict = SPEED_JUDGES[t['measure']](visits, lst, pairs, t)
            rows.append({'number': n, 'target': t['target'], 'list': lst, 'measured': measured, 'verdict': verdict})
        bar[lst] = _bar_on_list(visits, lst, pairs)
    return {'targets': rows, 'outcome': _outcome(visits, unlike), 'final_bar': _final_bar(visits, bar, speed['final_bar'])}


def targets_not_judged(status):
    """The one gate of the targets, which the report and the check both go through: None for a finished run (status
    'ok'), else why its targets are not judged. A stopped, null or failed run holds part of its plays or none, so no
    verdict is made from it."""
    if status == 'ok':
        return None
    why = {'stopped': 'the run was stopped before its last play',
           'null': 'the run is null (an indexer said its limit was reached)'}.get(status, 'the run did not finish')
    return f'{why}, and the targets are judged on a finished run alone'
