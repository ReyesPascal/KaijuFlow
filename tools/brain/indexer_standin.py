"""Indexer stand-in (#59): records newznab answers once per title list and replays them byte-identical to every side.

URL shape for a side: http://<host>:1340/<indexer-slug>/api?...  (any dummy API key). Search answers have their NZB
links rewritten to http://<host>:1340/<slug>/nzb/<token>, so a side never contacts the real indexer.

  record: python3 -I tools/brain/indexer_standin.py --mode record --config <indexers.json> --store <dir> --list <name>
  replay: python3 -I tools/brain/indexer_standin.py --mode replay --config <indexers.json> --store <dir> --list <name>

Config (outside the repo, holds the real keys): {"indexers": {"<slug>": {"url": "https://indexer.example", "apikey": "..."}}}
Store layout: <store>/<list>/<slug>/<sha256>.body + .meta.json. Switch list while running: GET /_standin/list?name=X.
Status: GET /_standin/status. A "limit reached" answer while recording writes <store>/LIMIT_REACHED.json, logs a
LIMIT_REACHED line, shows in /_standin/status, is NOT stored, and makes the process exit with status 3 when stopped.
No real indexer is contacted in replay mode.
Indexer time (#73): each stored answer keeps the milliseconds the real indexer took ("ms" in .meta.json). Replay waits that
long before answering (search answers and NZB files) unless --no-wait; every served stored answer logs
"HIT <slug> <request> wait_ms=<n>" (n is 0 when the wait is off, in record mode, or the recording has no time).
Dropped parameters (#73): an indexer entry may carry "drop_params": ["o"]; those query parameters are removed before the
request is looked up or forwarded (DrunkenSlug: o=json, as /home/ryan/ds-xml-proxy does). The list is saved as
<store>/<list>/<slug>/indexer.json (no key in it) and replay reads it from there, so replay needs no key file.
"""
import argparse, signal, base64, hashlib, http.server, json, os, re, sys, threading, time, urllib.error, urllib.request
from urllib.parse import urlparse, parse_qsl, quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
from common import DEFAULT_TEST_DIR  # noqa: E402

KEY_PARAM = 'apikey'
SAFE = re.compile(r'^[A-Za-z0-9._-]+$')
LIMIT_EXIT = 3
SETTINGS_FILE = 'indexer.json'  # per indexer inside a recording: {"drop_params": [...]}; holds no key
HOST_MARK = b'@@STANDIN@@'  # stored in place of the stand-in's own address in rewritten links


def is_limit(status, body):
    """True when an indexer answer says its request/grab limit is reached (HTTP 429, or a newznab <error> about it)."""
    if status == 429:
        return True
    if len(body) > 4096:
        return False
    if body.lstrip()[:1] == b'{':
        return _json_limit(body)
    m = re.search(rb'<error\b[^>]*>', body)
    if not m:
        return False
    tag = m.group(0).lower()
    code = re.search(rb'code="(\d+)"', tag)
    return bool(code and code.group(1) in (b'429', b'500')) or b'limit' in tag


def _json_limit(body):
    """newznab JSON error: {"error": {"@attributes": {"code": "500", "description": "..."}}} (or without @attributes)."""
    try:
        err = json.loads(body).get('error')
    except (ValueError, AttributeError):
        return False
    if isinstance(err, dict):
        err = err.get('@attributes', err)
    if not isinstance(err, dict):
        return isinstance(err, str) and 'limit' in err.lower()
    return str(err.get('code')) in ('429', '500') or 'limit' in json.dumps(err).lower()


def scrub(body, key):
    """Defence in depth: no occurrence of the real key (plain, URL-encoded or JSON-escaped) leaves the stand-in."""
    escaped = json.dumps(key)[1:-1]
    for form in {key, quote(key), quote(key, safe=''), escaped, escaped.replace('/', '\\/')}:
        if form:
            body = body.replace(form.encode(), b'***')
    return body


