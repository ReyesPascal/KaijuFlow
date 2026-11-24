"""The quick check's judging (#270, spec #268, ADR 0010): one visit's outcome, the verdict and report.md.

A quick check (`brainrun.py check --quick`) plays 5 new titles, live, one cold press of Best each, after the Browse pause,
and stops at the first video. This module holds what it decides from what it saw, with no I/O of its own, so the tests
can feed it any visit: whether a play is a fail (no video, or the wrong title or episode), a slow play, nothing to play,
which Sources were check misses and fallbacks, the verdict (pass on zero fails) and report.md with a ready-to-file
ticket text for each fail and check miss. The rules: tools/brain/docs/rules.md, "Real-use checks".
"""
import os
import re
import statistics
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import allowance  # noqa: E402
import brainreport as br  # noqa: E402
import diagnosis  # noqa: E402
import drill  # noqa: E402
import pool  # noqa: E402

QUICK_KINDS = {'popular-film': 2, 'rare-film': 1, 'popular-episode': 1, 'rare-episode': 1}  # the 5 titles' kinds (draw.KINDS)
SLOW_PLAY_S = 60  # video later than this after the press is a slow play (GLOSSARY "Slow play")
PLAY_TIMEOUT_S = 300  # how long the press is waited on: a slow play still shows, a play that never starts ends as a fail
# What one title can ask of an indexer at most, for the allowance check: a few searches (pages, title variants) and the
# Walk's 30 grabs (#228).
NEED_PER_TITLE = {'search': 12, 'download': 30}
# the step lines a check keeps per visit (KaijuFlow's [KF-STEP]): each indexer page's answer, the search's filter count, the
# list going out, the Play-time check's, the play's
KEPT_STEPS = ('indexer_page', 'list_filter', 'list', 'play_check', 'played', 'play_failed')

PLAYED, FAIL, NOTHING = 'played', 'fail', 'nothing to play'


def need(titles):
    """What a check of `titles` titles may ask of each indexer at most: {'search': n, 'download': n}."""
    return {kind: n * titles for kind, n in NEED_PER_TITLE.items()}


# --------------------------------------------------------------------------- the right title

def words(text):
    """A name as lower-case words, accents, apostrophes and punctuation gone, `&` read as `and`:
    "Amélie's.Café.&.Bar.2001" -> ['amelies', 'cafe', 'and', 'bar', '2001']."""
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode().lower()
    text = re.sub(r"['’`]", '', text).replace('&', ' and ')
    return re.findall(r'[a-z0-9]+', text)


def _holds(hay, needle):
    """Whether the words `needle` appear in `hay` one after another."""
    n = len(needle)
    return n > 0 and any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


EPISODE_LABEL = re.compile(r'^(.*) S(\d+)E(\d+)$')  # an episode's label from the draw: "Show Name S01E02"


def _markers(tokens):
    """(episodes, seasons) a release name names: {(season, episode)} from S01E02, S01E01E02, S01E01-E03 and 1x02, and
    {season} from a season pack's S01, S01-S03 or "Season 1"."""
    episodes, seasons = set(), set()
    for i, t in enumerate(tokens):
        m = re.fullmatch(r's(\d{1,3})((?:e\d{1,4})+)', t) or (
            re.fullmatch(r's(\d{1,3})()', t) if i + 1 < len(tokens) and re.fullmatch(r'e\d{1,4}', tokens[i + 1]) else None)
        if m:  # S01E02, S01E01E02, or S01.E02 (the season and the episode as two words)
            nums = [int(x) for x in re.findall(r'e(\d+)', m.group(2))]
            j = i + 1
            if not nums:  # S01.E02: the episode is the next word
                nums, j = [int(tokens[i + 1][1:])], i + 2
            while j < len(tokens) and re.fullmatch(r'e\d{1,4}', tokens[j]):  # S01E01-E03: the range's end
                nums.append(int(tokens[j][1:]))
                j += 1
            episodes |= {(int(m.group(1)), n) for n in range(min(nums), max(nums) + 1)}
            continue
        m = re.fullmatch(r'(\d{1,2})x(\d{1,3})', t)
        if m:
            episodes.add((int(m.group(1)), int(m.group(2))))
            continue
        m = re.fullmatch(r's(\d{1,3})', t)
        if m:
            end = re.fullmatch(r's(\d{1,3})', tokens[i + 1]) if i + 1 < len(tokens) else None  # S01-S03
            seasons |= set(range(int(m.group(1)), int(end.group(1)) + 1)) if end else {int(m.group(1))}
        elif t == 'season' and i + 1 < len(tokens) and tokens[i + 1].isdigit():
            seasons.add(int(tokens[i + 1]))
    return episodes, seasons


