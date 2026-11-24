"""Real RAR volume number of each scrambled, number-named part of an NZB.

Usage: python3 -I tools/brain/rarorder.py <file.nzb>
Reads one article per part (its first). Prints [[part name, [format, header type, flags, volume]], ...].
"""
import json, os, re, sys, threading, queue
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nntp import Conn, provider  # noqa: E402
from yenc import decode as ydecode  # noqa: E402

NS = {'n': 'http://www.newzbin.com/DTD/2003/nzb'}


def vint(b, i):
    v = s = 0
    while True:
        x = b[i]; i += 1
        v |= (x & 0x7f) << s; s += 7
        if not x & 0x80:
            return v, i


def rar_volume(data):
    if data.startswith(b'Rar!\x1a\x07\x01\x00'):  # RAR5
        i = 8 + 4  # skip sig + header CRC
        size, j = vint(data, i)
        htype, j = vint(data, j)
        hflags, j = vint(data, j)
        if hflags & 1: _, j = vint(data, j)  # extra size
        if hflags & 2: _, j = vint(data, j)  # data size
        aflags, j = vint(data, j)
        vol = vint(data, j)[0] if aflags & 2 else 0
        return 'rar5', htype, aflags, vol
    if data.startswith(b'Rar!\x1a\x07\x00'):
        flags = int.from_bytes(data[7 + 3:7 + 5], 'little')
        return 'rar4', None, flags, ('first' if flags & 0x100 else '?')
    return 'unknown', data[:8].hex()


def main():
    host, port, user, pw = provider()
    parts = []
    for f in ET.parse(sys.argv[1]).getroot().findall('n:file', NS):
        name = re.search(r'"([^"]+)"', f.get('subject')).group(1)
        if re.search(r'\.\d+$', name):
            seg = min(f.findall('n:segments/n:segment', NS), key=lambda s: int(s.get('number')))
            parts.append((name, seg.text.strip()))
    q = queue.Queue(); [q.put(p) for p in parts]
    res, lock = {}, threading.Lock()

    def work():
        c = Conn(host, port, user, pw)
        while True:
            try: name, mid = q.get_nowait()
            except queue.Empty: break
            c.s.sendall(f'BODY <{mid}>\r\n'.encode())
            st = c.line()
            lines = []
            if st.startswith('222'):
                while True:
                    ln = c.f.readline().rstrip(b'\r\n')
                    if ln == b'.': break
                    lines.append(ln[1:] if ln.startswith(b'..') else ln)
            with lock:
                res[name] = rar_volume(ydecode(lines)) if lines else ('err', st[:30])
        c.cmd('QUIT')

    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    rows = sorted(res.items(), key=lambda kv: int(kv[0].rsplit('.', 1)[1]))
    print(json.dumps(rows))


if len(sys.argv) != 2:
    sys.exit('usage: python3 -I tools/brain/rarorder.py <file.nzb>')
main()
