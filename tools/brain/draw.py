"""The title draw for real-use checks (#269, spec #268, ADR 0010): new titles from TMDB by kind, never played before.

    python3 -I tools/brain/draw.py titles --check <name> --kinds popular-film=3,popular-episode=2 --out <titles.json>
                                          [--ledger FILE] [--test-dir DIR]
    python3 -I tools/brain/draw.py seed [--ledger FILE] [--pool tools/brain/pool.json]

`titles` asks TMDB for titles of each kind (KINDS), takes them at random from the kind's lists, skips every title in
the ledger (the titles already played, `<runs root>/titles-played.json`, outside the repo) and checks each one's ID
the way `pool.py check-ids` does. It writes the drawn titles to the ledger first, then the check's title list
(`[type, id, label, kind]`); one line per title, then `done in N s`. A title is chosen by its kind only, never by
hand and never by whether it will play. `--kinds anime=1` hands back one more title of a kind (a replacement).
`seed` adds the titles the replayed recording's speed tests played (Test 1's ten and the pool's used titles), once.
Format: docs/formats.md, "The title draw and the ledger". The TMDB key is read from KaijuFlow's test copy, never printed.
"""
import argparse
import datetime
import json
import os
import random
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402
import pool  # noqa: E402

DEFAULT_LEDGER = os.path.expanduser('~/kaijuflow-notes/brain-runs/titles-played.json')
FOREIGN_LANGUAGES = ('fr', 'de', 'es', 'it', 'ja', 'ko', 'zh', 'hi', 'sv', 'da', 'pt', 'ru')
# Each kind: what it is (said in the title list's kind field and the ledger), film or episode, and the TMDB lists
# it is drawn from (a path per list, `{page}` and `{lang}` filled in at random). A rare kind has two lists: older
# titles and little-known ones.
KINDS = {
    'popular-film': ('movie', ['/movie/popular?page={page}']),
    'popular-episode': ('series', ['/tv/popular?page={page}']),
    'rare-film': ('movie', ['/discover/movie?sort_by=vote_count.desc&primary_release_date.lte=1999-12-31&page={page}',
                            '/discover/movie?sort_by=popularity.desc&vote_count.gte=20&vote_count.lte=200&page={page}']),
    'rare-episode': ('series', ['/discover/tv?sort_by=vote_count.desc&first_air_date.lte=2004-12-31&page={page}',
                                '/discover/tv?sort_by=popularity.desc&vote_count.gte=20&vote_count.lte=200&page={page}']),
    # a title with a foreign or alternate name: TMDB's English title is not its original one
    'foreign': ('movie', ['/discover/movie?sort_by=popularity.desc&vote_count.gte=50&with_original_language={lang}'
                          '&page={page}']),
    'anime': ('series', ['/discover/tv?sort_by=popularity.desc&with_genres=16&with_original_language=ja&page={page}']),
    # a title shared with a remake: another film on TMDB has the same name and another year
    'remake': ('movie', ['/discover/movie?sort_by=vote_count.desc&page={page}']),
    # a daily show (talk show), whose episodes indexers know by date
    'daily': ('series', ['/discover/tv?sort_by=popularity.desc&with_genres=10767&with_original_language=en&page={page}']),
}
PAGES = 10  # a list's page is drawn from its first PAGES pages
TRIES = 8  # pages looked at per title before a kind gives up


class Refused(Exception):
    """The one sentence that says why the draw could not be done."""


