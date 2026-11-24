"""Indexer allowance (spec #77, ticket #87): how much of each indexer's daily limit is used since its last reset.

The limits sit in each indexer's entry of the key file, outside the repo (#302; format: tools/brain/indexers.example.json;
written by `testbed.py indexer add`). Only the limit fields are read here, never a key.
Counted per indexer, since its last reset:
  - the stand-in's recorded requests: RECORD and ERROR lines of every record folder's logs/standin.log ("t=" is the epoch ms);
    an "api" request is a search, an "nzb" request is a download. HIT lines are replays and cost the indexer nothing.
  - the counts the live copy keeps: queryHistory (searches) and grabHistory (downloads) in its config/stats.json.
    The test copies are not counted: they only talk to the stand-in. A copy keeps only its latest 100 entries of each, so a busy day can be undercounted.
This counts this machine only. Nothing here talks to an indexer.
"""
import datetime
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402

ROLLING = 'rolling-24h'
DEFAULT_LIVE_STATS = os.path.expanduser('~/usenet-stack/usenet-ultimate_config/stats.json')
KINDS = ('search', 'download')
KIND_NAMES = {'search': 'searches', 'download': 'downloads'}
CAVEAT = ('This counts this machine only, and each copy of Usenet Ultimate keeps only its latest hundred searches '
          'and its latest hundred downloads, so on a busy day the real use can be higher.')
COLUMNS = ('Columns: Used = requests counted since the indexer last reset; Limit = the daily limit from the key file; '
           'Left = Limit minus Used.')
ADD_COMMAND = 'python3 -I tools/brain/testbed.py indexer add {slug} --stash <entry> --searches <n> --downloads <n>'
LIMIT_FIELDS = ('search_per_day', 'download_per_day', 'reset', 'timezone')
CAPS_PING_LOG = 'caps-pings.log'  # in the runs root: the check preflight's caps requests (#303), one search each


def limits_path(cfg):
    """The key file: --key-file, else the test folder's indexers.json. The limits live in its entries (#302)."""
    return cfg.get('key_file') or os.path.join(cfg['test_dir'], 'indexers.json')


def add_command(slug='<slug>'):
    """The command that writes an indexer's entry, its limits with it."""
    return ADD_COMMAND.format(slug=slug)


def norm(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def _reset_time(reset):
    m = re.fullmatch(r'([01]?\d|2[0-3]):([0-5]\d)', str(reset))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _whole(n):
    return isinstance(n, int) and not isinstance(n, bool)


def load_limits(path):
    """({normalized name: {'name', 'search', 'download', 'reset', 'timezone'}}, problem sentence or None), read from the
    key file's entries (#302). An entry with no limit field in it has no limits (left out); no sentence holds a key."""
    if not os.path.exists(path):
        return None, (f'There is no key file yet at {path}, so the daily limits cannot be checked: add each indexer with '
                      f'{add_command()}.')
    data = br.read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get('indexers'), dict):
        return None, f'The key file {path} has no "indexers" list: add each indexer with {add_command()}.'
    out = {}
    for name, v in data['indexers'].items():
        v = v if isinstance(v, dict) else {}
        if not any(k in v for k in LIMIT_FIELDS):
            continue
        search, down, reset = v.get('search_per_day'), v.get('download_per_day'), v.get('reset', ROLLING)
        if not _whole(search) or not _whole(down) or (reset != ROLLING and _reset_time(reset) is None):
            return None, (f'The key file {path} has wrong limits for {name}: it needs search_per_day and download_per_day '
                          f'(whole numbers) and reset ("{ROLLING}" or a clock time like "04:00"); write them with '
                          f'{add_command(name)}.')
        out[norm(name)] = {'name': name, 'search': search, 'download': down, 'reset': reset, 'timezone': v.get('timezone', 'UTC')}
    if not out:
        return None, f'The key file {path} has no daily limits for any indexer: add them with {add_command()}.'
    return out, None


def last_reset(limit, now):
    """When this indexer last reset (an aware datetime). Rolling: 24 hours ago. Clock time: the latest such time not after now."""
    if limit['reset'] == ROLLING:
        return now - datetime.timedelta(hours=24)
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(limit['timezone'])
    except Exception:  # an unknown zone name: read the clock time as UTC
        tz = datetime.timezone.utc
    h, m = _reset_time(limit['reset'])
    local = now.astimezone(tz)
    at = local.replace(hour=h, minute=m, second=0, microsecond=0)
    if at > local:
        at -= datetime.timedelta(days=1)
    return at


