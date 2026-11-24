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