def read_ledger(path):
    """The ledger's titles (a list of dicts); [] when there is no ledger yet."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)['titles']


def base_id(tid):
    """A film's IMDb ID, or a show's for an episode: a show once played is not drawn again."""
    return tid.split(':')[0]


def add_to_ledger(path, titles, check, when):
    """Adds the titles ([type, id, label, kind]) as played by `check`, skipping those already in it; returns how many
    were added. Written through a temporary file, so a failed write leaves the old ledger whole."""
    entries = read_ledger(path)
    have = {base_id(e['id']) for e in entries}
    added = 0
    for kind_type, tid, label, kind in titles:
        if base_id(tid) in have:
            continue
        have.add(base_id(tid))
        entries.append({'id': tid, 'type': kind_type, 'label': label, 'kind': kind, 'check': check, 'when': when})
        added += 1
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pool.write_json(path, '{"about": "Titles already played by a real-use check; a draw never takes them again '
                    '(tools/brain/draw.py).",\n "titles": ' + pool.dump_lines(entries) + '}\n')
    return added


def cached(get):
    """get(path) remembered per path, so the ID check repeats no call the draw made."""
    seen = {}

    def once(path):
        if path not in seen:
            seen[path] = get(path)
        return seen[path]
    return once


def _year(text):
    return (text or '')[:4]


def _is_foreign(found):
    return pool.norm(found.get('title')) != pool.norm(found.get('original_title'))


def _is_remake(found, get):
    """Whether another film on TMDB has this film's name and another year."""
    name = found.get('title') or ''
    _, hits = get('/search/movie?' + urllib.parse.urlencode({'query': name}))
    return any(h.get('id') != found.get('id') and pool.norm(h.get('title')) == pool.norm(name)
               and _year(h.get('release_date')) and _year(h.get('release_date')) != _year(found.get('release_date'))
               for h in (hits or {}).get('results') or [])


def _imdb(get, what, tmdb_id):
    status, ids = get(f'/{what}/{tmdb_id}/external_ids')
    tid = (ids or {}).get('imdb_id') if status == 200 else None
    return tid if tid and pool.ID_SHAPE['movie'].fullmatch(tid) else None


def _episode(get, show, rng, today, latest):
    """(season, episode) of an aired episode of the show, at random (from its latest season for a daily show);
    None when it has none."""
    status, full = get(f"/tv/{show['id']}")
    seasons = [s for s in (full or {}).get('seasons') or [] if status == 200 and s.get('season_number', 0) > 0
               and s.get('episode_count', 0) > 0 and s.get('air_date') and s['air_date'] <= today]
    if not seasons:
        return None
    season = max(seasons, key=lambda s: s['season_number']) if latest else rng.choice(seasons)
    for episode in rng.sample(range(1, season['episode_count'] + 1), min(3, season['episode_count'])):
        status, ep = get(f"/tv/{show['id']}/season/{season['season_number']}/episode/{episode}")
        if status == 200 and ep and ep.get('air_date') and ep['air_date'] <= today:
            return season['season_number'], episode
    return None


def _title(get, kind, found, rng, today):
    """The title ([type, id, label, kind]) for one TMDB list entry of the kind, or None when it is not one: no
    IMDb ID, not released yet, not of the kind (foreign, remake), or no aired episode."""
    kind_type = KINDS[kind][0]
    if kind_type == 'movie':
        if not found.get('release_date') or found['release_date'] > today:
            return None
        if (kind == 'foreign' and not _is_foreign(found)) or (kind == 'remake' and not _is_remake(found, get)):
            return None
        tid = _imdb(get, 'movie', found['id'])
        return tid and ['movie', tid, found.get('title') or '', kind]
    show = _imdb(get, 'tv', found['id'])
    picked = show and _episode(get, found, rng, today, latest=kind == 'daily')
    if not picked:
        return None
    season, episode = picked
    return ['series', f'{show}:{season}:{episode}', f"{found.get('name') or ''} S{season:02d}E{episode:02d}", kind]


def draw(get, ledger, kinds, rng, today, say=lambda line: None):
    """The drawn titles ([type, id, label, kind]) for `kinds` ({kind: count}, in that order), none in the ledger
    (a list of its entries) and none twice; each ID checked as `pool.py check-ids` does. Refused, naming the kind,
    when a kind runs out of tries."""
    get = cached(get)
    taken = {base_id(e['id']) for e in ledger}
    drawn = []
    for kind, count in kinds.items():
        if kind not in KINDS:
            raise Refused(f"There is no kind {kind!r}: the kinds are {', '.join(KINDS)}.")
        for _ in range(count):
            title = _one(get, kind, taken, rng, today)
            if not title:
                raise Refused(f'TMDB gave no new {kind} title in {TRIES} pages: nothing was drawn.')
            taken.add(base_id(title[1]))
            drawn.append(title)
            say(f'{kind}: {title[2]} ({title[1]})')
    return drawn


