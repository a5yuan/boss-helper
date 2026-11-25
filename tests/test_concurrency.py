"""并发验收：真 BOSS 适配器 + 假平台同时跑完整 run_collection。

这里刻意不 mock 引擎：两个任务都走 ``src.collector.run_collection``，
BOSS 侧用真实 ``BossAdapter`` 驱动一个只在内存里应答页面脚本的页面替身，
假平台侧走 ``src.adapters.fake``。浏览器传输层被替换，是因为验收不想
真开两个浏览器；判断采集行为、文件落盘、tracking 隔离仍然看真实产物。

覆盖：
- 两个平台的输出、tracking 各写各的目录，互不覆盖
- 事件流每条带正确 task_id，不串台
- LLM 并发不超过 ai.concurrency
- 停一个任务不影响另一个任务
- 不带 task_id 的老调用方式行为不变
"""
import io
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from server.session import Session
from src.runtime import get_runtime
import src.runtime as runtime_module


# ---------------------------------------------------------------- 页面替身

_BOSS_URL = "https://www.zhipin.com/web/geek/jobs?query=python"

_BOSS_CARDS = [
    {"securityId": "sid-1", "jobName": "后端工程师", "salaryDesc": "20-30K",
     "areaDistrict": "西湖区", "brandName": "甲公司"},
    {"securityId": "sid-2", "jobName": "数据工程师", "salaryDesc": "25-35K",
     "areaDistrict": "滨江区", "brandName": "乙公司"},
]

_BOSS_DETAILS = {
    "sid-1": {"encryptJobId": "enc-1", "jobName": "后端工程师", "salaryDesc": "20-30K",
              "locationName": "杭州 西湖区", "experienceName": "3-5年", "degreeName": "本科",
              "postDescription": "负责服务端开发。", "brandName": "甲公司",
              "skills": ["Python"], "welfareList": ["双休"], "jobLabels": []},
    "sid-2": {"encryptJobId": "enc-2", "jobName": "数据工程师", "salaryDesc": "25-35K",
              "locationName": "杭州 滨江区", "experienceName": "5-10年", "degreeName": "硕士",
              "postDescription": "负责数据管道。", "brandName": "乙公司",
              "skills": ["SQL"], "welfareList": ["五险一金"], "jobLabels": []},
}


