"""列表到底终止：所有卡片都被跳过时，采集必须收敛而不是空转。

覆盖 ``run_collection`` 的收敛规则：
- 连续 2 轮没有新卡片触发刷新，最多刷新 2 次，之后判定「到底」正常结束
- 刷新失败直接结束，不抛异常
- 有新的（即使被跳过的）卡片时，连续计数必须清零
"""
import json
import tempfile
import unittest
from unittest import mock

from src.collector import run_collection


class FakeBrowser:
    """页面门面的假实现：只记录 URL，不做任何 I/O。"""

    def __init__(self, config=None):
        self.config = config
        self.port = 0
        self.ws = None
        self.should_stop = None
        self.url = "https://fake.example/jobs?q=python"

    def try_connect_existing(self):
        return True

    def launch(self, start_url=None):
        if start_url:
            self.url = start_url
        return True

    def close(self):
        self.ws = None

    def list_pages(self):
        return [{"type": "page", "url": self.url, "webSocketDebuggerUrl": "ws://fake"}]

    def connect_ws(self, ws_url):
        self.ws = ws_url
        return True

    def evaluate(self, expression, await_promise=False, timeout=30):
        if expression == "location.href":
            return self.url
        if expression.startswith("location.href="):
            self.url = json.loads(expression.split("=", 1)[1])
        return None

    def get_value(self, result):
        return result

    def disconnect(self):
        self.ws = None

    def bring_to_front(self):
        pass

    def native_click(self, x, y):
        pass

    def send_cdp(self, method, params=None, timeout=30, stop_check=None):
        return {}


class RecordingController:
    """记录日志、进度和终态，遇到人工等待直接失败。"""

    def __init__(self):
        self.logs = []
        self.progress_events = []
        self.final_state = None
        self.final_detail = None

    def log(self, msg="", level="info", end="\n"):
        self.logs.append(str(msg))

    def progress(self, done, total, stats=None):
        self.progress_events.append({"done": done, "total": total, "stats": stats or {}})

    def status(self, state, detail=None):
        self.final_state = state
        self.final_detail = detail

    def wait_user(self, reason, kind="confirm"):
        raise AssertionError(f"到底流程不该等待人工输入: {reason}")

    def should_stop(self):
        return False

    def should_pause(self):
        return False


def _card(job_id):
    from src.adapters import fake as fake_platform
    data = fake_platform.JOBS[job_id]
    return {
        "job_id": job_id,
        "title": data["title"],
        "salary": data["salary"],
        "area": data["area"],
        "company": data["company"],
        "raw": {},
    }


def _list_result(job_ids):
    return {"ok": True, "reason": "", "jobs": [_card(j) for j in job_ids]}


def _repeating_jobs(job_ids, limit=40):
    """每轮都返回同一批卡片；超过上限说明没有收敛，直接失败而不是挂死。"""
    calls = {"n": 0}

    def side_effect():
        calls["n"] += 1
        if calls["n"] > limit:
            raise AssertionError("采集没有收敛：list_jobs 调用次数超过上限")
        return _list_result(job_ids)

    return side_effect


class TestCollectorBottomTermination(unittest.TestCase):
    def setUp(self):
        # 延迟导入：tests/test_fake_platform.py 在导入时快照已注册适配器，
        # 这里不能提前把 fake 注册进 registry。
        from src.adapters import fake as fake_platform
        self.fake_platform = fake_platform

    def _run(self, list_jobs_side_effect, reload_side_effect):
        ctrl = RecordingController()
        adapter_cls = self.fake_platform.FakePlatformAdapter
        with tempfile.TemporaryDirectory() as out_dir, \
                mock.patch("src.collector.BrowserManager", FakeBrowser), \
                mock.patch("src.collector.get_config", return_value={"output_dir": out_dir}), \
                mock.patch("src.storage.events.get_config",
                           return_value={"output_dir": out_dir}), \
                mock.patch("src.collector._interruptible_sleep"), \
                mock.patch.object(adapter_cls, "list_jobs", side_effect=list_jobs_side_effect), \
                mock.patch.object(adapter_cls, "reload", side_effect=reload_side_effect):
            result = run_collection(
                count=3, site="fake", query="python", keyword_search=True,
                tag="stale", speed="fast", controller=ctrl,
                salary_min=5, salary_max=10,
            )
        return result, ctrl

    def test_all_cards_skipped_ends_at_bottom_after_two_reloads(self):
        reload_calls = []

        def reload_side_effect():
            reload_calls.append(1)
            return {"ok": True, "reason": ""}

        result, ctrl = self._run(_repeating_jobs(["fake-1", "fake-2"]), reload_side_effect)

        self.assertEqual(ctrl.final_state, "done")
        self.assertEqual(result["reason"], "bottom")
        self.assertEqual(len(reload_calls), 2)
        self.assertEqual(result["success"], 0)
        self.assertEqual(result["skip"], 2)

        summary = [line for line in ctrl.logs if "已滚动到底" in line]
        self.assertEqual(len(summary), 1, ctrl.logs)
        self.assertIn("刷新 2 次", summary[0])
        self.assertEqual(ctrl.final_detail["reason"], "bottom")

    def test_reload_failure_ends_without_exception(self):
        reload_calls = []

        def reload_side_effect():
            reload_calls.append(1)
            return {"ok": False, "reason": "boom"}

        result, ctrl = self._run(_repeating_jobs(["fake-1", "fake-2"]), reload_side_effect)

        self.assertEqual(ctrl.final_state, "done")
        self.assertEqual(result["reason"], "reload_failed")
        self.assertEqual(len(reload_calls), 1)
        self.assertTrue(any("boom" in line for line in ctrl.logs), ctrl.logs)

    def test_stale_count_resets_when_a_new_card_appears(self):
        list_rounds = []
        reload_at = []

        def list_jobs_side_effect():
            list_rounds.append(len(list_rounds) + 1)
            job_ids = ["fake-1"] if len(list_rounds) == 1 else ["fake-1", "fake-2"]
            return _list_result(job_ids)

        def reload_side_effect():
            reload_at.append(len(list_rounds))
            return {"ok": True, "reason": ""}

        result, ctrl = self._run(list_jobs_side_effect, reload_side_effect)

        # 第 2 轮还有新卡片（fake-2），必须再连续 2 轮空转才刷新 → 第 4 轮才 reload
        self.assertEqual(reload_at[0], 4, reload_at)
        self.assertEqual(len(reload_at), 2)
        self.assertEqual(result["reason"], "bottom")

        processed = [ev["stats"].get("processed", 0) for ev in ctrl.progress_events]
        self.assertEqual(processed[0], 0)
        self.assertEqual(max(processed), 2)
        self.assertGreater(processed[-1], processed[0])


if __name__ == "__main__":
    unittest.main()