class State:
    def __init__(self, cfg, store, mode, listname, wait=True):
        self.cfg, self.store, self.mode, self.listname, self.wait = cfg, store, mode, listname, wait
        self.limit_reached = None
        self.log_lines = []
        self.lock = threading.Lock()

    def log(self, line):
        with self.lock:
            self.log_lines.append(line)
        print(line, file=sys.stderr, flush=True)

    def drop_params(self, slug):
        """Request parameters to remove for this indexer: from the key file when recording (and saved next to the
        recorded answers), from the recording itself when replaying. A recording without the file drops nothing."""
        d = os.path.join(self.store, self.listname, slug)
        saved = os.path.join(d, SETTINGS_FILE)
        if self.mode == 'record':
            want = list(self.cfg['indexers'].get(slug, {}).get('drop_params') or [])
            if want:
                if not os.path.exists(saved) or json.loads(rd(saved)).get('drop_params') != want:
                    os.makedirs(d, exist_ok=True)
                    wr(saved, json.dumps({'drop_params': want}))
            elif os.path.exists(saved):
                os.remove(saved)
            return want
        try:
            return list(json.loads(rd(saved)).get('drop_params') or [])
        except (OSError, ValueError):
            return []

    def path(self, slug, key):
        d = os.path.join(self.store, self.listname, slug)
        return d, os.path.join(d, key)


def rd(path, mode='r'):
    with open(path, mode) as f:
        return f.read()


def wr(path, data):
    with open(path, 'wb' if isinstance(data, bytes) else 'w') as f:
        f.write(data)


def cache_key(kind, items):
    return hashlib.sha256((kind + '\n' + '\n'.join(f'{k}={v}' for k, v in items)).encode()).hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    @property
    def st(self):
        return self.server.state

    def reply(self, status, ctype, body):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        parts = u.path.strip('/').split('/')
        q = parse_qsl(u.query, keep_blank_values=True)
        st = self.st
        if parts[0] == '_standin':
            if parts[1:] == ['status']:
                return self.reply(200, 'application/json', json.dumps(
                    {'mode': st.mode, 'list': st.listname, 'wait': st.wait, 'limit_reached': st.limit_reached}).encode())
            if parts[1:] == ['list']:
                name = dict(q).get('name', '')
                if not SAFE.match(name):
                    return self.reply(400, 'text/plain', b'bad list name')
                st.listname = name
                st.log(f'LIST {name}')
                return self.reply(200, 'text/plain', b'ok')
            return self.reply(404, 'text/plain', b'unknown')
        slug = parts[0]
        if not SAFE.match(slug) or (st.mode == 'record' and slug not in st.cfg['indexers']):
            return self.reply(404, 'text/plain', b'unknown indexer')
        host = self.headers.get('Host') or f'127.0.0.1:{self.server.server_port}'
        base = f'http://{host}/{slug}'
        if len(parts) == 3 and parts[1] == 'nzb':
            token = parts[2]
            key = cache_key('nzb', [('token', token)])

            def real_url(ix):
                """The decoded link, or None when it does not lead to the configured indexer's own host."""
                raw = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)).decode()
                a, b = urlparse(raw), urlparse(ix['url'])
                if (a.scheme, a.netloc) != (b.scheme, b.netloc):
                    return None
                return raw.replace('{KEY}', ix['apikey'])
            return self.serve(slug, key, f'nzb {token[:12]}', real_url, base, rewrite=False)
        if len(parts) == 2 and parts[1] == 'api':
            drop = set(st.drop_params(slug))
            items = sorted((k, v) for k, v in q if k != KEY_PARAM and k not in drop)
            key = cache_key('api', items)
            shown = '&'.join(f'{k}={v}' for k, v in items)

            def real_url(ix):
                return ix['url'].rstrip('/') + '/api?' + '&'.join(
                    f'{quote(k)}={quote(v)}' for k, v in items + [(KEY_PARAM, ix['apikey'])])
            return self.serve(slug, key, 'api ' + shown, real_url, base, rewrite=dict(items).get('t') != 'get')
        return self.reply(404, 'text/plain', b'unknown path')

    def serve(self, slug, key, shown, real_url, base, rewrite):
        st = self.st
        d, p = st.path(slug, key)
        if os.path.exists(p + '.body'):
            body = rd(p + '.body', 'rb')
            meta = json.loads(rd(p + '.meta.json'))
            waited = round(meta.get('ms', 0)) if st.mode == 'replay' and st.wait else 0
            st.log(f'HIT {slug} {shown} wait_ms={waited}')
            if waited:
                time.sleep(waited / 1000)
            return self.reply(meta['status'], meta['content_type'], body.replace(HOST_MARK, base.encode()))
        if st.mode == 'replay':
            st.log(f'MISS {slug} {shown}')
            return self.reply(404, 'text/plain', b'not recorded')
        ix = st.cfg['indexers'][slug]
        url = real_url(ix)
        if url is None:
            st.log(f'REFUSED {slug} {shown} (token leads to another host)')
            return self.reply(403, 'text/plain', b'refused')
        began = time.monotonic()
        status, ctype, body = fetch_real(url)
        took_ms = round((time.monotonic() - began) * 1000)
        if is_limit(status, body):
            info = {'indexer': slug, 'time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'status': status,
                    'answer': scrub(body[:300], ix['apikey']).decode('utf-8', 'replace'), 'request': shown}
            st.limit_reached = info
            os.makedirs(st.store, exist_ok=True)
            wr(os.path.join(st.store, 'LIMIT_REACHED.json'), json.dumps(info))
            st.log(f'LIMIT_REACHED indexer={slug} at={info["time"]} status={status}')
            return self.reply(status, ctype, scrub(body, ix['apikey']))
        if rewrite:
            body = rewrite_links(body, ix, slug)
        body = scrub(body, ix['apikey'])
        os.makedirs(d, exist_ok=True)
        wr(p + '.body', body)
        wr(p + '.meta.json', json.dumps({'status': status, 'content_type': ctype, 'request': shown, 'ms': took_ms}))
        st.log(f'RECORD {slug} {shown} -> {status} {len(body)} bytes')
        self.reply(status, ctype, body.replace(HOST_MARK, base.encode()))


