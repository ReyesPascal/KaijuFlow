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
import json
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


def run(name, evidence, failure, library=None):
    """{'clue', 'answer', 'facts'} of one Clue (from `library`, else CLUES) on one failure. A Clue that raises answers
    can't tell, with the error."""
    try:
        answer, facts = (CLUES if library is None else library)[name].run(evidence, failure)
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


# --------------------------------------------------------------------------- AltMount's raw answer for an import (#284)
#
# KaijuFlow logs AltMount's HTTP answer to an import that failed (`AltMount could not process the Source: {"error":
# {"code": ..., "message": ...}}`); the answer stops at the queue item's top-level error, and the reason under it is in
# AltMount's log alone (DIAGNOSIS_EVIDENCE.md, section 2). altmount_answer joins the two for one Source.

KF_ANSWER = re.compile(r'AltMount could not process the Source: (\{.*\})\s*$')
QUEUED = 'msg="Added NZB file to queue"'
QUEUE_ID = re.compile(r'\bqueue_id=(\d+)\b')
ERROR_FIELD = re.compile(r'\berror="((?:[^"\\]|\\.)*)"')
LEVEL = re.compile(r'\blevel=(WARN|ERROR)\b')
MSG = re.compile(r'\bmsg="((?:[^"\\]|\\.)*)"')
NOT_A_REASON = ('First segment has no data', 'subscriber channel full', 'Live heap is pressing', 'Processing failed',
                'Item failed')  # noise in every import, good or bad (DIAGNOSIS_EVIDENCE.md 2), and the lifecycle itself
REASONS = 5


def kaijuflow_answer(evidence, release):
    """(code, message) of AltMount's answer to KaijuFlow for one Source's failed import, from KaijuFlow's line nearest
    its failed import_wait (within 2 s), or None."""
    failed = [s for s in source_steps(evidence, release) if s.get('step') == 'import_wait' and not s.get('ok')]
    if not failed:
        return None
    at, best = br.parse_ts(failed[-1]['t']), None
    for line in evidence.kf_lines:
        m, t = KF_ANSWER.search(line), _ts(line)
        if not m or t is None:
            continue
        gap = abs((t - at).total_seconds())
        if gap <= 2 and (best is None or gap < best[0]):
            best = (gap, m.group(1))
    if best is None:
        return None
    try:
        err = (json.loads(best[1]).get('error') or {})
    except ValueError:
        return None
    return err.get('code'), err.get('message')


def altmount_import(evidence, release):
    """{'queue_id', 'ended' (the last lifecycle line's msg), 'error', 'reasons' (its WARN and ERROR lines, noise left
    out)} of AltMount's import of one Source while it was prepared, or None when its log has no queue line for it."""
    lines = altmount_lines(evidence, release) or []
    added = [line for line in lines if QUEUED in line and release + '.nzb' in line]
    if not added:
        return None
    qid = QUEUE_ID.search(added[-1]).group(1)
    start = lines.index(added[-1])
    out = {'queue_id': qid, 'ended': None, 'error': None, 'reasons': []}
    for line in lines[start + 1:]:
        q = QUEUE_ID.search(line)
        msg = (MSG.search(line) or [None, ''])[1]
        if q and q.group(1) == qid and msg == 'Processing failed':
            e = ERROR_FIELD.search(line)
            out['ended'], out['error'] = msg, e.group(1).replace('\\"', '"') if e else None
            continue  # its `Item failed` line follows
        if q and q.group(1) == qid and msg in ('Item failed', 'Successfully processed queue item'):
            out['ended'] = out['ended'] or msg
            break
        if q and q.group(1) != qid:
            continue  # another queue item's line
        if LEVEL.search(line) and not any(n in line for n in NOT_A_REASON):
            if msg not in [MSG.search(r)[1] for r in out['reasons'] if MSG.search(r)] and len(out['reasons']) < REASONS:
                out['reasons'].append(line)
    return out


@clue('altmount-refused-import', "Did AltMount refuse the Source's import (its answer, error and the reasons its log "
      'gives under it)?')