# The words a release may put between an episode's show name and its marker, each seen there in the recordings' release
# names (`The.Witcher.US.S01E01`, `Utopia.UK.S01E01`, `Utopia.AU.S01`, `REACHER.TV.S01E01`, `Game.of.Thrones.complete
# .S01-S08`); beside them a year and a TVDB number (`The Witcher (2019) (362696) - S01E01`). Any other word there is a
# longer show around the name: `Squid.Game.The.Challenge.S01E01`, `The.Witcher.Blood.Origin.S01`.
SHOW_TAGS = {'us', 'uk', 'au', 'tv', 'complete'}
# The words a release may put between a film's name and its year, each seen there in the recordings' release names: an
# edition, a language, a 3D or video tag (`Vol.3.IMAX.1080p.2023`, `Deadpool.and.Wolverine.GERMAN.2024`,
# `Akira.Special.Edition.1988`, `Joker nl subs 2019`). Any other word there is a longer film around the name
# (`Inception.The.Cobol.Job.2010`, `Avatar.Pandoras.Box.2009`); a title in another language fits through TMDB's other
# names of it (`Avatar.Aufbruch.nach.Pandora.Extended.Collectors.Edition.2009`).
FILM_TAGS = {'imax', '3d', '2d', 'hsbs', '3dbd', 'uhd', 'multi', 'german', 'en', 'nl', 'eng', 'ukr', 'subs', 'anime',
             'se', 'ue', 'special', 'extended', 'collector', 'collectors', 's', 'edition', 'theatrical',
             'cut', 'remastered'}
VIDEO_TAG = re.compile(r'\d{3,4}p|4k')  # a resolution among them (`Avatar.720P.(2009)`, `IMAX.2160p.4k.2023`)
UMLAUTS = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss'})


def _after(rel, name):
    """The positions in the release words just after each place the name's words stand, one after another."""
    n = len(name)
    return [i + n for i in range(len(rel) - n + 1) if n and rel[i:i + n] == name]


def _year(word):
    return int(word) if re.fullmatch(r'(19|20)\d\d', word or '') else None


def _film_year(rel, j):
    """The year that dates a film whose name ends before word j, past any FILM_TAGS and resolutions; None when another
    word or number comes first (`Inside.Out.2.2024` is not Inside Out, `Inception.The.Cobol.Job.2010` not Inception)."""
    for w in rel[j:]:
        if _year(w):
            return _year(w)
        if not (w in FILM_TAGS or VIDEO_TAG.fullmatch(w)):
            return None
    return None


def _episode_start(rel, j):
    """Whether an episode, season or date marker starts at word j, past any SHOW_TAGS, years and TVDB numbers."""
    for k, w in enumerate(rel[j:], j):
        if re.fullmatch(r's\d{1,3}(e\d{1,4})*|\d{1,2}x\d{1,3}|season', w) or (_year(w) and k + 2 < len(rel)
                                                                             and rel[k + 1].isdigit() and rel[k + 2].isdigit()):
            return True
        if not (_year(w) or w in SHOW_TAGS or re.fullmatch(r'\d{5,}', w)):
            return False
    return False


