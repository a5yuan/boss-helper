"""投递状态库的单元测试。

运行：
    .venv/Scripts/python -m unittest discover -s tests -v
"""
import json
import os
import tempfile
import unittest

from src.tracking import Tracker, track_key


class TestTrackKey(unittest.TestCase):
    def test_prefers_encrypt_job_id(self):
        self.assertEqual(track_key("sid", "eid"), "eid")

    def test_falls_back_to_security_id(self):
        self.assertEqual(track_key("sid", ""), "sid")

    def test_empty(self):
        self.assertEqual(track_key("", ""), "")


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "tracking.json")
        self.tracker = Tracker(path=self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_set_and_get_persist(self):
        self.tracker.set("eid-1", "shortlisted", note="看起来不错")
        self.assertEqual(self.tracker.get("eid-1")["status"], "shortlisted")
        self.assertEqual(self.tracker.get("eid-1")["note"], "看起来不错")

        # 新实例从磁盘重新加载
        again = Tracker(path=self.path)
        self.assertEqual(again.get("eid-1")["status"], "shortlisted")

    def test_unknown_id_returns_empty_dict(self):
        self.assertEqual(self.tracker.get("missing"), {})

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            self.tracker.set("eid-1", "done")

    def test_empty_id_raises(self):
        with self.assertRaises(ValueError):
            self.tracker.set("", "applied")

    def test_write_is_atomic(self):
        self.tracker.set("eid-1", "applied")
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("eid-1", data)

    def test_all_returns_dict(self):
        self.tracker.set("eid-1", "skipped")
        self.assertIsInstance(self.tracker.all(), dict)


if __name__ == "__main__":
    unittest.main()