def altmount_refused_import(evidence, failure):
    release = failure.get('release')
    if not release:
        return CANT, ['the failure names no Source, so no AltMount import is tied to it']
    item = altmount_import(evidence, release)
    if item is None:
        return CANT, [f"AltMount's log has no queue line for {release} while it was prepared"]
    if item['ended'] == 'Successfully processed queue item':
        return NO, [f"queue item {item['queue_id']}: Successfully processed queue item"]
    facts = []
    answer = kaijuflow_answer(evidence, release)
    if answer:
        facts.append(f'AltMount answered KaijuFlow {answer[0]}: {answer[1]}')
    if item['ended'] is None:
        return CANT, facts + [f"queue item {item['queue_id']}: no end line while {release} was prepared"]
    facts.append(f"queue item {item['queue_id']}: {item['ended']}" + (f": {item['error']}" if item['error'] else ''))
    return YES, facts + item['reasons']


# --------------------------------------------------------------------------- live read-only Clues (#284)
#
# A live Clue asks the provider, read-only, about the Source's NZB: `(evidence, failure, usenet) -> (answer, facts)`,
# `usenet` the one connection (nntp.Usenet: STAT and BODY, nothing saved). Facts that fade (articles, retention) are
# asked once, right after the check (diagnosis.live_clues), and the answers kept in the evidence folder's live.json; the
# Clue registered under the same name in CLUES reads that kept answer, so a later diagnosis never asks again.

LIVE = {}
NZB_NS = '{http://www.newzbin.com/DTD/2003/nzb}'
SUBJECT_NAME = re.compile(r'"([^"]+)"')
MISS, HAVE = 430, 223


def live_clue(name, question):
    """Registers a live Clue under `name` in LIVE, and in CLUES the reader of its kept answer."""
    def register(fn):
        LIVE[name] = fn
        clue(name, question)(lambda evidence, failure: kept_live_answer(evidence, failure, name))
        return fn
    return register


def kept_live_answer(evidence, failure, name):
    release = failure.get('release')
    if not release:
        return CANT, ['the failure names no Source, so no NZB was asked about']
    if evidence.live.get('error'):
        return CANT, [f"the live Clues could not run after this check: {evidence.live['error']}"]
    kept = ((evidence.live.get('clues') or {}).get(name) or {}).get(release)
    if kept is None:
        why = 'no NZB of it was kept' if evidence.nzb(release) is None else 'the live Clues did not run after this check'
        return CANT, [f'{name} was not asked live for {release}: {why}']
    return kept['answer'], [f"asked live at {evidence.live.get('t')}"] + list(kept['facts'])


def run_live(name, evidence, failure, usenet):
    """{'clue', 'answer', 'facts'} of one live Clue, asked now. A Clue that raises answers can't tell, with the error."""
    try:
        answer, facts = LIVE[name](evidence, failure, usenet)
    except Exception as e:  # noqa: BLE001  (a dropped connection never stops the other Clues)
        answer, facts = CANT, [br.scrub_text(f'the Clue failed: {type(e).__name__}: {e}')]
    return {'clue': name, 'answer': answer, 'facts': [fact(f) for f in facts]}


def nzb_files(body):
    """[(file name, [(segment number, bytes, message-id)] in number order)] of an NZB's bytes; the name is the one in the
    subject's quotes, else the subject."""
    import xml.etree.ElementTree as ET  # an NZB is the indexer's XML: parsed only when a live Clue needs it
    out = []
    for f in ET.fromstring(body).iter(NZB_NS + 'file'):
        subject = f.get('subject') or ''
        m = SUBJECT_NAME.search(subject)
        segs = sorted(((int(s.get('number') or 0), int(s.get('bytes') or 0), (s.text or '').strip())
                       for s in f.iter(NZB_NS + 'segment')), key=lambda s: s[0])
        out.append((m.group(1) if m else subject, segs))
    return out


def _par2(name):
    return name.lower().endswith('.par2')