def right_title(release, title, names=()):
    """(True, '') when the release name played is the drawn title, else (False, why). KaijuFlow's Search Flow holds a
    copy of this rule (`strictMatch`, src/parsers/searchFlow.ts, #282): both are tested on the shared table of real
    release names (tests/fixtures/release-names/table.tsv), so a change here (a tag allowed, a why reworded) goes into
    both copies and the table. `title` is the draw's
    [type, id, label, kind, date]; `names` are other names of it (TMDB's original and alternative titles), tried when the
    label's name does not fit.

    A film's name is followed by a year within one of its release year (releases are dated by their own release), past
    only edition, language and video tags (FILM_TAGS), so a sequel or a longer film around it does not count. An episode's
    show name is followed by its marker, past only show tags, years and TVDB numbers (SHOW_TAGS); the marker
    is its episode (S01E02, 1x02, in a range S01E01-E03), or its season when the release is a season pack (KaijuFlow picks
    the file inside), or its air date (a daily show, 2026.11.20). A why that starts "the name" is one another name of the
    title may mend."""
    title_type, _, label, _, date = title
    rel = words(release)
    m = EPISODE_LABEL.match(label) if title_type == 'series' else None
    name = m.group(1) if m else label
    tried = [name, *names]
    tried += [n.translate(UMLAUTS) for n in tried if n.translate(UMLAUTS) != n]  # Einzelgänger as released: Einzelgaenger
    spots = [j for n in tried for j in _after(rel, words(n))]
    if not spots:
        return False, f'the name "{name}" is not in it'
    if title_type == 'movie':
        year = int(date[:4]) if re.match(r'\d{4}', date or '') else None
        years = [y for y in (_film_year(rel, j) for j in spots) if y]
        if not years:
            return False, f'the name "{name}" is not followed by a year' + (f' ({year} wanted)' if year else '')
        if year and not any(abs(y - year) <= 1 for y in years):
            return False, f"its year is {years[0]}, not {year}"
        return True, ''
    if not m:
        return False, f'the label "{label}" names no episode'
    if not any(_episode_start(rel, j) for j in spots):
        return False, f'the name "{name}" is not followed by a season or episode'
    season, episode = int(m.group(2)), int(m.group(3))
    if re.match(r'\d{4}-\d\d-\d\d$', date or '') and _holds(rel, [date[:4], date[5:7], date[8:10]]):
        return True, ''
    episodes, seasons = _markers(rel)
    if (season, episode) in episodes:
        return True, ''
    if episodes:
        s, e = sorted(episodes)[0]
        return False, f'it is S{s:02d}E{e:02d}, not S{season:02d}E{episode:02d}'
    if season in seasons:
        return True, ''
    if seasons:
        return False, f'it is a pack of season {min(seasons)}, not season {season}'
    return False, f'it names no season or episode (S{season:02d}E{episode:02d} wanted)'


def odd_word(release, title, names=()):
    """The one word that keeps the strict rule from passing a release of the right title, with where it stands:
    ('ce', 'between the name and the year') for Pulp.Fiction.CE.1994. None when no single word does (the release
    passes already, or more than one word stands in the way, as another name of the title does). A maybe that played
    the right title offers it as a new allowed word (#286, spec #279 story 72)."""
    rel = words(release)
    if right_title(release, title, names)[0]:
        return None
    where = 'between the name and the year' if title[0] == 'movie' else 'between the name and the season or episode'
    for i, word in enumerate(rel):
        if right_title(' '.join(rel[:i] + rel[i + 1:]), title, names)[0]:
            return word, where
    return None


def tmdb_names(get, title):
    """The other names TMDB knows a title by, from its IMDb ID (an episode's show): original and alternative titles.
    `get(path)` -> (status, JSON), as pool.tmdb_getter gives it. [] when TMDB does not know it; pool.TmdbError when it
    did not answer (any status but 200: a limit, an outage), so the fail can say the names could not be read."""
    def answer(path):
        status, data = get(path)
        if status != 200:
            raise pool.TmdbError(f'TMDB answered HTTP {status} to {path.split("?")[0]}')
        return data or {}
    imdb = title[1].split(':')[0]
    what = 'movie' if title[0] == 'movie' else 'tv'
    hits = answer(f'/find/{imdb}?external_source=imdb_id').get(f'{what}_results') or []
    if not hits:
        return []
    hit = hits[0]
    names = [hit.get('title') or hit.get('name'), hit.get('original_title') or hit.get('original_name')]
    alt = answer(f"/{what}/{hit['id']}/alternative_titles")
    names += [a.get('title') for a in (alt.get('titles' if what == 'movie' else 'results') or [])]
    out = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


# --------------------------------------------------------------------------- one visit

