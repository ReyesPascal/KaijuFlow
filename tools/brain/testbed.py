"""Reset and emptiness check for the test copies (spec #58, ticket #60).

    python3 -I tools/brain/testbed.py up|stop|status
    python3 -I tools/brain/testbed.py reset [side ...]    cold reset, then the emptiness check
    python3 -I tools/brain/testbed.py check [side ...]    emptiness check only
    python3 -I tools/brain/testbed.py settings [--limit 100]   every test copy's settings and the connection budget, read from its config files

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
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves it off sys.path
import brainreport as br  # noqa: E402
from common import DEFAULT_TEST_DIR  # noqa: E402

PROJECT = "kaijuflow-test"
NETWORK = "kaijuflow-test-net"
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


# --------------------------------------------------------------------------- settings reader (spec #72, ticket #74)

STANDIN_PORT = 1340
PROVIDER_LIMIT = 100  # NewsHosting plan, owner 2026-11-09
STANDIN_HOST = "host.docker.internal"
# One table of the sides in the settings table, in column order: title (column head), short name, and the JSON config
# (relative to the test folder) of the sides that have one.
SETTINGS = {
    "kaijuflow": dict(title="KaijuFlow (1338)", short="KaijuFlow", json="config/config.json"),
    "uu": dict(title="Usenet Ultimate (1339)", short="Usenet Ultimate", json="uu/config/config.json"),
    "nzbdav": dict(title="NzbDAV (3001)", short="NzbDAV"),
    "altmount-addon": dict(title="AltMount addon (8086)", short="AltMount addon"),
    "altmount-kf": dict(title="AltMount KaijuFlow (8087)", short="AltMount KaijuFlow"),
}
SETTINGS_SIDES = list(SETTINGS)
JSON_CONFIGS = {side: v["json"] for side, v in SETTINGS.items() if "json" in v}


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _read_text(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def nzbdav_settings(db_path):
    """NzbDAV's stored settings (ConfigItems), secrets replaced by ***."""
    if not os.path.exists(db_path):
        return {}
    db = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    try:
        rows = db.execute("select ConfigName, ConfigValue from ConfigItems").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        db.close()
    out = {}
    for name, value in rows:
        try:
            parsed = json.loads(value) if value and value.strip()[:1] in "{[" else None
        except ValueError:
            parsed = None
        if parsed is not None:
            out.update(br.flatten(parsed, name))
        else:
            out[name] = br._scrub_value(name, value)
    return out


def read_settings(test_dir):
    """Settings of every test copy with secrets removed: {side: {dotted key: value}}."""
    snap = {}
    for side, rel in JSON_CONFIGS.items():
        data = _read_json(os.path.join(test_dir, rel))
        snap[side] = br.flatten(data) if data is not None else {"(file missing)": rel}
    snap["nzbdav"] = nzbdav_settings(os.path.join(test_dir, "nzbdav/config/db.sqlite"))
    for side in ("altmount-addon", "altmount-kf"):
        text = _read_text(os.path.join(test_dir, side, "config/config.yaml"))
        snap[side] = br.flatten_yaml(text) if text is not None else {"(file missing)": side}
    return snap


def standin_slug(url, port=STANDIN_PORT):
    """The indexer slug of a stand-in address (http://host.docker.internal:<port>/<slug>[/api]), else None."""
    try:
        u = urllib.parse.urlparse(url)
        if u.scheme != "http" or u.hostname != STANDIN_HOST or u.port != port:
            return None
    except ValueError:
        return None
    parts = [p for p in u.path.split("/") if p]
    if len(parts) == 1 or (len(parts) == 2 and parts[1] == "api"):
        return parts[0]
    return None


def _bare(url):
    """An address without query or login, so no key can ride along."""
    try:
        u = urllib.parse.urlparse(str(url))
        return urllib.parse.urlunparse((u.scheme, u.netloc.rsplit("@", 1)[-1], u.path, "", "", ""))
    except ValueError:
        return "(unreadable address)"