def rewrite_links(body, ix, slug):
    """Point every link on the real indexer's host to the stand-in; the key becomes {KEY} inside the token."""
    o = urlparse(ix['url'])
    # '/' may be JSON-escaped as '\/' in o=json answers; the rewritten link is plain (still valid JSON)
    pat = re.compile(re.escape(o.scheme).encode() + rb':(?:\\?/){2}' + re.escape(o.netloc).encode() + rb'[^\s"\'<>]*')

    def sub(m):
        real = m.group(0).decode().replace('\\/', '/').replace('\\u0026', '&').replace('&amp;', '&').replace(ix['apikey'], '{KEY}').replace(quote(ix['apikey']), '{KEY}')
        token = base64.urlsafe_b64encode(real.encode()).decode().rstrip('=')
        return HOST_MARK + b'/nzb/' + token.encode()  # HOST_MARK becomes http://<host>:<port>/<slug> when served
    return pat.sub(sub, body)


def fetch_real(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'kaijuflow-indexer-standin'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.headers.get('Content-Type', 'application/octet-stream'), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type', 'text/plain'), e.read()


def make_server(cfg, store, mode, listname, port=1340, bind='0.0.0.0', wait=True):
    if mode not in ('record', 'replay') or not SAFE.match(listname):
        raise ValueError('mode must be record or replay; list name letters, digits, . _ -')
    srv = http.server.ThreadingHTTPServer((bind, port), Handler)
    srv.state = State(cfg, store, mode, listname, wait)
    return srv


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--mode', required=True, choices=['record', 'replay'])
    ap.add_argument('--config', default=os.path.join(DEFAULT_TEST_DIR, 'indexers.json'))
    ap.add_argument('--store', required=True)
    ap.add_argument('--list', required=True, dest='listname')
    ap.add_argument('--port', type=int, default=1340)
    ap.add_argument('--bind', default='0.0.0.0')
    ap.add_argument('--no-wait', action='store_true', help='replay at once instead of waiting the recorded indexer time')
    a = ap.parse_args()
    cfg = json.loads(rd(a.config)) if a.mode == 'record' else {'indexers': {}}
    srv = make_server(cfg, a.store, a.mode, a.listname, a.port, a.bind, wait=not a.no_wait)
    print(f'stand-in {a.mode} list={a.listname} on {a.bind}:{a.port}', file=sys.stderr, flush=True)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown).start())
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    sys.exit(LIMIT_EXIT if srv.state.limit_reached else 0)


if __name__ == '__main__':
    main()