def visit_steps(steps, vid, since):
    """The step lines of one visit that a check keeps (KEPT_STEPS): the indexer pages, the filter count, the Play-time check's and
    the play's, from `since` (an ISO time) on, its own title's (`ref` the title's id) or with no ref."""
    lo = br.parse_ts(since)

    def from_then(s):
        try:
            return br.parse_ts(s['t']) >= lo
        except (KeyError, TypeError, ValueError):
            return False
    return [s for s in steps if s.get('step') in KEPT_STEPS and s.get('ref') in (None, vid) and from_then(s)]


def _and(items):
    """`A`, `A and B`, `A, B and C`."""
    items = list(items)
    return ', '.join(items[:-1]) + ' and ' + items[-1] if len(items) > 1 else ''.join(items)


def _indexer_names(steps):
    """{slug: the name KaijuFlow's lines give the indexer} (`ninjacentral` -> `NinjaCentral`), slugs as the key file's
    (allowance.norm)."""
    return {allowance.norm(s['source']): s['source'] for s in steps if s.get('step') == 'indexer_page' and s.get('source')}


def down_indexers(steps, indexers=()):
    """(asked, down): the switched-on indexers (`indexers`, slugs; else the ones the page lines name) and those of them no
    page of which answered, by the name KaijuFlow's lines give them. One that has no page line at all was not heard from
    either, so it is down too."""
    names = _indexer_names(steps)
    asked = [allowance.norm(i) for i in indexers] or list(names)
    answered = {allowance.norm(s.get('source')) for s in steps if s.get('step') == 'indexer_page' and s.get('ok')}
    return asked, [names.get(i, i) for i in asked if i not in answered]


def _empty_list(steps, indexers=()):
    """(outcome, why) of a list with no Source (#304, spec #298 stories 23 and 24). Every switched-on indexer down is
    nothing to play: `indexers down: no switched-on indexer answered its search (NinjaCentral)`, never a fail. Else the
    list is judged: nothing to play when KaijuFlow's `list_filter` line says what its search kept (its name match, junk
    strip and remake filter done) and what its filters (dead marks, the user's) left, `the list held no Source:
    KaijuFlow's search kept 12 Sources and its filters kept none`, naming any indexer that did not answer; no
    `list_filter` line (the list's handler failed) is a fail."""
    asked, down = down_indexers(steps, indexers)
    if asked and len(down) == len(asked):
        return NOTHING, f'indexers down: no switched-on indexer answered its search ({_and(down)})'
    f = next((s for s in steps if s.get('step') == 'list_filter'), None)
    if not f or f.get('results') is None:
        return FAIL, "the list held no Source, and KaijuFlow's log has no list_filter line, so it is not shown that nothing would play"
    n, kept = f['results'], f.get('kept') or 0
    why = (f"the list held no Source: KaijuFlow's search kept {n} Source{'' if n == 1 else 's'} and its filters "
           f"kept {kept or 'none'}")
    return NOTHING, why + (f'; {_and(down)} did not answer its search' if down else '')