def _one(get, kind, taken, rng, today):
    for _ in range(TRIES):
        path = rng.choice(KINDS[kind][1]).format(page=rng.randint(1, PAGES), lang=rng.choice(FOREIGN_LANGUAGES))
        status, page = get(path)
        if status != 200:
            raise pool.TmdbError(f'TMDB answered HTTP {status} for a {kind} list, so nothing was drawn.')
        entries = list((page or {}).get('results') or [])
        rng.shuffle(entries)
        for found in entries:
            title = _title(get, kind, found, rng, today)
            if not title or base_id(title[1]) in taken:
                continue
            ok, _ = pool.check_title({'type': title[0], 'id': title[1], 'label': title[2]}, get)
            if ok:
                return title
    return None


def parse_kinds(text):
    """{kind: count} from `popular-film=3,anime=1`, in the order given."""
    out = {}
    for part in (p.strip() for p in text.split(',') if p.strip()):
        kind, _, count = part.partition('=')
        if not count.isdigit() or int(count) < 1:
            raise Refused(f'{part!r} is not a kind and a count, like popular-film=3.')
        out[kind] = out.get(kind, 0) + int(count)
    return out


def titles_command(a, http, rng, now):
    began = time.monotonic()
    try:
        kinds = parse_kinds(a.kinds)
        drawn = draw(pool.tmdb_getter(a.test_dir, http), read_ledger(a.ledger), kinds, rng, now.date().isoformat(),
                     say=lambda line: print(line, flush=True))
    except (Refused, pool.TmdbError) as e:
        print(e)
        return 1
    # The ledger first: a failure after it can only waste the drawn titles, never let a later draw take them again.
    add_to_ledger(a.ledger, drawn, a.check, now.isoformat(timespec='seconds'))
    try:
        pool.write_json(a.out, pool.dump_lines(drawn) + '\n')
    except OSError as e:
        print(f'The ledger has the {len(drawn)} titles drawn for {a.check}, but the title list could not be written to '
              f'{a.out} ({type(e).__name__}): those titles are spent; draw again.')
        return 1
    print(f'Drew {len(drawn)} titles for {a.check} into {a.out}; the ledger has them.')
    print(f'done in {round(time.monotonic() - began)} s')
    return 0


def seed_command(a, now):
    old = [[kind, tid, label, 'old process'] for kind, tid, label in common.TITLES]
    old += [[t['type'], t['id'], t['label'], 'old process'] for t in pool.read_json(a.pool)['titles'] if t.get('used_by')]
    added = add_to_ledger(a.ledger, old, 'replayed recording', now.isoformat(timespec='seconds'))
    print(f'{added} titles the replayed recording played were added to {a.ledger}.')
    return 0


def main(argv, http=pool.real_http, rng=None, now=None):
    ap = argparse.ArgumentParser(prog='draw.py', description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('titles', help="draw a check's new titles by kind")
    t.add_argument('--check', required=True, help='the check the titles are for, e.g. "quick 2026-11-25"')
    t.add_argument('--kinds', required=True, help=f"kind=count, comma-separated; kinds: {', '.join(KINDS)}")
    t.add_argument('--out', required=True, help="where to write the check's title list (JSON)")
    t.add_argument('--ledger', default=DEFAULT_LEDGER)
    t.add_argument('--test-dir', default=os.environ.get('TEST_DIR', common.DEFAULT_TEST_DIR))
    s = sub.add_parser('seed', help="add the replayed recording's played titles to the ledger")
    s.add_argument('--ledger', default=DEFAULT_LEDGER)
    s.add_argument('--pool', default=pool.DEFAULT_POOL)
    a = ap.parse_args(argv)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if a.cmd == 'seed':
        return seed_command(a, now)
    return titles_command(a, http, rng or random.Random(), now)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
