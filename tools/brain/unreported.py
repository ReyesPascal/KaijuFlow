"""The runs the handoff note may not know: INDEX.md rows newer than the note's last commit (#229).

    python3 -I tools/brain/unreported.py [runs root]

Prints one line per row of `<runs root>/INDEX.md` (default ~/kaijuflow-notes/brain-runs) dated after the last commit of
the handoff note ~/kaijuflow-notes/NEXT_SESSION.md (in the KaijuFlow repo before 2026-11-24): date, name, result, folder. A run that stopped or missed requests and never reached
the note shows here, so the next session reads it before running again (on 2026-11-21 a stopped #218 attempt missed 863
requests, the note never said so, and the next session ran into the same misses). Prints "none" when there is no such row.
Exits 0; 1 when git cannot date the note.
"""
import os
import re
import subprocess
import sys

NOTE = os.path.expanduser('~/kaijuflow-notes/NEXT_SESSION.md')
DEFAULT_ROOT = os.path.expanduser('~/kaijuflow-notes/brain-runs')
ROW = re.compile(r'^\|\s*(\d{4}-\d\d-\d\dT[\d:.]+Z)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|.*\|\s*\[([^\]]*)\]\([^)]*\)\s*\|\s*$')


def note_time(note=NOTE):
    """The note's last commit as a UTC ISO time with a Z, like INDEX.md's dates; None when git cannot say."""
    done = subprocess.run(['git', '-C', os.path.dirname(note), 'log', '-1', '--date=format-local:%Y-%m-%dT%H:%M:%S',
                           '--format=%cd', '--', os.path.basename(note)],
                          capture_output=True, text=True, env={**os.environ, 'TZ': 'UTC'})
    stamp = done.stdout.strip()
    return stamp + 'Z' if done.returncode == 0 and stamp else None


def rows_after(index_text, since):
    """(date, name, result, folder) for each INDEX.md row dated after `since`, oldest first."""
    out = []
    for line in index_text.splitlines():
        m = ROW.match(line)
        if m and m.group(1) > since:
            out.append(m.groups())
    return out


def main(argv):
    root = argv[1] if len(argv) > 1 else DEFAULT_ROOT
    since = note_time()
    if not since:
        print(f'git cannot date {NOTE}', file=sys.stderr)
        return 1
    try:
        text = open(os.path.join(root, 'INDEX.md')).read()
    except OSError:
        text = ''
    rows = rows_after(text, since)
    print(f'Runs since the handoff note ({since}):' + (' none' if not rows else ''))
    for date, name, result, folder in rows:
        print(f'  {date}  {name}  {result}  {folder}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