def judge(visit, names=lambda: (), indexers=()):
    """One visit's outcome: {'outcome': played | fail | nothing to play, 'why', 'release' (the release played, or None),
    'title_to_video', 'start_s', 'slow', 'fallbacks', 'video', 'check_misses': [{'release', 'reason'}],
    'checked': [{'release', 'ok', 'status'}]}.

    `visit` is what the check saw: 'title' (the draw's five fields), 'list_status', 'list_s', 'sources' (Sources in the
    list, the Best entry left out), 'best' (whether the list had the Best entry), 'play' (common.play_stream's result for
    the press of Best, or None), 'steps' (visit_steps). `names()` gives the title's other names, asked for only when the
    release played does not carry the label's name; None when TMDB could not be read (the fail then says so).
    `indexers` are the check's switched-on indexers (slugs): a list is judged on what it held when one of them was down
    and another answered, and is nothing to play, indexers down, only when every one of them was down."""
    steps = visit.get('steps') or []
    checked = [{'release': s.get('title'), 'ok': bool(s.get('ok')), 'status': s.get('status')} for s in steps if s['step'] == 'play_check']
    passed = {c['release'] for c in checked if c['ok']}
    failed = []  # one entry per release, its first reason: a Source the Head start and the press both tried fails twice
    for s in steps:
        if s['step'] == 'play_failed' and s.get('title') not in {f.get('title') for f in failed}:
            failed.append(s)
    played = next((s for s in steps if s['step'] == 'played'), None)
    play = visit.get('play') or {}
    video = bool(play.get('plays'))
    title = visit['title']
    out = {'label': title[2], 'id': title[1], 'kind': title[3], 'sources': visit.get('sources') or 0,
           'release': played.get('title') if played else None, 'video': video, 'checked': checked,
           'fallbacks': len(failed),
           'check_misses': [{'release': f.get('title'), 'reason': f.get('reason') or ''} for f in failed if f.get('title') in passed],
           'start_s': play.get('first_byte_s') if video else None, 'title_to_video': None, 'slow': False,
           'allowed_word': None}

    def end(outcome, why):
        return {**out, 'outcome': outcome, 'why': why}

    if visit.get('list_status') != 200:
        return end(FAIL, f"KaijuFlow's list did not come: {visit.get('note') or 'HTTP %s' % visit.get('list_status')}")
    if not visit.get('sources'):
        return end(*_empty_list(steps, indexers))
    if not visit.get('best'):
        return end(FAIL, 'the list had no Best entry to press')
    if video:
        out['title_to_video'] = round(visit['list_s'] + play['first_byte_s'], 2) if visit.get('list_s') is not None else None
        if not played:
            return end(FAIL, "video came, but KaijuFlow's log names no release played, so the right title cannot be told")
        ok, why = right_title(played['title'], visit['title'])
        other = []
        if not ok and why.startswith('the name'):  # another name of the title may fit
            got = names()
            if got is None:
                why += "; TMDB's other names of the title could not be read"
            else:
                other = got
                ok, why = right_title(played['title'], visit['title'], other)
        # A maybe (#286): the release name does not show the title, but the video file KaijuFlow played does (its played
        # line's `video`, dev switch on). It played the right title, and offers its odd word as a new allowed word.
        file = played.get('video')
        if not ok and why.startswith('the name') and file and right_title(file, visit['title'], other)[0]:
            ok = True
            odd = odd_word(played['title'], visit['title'], other)
            if odd:
                out['allowed_word'] = {'word': odd[0], 'where': odd[1], 'release': played['title'], 'video': file,
                                       'proof': played.get('proof')}
        if not ok:
            return end(FAIL, f"the wrong title played: {played['title']} ({why})")
        out['slow'] = play['first_byte_s'] > SLOW_PLAY_S  # a slow play is the right video, late
        return end(PLAYED, '')
    no_video = f"no video ({play.get('note') or 'no answer'})"
    if passed or failed:
        reason = f"; AltMount refused {failed[0].get('title')}: {failed[0].get('reason')}" if failed else ''
        return end(FAIL, no_video + reason)
    looked = len({c['release'] for c in checked})
    if looked >= visit['sources']:
        return end(NOTHING, f"every Source KaijuFlow looked at failed its check ({looked} of {visit['sources']})")
    return end(FAIL, f"{no_video}, and only {looked} of {visit['sources']} Sources were checked")


# --------------------------------------------------------------------------- what each indexer is worth

def release_key(name):
    """A release name as KaijuFlow's Release merge matches it (`releaseNameKey`, src/addon/kaijuSearch.ts, #299): lower
    case, spaces, `.`, `-` and `_` gone."""
    return re.sub(r'[\s._-]+', '', str(name or '').lower())


def found_by_indexer(steps, vid, since):
    """{indexer: [release names]} that each indexer's search found for one visit, from KaijuFlow's `search` lines (the
    dev switch's, one per indexer and way, each Source with its name), from `since` (an ISO time) on. {} when there are
    none (the dev switch off)."""
    lo, out = br.parse_ts(since), {}
    for s in steps:
        if s.get('step') != 'search' or s.get('ref') != vid or not s.get('source'):
            continue
        try:
            if br.parse_ts(s['t']) < lo:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        names = out.setdefault(s['source'], [])
        names += [r['release'] for r in s.get('results') or [] if r.get('release') and r['release'] not in names]
    return out


def requests_by_indexer(requests):
    """{slug: {'search': n, 'download': n}} from the stand-in's requests ([(slug, kind, when)], allowance.requests_in)."""
    out = {}
    for slug, kind, _ in requests:
        out.setdefault(slug, {'search': 0, 'download': 0})[kind] += 1
    return out


