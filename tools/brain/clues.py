"""The Clue library (spec #279, #283): small reusable yes / no / can't-tell tests, registered here by name.

A Clue answers one question about one failure from its evidence folder (or, from #284, a live read-only look at Usenet
or AltMount): it is a function `(evidence, failure) -> (answer, facts)`, `evidence` an `evidence.Saved`, `failure` the
failure Diagnosis is proving (`release`, the Source that failed, or None for a play with no failed Source; `kind`;
`step`, its failing step line), `answer` one of YES, NO, CANT, and `facts` the lines and fields it saw, quoted from the
evidence so every claim can be checked against it. A Casebook entry's `confirm` is a recipe of Clue names, each with the
answer that proves the cause (tools/brain/casebook/README.md); `casebook.py check` counts a recipe as a confirming test
that runs only when every Clue it names is registered here. A new Clue is built only for a truly new question, and
nothing is ever deleted from the library. Each Clue is tried in `npm run check:brain` on two real captures, the cause
present (yes) and absent (no): test_diagnosis.py.
"""
import collections
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402

YES, NO, CANT = 'yes', 'no', "can't tell"
ANSWERS = (YES, NO, CANT)
Clue = collections.namedtuple('Clue', 'name question run')
CLUES = {}

PREPARE = ('nzb_fetch', 'unscramble', 'upload', 'import_wait', 'first_byte')
GAVE_UP = ('read-error', 'timeout', 'error')  # Unscramble results that leave a Scrambled RAR set as it came
FACT_CHARS = 300


def clue(name, question):
    """Registers a Clue under `name`; `question` is the yes/no question it answers."""
    def register(fn):
        if name in CLUES:
            raise ValueError(f'Clue {name} is registered twice')
        CLUES[name] = Clue(name, question, fn)
        return fn
    return register


def run(name, evidence, failure):
    """{'clue', 'answer', 'facts'} of one Clue on one failure. A Clue that raises answers can't tell, with the error."""
    try:
        answer, facts = CLUES[name].run(evidence, failure)
    except Exception as e:  # noqa: BLE001  (one broken Clue never stops a diagnosis)
        answer, facts = CANT, [f'the Clue failed: {type(e).__name__}: {e}']
    if answer not in ANSWERS:
        answer, facts = CANT, [f'the Clue gave {answer!r}, not yes, no or can\'t tell']
    return {'clue': name, 'answer': answer, 'facts': [fact(f) for f in facts]}


def fact(text):
    text = str(text).strip()
    return text if len(text) <= FACT_CHARS else text[:FACT_CHARS - 1] + '…'


def step_text(s):
    """A step line as a fact: its JSON fields, as the log wrote them."""
    keep = ('step', 'source', 'ms', 'ok', 't', 'title', 'status', 'result', 'parts', 'retry', 'reason', 'job')
    return '[KF-STEP] ' + ', '.join(f'{k}={s[k]}' for k in keep if k in s)


def source_steps(evidence, release):
    return [s for s in evidence.steps if s.get('title') == release]


def _ts(line):
    try:
        return br.parse_ts(line.split(' ', 1)[0])
    except (ValueError, IndexError):
        return None


def altmount_lines(evidence, release):
    """AltMount's log lines while one Source was prepared: from its first prepare step's start to a second after its last
    prepare step, leaving out lines that name another of the play's releases and not this one. None when the Source has
    no prepare step (nothing was handed to AltMount)."""
    steps = [s for s in source_steps(evidence, release) if s.get('step') in PREPARE]
    if not steps:
        return None
    lo = min(br.parse_ts(s['t']) - datetime.timedelta(milliseconds=s.get('ms') or 0) for s in steps)
    hi = max(br.parse_ts(s['t']) for s in steps) + datetime.timedelta(seconds=1)
    others = {s.get('title') for s in evidence.steps if s.get('title') and s.get('title') != release}
    others = {o for o in others if o not in release}
    out = []
    for line in evidence.am_lines:
        t = _ts(line)
        if t is None or not lo <= t <= hi:
            continue
        if release not in line and any(o in line for o in others):
            continue
        out.append(line)
    return out


def _altmount_said(evidence, failure, pattern, what):
    if not failure.get('release'):
        return CANT, ['the failure names no Source, so no AltMount import is tied to it']
    lines = altmount_lines(evidence, failure['release'])
    if lines is None:
        return CANT, [f"{failure['release']} has no prepare step, so AltMount was not handed it"]
    if not lines:
        return CANT, [f"AltMount's log has no line while {failure['release']} was prepared"]
    said = [line for line in lines if re.search(pattern, line)]
    if said:
        return YES, said[:3]
    return NO, [f"none of AltMount's {len(lines)} lines while {failure['release']} was prepared says {what}"]