def read_indexers(test_dir):
    """{side: [{"name", "url", "enabled"}] or None when the config cannot be read}; no keys, no queries.

    Also lists any other route to an indexer that is switched on (Easynews, Prowlarr), under its own name.
    """
    out = {}
    for side, rel in JSON_CONFIGS.items():
        data = _read_json(os.path.join(test_dir, rel))
        if not isinstance(data, dict):
            out[side] = None
            continue
        rows = [{"name": str(i.get("name", "?")), "url": _bare(i.get("url", "")), "enabled": bool(i.get("enabled"))}
                for i in data.get("indexers", []) if isinstance(i, dict)]
        if data.get("easynewsEnabled"):
            rows.append({"name": "Easynews", "url": "(Easynews)", "enabled": True})
        out[side] = rows
    for side in ("altmount-addon", "altmount-kf"):
        text = _read_text(os.path.join(test_dir, side, "config/config.yaml"))
        if text is None:
            out[side] = None
            continue
        flat = br.flatten_yaml(text)
        rows = [r for _n, r in _altmount_indexers(flat)]
        for k in ("stremio.indexers.prowlarr.enabled", "stremio.prowlarr.enabled"):
            if _true(flat.get(k, "")):
                rows.append({"name": "Prowlarr", "url": "(Prowlarr)", "enabled": True})
        out[side] = rows
    out["nzbdav"] = []
    return out


def enabled_slugs(rows, port=STANDIN_PORT):
    """Sorted slugs of the switched-on indexers; an address that is not the stand-in's shows as ?name."""
    return sorted({standin_slug(r["url"], port) or "?" + r["name"] for r in rows if r["enabled"]})


def _int(v):
    try:
        return int(str(v))
    except ValueError:
        return None


def _true(v):
    """A true/false setting as read from a YAML or JSON flat map."""
    return str(v).lower() == "true"


def _altmount_indexers(flat):
    """[(index, {"name", "url", "enabled"})] of AltMount's newznab indexers, from its flattened config."""
    nums = sorted({int(m.group(1)) for k in flat for m in [re.match(r"stremio\.indexers\.newsnab\[(\d+)\]\.", k)] if m})
    out = []
    for n in nums:
        p = "stremio.indexers.newsnab[%d]." % n
        out.append((n, {"name": str(flat.get(p + "name", "?")), "url": _bare(flat.get(p + "url", "")), "enabled": _true(flat.get(p + "enabled", ""))}))
    return out


def provider_rows(flat, kind):
    """The Usenet provider entries of a Backend as [{"host", "max", "main"}]: NzbDAV (types 1 and 2 are main providers, type 3
    a backup login) or AltMount (enabled providers; main = not flagged as a backup provider)."""
    rows = []
    for i in range(20):
        if kind == "nzbdav":
            p = "usenet.providers.Providers[%d]." % i
            t = _int(flat.get(p + "Type"))
            if t is None:
                continue
            rows.append({"host": flat.get(p + "Host"), "max": _int(flat.get(p + "MaxConnections")), "main": t in (1, 2)})
        else:
            p = "providers[%d]." % i
            if _true(flat.get(p + "enabled")):
                rows.append({"host": flat.get(p + "host"), "max": _int(flat.get(p + "max_connections")),
                             "main": not _true(flat.get(p + "is_backup_provider"))})
    return rows


def counted_rows(rows):
    """(entries on the main provider's host, entries on another host). Backup flag or not, an entry on the same Usenet host
    as a main provider draws on the same connection limit; an entry on another host (a backup login) has its own."""
    hosts = {r["host"] for r in rows if r["main"]}
    return [r for r in rows if r["host"] in hosts], [r for r in rows if r["host"] not in hosts]