def _list_line(steps):
    return next((s for s in steps if s.get('step') == 'list'), None)


def indexer_rows(check, outcomes):
    """One row per switched-on indexer (#304, spec #298 story 25), what it is worth: `searches` and `downloads` the
    stand-in sent it (check['requests']), its pages' answer time (`typical_s` the median, `slowest_s`, None when none
    answered; `not_answered`), `lists` (the lists KaijuFlow searched for, a cached one left out) and `without` (those it
    sent before this indexer's last page came, or with no page of it at all), and `only_it`: the plays from a Release
    only this indexer's search found, by the Release merge's name match (sizes are not in the lines), None when the
    check has no search lines. `outcomes` are judge's, in judged(check)'s order."""
    visits = judged(check)
    steps = [s for v in visits for s in v.get('steps') or []]
    names = _indexer_names(steps)
    slugs = [allowance.norm(i) for i in check.get('indexers') or []] or list(names)
    requests = check.get('requests') or {}
    known = any(v.get('found') for v in visits)
    only = {}
    for v, o in zip(visits, outcomes):
        if o['outcome'] != PLAYED or not o.get('release'):
            continue
        had = {allowance.norm(i) for i, rels in (v.get('found') or {}).items() if release_key(o['release']) in map(release_key, rels)}
        if len(had) == 1:
            slug = had.pop()
            only[slug] = only.get(slug, 0) + 1
    rows = []
    for slug in slugs:
        pages = [s for s in steps if s.get('step') == 'indexer_page' and allowance.norm(s.get('source')) == slug]
        ms = [s.get('ms') or 0 for s in pages if s.get('ok')]
        lists = without = 0
        for v in visits:
            line = _list_line(v.get('steps') or [])
            if not line or line.get('cache') == 'hit':
                continue
            lists += 1
            at = br.parse_ts(line['t'])
            mine = [s for s in v['steps'] if s.get('step') == 'indexer_page' and allowance.norm(s.get('source')) == slug]
            if not mine or max(br.parse_ts(s['t']) for s in mine) > at:
                without += 1
        rows.append({'indexer': names.get(slug, slug), 'searches': (requests.get(slug) or {}).get('search', 0),
                     'downloads': (requests.get(slug) or {}).get('download', 0),
                     'typical_s': round(statistics.median(ms) / 1000, 2) if ms else None,
                     'slowest_s': round(max(ms) / 1000, 2) if ms else None, 'not_answered': len(pages) - len(ms),
                     'lists': lists, 'without': without, 'only_it': only.get(slug, 0) if known else None})
    return rows


INDEXER_HEADS = ('Indexer', 'Searches', 'Downloads', 'Answer time', 'Lists sent without it', 'Plays from a Release only it had')


def indexer_cells(row):
    """One indexer_rows row as the table's cells (text), the report's and the Speed Check page's (checkpage.py)."""
    missed = f", {row['not_answered']} not answered" if row['not_answered'] else ''
    answer = (f"{row['typical_s']:.2f} s typical, {row['slowest_s']:.2f} s slowest" if row['typical_s'] is not None
              else 'none answered') + missed
    only = 'not known (no search lines: the dev switch was off)' if row['only_it'] is None else str(row['only_it'])
    return [row['indexer'], str(row['searches']), str(row['downloads']), answer, f"{row['without']} of {row['lists']}", only]


def indexer_lines(check, outcomes):
    """The report's table of indexer_rows."""
    out = ['| ' + ' | '.join(INDEXER_HEADS) + ' |', '|' + '---|' * len(INDEXER_HEADS)]
    return out + ['| ' + ' | '.join(indexer_cells(r)) + ' |' for r in indexer_rows(check, outcomes)]


def requests_of(run_dir):
    """What the stand-in sent each indexer in a check (requests_by_indexer), from the folder's logs/standin.log: the
    check's ending and the Speed Check page read it the same way."""
    return requests_by_indexer(allowance.requests_in(os.path.join(run_dir, 'logs', 'standin.log')))


# --------------------------------------------------------------------------- the verdict and the report

def judged(check):
    """The visits a check judges: all but the one the cap rule stopped (its play was cut by the limit, so it says nothing
    of KaijuFlow)."""
    return [v for v in check.get('visits') or [] if not v.get('cut_by_limit')]