def _parse_iso(s):
    try:
        when = datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=datetime.timezone.utc)


def requests_in(log):
    """[(slug, kind, when)] for the RECORD and ERROR lines of one stand-in log."""
    out = []
    try:
        with open(log, errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        m = re.match(r'(RECORD|ERROR) (\S+) (api|nzb)\b.* t=(\d+)$', line)
        if m:
            out.append((norm(m.group(2)), 'search' if m.group(3) == 'api' else 'download',
                        datetime.datetime.fromtimestamp(int(m.group(4)) / 1000, datetime.timezone.utc)))
    return out


def standin_requests(runs_root):
    """Every request the stand-in sent to a real indexer, from every record folder's log."""
    out = []
    for log in sorted(glob.glob(os.path.join(runs_root, '*', 'logs', 'standin.log'))) + [os.path.join(runs_root, CAPS_PING_LOG)]:
        out.extend(requests_in(log))
    return out


def copy_requests(stats_files):
    """[(slug, kind, when)] from the counter files (config/stats.json) the copies keep."""
    out = []
    for path in stats_files:
        data = br.read_json(path)
        indexers = data.get('indexers') if isinstance(data, dict) else None
        if not isinstance(indexers, dict):
            continue
        for name, v in indexers.items():
            if not isinstance(v, dict):
                continue
            for field, kind in (('queryHistory', 'search'), ('grabHistory', 'download')):
                for e in v.get(field) or []:
                    when = _parse_iso(e.get('timestamp')) if isinstance(e, dict) else None
                    if when is not None:
                        out.append((norm(name), kind, when))
    return out


def default_stats_files(cfg):
    """Only the live copy: the test copies talk to the stand-in, so their counters never measure real indexer hits."""
    return [DEFAULT_LIVE_STATS]


def usage(limits, standin, copies, now):
    """{normalized name: {'since', 'standin': {kind: n}, 'copies': {kind: n}}} for every indexer in the limits file."""
    out = {}
    for slug, lim in limits.items():
        since = last_reset(lim, now)
        row = {'since': since, 'standin': dict.fromkeys(KINDS, 0), 'copies': dict.fromkeys(KINDS, 0)}
        for src, key in ((standin, 'standin'), (copies, 'copies')):
            for s, kind, when in src:
                if s == slug and since <= when <= now:
                    row[key][kind] += 1
        out[slug] = row
    return out


def table(limits, used):
    lines = ['Indexer      What        Used   Limit    Left']
    for slug, lim in limits.items():
        row = used[slug]
        for kind in KINDS:
            n = row['standin'][kind] + row['copies'][kind]
            lines.append(f'{lim["name"]:<12} {KIND_NAMES[kind]:<10} {n:>5}  {lim[kind]:>6}  {lim[kind] - n:>6}')
        lines.append(f'  since {row["since"].strftime("%Y-%m-%d %H:%M %Z")}; stand-in recordings '
                     f'{row["standin"]["search"]} searches, {row["standin"]["download"]} downloads; copies '
                     f'{row["copies"]["search"]} searches, {row["copies"]["download"]} downloads.')
    return lines


def _compute(cfg, now, stats_files):
    """(limits, used, problem): the key file's limits read and the counts added up."""
    limits, problem = load_limits(limits_path(cfg))
    if problem:
        return None, None, problem
    standin = standin_requests(cfg['runs_root']) if cfg.get('runs_root') else []
    copies = copy_requests(stats_files if stats_files is not None else default_stats_files(cfg))
    return limits, usage(limits, standin, copies, now), None


def usage_lines(cfg, now=None, stats_files=None):
    """The `usage` command's text, one string per line. Limits that cannot be read give the one sentence."""
    limits, used, problem = _compute(cfg, now or datetime.datetime.now(datetime.timezone.utc), stats_files)
    if problem:
        return [problem]
    return table(limits, used) + [COLUMNS, CAVEAT]


def left(cfg, now=None, stats_files=None):
    """({normalized name: {'search': n, 'download': n}} left since each indexer's last reset, None) or (None, the problem
    sentence when the key file's limits cannot be used). What a real-use check's preflight holds against what it may ask (#270)."""
    limits, used, problem = _compute(cfg, now or datetime.datetime.now(datetime.timezone.utc), stats_files)
    if problem:
        return None, problem
    return {slug: {kind: lim[kind] - used[slug]['standin'][kind] - used[slug]['copies'][kind] for kind in KINDS}
            for slug, lim in limits.items()}, None
