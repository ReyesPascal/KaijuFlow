"""Scrub an NZB captured on Brain into a test fixture.

Kept as captured: the XML layout, file order, subjects (release names, yEnc
counters), dates, groups, segment numbers and byte counts. Scrubbed: message
ids (replaced by `<file>-<segment>@fixture`, so no article can be fetched with
them), posters and the <head> metadata. Trimmed: each file keeps five segments
(the first two, the middle one and the last two), which still hold the first,
middle and last segment the health check samples.

Run from the repo root: python3 -I tests/fixtures/nzbs/scrub.py <captured.nzb> <fixture.nzb>
The fixtures here came from the indexer answers recorded for the `kf-189`
recording (run #189, 2026-11-20).
"""
import re
import sys

SEGMENT = re.compile(r'([ \t]*)<segment bytes="(\d+)" number="(\d+)">[^<]*</segment>\n?')


def keep(numbers):
    ordered = sorted(numbers)
    n = len(ordered)
    picks = {0, 1, n // 2, n - 2, n - 1}
    return {ordered[i] for i in picks if 0 <= i < n}


def scrub_file(match, index):
    head, body = match.group(1), match.group(2)
    head = re.sub(r'poster="[^"]*"', 'poster="poster@example.invalid"', head)
    segs = SEGMENT.findall(body)
    kept = keep([int(num) for _, _, num in segs])
    lines = ''.join(
        f'{indent}<segment bytes="{size}" number="{num}">f{index}-{num}@fixture</segment>\n'
        for indent, size, num in segs if int(num) in kept
    )
    body = re.sub(r'(<segments>\n?)(?:.*?)([ \t]*</segments>)', lambda m: m.group(1) + lines + m.group(2), body, flags=re.S)
    return head + body


def scrub(xml):
    xml = re.sub(r'<head>.*?</head>\n?', '', xml, flags=re.S)
    files = re.compile(r'(<file [^>]*>)(.*?</file>)', re.S)
    counter = iter(range(1, 10**6))
    return files.sub(lambda m: scrub_file(m, next(counter)), xml)


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding='utf-8') as f:
        out = scrub(f.read())
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(out)
