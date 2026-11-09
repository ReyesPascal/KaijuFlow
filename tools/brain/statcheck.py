"""STAT every article of an NZB on the provider; downloads nothing.

Usage: python3 -I tools/brain/statcheck.py <file.nzb>
Prints missing articles per file, split into video parts and par2 files.
"""
import json, os, re, sys, threading, queue

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nntp import Conn, provider  # noqa: E402
import xml.etree.ElementTree as ET

NS = {'n': 'http://www.newzbin.com/DTD/2003/nzb'}
CONNS = 8


def articles(path):
    out = []
    for f in ET.parse(path).getroot().findall('n:file', NS):
        name = re.search(r'"([^"]+)"', f.get('subject')).group(1)
        for s in f.findall('n:segments/n:segment', NS):
            out.append((name, int(s.get('number')), s.text.strip()))
    return out


def main():
    arts = articles(sys.argv[1])
    host, port, user, pw = provider()
    q = queue.Queue()
    for a in arts:
        q.put(a)
    missing, errors, lock = [], [], threading.Lock()

    def work():
        c = Conn(host, port, user, pw)
        while True:
            try:
                a = q.get_nowait()
            except queue.Empty:
                break
            try:
                r = c.cmd(f'STAT <{a[2]}>')
            except Exception as e:  # reconnect once
                c = Conn(host, port, user, pw)
                r = c.cmd(f'STAT <{a[2]}>')
            if r.startswith('223'):
                continue
            with lock:
                (missing if r.startswith('430') else errors).append((a[0], a[1], r[:40]))
        c.cmd('QUIT')

    ts = [threading.Thread(target=work) for _ in range(CONNS)]
    for t in ts: t.start()
    for t in ts: t.join()
    by_file = {}
    for name, num, _ in arts:
        by_file.setdefault(name, [0, 0])[0] += 1
    for name, num, _ in missing:
        by_file[name][1] += 1
    par2 = lambda n: n.endswith('.par2')
    video = {n: v for n, v in by_file.items() if not par2(n)}
    rep = {
        'articles': len(arts), 'missing': len(missing), 'errors': errors[:10],
        'video_parts': len(video), 'video_articles': sum(v[0] for v in video.values()),
        'video_missing': sum(v[1] for v in video.values()),
        'video_parts_with_missing': {n: v for n, v in video.items() if v[1]},
        'par2_missing': {n: v for n, v in by_file.items() if par2(n) and v[1]},
    }
    print(json.dumps(rep, indent=1))


if len(sys.argv) != 2:
    sys.exit('usage: python3 -I tools/brain/statcheck.py <file.nzb>')
main()
