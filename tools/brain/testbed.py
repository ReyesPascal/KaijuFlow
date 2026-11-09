"""Reset and emptiness check for the test copies (spec #58, ticket #60).

    python3 -I tools/brain/testbed.py up|stop|status
    python3 -I tools/brain/testbed.py reset [side ...]    cold reset, then the emptiness check
    python3 -I tools/brain/testbed.py check [side ...]    emptiness check only

Sides: nzbdav, altmount-addon, altmount-kf (Backends), uu, kaijuflow (their health/dead caches).
Config folders (with secrets) live in TEST_DIR (default /home/ryan/kaijuflow-test), never in the repo.
Every Docker command is pinned to compose project `kaijuflow-test` and to the five test services
(compose_cmd), so nothing here can act on a live container.
"""
import base64
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
from common import DEFAULT_TEST_DIR  # noqa: E402

PROJECT = "kaijuflow-test"
COMPOSE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compose.test.yaml")
TEST_CONTAINERS = ["kaijuflow-test", "uu-test", "nzbdav-test", "altmount-addon-test", "altmount-kf-test"]

# side -> compose service, kind, config folder, template folder, port
SIDES = {
    "nzbdav": dict(kind="nzbdav", conf="nzbdav/config", tpl="nzbdav", port=3001),
    "altmount-addon": dict(kind="altmount", conf="altmount-addon/config", tpl="altmount", port=8086),
    "altmount-kf": dict(kind="altmount", conf="altmount-kf/config", tpl="altmount", port=8087),
    "uu": dict(kind="cache", conf="uu/config", tpl="uu", port=1339),
    "kaijuflow": dict(kind="cache", conf="config", tpl="kaijuflow", port=1338),
}
CACHE_FILES = ("healthy-nzbs.json", "dead-nzbs.json")


def compose_cmd(test_dir, verb, *services):
    """argv of one `docker compose` call; refuses anything but the test folder and test services."""
    if os.path.basename(os.path.normpath(test_dir)) != PROJECT:
        raise ValueError("TEST_DIR must be the %s folder, got %s" % (PROJECT, test_dir))
    for s in services:
        if s not in SIDES:
            raise ValueError("not a test service: %s" % s)
    cmd = ["docker", "compose", "-p", PROJECT, "--env-file", os.path.join(test_dir, ".env"), "-f", COMPOSE_FILE, verb]
    if verb == "up":
        cmd.append("-d")
    return cmd + list(services)


def _run(argv):
    import subprocess
    return subprocess.call(argv, timeout=300)


def wait_ready(side, timeout=180):
    """Waits until the side answers HTTP on its port (any status counts)."""
    url = "http://127.0.0.1:%d/" % SIDES[side]["port"]
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=5)
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(2)
    raise RuntimeError("%s did not answer on %s within %d s" % (side, url, timeout))