def connection_caps(settings):
    """NewsHosting connections each test copy may open: {side: int or None when it cannot be read}.

    KaijuFlow and Usenet Ultimate: their health-check cap. NzbDAV: its main providers (types 1 and 2; a backup login,
    type 3, has its own limit unless it is on the same host). AltMount: its enabled providers. In both, every entry on the
    main provider's Usenet host counts, backup flag or not; an entry on another host is shown beside and not counted.
    """
    caps = {}
    for side in ("kaijuflow", "uu"):
        caps[side] = _int(settings.get(side, {}).get("healthChecks.maxConnections"))
    for side, kind in (("nzbdav", "nzbdav"), ("altmount-addon", "altmount"), ("altmount-kf", "altmount")):
        mine, _other = counted_rows(provider_rows(settings.get(side, {}), kind))
        caps[side] = sum(r["max"] for r in mine) if mine and None not in [r["max"] for r in mine] else None
    return caps


def settings_report(test_dir, limit=PROVIDER_LIMIT):
    """Everything the settings command prints and the preflight checks, from the test copies' own files."""
    settings = read_settings(test_dir)
    indexers = read_indexers(test_dir)
    caps = connection_caps(settings)
    return {"settings": settings, "indexers": indexers,
            "enabled": {s: enabled_slugs(r) if r is not None else None for s, r in indexers.items()},
            "caps": caps, "total": sum(c for c in caps.values() if c is not None), "limit": limit}


def _cell(flat, *keys):
    vals = [str(flat[k]) for k in keys if k in flat]
    return " / ".join(vals) if vals else "-"


def _per_indexer(flat, key, names):
    """Name and value of each switched-on indexer of a KaijuFlow or Usenet Ultimate config."""
    vals = []
    for k in sorted(flat):
        m = re.match(r"indexers\[(.+)\]\.%s$" % re.escape(key), k)
        if m and m.group(1) in names:
            vals.append("%s %s" % (m.group(1), flat[k]))
    return ", ".join(vals) if vals else "-"


def _am_timeouts(flat):
    vals = sorted({str(v) for k, v in flat.items() if re.match(r"stremio\.indexers\.newsnab\[\d+\]\.timeout_seconds$", k)})
    return " / ".join(v + " s" for v in vals) if vals else "-"


