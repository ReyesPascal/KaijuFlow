"""yEnc for the Brain tools (#284): decode an article's body and check it against its own trailer.

An article's body is `=ybegin ...`, for a part `=ypart begin=B end=E`, the encoded lines, then `=yend size=S part=N
pcrc32=XXXXXXXX` (a part's CRC32) or `crc32=` (a whole one-part file's). STAT says only that a server has an article by
that name; this says whether the bytes it sends are the bytes that were posted (NNTP_HEALTH_CHECKS.md, gap D).
"""
import re
import zlib

FIELD = re.compile(rb'(\w+)=(\S+)')


def decode(lines):
    """The bytes of a yEnc body (its lines without line ends, dot-unstuffed); the `=y` lines are left out."""
    out = bytearray()
    for ln in lines:
        if ln.startswith(b'=y'):
            continue
        i = 0
        while i < len(ln):
            c = ln[i]
            if c == 0x3d and i + 1 < len(ln):
                i += 1
                c = (ln[i] - 64) & 0xff
            out.append((c - 42) & 0xff)
            i += 1
    return bytes(out)


def _fields(lines, head):
    line = next((ln for ln in lines if ln.startswith(head)), None)
    if line is None:
        return None
    return {k.decode(): v.decode('latin-1') for k, v in FIELD.findall(line[len(head):])}


def check(lines):
    """{'intact': True/False, 'why', 'size', 'want_size', 'crc', 'want_crc'} for one article's body: intact when its decoded
    bytes have the size its trailer (or its part range) names and the CRC32 it names."""
    begin, part, end = _fields(lines, b'=ybegin '), _fields(lines, b'=ypart '), _fields(lines, b'=yend')
    data = decode(lines)
    crc = f'{zlib.crc32(data) & 0xffffffff:08x}'
    out = {'size': len(data), 'crc': crc, 'want_size': None, 'want_crc': None}
    if begin is None:
        return dict(out, intact=False, why='no =ybegin line: not a yEnc body')
    if end is None:
        return dict(out, intact=False, why='no =yend line: the body ends early')
    want_size = int(end.get('size', -1))
    if part and 'begin' in part and 'end' in part:
        want_size = int(part['end']) - int(part['begin']) + 1
    named = end.get('pcrc32') or end.get('crc32')
    want_crc = named.lower().rjust(8, '0') if named else None
    out.update(want_size=want_size, want_crc=want_crc)
    if len(data) != want_size:
        return dict(out, intact=False, why=f'{len(data)} bytes decoded, its trailer names {want_size}')
    if want_crc and crc != want_crc:
        return dict(out, intact=False, why=f'CRC32 {crc}, its trailer names {want_crc}')
    return dict(out, intact=True, why='size and CRC32 match its trailer' if want_crc else 'size matches; no CRC32 in its trailer')