def _rm(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def _empty_dir(path):
    if os.path.isdir(path):
        for name in os.listdir(path):
            _rm(os.path.join(path, name))


def _restore(test_dir, side):
    spec = SIDES[side]
    conf = os.path.join(test_dir, spec["conf"])
    tpl = os.path.join(test_dir, "templates", spec["tpl"])
    if spec["kind"] == "nzbdav":
        for name in ("db.sqlite", "db.sqlite-wal", "db.sqlite-shm", "blobs"):
            _rm(os.path.join(conf, name))
        shutil.copyfile(os.path.join(tpl, "db.sqlite"), os.path.join(conf, "db.sqlite"))
    elif spec["kind"] == "altmount":
        for name in ("altmount.db", "altmount.db-wal", "altmount.db-shm", ".nzbs"):
            _rm(os.path.join(conf, name))
        _empty_dir(os.path.join(conf, "metadata"))
        _empty_dir(os.path.join(conf, "segment-cache"))
        shutil.copyfile(os.path.join(tpl, "altmount.db"), os.path.join(conf, "altmount.db"))
    else:
        for name in CACHE_FILES:
            _rm(os.path.join(conf, name))
            shutil.copyfile(os.path.join(tpl, name), os.path.join(conf, name))
        _rm(os.path.join(conf, "stats.json"))


def reset(test_dir, sides=None, runner=_run, wait=wait_ready, log=None):
    """Cold reset: stop each side, restore it from its template, start it again."""
    log = log or (lambda msg: None)
    sides = list(sides) if sides else list(SIDES)
    for s in sides:
        if s not in SIDES:
            raise ValueError("not a test side: %s" % s)
    for s in sides:
        if runner(compose_cmd(test_dir, "stop", s)) != 0:
            raise RuntimeError("docker compose stop %s failed; nothing wiped for it" % s)
        _restore(test_dir, s)
        log("reset %s: restored from template" % s)
        if runner(compose_cmd(test_dir, "up", s)) != 0:
            raise RuntimeError("docker compose up %s failed" % s)
        wait(s)
        log("reset %s: up" % s)


def default_http(method, url, headers=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _ro(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)


def _count(db, sql):
    return db.execute(sql).fetchone()[0]


def _check_nzbdav(test_dir, side, http):
    spec = SIDES[side]
    path = os.path.join(test_dir, spec["conf"], "db.sqlite")
    out = []
    try:
        db = _ro(path)
        files = _count(db, "select count(*) from DavItems where Type != 1")
        hist = _count(db, "select count(*) from HistoryItems")
        queue = _count(db, "select count(*) from QueueItems")
        cfg = dict(db.execute("select ConfigName, ConfigValue from ConfigItems").fetchall())
        db.close()
    except sqlite3.Error as e:
        return ["%s: cannot read database (%s)" % (side, e)]
    for label, n in (("DavItems files", files), ("HistoryItems", hist), ("QueueItems", queue)):
        if n:
            out.append("%s: database has %d %s" % (side, n, label))
    for mode in ("history", "queue"):
        url = "http://127.0.0.1:%d/api?mode=%s&output=json&apikey=%s" % (spec["port"], mode, cfg.get("api.key", ""))
        try:
            status, body = http("GET", url)
            n = json.loads(body)[mode]["noofslots"]
        except (OSError, ValueError, KeyError) as e:
            out.append("%s: %s API unreadable (%s)" % (side, mode, type(e).__name__))
            continue
        if status != 200 or n:
            out.append("%s: %s API shows %s entries (status %s)" % (side, mode, n, status))
    return out


ALTMOUNT_TABLES = ("import_queue", "import_history", "media_files", "file_health", "nzb_store_refs", "duplicate_lookup_catalog")


def _yaml_value(text, section, key):
    m = re.search(r"^%s:\n(?:    .*\n)*?    %s: (.*)$" % (section, key), text, re.M)
    return m.group(1).strip().strip('"') if m else ""


def _files_under(path):
    found = []
    for root, _dirs, files in os.walk(path):
        found += [os.path.join(root, f) for f in files]
    return found


def _check_altmount(test_dir, side, http):
    spec = SIDES[side]
    conf = os.path.join(test_dir, spec["conf"])
    out = []
    try:
        db = _ro(os.path.join(conf, "altmount.db"))
        for t in ALTMOUNT_TABLES:
            n = _count(db, 'select count(*) from "%s"' % t)
            if n:
                out.append("%s: database table %s has %d rows" % (side, t, n))
        db.close()
    except sqlite3.Error as e:
        out.append("%s: cannot read database (%s)" % (side, e))
    for sub in ("metadata", ".nzbs", "segment-cache"):
        n = len(_files_under(os.path.join(conf, sub)))
        if n:
            out.append("%s: %d files left in %s" % (side, n, sub))
    try:
        with open(os.path.join(conf, "config.yaml")) as f:
            text = f.read()
        auth = base64.b64encode(("%s:%s" % (_yaml_value(text, "webdav", "user"), _yaml_value(text, "webdav", "password"))).encode()).decode()
        status, body = http("PROPFIND", "http://127.0.0.1:%d/webdav/" % spec["port"], {"Depth": "1", "Authorization": "Basic " + auth})
        entries = len(re.findall(r"<[A-Za-z]*:?href>", body, re.I))
        if status not in (200, 207):
            out.append("%s: webdav answered status %s" % (side, status))
        elif entries > 1:
            out.append("%s: webdav lists %d entries below /webdav/" % (side, entries - 1))
    except OSError as e:
        out.append("%s: webdav unreadable (%s)" % (side, type(e).__name__))
    return out


def _check_cache(test_dir, side, _http):
    out = []
    for name in CACHE_FILES:
        path = os.path.join(test_dir, SIDES[side]["conf"], name)
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            out.append("%s: %s unreadable (%s)" % (side, name, type(e).__name__))
            continue
        if data:
            out.append("%s: %s holds %d entries" % (side, name, len(data)))
    return out


def check_empty(test_dir, sides=None, http=default_http):
    """Returns a list of problems; empty means every named side holds no imported item."""
    problems = []
    for side in (sides or list(SIDES)):
        kind = SIDES[side]["kind"]
        fn = {"nzbdav": _check_nzbdav, "altmount": _check_altmount, "cache": _check_cache}[kind]
        problems += fn(test_dir, side, http)
    return problems


def main(argv):
    test_dir = os.environ.get("TEST_DIR", DEFAULT_TEST_DIR)
    if len(argv) < 2 or argv[1] not in ("up", "stop", "status", "reset", "check"):
        print(__doc__)
        return 2
    cmd, sides = argv[1], argv[2:]
    start = time.time()
    code = 0
    if cmd in ("up", "stop", "status"):
        verb = {"up": "up", "stop": "stop", "status": "ps"}[cmd]
        argv_ = compose_cmd(test_dir, verb, *sides)
        code = _run(argv_)
    else:
        if cmd == "reset":
            reset(test_dir, sides or None, log=print)
        problems = check_empty(test_dir, sides or None)
        for p in problems:
            print("NOT EMPTY: " + p)
        if problems:
            code = 1
        else:
            print("EMPTY: every checked test Backend holds no imported item")
    print("done in %d s" % (time.time() - start))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