def verdict(check, outcomes):
    """'pass', 'fail' or None (no verdict: the check did not finish, the cap rule stopped it, or it failed)."""
    if check.get('status') != 'ok':
        return None
    return 'fail' if any(o['outcome'] == FAIL for o in outcomes) else 'pass'


def _s(x):
    return f'{x:.2f} s'


def no_verdict_text(check):
    """Why a check has no verdict, in one sentence."""
    status = check.get('status')
    if status == 'null':
        n = check['null']
        return f"No verdict: {n['indexer']} said its limit was reached at {n['time']}, so the check stopped (the cap rule)."
    if status == 'stopped':
        return f"No verdict: the check was {check.get('stopped_text') or 'stopped'}."
    return f"No verdict: the check failed: {check.get('error')}"


def headline(check, outcomes):
    """The report's first line and the INDEX.md row's: `Pass: 0 fails in 5 titles.` / `Fail: 2 of 5 titles failed ...`."""
    v = verdict(check, outcomes)
    if v is None:
        return no_verdict_text(check)
    fails = [o for o in outcomes if o['outcome'] == FAIL]
    if v == 'pass':
        return f"Pass: 0 fails in {br.plural(len(outcomes), 'title')}."
    return f"Fail: {len(fails)} of {br.plural(len(outcomes), 'title')} failed (" + '; '.join(o['label'] for o in fails) + ').'


def check_said(c):
    """What one Play-time check said of a Source: its status (`verified`, `blocked`), else passed or failed."""
    return c['status'] or ('passed' if c['ok'] else 'failed')


def checked_text(o):
    """The Sources a visit's Play-time check looked at, with what each check said: `A.2020.1080p (verified), B (blocked)`."""
    return ', '.join('%s (%s)' % (c['release'], check_said(c)) for c in o['checked']) or 'none'


def check_name(check):
    """`Quick check` or `Drill-down` (#272), as the report and its tickets name the check."""
    return {'drill-down': 'Drill-down'}.get(check.get('kind'), 'Quick check')


def ticket_texts(check, outcomes):
    """One ready-to-file ticket per fail and per check miss: [(title, body)]."""
    name = check_name(check)
    where = f"{name} `{check['folder']}` (commit {str(check.get('commit') or '?')[:7]}, {check['started']})"
    out = []
    for o in outcomes:
        tid, kind = o['id'], o['kind']
        if o['outcome'] == FAIL:
            out.append((f"{name} fail: {o['label']}",
                        f"{where}: pressing Best on **{o['label']}** (`{tid}`, {kind}) failed: {o['why']}.\n\n"
                        f"Release played: {o['release'] or 'none'}. Sources in the list: {o['sources']}; checked: "
                        f"{checked_text(o)}.\n\n"
                        'A fail is no video, or the wrong title or episode (tools/brain/docs/rules.md, "Real-use checks"). '
                        'The fix is proven by a drill-down on this title.'))
        for m in o['check_misses']:
            out.append((f"Check miss: {m['release']}",
                        f"{where}: the health check passed **{m['release']}** for {o['label']} (`{tid}`), and AltMount then "
                        f"refused it: {m['reason'] or 'no reason given'}. The play {'still came, after a fallback' if o['video'] else 'gave no video'}.\n\n"
                        'A check miss counts even when a fallback saved the play (tools/brain/docs/rules.md, "Real-use checks"). '
                        'The fix is proven by a drill-down on this title.'))
    return out


def played_line(check):
    """The report's line for a check that did not play every title: how many it played, and the play the cap rule cut,
    which is played but not judged. [] when every title was played and judged."""
    visits, drawn = check.get('visits') or [], len(check.get('titles') or [])
    cut = sum(1 for v in visits if v.get('cut_by_limit'))
    if len(visits) >= drawn and not cut:
        return []
    return [f"\nPlayed {len(visits)} of {br.plural(drawn, 'title')}" + (f"; {cut} cut by the limit, not judged." if cut else '.')]


