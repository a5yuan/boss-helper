"""事件流：写入、读取、坏行跳过、写失败不影响调用方。"""
import json
import os
import tempfile
import unittest
from unittest import mock

from src.storage import events


class _TempPlatform:
    """把事件文件指向临时目录，不碰真实的 output/。"""

    def __init__(self, root):
        self.root = root
        self._patches = []

    def start(self):
        def fake_config(browser_type="chrome", platform=None):
            name = platform or "boss"
            path = os.path.join(self.root, name)
            os.makedirs(path, exist_ok=True)
            return {"output_dir": path}

        p = mock.patch("src.storage.events.get_config", side_effect=fake_config)
        p.start()
        self._patches.append(p)

        def fake_platforms():
            try:
                return sorted(n for n in os.listdir(self.root)
                              if os.path.isdir(os.path.join(self.root, n)))
            except OSError:
                return []

        q = mock.patch("src.storage.events.known_platforms", side_effect=fake_platforms)
        q.start()
        self._patches.append(q)
        return self

    def stop(self):
        for p in reversed(self._patches):
            p.stop()
        self._patches = []

    def path(self, platform="boss"):
        return os.path.join(self.root, platform, "events.jsonl")


class TestRecord(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = _TempPlatform(self.tmp.name).start()
        self.addCleanup(self.env.stop)

    def test_record_writes_one_json_line(self):
        events.record("apply", "boss", job_id="J1", company="甲公司", status="submitted")

        with open(self.env.path(), "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec["event"], "apply")
        self.assertEqual(rec["platform"], "boss")
        self.assertEqual(rec["job_id"], "J1")
        self.assertEqual(rec["status"], "submitted")
        self.assertIs(rec["ok"], True)
        # ts 自动填，调用方不传
        self.assertTrue(rec["ts"])

    def test_record_appends_never_overwrites(self):
        events.record("apply", "boss", job_id="J1")
        events.record("apply", "boss", job_id="J2")
        self.assertEqual(len(events.load("boss")), 2)

    def test_ts_can_be_given_explicitly(self):
        events.record("collect", "boss", ts="2020-01-01T00:00:00", count=3)
        rec = events.load("boss")[0]
        self.assertEqual(rec["ts"], "2020-01-01T00:00:00")

    def test_write_failure_never_raises(self):
        """统计是旁路：写失败不能拖垮投递。"""
        with mock.patch("builtins.open", side_effect=OSError("磁盘满了")):
            events.record("apply", "boss", job_id="J1")   # 不抛异常

    def test_write_failure_in_unwritable_dir_never_raises(self):
        with mock.patch("src.storage.events.os.makedirs",
                        side_effect=PermissionError("没有权限")):
            events.record("apply", "boss", job_id="J1")

    def test_none_fields_are_dropped(self):
        events.record("apply", "boss", job_id="J1", reason=None, duration_ms=0)
        rec = events.load("boss")[0]
        self.assertNotIn("reason", rec)
        self.assertEqual(rec["duration_ms"], 0)


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = _TempPlatform(self.tmp.name).start()
        self.addCleanup(self.env.stop)

    def _write(self, platform, *lines):
        path = self.env.path(platform)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")

    def test_bad_line_is_skipped_not_fatal(self):
        self._write("boss",
                    json.dumps({"ts": "2026-01-01T00:00:00", "event": "apply"}),
                    "{这不是 JSON",
                    json.dumps({"ts": "2026-01-01T00:01:00", "event": "apply"}))
        got = events.load("boss")
        self.assertEqual(len(got), 2)
        self.assertEqual(got.bad_lines, 1)

    def test_non_dict_line_is_skipped(self):
        self._write("boss", "[1,2,3]", "\"abc\"")
        got = events.load("boss")
        self.assertEqual(got, [])
        self.assertEqual(got.bad_lines, 2)

    def test_missing_file_is_empty_not_error(self):
        got = events.load("zhaopin")
        self.assertEqual(got, [])
        self.assertEqual(got.bad_lines, 0)

    def test_platform_filter(self):
        self._write("boss", json.dumps({"ts": "2026-01-01T00:00:00", "event": "apply"}))
        self._write("zhaopin", json.dumps({"ts": "2026-01-01T00:00:00", "event": "apply"}))
        self.assertEqual(len(events.load("boss")), 1)
        self.assertEqual(len(events.load("zhaopin")), 1)
        self.assertEqual(len(events.load()), 2)

    def test_since_filters_by_ts(self):
        self._write("boss",
                    json.dumps({"ts": "2026-01-01T00:00:00", "event": "apply"}),
                    json.dumps({"ts": "2026-01-02T00:00:00", "event": "apply"}))
        got = events.load("boss", since="2026-01-02T00:00:00")
        self.assertEqual(len(got), 1)

    def test_sorted_by_ts(self):
        self._write("boss",
                    json.dumps({"ts": "2026-01-03T00:00:00", "event": "apply"}),
                    json.dumps({"ts": "2026-01-01T00:00:00", "event": "apply"}))
        got = events.load("boss")
        self.assertEqual([r["ts"] for r in got],
                         ["2026-01-01T00:00:00", "2026-01-03T00:00:00"])


class TestLegacyMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = _TempPlatform(self.tmp.name).start()
        self.addCleanup(self.env.stop)

    def _legacy(self, platform="zhaopin"):
        path = os.path.join(self.tmp.name, platform, "apply_audit.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def test_migrates_apply_and_send_message(self):
        legacy = self._legacy()
        with open(legacy, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "2026-11-23T18:17:25", "event": "apply",
                                "job_id": "J1", "company": "甲公司", "ok": True,
                                "submitted": True, "reason": ""}) + "\n")
            f.write(json.dumps({"ts": "2026-11-23T18:17:27", "event": "send_message",
                                "job_id": "J1", "company": "甲公司", "length": 191,
                                "sent": True, "reason": ""}) + "\n")

        moved = events.migrate_legacy_audit("zhaopin")
        self.assertEqual(moved, 2)

        rows = {r["event"]: r for r in events.load("zhaopin")}
        self.assertEqual(rows["apply"]["status"], "submitted")
        self.assertEqual(rows["apply"]["ts"], "2026-11-23T18:17:25")
        self.assertEqual(rows["send_message"]["length"], 191)
        self.assertIs(rows["send_message"]["sent"], True)

    def test_migration_is_idempotent(self):
        legacy = self._legacy()
        with open(legacy, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "2026-11-23T18:17:25", "event": "apply",
                                "job_id": "J1", "submitted": True}) + "\n")
        self.assertEqual(events.migrate_legacy_audit("zhaopin"), 1)
        self.assertEqual(events.migrate_legacy_audit("zhaopin"), 0)
        self.assertEqual(len(events.load("zhaopin")), 1)

    def test_old_file_is_kept(self):
        legacy = self._legacy()
        with open(legacy, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "2026-11-23T18:17:25", "event": "apply",
                                "job_id": "J1", "submitted": True}) + "\n")
        events.migrate_legacy_audit("zhaopin")
        self.assertTrue(os.path.exists(legacy))

    def test_unsubmitted_apply_migrates_as_drafted(self):
        legacy = self._legacy()
        with open(legacy, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "2026-11-23T18:17:25", "event": "apply",
                                "job_id": "J1", "submitted": False}) + "\n")
        events.migrate_legacy_audit("zhaopin")
        self.assertEqual(events.load("zhaopin")[0]["status"], "drafted")


if __name__ == "__main__":
    unittest.main()
