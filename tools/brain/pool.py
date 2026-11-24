"""TMDB lookups the title draw (draw.py), the quick check and the Drill-down share: the key of KaijuFlow's test copy, read
here and never printed (tmdb_getter), and the check of a title's ID, season and episode against TMDB (check_title).

The speed tests' pool (`pool.json`) and its commands (`pool.py draw`, `pool.py check-ids`) are retired by ADR 0010 (#273)
and archived in archive/pool_draw.py and archive/pool.json: they stop unless run with --revive (retired.py).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retired  # noqa: E402

OLD_POOL = os.path.join(HERE, 'archive', 'pool.json')  # the retired speed tests' pool (ADR 0010), kept for draw.py seed

ID_SHAPE = {'movie': re.compile(r'tt\d+'), 'series': re.compile(r'tt\d+:\d+:\d+')}


def read_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, text):
    """Writes the text through a temporary file, so a failed write leaves the old file whole."""
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(text)
    os.replace(tmp, path)


def dump_lines(items):
    """A JSON list with one item per line, so a change to the pool is one line in a diff."""
    return '[\n' + ',\n'.join('  ' + json.dumps(i, ensure_ascii=False) for i in items) + '\n]'


TMDB = 'https://api.themoviedb.org/3'


class TmdbError(Exception):
    """One sentence about a TMDB call that failed, with the key never in it."""


def real_http(url, headers):
    """(status, body bytes) of a GET; TmdbError on a network error."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        raise TmdbError(f'TMDB did not answer ({type(e).__name__})') from None


def tmdb_getter(test_dir, http=real_http):
    """get(path) -> (status, JSON) on TMDB with the metadata key of KaijuFlow's test copy
    (`<test dir>/config/config.json`, searchConfig.tmdbApiKey). The key is read here and goes only into the request:
    never into a message, a log line or a command line."""
    try:
        with open(os.path.join(test_dir, 'config', 'config.json')) as f:
            key = ((json.load(f).get('searchConfig') or {}).get('tmdbApiKey') or '').strip()
    except (OSError, ValueError):
        key = ''
    if not key:
        raise TmdbError(f"There is no TMDB key in KaijuFlow's test copy ({test_dir}/config/config.json, "
                        'searchConfig.tmdbApiKey), so no ID can be checked.')
    bearer = len(key) > 40 or key.startswith('eyJ')  # a v4 read token, as src/idResolver.ts tells them apart

    def get(path):
        url = TMDB + path + ('' if bearer else ('&' if '?' in path else '?') + urllib.parse.urlencode({'api_key': key}))
        status, body = http(url, {'Authorization': f'Bearer {key}'} if bearer else {})
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if status == 401:
            raise TmdbError('TMDB refused the key of KaijuFlow\'s test copy (HTTP 401), so no ID can be checked.')
        return status, data
    return get


def norm(text):
    return re.sub(r'[^a-z0-9]', '', (text or '').lower())


def check_title(t, get):
    """(ok, line) for one pool title, checked against TMDB: the film, or the show and its season and episode."""
    name = f"{t['label']} ({t['id']})"
    if t['type'] == 'movie':
        _, found = get(f"/find/{t['id']}?external_source=imdb_id")
        hits, shows = (found or {}).get('movie_results') or [], (found or {}).get('tv_results') or []
        if shows:  # TMDB can list a stray film under a show's IMDb ID too (it does for Friends)
            return False, f"NOT FOUND {name}: TMDB has a show with this IMDb ID ({shows[0].get('name')}), not a film."
        if not hits:
            return False, f'NOT FOUND {name}: TMDB has no film with this IMDb ID.'
        tmdb = hits[0]
        what = f"film {tmdb.get('title')} ({(tmdb.get('release_date') or '')[:4]}), TMDB {tmdb.get('id')}"
        if norm(t['label']) not in (norm(tmdb.get('title')), norm(tmdb.get('original_title'))):
            return False, f'LABEL DIFFERS {name}: TMDB has {what}.'
        return True, f'OK {name}: {what}.'
    show_id, season, episode = t['id'].split(':')
    _, found = get(f'/find/{show_id}?external_source=imdb_id')
    hits = (found or {}).get('tv_results') or []
    if not hits:
        return False, f'NOT FOUND {name}: TMDB has no show with the IMDb ID {show_id}.'
    show = hits[0]
    what = f"show {show.get('name')} ({(show.get('first_air_date') or '')[:4]}), TMDB {show.get('id')}"
    status, ep = get(f"/tv/{show.get('id')}/season/{int(season)}/episode/{int(episode)}")
    if status != 200 or not ep:
        return False, f'NOT FOUND {name}: TMDB has the {what}, but no season {int(season)} episode {int(episode)}.'
    tag = f'S{int(season):02d}E{int(episode):02d}'
    what += f", {tag} \"{ep.get('name')}\" ({ep.get('air_date')})"
    if norm(t['label']) not in (norm(show.get('name')) + norm(tag), norm(show.get('original_name')) + norm(tag)):
        return False, f'LABEL DIFFERS {name}: TMDB has the {what}.'
    return True, f'OK {name}: {what}.'


def main(argv):
    """`pool.py draw` and `pool.py check-ids`, retired by ADR 0010: they stop unless run with --revive."""
    return retired.gate('pool', 'pool.py ' + (argv[0] if argv else ''), argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