def _source_files(evidence, failure):
    """(the Source's non-par2 files from its kept NZB, or None, and the facts when there are none to ask about)."""
    release = failure.get('release')
    if not release:
        return None, ['the failure names no Source, so there is no NZB to ask about']
    body = evidence.nzb(release)
    if body is None:
        return None, [f'no NZB of {release} was kept']
    files = [(n, segs) for n, segs in nzb_files(body) if not _par2(n) and segs]
    if not files:
        return None, [f'the NZB of {release} lists no article outside its par2 files']
    return files, []


ENOUGH_MISSES = 10  # the sweep stops once this many articles answered 430: each costs the provider about 0.5 s (#284)
FIRST_WINDOW, LAST_WINDOW = 10, 100  # STATs per window: from 10, doubling while every answer is 223


def sweep(usenet, mids):
    """(codes so far, articles asked) of a STAT sweep over `mids` in growing windows, stopping after the window in which
    ENOUGH_MISSES articles have answered something other than 223; the articles that did are asked a second time, after
    the sweep, so a moment's 430 is not counted."""
    codes, window = [], FIRST_WINDOW
    while len(codes) < len(mids):
        got = usenet.stat(mids[len(codes):len(codes) + window])
        codes += got
        if sum(1 for c in codes if c != HAVE) >= ENOUGH_MISSES:
            break
        window = FIRST_WINDOW if any(c != HAVE for c in got) else min(window * 2, LAST_WINDOW)
    again = [i for i, c in enumerate(codes) if c != HAVE]
    for i, c in zip(again, usenet.stat([mids[i] for i in again]) if again else []):
        codes[i] = c
    return codes


@live_clue('articles-missing', "Are articles of the Source's files (par2 left out) missing on the provider: a STAT of "
           'every article, each miss asked again?')
def articles_missing(evidence, failure, usenet):
    files, facts = _source_files(evidence, failure)
    if files is None:
        return CANT, facts
    mids = [s[2] for _, segs in files for s in segs]
    codes = sweep(usenet, mids)
    at, per_file = 0, []
    for name, segs in files:
        mine = codes[at:at + len(segs)]
        at += len(segs)
        if mine:
            per_file.append((name, len(mine), sum(1 for c in mine if c == MISS), sum(1 for c in mine if c not in (HAVE, MISS))))
    missing, odd = sum(p[2] for p in per_file), sum(p[3] for p in per_file)
    asked = f'all {len(mids)}' if len(codes) == len(mids) else f'{len(codes)} of {len(mids)}'
    facts = [f'STAT of {asked} articles of {len(files)} file{'' if len(files) == 1 else 's'} (par2 left out): {missing} missing (430 when asked twice), '
             f'{odd} other answers' + ('' if len(codes) == len(mids) else
                                       f'; the sweep stopped once {ENOUGH_MISSES} had not answered 223')]
    facts += [f'{name}: {m} of the {n} articles asked missing' for name, n, m, _ in sorted(per_file, key=lambda p: -p[2])[:5] if m]
    if missing:
        return YES, facts
    return (CANT if odd or len(codes) < len(mids) else NO), facts


@live_clue('segment-crc-bad', "Does an article of the Source's biggest file come back damaged (its yEnc size or CRC32 "
           'not the ones its trailer names) although the provider has it?')
def segment_crc_bad(evidence, failure, usenet):
    files, facts = _source_files(evidence, failure)
    if files is None:
        return CANT, facts
    name, segs = max(files, key=lambda f: sum(s[1] for s in f[1]))
    picks = sorted({0, len(segs) // 2, len(segs) - 1})  # first, middle and last, as KaijuFlow's own check picks
    facts, damaged, read = [f'BODY of articles {", ".join(str(segs[i][0]) for i in picks)} of {name} ({len(segs)} '
                            'articles), checked in memory and dropped'], 0, 0
    for i in picks:
        got = usenet.body(segs[i][2])
        if got.get('code') != 222:
            facts.append(f"{name} article {segs[i][0]}: answer {got.get('code')}, not read")
            continue
        read += 1
        damaged += not got.get('intact')
        facts.append(f"{name} article {segs[i][0]}: {got.get('why')}")
    if damaged:
        return YES, facts
    return (NO if read == len(picks) else CANT), facts