@clue('unscramble-read-error', 'Did Unscramble end in read-error for the Source that failed?')
def unscramble_read_error(evidence, failure):
    lines = [s for s in source_steps(evidence, failure.get('release')) if s.get('step') == 'unscramble']
    if not lines:
        return CANT, [f"no unscramble line for {failure.get('release')}"]
    last = lines[-1]  # a read-error is retried once (#245): the last line is the result
    return (YES if last.get('result') == 'read-error' else NO), [step_text(s) for s in lines]


@clue('original-uploaded-after-unscramble',
      'Was the Source uploaded as it came (still scrambled) after Unscramble gave up on it?')
def original_uploaded_after_unscramble(evidence, failure):
    steps = source_steps(evidence, failure.get('release'))
    unscrambles = [s for s in steps if s.get('step') == 'unscramble']
    if not unscrambles:
        return CANT, [f"no unscramble line for {failure.get('release')}"]
    gave_up = [s for s in unscrambles if s.get('result') in GAVE_UP]
    if not gave_up:
        return NO, [f"Unscramble did not give up on it ({', '.join(str(s.get('result')) for s in unscrambles)})"] + \
            [step_text(s) for s in unscrambles]
    when = br.parse_ts(gave_up[-1]['t'])
    after = [s for s in steps if s.get('step') in ('upload', 'import_wait') and br.parse_ts(s['t']) >= when]
    if after:
        return YES, [step_text(gave_up[-1]), step_text(after[0])]
    return NO, [step_text(gave_up[-1]), 'no upload or import_wait line for the Source after it']


@clue('altmount-missing-volumes', 'Did AltMount say volumes of the Source\'s RAR set were missing?')
def altmount_missing_volumes(evidence, failure):
    return _altmount_said(evidence, failure, r'Skipping RAR archive group with missing volume', 'volumes were missing')


SMART_NONE = 'Smart mode: no healthy result found after checking'  # the old list-time check (before #190) found none


def _check_lines(evidence, release):
    return [s for s in evidence.steps if s.get('step') == 'play_check' and s.get('title') == release]


def _old_check_found_none(evidence):
    """The old list-time check's line that it found no healthy Source, from a build before the Play-time check (#190),
    or None."""
    if any(s.get('step') == 'play_check' for s in evidence.steps):
        return None
    return next((line for line in evidence.kf_lines if SMART_NONE in line), None)


@clue('played-source-unchecked', 'Was the Source that failed handed to AltMount with no health check of its own?')
def played_source_unchecked(evidence, failure):
    release = failure.get('release')
    own = _check_lines(evidence, release)
    if own:
        return NO, [step_text(s) for s in own]
    if any(s.get('step') == 'play_check' for s in evidence.steps):
        return YES, [f'no play_check line for {release}, among the play\'s '
                     f"{sum(1 for s in evidence.steps if s.get('step') == 'play_check')} play_check lines"]
    none = _old_check_found_none(evidence)
    if none:  # the old check kept every Source it had not checked once it found none healthy (#190)
        return YES, [none, f'no check line names {release}']
    return CANT, ['this build writes no play_check lines, and its list-time check does not say which Sources it checked']


@clue('altmount-fast-fail-refused', 'Did AltMount refuse the Source at its fast-fail segment check?')
def altmount_fast_fail_refused(evidence, failure):
    return _altmount_said(evidence, failure, r'fast-fail segment check failed', 'its fast-fail segment check failed')


@clue('check-passed-source', 'Did the health check pass the Source before AltMount refused it?')
def check_passed_source(evidence, failure):
    release = failure.get('release')
    own = _check_lines(evidence, release)
    if own:
        return (YES if any(s.get('ok') for s in own) else NO), [step_text(s) for s in own]
    if any(s.get('step') == 'play_check' for s in evidence.steps):
        return NO, [f'no play_check line for {release}: it was not checked']
    none = _old_check_found_none(evidence)
    if none:
        return NO, [none]
    return CANT, ['this build writes no play_check lines, and its list-time check does not say which Sources it passed']


@clue('altmount-extension-refused', "Did AltMount refuse the Source's file for its extension?")
def altmount_extension_refused(evidence, failure):
    return _altmount_said(evidence, failure, r'does not match allowed extensions', 'the file does not match allowed extensions')
