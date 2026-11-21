"""Tests for testbed.py (reset and emptiness check of the test copies), run in CI with no Docker.

    python3 -I -m unittest discover -s tools/brain -p 'test_*.py'

Seams: compose_cmd() (what may be run), reset() (what it does to config folders and containers)
and check_empty() (what counts as empty), all against fakes: a temp TEST_DIR, a recording
runner instead of Docker, and canned HTTP replies.
"""
import os
import re
import sqlite3
import tempfile
import unittest

import testbed

LIVE = ("usenet-ultimate", "nzbdav", "altmount-altmount-1", "ds-xml-proxy")
# the live services, and the test copies of the runs before #185, which nothing here sets up any more (#187)
NOT_TEST_SERVICES = ("usenet-ultimate", "altmount-altmount-1", "ds-xml-proxy", "altmount", "everything", "uu", "nzbdav",
                     "altmount-addon")


def make_altmount_db(path, queue=0, history=0, media=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    for t in ("import_queue", "import_history", "media_files", "file_health", "nzb_store_refs", "duplicate_lookup_catalog"):
        db.execute("create table %s (id integer)" % t)
    for t, n in (("import_queue", queue), ("import_history", history), ("media_files", media)):
        for i in range(n):
            db.execute("insert into %s values (?)" % t, (i,))
    db.commit()
    db.close()


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class Bed:
    """A fake TEST_DIR: clean templates, dirty live-looking config folders."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "kaijuflow-test")
        d = self.dir
        # templates (clean)
        make_altmount_db(d + "/templates/altmount/altmount.db")
        write(d + "/templates/kaijuflow/healthy-nzbs.json", "{}")
        write(d + "/templates/kaijuflow/dead-nzbs.json", "{}")
        # dirty config folders
        c = d + "/altmount-kf/config"
        make_altmount_db(c + "/altmount.db", queue=2, history=4, media=3)
        write(c + "/altmount.db-wal")
        write(c + "/metadata/movies/item.meta")
        write(c + "/.nzbs/a/x.nzb")
        write(c + "/segment-cache/seg1")
        write(c + "/config.yaml", "webdav:\n    port: 8080\n    user: wu\n    password: wp\n    host: \"\"\n")
        write(d + "/config/healthy-nzbs.json", '{"a": 1}')
        write(d + "/config/dead-nzbs.json", '{"b": 2}')
        write(d + "/config/stats.json", "{}")
        write(d + "/config/uf-sessions.json", '[{"sessionKey": "k:movie:tt1::"}]')
        write(d + "/config/config.json", '{"keep": true}')
        # a stopped test copy of the runs before #185: nothing here touches it (#187)
        write(d + "/uu/config/healthy-nzbs.json", '{"a": 1}')

    def close(self):
        self.tmp.cleanup()


class Runner:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return 0


def http_empty(method, url, headers=None):
    return 207, '<D:multistatus><D:response><D:href>/webdav/</D:href></D:response></D:multistatus>'


class ComposeCmd(unittest.TestCase):
    def test_every_command_is_pinned_to_the_test_project_and_file(self):
        cmd = testbed.compose_cmd("/x/kaijuflow-test", "stop", "altmount-kf")
        self.assertEqual(cmd[:3], ["docker", "compose", "-p"])
        self.assertEqual(cmd[3], "kaijuflow-test")
        self.assertIn("-f", cmd)
        self.assertTrue(cmd[cmd.index("-f") + 1].endswith("tools/brain/compose.test.yaml"))
        self.assertEqual(cmd[-2:], ["stop", "altmount-kf"])

    def test_refuses_a_service_that_is_not_a_test_copy(self):
        for name in NOT_TEST_SERVICES:
            with self.assertRaises(ValueError):
                testbed.compose_cmd("/x/kaijuflow-test", "stop", name)

    def test_refuses_a_test_dir_that_is_not_the_test_folder(self):
        with self.assertRaises(ValueError):
            testbed.compose_cmd("~/usenet-stack", "stop", "altmount-kf")

    def test_compose_file_names_only_test_containers(self):
        text = read(testbed.COMPOSE_FILE)
        self.assertIn("name: kaijuflow-test", text)
        for live in LIVE:
            self.assertNotIn("container_name: %s\n" % live, text)
        for c in testbed.TEST_CONTAINERS:
            self.assertIn("container_name: %s\n" % c, text)

    def test_the_compose_file_sets_up_the_one_setup_alone(self):
        text = read(testbed.COMPOSE_FILE)
        self.assertEqual(sorted(testbed.TEST_CONTAINERS), ["altmount-kf-test", "kaijuflow-test"])
        self.assertEqual(text.count("container_name: "), len(testbed.TEST_CONTAINERS))


class Reset(unittest.TestCase):
    def setUp(self):
        self.bed = Bed()
        self.addCleanup(self.bed.close)

    def test_dirty_beds_fail_the_check(self):
        problems = testbed.check_empty(self.bed.dir, http=http_empty)
        text = "\n".join(problems)
        self.assertIn("altmount-kf", text)
        self.assertIn("kaijuflow", text)

    def test_reset_all_leaves_every_backend_empty(self):
        runner = Runner()
        testbed.reset(self.bed.dir, runner=runner, wait=lambda s: None)
        self.assertEqual(testbed.check_empty(self.bed.dir, http=http_empty), [])

    def test_reset_stops_each_service_before_touching_files_and_starts_it_after(self):
        runner = Runner()
        testbed.reset(self.bed.dir, sides=["altmount-kf"], runner=runner, wait=lambda s: None)
        verbs = [c[c.index("kaijuflow-test") + 1:] for c in runner.calls]
        flat = [v for v in verbs if v]
        self.assertTrue(any("stop" in v and "altmount-kf" in v for v in flat))
        self.assertTrue(any("up" in v and "altmount-kf" in v for v in flat))
        stop_i = next(i for i, c in enumerate(runner.calls) if "stop" in c)
        up_i = next(i for i, c in enumerate(runner.calls) if "up" in c)
        self.assertLess(stop_i, up_i)

    def test_reset_touches_only_the_named_side(self):
        runner = Runner()
        testbed.reset(self.bed.dir, sides=["altmount-kf"], runner=runner, wait=lambda s: None)
        problems = "\n".join(testbed.check_empty(self.bed.dir, http=http_empty))
        self.assertNotIn("altmount-kf", problems)
        self.assertIn("kaijuflow", problems)
        for call in runner.calls:
            self.assertNotIn("kaijuflow", call)

    def test_reset_keeps_settings_and_login_files(self):
        testbed.reset(self.bed.dir, runner=Runner(), wait=lambda s: None)
        d = self.bed.dir
        self.assertIn("wu", read(d + "/altmount-kf/config/config.yaml"))
        self.assertEqual(read(d + "/config/config.json"), '{"keep": true}')

    def test_reset_clears_kaijuflows_health_and_dead_caches_and_stats_and_leaves_the_stopped_copies_alone(self):
        runner = Runner()
        testbed.reset(self.bed.dir, runner=runner, wait=lambda s: None)
        d = self.bed.dir
        self.assertEqual(read(d + "/config/healthy-nzbs.json"), "{}")
        self.assertEqual(read(d + "/config/dead-nzbs.json"), "{}")
        self.assertFalse(os.path.exists(d + "/config/stats.json"))
        self.assertFalse(os.path.exists(d + "/config/uf-sessions.json"), "Best's remembered plays go too (#190)")
        self.assertEqual(read(d + "/uu/config/healthy-nzbs.json"), '{"a": 1}')
        self.assertEqual(sorted(c[-1] for c in runner.calls if c[-2] == "stop"), ["altmount-kf", "kaijuflow"])

    def test_reset_removes_imported_files_and_blobs(self):
        testbed.reset(self.bed.dir, runner=Runner(), wait=lambda s: None)
        d = self.bed.dir
        self.assertFalse(os.path.exists(d + "/altmount-kf/config/.nzbs/a/x.nzb"))
        self.assertFalse(os.path.exists(d + "/altmount-kf/config/metadata/movies/item.meta"))
        self.assertFalse(os.path.exists(d + "/altmount-kf/config/segment-cache/seg1"))

    def test_reset_stops_when_a_container_command_fails(self):
        def failing(argv):
            return 1 if "stop" in argv else 0
        with self.assertRaises(RuntimeError):
            testbed.reset(self.bed.dir, runner=failing, wait=lambda s: None)
        # nothing was wiped
        self.assertTrue(os.path.exists(self.bed.dir + "/altmount-kf/config/.nzbs/a/x.nzb"))

    def test_unknown_side_is_refused(self):
        with self.assertRaises(ValueError):
            testbed.reset(self.bed.dir, sides=["usenet-ultimate"], runner=Runner(), wait=lambda s: None)


class CheckEmpty(unittest.TestCase):
    def setUp(self):
        self.bed = Bed()
        self.addCleanup(self.bed.close)
        testbed.reset(self.bed.dir, runner=Runner(), wait=lambda s: None)

    def test_clean_beds_pass(self):
        self.assertEqual(testbed.check_empty(self.bed.dir, http=http_empty), [])

    def test_altmount_queue_row_fails(self):
        make_altmount_db(self.bed.dir + "/altmount-kf/config/altmount.db", queue=1)
        problems = testbed.check_empty(self.bed.dir, http=http_empty)
        self.assertTrue(any("altmount-kf" in p and "import_queue" in p for p in problems))

    def test_altmount_webdav_entry_fails(self):
        def http(method, url, headers=None):
            if method == "PROPFIND":
                return 207, ('<D:multistatus><D:response><D:href>/webdav/</D:href></D:response>'
                             '<D:response><D:href>/webdav/movies/</D:href></D:response></D:multistatus>')
            return http_empty(method, url, headers)
        self.assertTrue(any("webdav" in p for p in testbed.check_empty(self.bed.dir, http=http)))

    def test_altmount_metadata_file_fails(self):
        write(self.bed.dir + "/altmount-kf/config/metadata/tv/leftover.meta")
        problems = testbed.check_empty(self.bed.dir, http=http_empty)
        self.assertTrue(any("altmount-kf" in p and "metadata" in p for p in problems))

    def test_unreachable_backend_is_a_problem_not_a_pass(self):
        def http(method, url, headers=None):
            raise OSError("connection refused")
        problems = testbed.check_empty(self.bed.dir, http=http)
        self.assertTrue(problems)

    def test_kaijuflows_caches_must_be_empty_too(self):
        write(self.bed.dir + "/config/healthy-nzbs.json", '{"a": 1}')
        problems = testbed.check_empty(self.bed.dir, http=http_empty)
        self.assertTrue(any("kaijuflow" in p and "healthy-nzbs" in p for p in problems))

    def test_kaijuflows_remembered_best_plays_must_be_gone_too(self):
        write(self.bed.dir + "/config/uf-sessions.json", '[{"sessionKey": "k:movie:tt1::"}]')
        problems = testbed.check_empty(self.bed.dir, http=http_empty)
        self.assertTrue(any("kaijuflow" in p and "uf-sessions" in p for p in problems))


class KaijuFlowDefaultCap(unittest.TestCase):
    def test_the_settings_reader_assumes_kaijuflows_own_default_connection_cap(self):
        # a copy whose config names no cap runs on KaijuFlow's default: the reader must count the same number
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "health", "nntpConnection.ts")
        with open(src, encoding="utf-8") as f:
            m = re.search(r"export const DEFAULT_HEALTH_CHECK_CONNECTION_CAP = (\d+);", f.read())
        self.assertIsNotNone(m, "KaijuFlow's default cap is no longer where the brain tools look for it")
        self.assertEqual(testbed.KF_DEFAULT_CONNECTION_CAP, int(m.group(1)))


if __name__ == "__main__":
    unittest.main()
