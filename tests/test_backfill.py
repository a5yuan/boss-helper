"""回填脚本：从历史采集与筛选文件补事件，且重复跑不产生重复。"""
import json
import os
import tempfile
import unittest
from unittest import mock

from src.storage import events
from src.storage.stats import backfill_collect_events, backfill_plan_events


class TestBackfillCandidates(unittest.TestCase):
    def test_collect_events_from_jobs_files(self):
        with tempfile.TemporaryDirectory() as root:
            jobs = [{"encrypt_job_id": "E1", "collected_at": "2026-11-20T16:02:44.949769"},
                    {"encrypt_job_id": "E2", "collected_at": "2026-11-20T16:03:00.100000"}]
            with open(os.path.join(root, "jobs_2026-11-20_x.json"), "w", encoding="utf-8") as f:
                json.dump(jobs, f)
            got = backfill_collect_events(root, "boss")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["event"], "collect")
        self.assertEqual(got[0]["count"], 2)
        self.assertEqual(got[0]["file"], "jobs_2026-11-20_x.json")
        # 时间取最后一条的 collected_at
        self.assertTrue(got[0]["ts"].startswith("2026-11-20T16:03"))

    def test_plan_events_from_ai_plan_files(self):
        with tempfile.TemporaryDirectory() as root:
            plan = {
                "generated_at": "2026-11-25T09:34:56",
                "summary": {"total": 30, "planned": 17, "skipped": 13, "excluded": 0},
            }
            with open(os.path.join(root, "ai_plan_2026-11-25_x.json"), "w", encoding="utf-8") as f:
                json.dump(plan, f)
            got = backfill_plan_events(root, "boss")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["event"], "screen")
        self.assertEqual(got[0]["count"], 30)
        self.assertEqual(got[0]["planned"], 17)
        self.assertEqual(got[0]["skipped"], 13)

    def test_non_plan_files_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("readme.txt", "plan.json", "ai_plan_x.md"):
                with open(os.path.join(root, name), "w", encoding="utf-8") as f:
                    f.write("{}")
            self.assertEqual(backfill_plan_events(root, "boss"), [])
            self.assertEqual(backfill_collect_events(root, "boss"), [])

    def test_broken_json_is_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "ai_plan_x.json"), "w", encoding="utf-8") as f:
                f.write("{坏的")
            self.assertEqual(backfill_plan_events(root, "boss"), [])

    def test_missing_dir_returns_empty(self):
        self.assertEqual(backfill_plan_events("/nonexistent/dir", "boss"), [])
        self.assertEqual(backfill_collect_events("/nonexistent/dir", "boss"), [])


class TestBackfillScript(unittest.TestCase):
    """真跑 scripts/backfill_events.py 的回填逻辑。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "boss")
        os.makedirs(self.out, exist_ok=True)

        with open(os.path.join(self.out, "jobs_2026-11-20_x.json"), "w", encoding="utf-8") as f:
            json.dump([{"collected_at": "2026-11-20T16:02:44.9"}], f)
        with open(os.path.join(self.out, "ai_plan_2026-11-25_y.json"), "w", encoding="utf-8") as f:
            json.dump({"generated_at": "2026-11-25T09:34:56",
                       "summary": {"total": 3, "planned": 1, "skipped": 2, "excluded": 0}}, f)

        def fake_config(browser_type="chrome", platform=None):
            return {"output_dir": self.out}

        # 脚本从 platform_output_dir 找文件，写入走 events.get_config，两处都要指到临时目录
        p = mock.patch("src.storage.events.get_config", side_effect=fake_config)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch("src.storage.events.known_platforms", return_value=["boss"])
        q.start()
        self.addCleanup(q.stop)

    def _backfill(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "backfill_events",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "scripts", "backfill_events.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.backfill_platform("boss", out_dir=self.out)

    def test_backfill_writes_events(self):
        result = self._backfill()
        self.assertEqual(result["written"], 2)
        rows = events.load("boss")
        self.assertEqual(len(rows), 2)
        kinds = sorted(r["event"] for r in rows)
        self.assertEqual(kinds, ["collect", "screen"])

    def test_backfill_is_idempotent(self):
        """重复跑不产生重复事件。"""
        self._backfill()
        before = len(events.load("boss"))
        second = self._backfill()
        after = len(events.load("boss"))
        self.assertEqual(second["written"], 0)
        self.assertEqual(second["skipped"], 2)
        self.assertEqual(before, after)

    def test_third_run_still_idempotent(self):
        self._backfill()
        self._backfill()
        self._backfill()
        self.assertEqual(len(events.load("boss")), 2)

    def test_same_file_twice_does_not_duplicate(self):
        """jobs_*.json 是累积文件，回填两次也不能变成两条。"""
        self._backfill()
        # 模拟又采集了一次同一个文件，collected_at 变了
        path = os.path.join(self.out, "jobs_2026-11-20_x.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([{"collected_at": "2026-11-20T18:00:00.0"}], f)
        self._backfill()
        collects = [r for r in events.load("boss") if r["event"] == "collect"]
        self.assertEqual(len(collects), 1)


class TestDedupKey(unittest.TestCase):
    def test_file_backed_events_dedupe_by_event_and_file(self):
        """累积文件多次回填的 ts 会变，去重键不能含 ts。"""
        a = {"event": "collect", "file": "jobs_x.json", "ts": "2026-11-20T16:00:00"}
        b = {"event": "collect", "file": "jobs_x.json", "ts": "2026-11-20T18:00:00"}
        self.assertEqual(events.dedup_key(a), events.dedup_key(b))

    def test_different_files_are_distinct(self):
        a = {"event": "collect", "file": "jobs_a.json"}
        b = {"event": "collect", "file": "jobs_b.json"}
        self.assertNotEqual(events.dedup_key(a), events.dedup_key(b))

    def test_runtime_events_dedupe_by_ts_event_job(self):
        a = {"event": "apply", "job_id": "J1", "ts": "2026-11-23T18:17:25"}
        b = {"event": "apply", "job_id": "J1", "ts": "2026-11-23T18:17:25"}
        c = {"event": "apply", "job_id": "J1", "ts": "2026-11-23T18:17:26"}
        self.assertEqual(events.dedup_key(a), events.dedup_key(b))
        self.assertNotEqual(events.dedup_key(a), events.dedup_key(c))


if __name__ == "__main__":
    unittest.main()
