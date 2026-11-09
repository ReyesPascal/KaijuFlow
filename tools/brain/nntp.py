"""NNTP access for the Brain tools: the Usenet provider from AltMount's config, read-only commands only."""
import re, socket, ssl

ALTMOUNT_CONFIG = '/home/ryan/altmount-stack/config/config.yaml'


def provider(config=ALTMOUNT_CONFIG):
    """(host, port, user, password) of the first provider in AltMount's config.yaml."""
    txt = open(config).read()
    block = txt.split('\nproviders:', 1)[1]
    get = lambda k: re.search(rf'\n\s+{k}:\s*(.+)', block).group(1).strip().strip('"\'')
    return get('host'), int(get('port')), get('username'), get('password')


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