class BossPageDouble:
    """实现 BrowserManager 的页面门面，按 BossAdapter 发出的脚本应答。

    它不是假平台：``create_adapter("boss")`` 仍然构造真正的 ``BossAdapter``，
    只是 CDP 那一层换成了内存对象。
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.port = 0
        self.ws = None
        self.should_stop = None
        self.url = _BOSS_URL

    def try_connect_existing(self):
        return True

    def launch(self, start_url=None):
        if start_url:
            self.url = start_url
        return True

    def close(self):
        self.ws = None

    def list_pages(self):
        return [{"type": "page", "url": self.url,
                 "webSocketDebuggerUrl": "ws://boss-page-double"}]

    def connect_ws(self, ws_url):
        self.ws = ws_url
        return True

    def evaluate(self, expression, await_promise=False, timeout=30):
        expr = expression or ""
        if expr == "location.href":
            return self.url
        if expr.startswith("location.href="):
            self.url = json.loads(expr.split("=", 1)[1])
            return None
        # 登录探测：页面替身始终认为已登录，避免测试卡在扫码等待
        if "header-username" in expr or "bst=" in expr:
            return json.dumps({"state": "in", "source": "page_double"})
        # read_panel.js 必须排在 extract_list.js 前面：两个脚本都读 __vue__
        if "page-jobs-main" in expr:
            sid = next((s for s in _BOSS_DETAILS if f"'{s}'" in expr), None)
            if not sid:
                return json.dumps({"found": False})
            return json.dumps({"found": True, "sid": sid, **_BOSS_DETAILS[sid]})
        if "card_sel" in expr:
            return json.dumps({"ok": True, "online": True, "source": "double",
                               "evidence": {}})
        if "clickJobCard" in expr:
            return json.dumps({"ok": True, "index": 0, "total": len(_BOSS_CARDS)})
        if ".job-card-box" in expr:
            return json.dumps({"found": True, "index": 0, "total": len(_BOSS_CARDS)})
        if "job-detail" in expr:
            return "scrolled"
        if "search-job-result" in expr:
            return json.dumps({"scrollTop": 0, "scrollHeight": 2000, "clientHeight": 800})
        if "__vue__" in expr:
            return json.dumps(_BOSS_CARDS)          # extract_list.js
        return None

    def get_value(self, result):
        # 与真实 BrowserManager 一致：字符串形式的 JSON 在这里解包
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return result
        return result

    def disconnect(self):
        self.ws = None

    def bring_to_front(self):
        return True

    def native_click(self, x, y):
        pass

    def send_cdp(self, method, params=None, timeout=30, stop_check=None):
        return {}


class FakeBrowserDouble:
    """假平台的浏览器门面：只记录 URL，不做任何 I/O。"""

    def __init__(self, config=None):
        self.config = config or {}
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
        return [{"type": "page", "url": self.url,
                 "webSocketDebuggerUrl": "ws://fake-page-double"}]

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


class BrowserFactory:
    """按配置里的 platform 返回对应门面，并用栅栏保证两个任务真的同时活着。"""

    def __init__(self, overlap_barrier=None):
        self.barrier = overlap_barrier

    def __call__(self, config=None):
        if self.barrier is not None:
            try:
                self.barrier.wait(timeout=10)
            except threading.BrokenBarrierError:
                pass
        platform = (config or {}).get("platform")
        if platform == "fake":
            return FakeBrowserDouble(config)
        return BossPageDouble(config)


# ---------------------------------------------------------------- 测试工具

class _Env:
    """临时输出目录 + 按平台解析的配置。"""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def config(self, browser_type="chrome", platform=None):
        platform = platform or "boss"
        out = os.path.join(self.root, platform)
        return {
            "platform": platform,
            "output_dir": out,
            "tracking_file": os.path.join(out, "tracking.json"),
            "legacy_tracking_file": None,
        }

    def out(self, platform):
        return os.path.join(self.root, platform)

    def cleanup(self):
        self._tmp.cleanup()


def _wait(thread, timeout=15.0):
    """线程为空说明任务已结束并转入终态记录。"""
    if thread is None:
        return True
    thread.join(timeout)
    return not thread.is_alive()


def _start(session, params):
    task_id = session.start(params)
    task = session.tasks.get(task_id) or {}
    return task_id, task.get("thread")


def _json_files(path):
    if not os.path.isdir(path):
        return []
    return [os.path.join(path, n) for n in os.listdir(path)
            if n.startswith("jobs_") and n.endswith(".json")]


class TestConcurrentPlatforms(unittest.TestCase):
    def setUp(self):
        self.env = _Env()
        self.barrier = threading.Barrier(2)
        self.factory = BrowserFactory(self.barrier)
        runtime_module._RUNTIMES.clear()
        self.patches = [
            mock.patch("src.collector.BrowserManager", self.factory),
            mock.patch("src.collector.get_config", side_effect=self.env.config),
            mock.patch("src.runtime.get_config", side_effect=self.env.config),
            # 统计事件也写到临时目录，别污染真实的 output/
            mock.patch("src.storage.events.get_config", side_effect=self.env.config),
            mock.patch("server.session.ai_after_collect"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        runtime_module._RUNTIMES.clear()
        self.env.cleanup()

    # -- 核心用例 -------------------------------------------------------

    def test_two_platforms_run_concurrently_and_keep_outputs_separate(self):
        session = Session()
        events = []
        stop_drain = threading.Event()

        def drain():
            while not stop_drain.is_set():
                events.extend(session.drain_events())
                time.sleep(0.02)
            events.extend(session.drain_events())

        drainer = threading.Thread(target=drain, daemon=True)

        with redirect_stdout(io.StringIO()):
            boss_id, boss_thread = _start(session, {
                "count": 2, "site": "boss", "browser_type": "chrome",
                "keyword_search": True, "query": "python", "speed": "fast",
            })
            fake_id, fake_thread = _start(session, {
                "count": 2, "site": "fake", "browser_type": "chrome",
                "keyword_search": True, "query": "python", "speed": "fast",
            })
            drainer.start()

            # tracking 也并发写：两个平台的 Tracker 不得写同一个文件
            tracking_errors = []

            def write_tracking(platform, key):
                try:
                    get_runtime(platform).tracker.set(key, "applied")
                except Exception as exc:  # noqa: BLE001
                    tracking_errors.append(exc)

            tb = threading.Thread(target=write_tracking, args=("boss", "enc-1"))
            tf = threading.Thread(target=write_tracking, args=("fake", "fake-1"))
            tb.start()
            tf.start()
            tb.join(5)
            tf.join(5)

            self.assertTrue(_wait(boss_thread), "BOSS 任务没有在 15s 内结束")
            self.assertTrue(_wait(fake_thread), "假平台任务没有在 15s 内结束")
            stop_drain.set()
            drainer.join(5)

        self.assertEqual(tracking_errors, [])
        boss_ctrl = session.controller(boss_id)
        fake_ctrl = session.controller(fake_id)
        self.assertEqual(boss_ctrl.state, "done",
                         [e for e in boss_ctrl.drain() if e.get("level") == "error"])
        self.assertEqual(fake_ctrl.state, "done",
                         [e for e in fake_ctrl.drain() if e.get("level") == "error"])

        # ① 输出文件各落各的平台目录
        boss_files = _json_files(self.env.out("boss"))
        fake_files = _json_files(self.env.out("fake"))
        self.assertEqual(len(boss_files), 1, boss_files)
        self.assertEqual(len(fake_files), 1, fake_files)
        with open(boss_files[0], encoding="utf-8") as f:
            boss_jobs = json.load(f)
        with open(fake_files[0], encoding="utf-8") as f:
            fake_jobs = json.load(f)
        # 假平台 fixture 的 encrypt_job_id 也是 enc-1 / enc-2，只能靠 platform 区分
        self.assertEqual([j["encrypt_job_id"] for j in boss_jobs], ["enc-1", "enc-2"])
        self.assertEqual([j["encrypt_job_id"] for j in fake_jobs], ["enc-1", "enc-2"])
        self.assertTrue(all(j["platform"] == "boss" for j in boss_jobs))
        self.assertTrue(all(j["platform"] == "fake" for j in fake_jobs))

        # ② tracking 各写各的文件
        boss_track = get_runtime("boss").tracker
        fake_track = get_runtime("fake").tracker
        self.assertNotEqual(boss_track.path, fake_track.path)
        self.assertTrue(boss_track.path.startswith(self.env.out("boss")))
        self.assertTrue(fake_track.path.startswith(self.env.out("fake")))
        self.assertEqual(set(boss_track.all()), {"enc-1"})
        self.assertEqual(set(fake_track.all()), {"fake-1"})

        # ③ 事件流：每条都有 task_id，且没有串台
        self.assertTrue(events, "事件流是空的")
        ids = {boss_id, fake_id}
        self.assertTrue(all(ev.get("task_id") in ids for ev in events),
                        [ev for ev in events if ev.get("task_id") not in ids][:3])
        self.assertEqual({ev["task_id"] for ev in events}, ids)
        boss_logs = [ev for ev in events if ev["task_id"] == boss_id and ev["type"] == "log"]
        fake_logs = [ev for ev in events if ev["task_id"] == fake_id and ev["type"] == "log"]
        self.assertTrue(any("BOSS 直聘 V14" in ev["msg"] for ev in boss_logs))
        self.assertTrue(any("假平台 V14" in ev["msg"] for ev in fake_logs))
        # 反向断言：平台自报的那一行只能出现在自己的 task_id 下
        for ev in events:
            if ev["type"] != "log":
                continue
            if "BOSS 直聘 V14" in ev["msg"]:
                self.assertEqual(ev["task_id"], boss_id)
            if "假平台 V14" in ev["msg"]:
                self.assertEqual(ev["task_id"], fake_id)
        final_states = {ev["task_id"]: ev["state"] for ev in events
                        if ev["type"] == "status" and ev.get("state") in ("done", "stopped", "error")}
        self.assertEqual(final_states.get(boss_id), "done")
        self.assertEqual(final_states.get(fake_id), "done")

    def test_stopping_one_task_does_not_stop_the_other(self):
        session = Session()
        # 假平台只有 2 条数据，count=3 会让它一直滚动等待，方便在它运行时叫停
        with redirect_stdout(io.StringIO()):
            boss_id, boss_thread = _start(session, {
                "count": 2, "site": "boss", "browser_type": "chrome",
                "keyword_search": True, "query": "python", "speed": "fast",
            })
            fake_id, fake_thread = _start(session, {
                "count": 3, "site": "fake", "browser_type": "chrome",
                "keyword_search": True, "query": "python", "speed": "fast",
            })

            self.assertTrue(_wait(boss_thread), "BOSS 任务没有在 15s 内结束")
            boss_ctrl = session.controller(boss_id)
            fake_ctrl = session.controller(fake_id)
            self.assertEqual(boss_ctrl.state, "done")
            self.assertFalse(boss_ctrl.should_stop())

            session.stop(fake_id)
            self.assertTrue(fake_ctrl.should_stop())
            self.assertFalse(boss_ctrl.should_stop())
            self.assertTrue(_wait(fake_thread), "被停止的假平台任务没有退出")

        self.assertEqual(fake_ctrl.state, "stopped")
        # 假平台已经采到 2 条并落盘，BOSS 的 2 条也没受影响
        self.assertEqual(len(_json_files(self.env.out("boss"))), 1)
        self.assertEqual(len(_json_files(self.env.out("fake"))), 1)

    def test_legacy_stop_without_task_id_keeps_working(self):
        session = Session()
        # 只有一个任务，不需要并发栅栏（否则会白等超时）
        self.factory.barrier = None
        with redirect_stdout(io.StringIO()):
            _task_id, thread = _start(session, {
                "count": 3, "site": "fake", "browser_type": "chrome",
                "keyword_search": True, "query": "python", "speed": "fast",
            })
            time.sleep(0.2)
            ctrl = session.controller()
            session.stop()          # 前端老调用：不带 task_id
            self.assertTrue(_wait(thread), "不带 task_id 的停止没有生效")
        self.assertTrue(ctrl.should_stop())
        self.assertEqual(ctrl.state, "stopped")


class TestLLMConcurrencyCap(unittest.TestCase):
    """LLM 并发上限是模块级信号量，跨任务共享。"""

    def test_peak_concurrency_never_exceeds_capacity(self):
        from src.ai import client as ai_client

        cap = 2
        ai_client._SEM = None
        try:
            state = {"active": 0, "peak": 0, "calls": 0}
            lock = threading.Lock()

            class Resp:
                status_code = 200

                @staticmethod
                def json():
                    return {"choices": [{"message": {"content": '{"ok": true}'}}]}

            def fake_post(*_args, **_kwargs):
                with lock:
                    state["active"] += 1
                    state["calls"] += 1
                    state["peak"] = max(state["peak"], state["active"])
                time.sleep(0.05)
                with lock:
                    state["active"] -= 1
                return Resp()

            # 信号量在第一次调用时按 ai.concurrency 创建，所以整个调用期都要在 patch 里
            with mock.patch("src.config.load_ai_config",
                            return_value={"concurrency": cap}), \
                    mock.patch("src.ai.client.requests.post", side_effect=fake_post):
                llm = ai_client.LLMClient("http://llm.invalid", api_key="k", model="m",
                                          max_retries=0)
                threads = [threading.Thread(target=llm.chat_json,
                                            args=([{"role": "user", "content": "hi"}],))
                           for _ in range(6)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(10)
        finally:
            ai_client._SEM = None

        self.assertEqual(state["calls"], 6)
        self.assertLessEqual(state["peak"], cap)
        self.assertGreater(state["peak"], 1, "调用被完全串行了，测不到并发上限")


if __name__ == "__main__":
    unittest.main()
