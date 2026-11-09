"""Search side-by-side on Brain: the same titles through AltMount's own Stremio addon (8085), the KaijuFlow test
container with AltMount as Backend (1338) and UU 1337 with NzbDAV as the baseline.

Usage: python3 -I tools/brain/search.py <user-id> <altmount-download-key> <out.json>
SEARCH_TITLES="Interstellar,Game of Thrones" limits a run to the titles whose label contains one of the names.
SEARCH_TRIES=3 is how many Streams from the top of each list are played (64 KiB at the start).
SEARCH_SIDES="altmount-addon,kaijuflow-altmount" limits a run to those sides (default: all three).
For each title and side: Sources shown, time until the list shows, whether the first Stream plays on the first
try, time to the first byte of the first Stream that plays, and how many of the tried Streams are broken (listed
but won't play). Sides run one after the other (not in parallel) so the indexers are not hit by three searches at
once; the order rotates per title. Medians per side are printed as a Markdown table and written to <out>.md.
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
from common import finish, fmt, get, med, pick_titles, play_stream as play  # noqa: E402

if len(sys.argv) != 4:
    sys.exit('usage: python3 -I tools/brain/search.py <user-id> <altmount-download-key> <out.json>')
U, DK, OUT = sys.argv[1:4]
ALL_SIDES = [
    ('altmount-addon', f'http://localhost:8085/stremio/{DK}'),
    ('kaijuflow-altmount', f'http://localhost:1338/{U}'),
    ('uu-nzbdav', f'http://localhost:1337/{U}'),
]
_only = [s.strip() for s in os.environ.get('SEARCH_SIDES', '').split(',') if s.strip()]
SIDES = [s for s in ALL_SIDES if not _only or s[0] in _only]
if not SIDES:
    sys.exit(f'SEARCH_SIDES={_only} matches none of: ' + ', '.join(n for n, _ in ALL_SIDES))
SHORT = {'altmount-addon': 'AM', 'kaijuflow-altmount': 'KF', 'uu-nzbdav': 'UU'}
TRIES = int(os.environ.get('SEARCH_TRIES', '3'))


def side(base, kind, vid):
    out = {}
    st, h, body, t = get(f'{base}/stream/{kind}/{vid}.json', timeout=180, limit=0)
    out['list_status'] = st
    out['list_s'] = round(t.get('total', t['ready']), 2)
    try:
        streams = json.loads(body or b'{}').get('streams', []) if st == 200 else []
    except Exception as e:  # noqa
        streams, out['note'] = [], f'bad JSON: {e}'[:120]
    if st != 200:
        out['note'] = h.get('error') or f'HTTP {st}'
    out['sources'] = len(streams)
    out['tries'] = [play(s) for s in streams[:TRIES]]
    out['first_try_plays'] = bool(out['tries'] and out['tries'][0]['plays'])
    out['broken'] = sum(1 for x in out['tries'] if not x['plays'])
    first_ok = next((x for x in out['tries'] if x['plays']), None)
    out['first_byte_s'] = first_ok['first_byte_s'] if first_ok else None
    return out


def table(results):
    names = [n for n, _ in SIDES]
    abbr = ' / '.join(SHORT[n] for n in names)
    head = f'| Title | Sources {abbr} | List s {abbr} | 1st try plays {abbr} | 1st byte s {abbr} | Broken of {TRIES} {abbr} |'
    lines = [head, '|---|---|---|---|---|---|']
    agg = {n: {'sources': [], 'list_s': [], 'first_byte_s': [], 'broken': [], 'first_try': []} for n in names}
    for row in results:
        cells = {k: [] for k in ('sources', 'list_s', 'first_try', 'first_byte_s', 'broken')}
        for n in names:
            d = row[n]
            cells['sources'].append(fmt(d.get('sources')))
            cells['list_s'].append(fmt(d.get('list_s')))
            cells['first_try'].append('yes' if d.get('first_try_plays') else ('no' if d.get('sources') else 'none'))
            cells['first_byte_s'].append(fmt(d.get('first_byte_s')))
            cells['broken'].append(fmt(d.get('broken')) if d.get('sources') else '-')
            agg[n]['sources'].append(d.get('sources', 0))
            agg[n]['list_s'].append(d.get('list_s'))
            if d.get('first_byte_s') is not None:
                agg[n]['first_byte_s'].append(d['first_byte_s'])
            if d.get('sources'):
                agg[n]['broken'].append(d.get('broken', 0))
                agg[n]['first_try'].append(1 if d.get('first_try_plays') else 0)
        lines.append(f"| {row['title']} | " + ' | '.join(' / '.join(cells[k]) for k in ('sources', 'list_s', 'first_try', 'first_byte_s', 'broken')) + ' |')
    lines.append('| **Median** | ' + ' / '.join(fmt(med(agg[n]['sources'])) for n in names) + ' | ' +
                 ' / '.join(fmt(med(agg[n]['list_s'])) for n in names) + ' | ' +
                 ' / '.join(f"{sum(agg[n]['first_try'])}/{len(agg[n]['first_try'])}" for n in names) + ' | ' +
                 ' / '.join(fmt(med(agg[n]['first_byte_s'])) for n in names) + ' | ' +
                 ' / '.join(f"{sum(agg[n]['broken'])} total" for n in names) + ' |')
    lines.append('')
    lines.append("AM = AltMount's own Stremio addon (8085), KF = KaijuFlow test container with AltMount as Backend (1338), "
                 'UU = Usenet Ultimate 1337 with NzbDAV (baseline). List s = time until the Stream list arrived; '
                 f'1st byte s = time to the first byte of the first Stream that played; Broken = Streams among the first {TRIES} '
                 'that returned an error or the failure video. Sides ran one after the other, order rotating per title.')
    return '\n'.join(lines)


def main():
    started = time.time()
    results = []
    for i, (kind, vid, label) in enumerate(pick_titles('SEARCH_TITLES')):
        order = SIDES[i % len(SIDES):] + SIDES[:i % len(SIDES)]
        row = {'title': label, 'id': vid, 'order': [n for n, _ in order]}
        for n, base in order:
            row[n] = side(base, kind, vid)
            time.sleep(2)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        json.dump(results, open(OUT, 'w'), indent=2, ensure_ascii=False)  # partial results survive a timeout
    t = table(results)
    open(re.sub(r'\.json$', '', OUT) + '.md', 'w').write(t + '\n')
    print(t)
    finish(started)


main()