def allowed_word_lines(outcomes):
    """The report's lines for the allowed words offered (#286): each with the play that offered it and its release, the
    proof. Added through normal review, no extra owner OK (spec #279, Q27)."""
    out = []
    for o in outcomes:
        a = o.get('allowed_word')
        if not a:
            continue
        sure = f"; KaijuFlow made it sure by: {a['proof']}" if a.get('proof') else ''
        out.append(f"- `{a['word']}` ({a['where']}), offered by {o['label']}: {a['release']} played the right title (its video "
                   f"file {a['video']} fits{sure}). Added through normal review: the tag lists of both copies of the strict "
                   'rule (tools/brain/quickcheck.py, src/parsers/searchFlow.ts) and a row in tests/fixtures/release-names/table.tsv.')
    return out


def fallbacks_line(outcomes):
    """The fallbacks of a check in one line: how many, in how many titles, how many ended in video; or that none happened."""
    fell = [o for o in outcomes if o['fallbacks']]
    if not fell:
        return 'Fallbacks not tested this time: no play fell back.'
    return (f"{br.plural(sum(o['fallbacks'] for o in fell), 'fallback')} in {br.plural(len(fell), 'title')}; "
            f"{sum(1 for o in fell if o['video'])} of them ended in video.")


def typical_line(outcomes):
    """The typical title to video of a check in one line: the median of the plays with the right video."""
    times = [o['title_to_video'] for o in outcomes if o['outcome'] == PLAYED and o['title_to_video'] is not None]
    if not times:
        return 'None: no play gave the right video.'
    return (f"{_s(statistics.median(times))} (median of {br.plural(len(times), 'play')} with the right video; the list plus "
            'the start, the Browse pause left out).')


def render_report(check, outcomes):
    """report.md of a quick check: pass or fail and the fails first, then slow plays, check misses, fallbacks, nothing to
    play, the typical title to video, the allowed words offered (#286), and a ticket text for each fail and check miss.
    Totals only: no title by title, no comparison with an earlier check."""
    lines = [f"# {check_name(check)} {check['started']}", '', headline(check, outcomes), '']
    if verdict(check, outcomes) is None and not outcomes:
        if check.get('kind') == drill.KIND:
            lines += drill.report_lines(check.get('drill'), check.get('drill_error'))
        return '\n'.join(lines) + '\n'
    fails = [o for o in outcomes if o['outcome'] == FAIL]
    if fails:
        lines += ['## Fails', ''] + [f"- {o['label']}: {o['why']}." for o in fails] + ['']
    slow = [o for o in outcomes if o['slow']]
    lines += [f'## Slow plays (video later than {SLOW_PLAY_S} s after the press)', '']
    lines += [f"- {o['label']}: video {_s(o['start_s'])} after the press." for o in slow] or ['None.']
    misses = [(o, m) for o in outcomes for m in o['check_misses']]
    lines += ['', '## Check misses (a Source the health check passed that AltMount refused)', '']
    lines += [f"- {o['label']}: {m['release']}: {m['reason'] or 'no reason given'}." for o, m in misses] or ['None.']
    fell = [o for o in outcomes if o['fallbacks']]
    lines += ['', '## Fallbacks', '', fallbacks_line(outcomes)]
    lines += [f"- {o['label']}: {br.plural(o['fallbacks'], 'fallback')}, {'ended in video' if o['video'] else 'no video'}." for o in fell]
    nothing = [o for o in outcomes if o['outcome'] == NOTHING]
    lines += ['', '## Nothing to play', '']
    for o in nothing:
        lines.append(f"- {o['label']}: {o['why']}.")
        lines += [f"  - {c['release']}: {check_said(c)}" for c in o['checked']]
    if not nothing:
        lines.append('None.')
    lines += ['', '## Typical title to video', '', typical_line(outcomes)]
    lines += played_line(check)
    lines += ['', '## Indexers', ''] + indexer_lines(check, outcomes)
    lines += ['', '## Allowed words offered', ''] + (allowed_word_lines(outcomes) or ['None.'])
    lines += [''] + diagnosis.report_section(check.get('diagnosis'), check.get('diagnosis_error'))
    if check.get('kind') == drill.KIND:
        lines += [''] + drill.report_lines(check.get('drill'), check.get('drill_error'))
    tickets = ticket_texts(check, outcomes)
    if tickets:
        lines += ['', '## Tickets to file', '']
        for title, body in tickets:
            lines += [f'### {title}', '', body, '']
    return '\n'.join(lines).rstrip('\n') + '\n'