def _rows(rep):
    st = rep["settings"]
    both = ("kaijuflow", "uu")
    am = ("altmount-addon", "altmount-kf")

    def g(s):
        return st.get(s, {})

    def on(s):
        return {r["name"] for r in (rep["indexers"].get(s) or []) if r["enabled"]}

    def per(sides, fn):
        return {s: fn(g(s)) for s in sides}

    def conns(s):
        if rep["caps"].get(s) is None:
            return "-"
        _mine, other = counted_rows(provider_rows(g(s), "nzbdav" if s == "nzbdav" else "altmount"))
        return "max %s%s" % (rep["caps"][s], "".join(" (+ other host max %s, own limit)" % r["max"] for r in other))

    yield "Usenet connections (NewsHosting)", {s: conns(s) for s in SETTINGS_SIDES}
    yield "Health check: samples per NZB / NZBs inspected", per(both, lambda f: _cell(f, "healthChecks.sampleCount", "healthChecks.nzbsToInspect"))
    yield "Health check: method / batch / extra runs / min healthy", per(both, lambda f: _cell(
        f, "healthChecks.inspectionMethod", "healthChecks.smartBatchSize", "healthChecks.smartAdditionalRuns", "healthChecks.smartMinHealthy"))
    yield "Health check: archive inspection", per(both, lambda f: _cell(f, "healthChecks.archiveInspection"))
    yield "Pages per enabled indexer (maxPages)", {s: _per_indexer(g(s), "maxPages", on(s)) for s in both}
    yield "Pages: season pack / series pack extra pages", per(both, lambda f: _cell(f, "searchConfig.seasonPackAdditionalPages", "searchConfig.seriesPackAdditionalPages"))
    yield "Indexer timeout (s)", {**{s: _per_indexer(g(s), "timeout", on(s)) for s in both}, **per(am, _am_timeouts)}
    yield "Enabled indexers (slugs)", {s: ", ".join(rep["enabled"].get(s) or []) or "-" for s in SETTINGS_SIDES}
    yield "Import workers (max_processor_workers)", per(am, lambda f: _cell(f, "import.max_processor_workers"))
    yield "NzbDAV download connections / streaming priority", {"nzbdav": _cell(g("nzbdav"), "usenet.max-download-connections", "usenet.streaming-priority")}
    yield "Import samples % / health samples % / health system on", per(am, lambda f: _cell(f, "import.segment_sample_percentage", "health.segment_sample_percentage", "health.enabled"))
    yield "Prefetch: streaming.max_prefetch / import.max_download_prefetch", per(am, lambda f: _cell(f, "streaming.max_prefetch", "import.max_download_prefetch"))
    yield "In-flight per connection: normal / stat / stream", per(am, lambda f: _cell(f, "providers[0].inflight_requests", "providers[0].stat_inflight_requests", "providers[0].stream_inflight_requests"))
    yield "AltMount segment cache: on / GB / hours / MB memory", per(am, lambda f: _cell(f, "segment_cache.enabled", "segment_cache.max_size_gb", "segment_cache.expiry_hours", "segment_cache.memory_mb"))
    yield "Cache: search results (cacheTTL s)", per(both, lambda f: _cell(f, "cacheTTL"))
    yield "Cache: healthy NZB DB mode / TTL / MB", per(both, lambda f: _cell(f, "healthyNzbDbMode", "healthyNzbDbTTL", "healthyNzbDbMaxSizeMB"))
    yield "Cache: dead NZB DB mode / TTL / MB", per(both, lambda f: _cell(f, "deadNzbDbMode", "deadNzbDbTTL", "deadNzbDbMaxSizeMB"))
    yield "Cache: stream buffer / pipe buffer MB / method", {"uu": _cell(g("uu"), "nzbdavStreamBufferMB", "nzbdavPipeBufferMB", "nzbdavStreamingMethod")}
    yield "AltMount addon: fallback ms / retries / max fallback releases", per(am, lambda f: _cell(f, "stremio.fallback_timeout_ms", "stremio.max_retries", "stremio.max_fallback_releases"))
    yield "AltMount: fast_fail_header_only / skip_repair", per(am, lambda f: _cell(f, "stremio.fast_fail_header_only", "stremio.skip_repair"))
    yield "AltMount: PAR2 repair / failure masking / mount type", per(am, lambda f: _cell(f, "par2_repair.enabled", "streaming.failure_masking.enabled", "mount_type"))


def render_settings(rep):
    """The settings table and the connection budget, as Markdown with no secret in it."""
    lines = ["| Setting | " + " | ".join(SETTINGS[s]["title"] for s in SETTINGS_SIDES) + " |",
             "|---|" + "---|" * len(SETTINGS_SIDES)]
    for label, cells in _rows(rep):
        lines.append("| %s | " % label + " | ".join(str(cells.get(s, "-")) for s in SETTINGS_SIDES) + " |")
    caps = rep["caps"]
    per = ", ".join("%s %s" % (SETTINGS[s]["short"], caps[s] if caps.get(s) is not None else "unreadable") for s in SETTINGS_SIDES)
    verdict = "fits the provider limit" if rep["total"] <= rep["limit"] else "over the provider limit"
    lines += ["", "Connection budget (configured caps, not actual use)", "",
              "Per copy: %s." % per,
              "Total: %d of %d NewsHosting connections: %s." % (rep["total"], rep["limit"], verdict)]
    return "\n".join(lines) + "\n"


def main(argv):
    test_dir = os.environ.get("TEST_DIR", DEFAULT_TEST_DIR)
    if len(argv) >= 2 and argv[1] == "settings":
        limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else PROVIDER_LIMIT
        print(render_settings(settings_report(test_dir, limit)), end="")
        return 0
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
