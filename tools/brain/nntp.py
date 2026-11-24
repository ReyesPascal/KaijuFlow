"""NNTP access for the Brain tools: the Usenet provider from the test copy's AltMount config, read-only commands only.

The provider is the first enabled main (not backup) provider in `<test folder>/altmount-kf/config/config.yaml`, the test
folder `TEST_DIR` when set, else `common.DEFAULT_TEST_DIR` (#284: the old `~/altmount-stack` path is gone from this
machine). Its login is read by the program and never printed.
"""
import os
import socket
import ssl
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import common  # noqa: E402
import yenc  # noqa: E402

ALTMOUNT_CONFIG = os.path.join('altmount-kf', 'config', 'config.yaml')
NNTPS_PORT = 563


def config_path(test_dir=None):
    test_dir = test_dir or os.environ.get('TEST_DIR') or common.DEFAULT_TEST_DIR
    return os.path.join(os.path.expanduser(test_dir), ALTMOUNT_CONFIG)


def _providers(text):
    """The `providers:` list of AltMount's config.yaml as [{key: value}] (plain values only)."""
    out, inside, indent = [], False, None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        here = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if here == 0:
            inside = line == 'providers:'
            continue
        if not inside:
            continue
        if line.startswith('- '):
            if indent is None or here <= indent:
                indent = here
                out.append({})
            line = line[2:].strip()
        if not out:
            continue
        key, sep, value = line.partition(':')
        if sep and value.strip():
            out[-1][key.strip()] = value.strip().strip('"\'')
    return out


def provider(config=None, test_dir=None):
    """(host, port, user, password) of the first enabled main provider in the test copy's AltMount config.yaml."""
    path = config or config_path(test_dir)
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"AltMount's config is not at {path}") from None
    for p in _providers(text):
        if p.get('enabled', 'true').lower() == 'true' and p.get('is_backup_provider', 'false').lower() != 'true':
            return p['host'], int(p.get('port') or NNTPS_PORT), p.get('username', ''), p.get('password', '')
    raise ValueError(f'{path} names no enabled main provider')


class Conn:
    def __init__(self, host, port, user, pw):
        self.s = ssl.create_default_context().wrap_socket(socket.create_connection((host, port), timeout=30), server_hostname=host)
        self.f = self.s.makefile('rb')
        self.line()
        assert self.cmd(f'AUTHINFO USER {user}').startswith('381')
        assert self.cmd(f'AUTHINFO PASS {pw}').startswith('281'), 'auth failed'

    def line(self):
        return self.f.readline().decode('latin-1').strip()

    def cmd(self, c):
        self.s.sendall((c + '\r\n').encode())
        return self.line()



class Usenet:
    """The live Clues' one read-only connection to the provider (#284), opened at the first command and closed by
    `close`: STAT (pipelined) and BODY only. A body is checked in memory (yenc.check) and dropped; nothing is saved."""
    WINDOW = 100  # STATs sent before their answers are read (RFC 3977 3.5 pipelining)

    def __init__(self, login=None, connect=None):
        self._login, self._connect, self._conn = login, connect or Conn, None
        self.connections = 0

    def _c(self):
        if self._conn is None:
            self._conn = self._connect(*(self._login or provider()))
            self.connections += 1
        return self._conn

    def stat(self, mids):
        """The answer code to `STAT <mid>` for each message-id, in order (0 for an answer with no code)."""
        out = []
        for i in range(0, len(mids), self.WINDOW):
            window = mids[i:i + self.WINDOW]
            c = self._c()
            c.s.sendall(''.join(f'STAT <{m}>\r\n' for m in window).encode())
            for _ in window:
                line = c.line()
                out.append(int(line[:3]) if line[:3].isdigit() else 0)
        return out

    def body(self, mid):
        """{'code', 'intact', 'why', 'size', 'want_size', 'crc', 'want_crc'} for `BODY <mid>`: the body yEnc-checked, not kept."""
        c = self._c()
        c.s.sendall(f'BODY <{mid}>\r\n'.encode())
        status = c.line()
        code = int(status[:3]) if status[:3].isdigit() else 0
        if code != 222:
            return {'code': code}
        lines = []
        while True:
            ln = c.f.readline()
            if not ln:
                return dict(yenc.check(lines), code=code, intact=False, why='the connection ended inside the body')
            ln = ln.rstrip(b'\r\n')
            if ln == b'.':
                break
            lines.append(ln[1:] if ln.startswith(b'..') else ln)
        return dict(yenc.check(lines), code=code)

    def close(self):
        if self._conn is not None:
            try:
                self._conn.cmd('QUIT')
            except OSError:
                pass
            self._conn.s.close()
            self._conn = None
