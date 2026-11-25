"""写入点接线：五个写入点各写一条事件，且写失败不影响主流程。

重点验证 ADR-0003：BOSS 的填草稿必须记成 drafted，不能记成 submitted。
"""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from src.ai import apply as apply_mod
from src.ai import client as client_mod
from src.ai import pipeline as pipeline_mod


class _EventSink:
    """收集 record() 调用，不真的写文件。"""

    def __init__(self):
        self.calls = []

    def record(self, event, platform, ts=None, **fields):
        self.calls.append({"event": event, "platform": platform, "ts": ts, **fields})

    def of(self, event):
        return [c for c in self.calls if c["event"] == event]


class TestApplyEvents(unittest.TestCase):
    """src/ai/apply.py 的 run_apply 写 apply / send_message 事件。"""

    def setUp(self):
        self.sink = _EventSink()
        p = mock.patch("src.ai.apply.events", self.sink)
        p.start()
        self.addCleanup(p.stop)

    def _adapter(self, mode="apply_then_chat", submitted=True, sent=True):
        class _A:
            site = "zhaopin"
            delivery_mode = mode

            def apply(self, job_id):
                return {"ok": submitted, "submitted": submitted, "reason": "" if submitted else "boom"}

            def send_message(self, text):
                return {"ok": sent, "sent": sent, "length": len(text), "reason": ""}
        return _A()

    class _Tracker:
        def __init__(self, data=None):
            self.data = data or {}

        def all(self):
            return self.data

        def get(self, key):
            return self.data.get(key, {})

        def set(self, key, status, note=""):
            return {"status": status, "note": note}

    def test_submitted_apply_writes_apply_event(self):
        adapter = self._adapter()
        apply_mod.run_apply(adapter, {"job_id": "J1", "company": "甲公司", "title": "后端"},
                             "你好", tracker=self._Tracker(),
                             config={"enabled": True, "send_message": True, "daily_limit": 0})
        rows = self.sink.of("apply")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "submitted")
        self.assertEqual(rows[0]["platform"], "zhaopin")
        self.assertEqual(rows[0]["job_id"], "J1")
        self.assertGreaterEqual(rows[0]["duration_ms"], 0)

    def test_failed_apply_is_not_recorded_as_submitted(self):
        adapter = self._adapter(submitted=False)
        apply_mod.run_apply(adapter, {"job_id": "J1"}, "你好",
                             tracker=self._Tracker(),
                             config={"enabled": True, "send_message": True, "daily_limit": 0})
        rows = self.sink.of("apply")
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["status"], "submitted")
        self.assertEqual(rows[0]["status"], "skipped")

    def test_daily_limit_skip_is_recorded(self):
        class _T(self._Tracker):
            def all(self):
                return {"x": {"status": "applied", "updated_at": "2999-01-01T00:00:00"}}
        adapter = self._adapter()
        with mock.patch("src.ai.apply.datetime") as fake_dt:
            fake_dt.now.return_value.strftime.return_value = "2999-01-01"
            apply_mod.run_apply(adapter, {"job_id": "J1"}, "你好", tracker=_T(),
                                 config={"enabled": True, "send_message": True, "daily_limit": 1})
        rows = self.sink.of("apply")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "skipped")

    def test_send_message_event_written_after_send(self):
        adapter = self._adapter()
        apply_mod.run_apply(adapter, {"job_id": "J1"}, "你好", tracker=self._Tracker(),
                             config={"enabled": True, "send_message": True, "daily_limit": 0})
        rows = self.sink.of("send_message")
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["sent"], True)
        self.assertEqual(rows[0]["length"], 2)

    def test_event_write_failure_never_breaks_apply(self):
        """统计是旁路：写事件炸了，投递照样完成。"""

        def boom(*a, **kw):
            raise OSError("磁盘满了")

        with mock.patch("src.ai.apply.events.record", side_effect=boom):
            adapter = self._adapter()
            result = apply_mod.run_apply(
                adapter, {"job_id": "J1"}, "你好", tracker=self._Tracker(),
                config={"enabled": True, "send_message": True, "daily_limit": 0})
        self.assertIs(result["submitted"], True)
        self.assertIs(result["sent"], True)


class TestAiCallEvents(unittest.TestCase):
    """src/ai/client.py 的 _post 写 ai_call 事件。"""

    def setUp(self):
        self.sink = _EventSink()
        p = mock.patch("src.storage.events.record", self.sink.record)
        p.start()
        self.addCleanup(p.stop)

    def _client(self, kind="screen", platform="boss"):
        c = client_mod.LLMClient("http://llm.invalid", api_key="k", model="m",
                                  platform=platform, kind=kind)
        return c

    def _resp(self, payload, status=200):
        r = mock.Mock()
        r.status_code = status
        r.json.return_value = payload
        r.text = ""
        return r

    def test_successful_call_writes_ai_call_with_tokens(self):
        c = self._client()
        payload = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 34},
        }
        with mock.patch("src.ai.client.requests.post", return_value=self._resp(payload)):
            c._post({"model": "m"})
        rows = self.sink.of("ai_call")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "screen")
        self.assertEqual(rows[0]["model"], "m")
        self.assertEqual(rows[0]["tokens_in"], 120)
        self.assertEqual(rows[0]["tokens_out"], 34)
        self.assertIs(rows[0]["ok"], True)
        self.assertGreaterEqual(rows[0]["duration_ms"], 0)

    def test_missing_usage_leaves_tokens_empty(self):
        """取不到 token 就留空，不编。"""
        c = self._client()
        payload = {"choices": [{"message": {"content": "ok"}}]}
        with mock.patch("src.ai.client.requests.post", return_value=self._resp(payload)):
            c._post({"model": "m"})
        rows = self.sink.of("ai_call")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].get("tokens_in"))
        self.assertIsNone(rows[0].get("tokens_out"))

    def test_failed_call_still_writes_event_with_ok_false(self):
        c = self._client()
        with mock.patch("src.ai.client.requests.post",
                        side_effect=client_mod.requests.RequestException("断网")):
            with self.assertRaises(client_mod.LLMError):
                c._post({"model": "m"})
        rows = self.sink.of("ai_call")
        self.assertGreaterEqual(len(rows), 1)
        self.assertIs(rows[0]["ok"], False)

    def test_event_write_failure_never_breaks_call(self):
        c = self._client()
        payload = {"choices": [{"message": {"content": "ok"}}]}
        with mock.patch("src.ai.client.requests.post", return_value=self._resp(payload)), \
                mock.patch("src.storage.events.record", side_effect=OSError("满了")):
            out = c._post({"model": "m"})
        self.assertEqual(out, "ok")


class TestCollectEvent(unittest.TestCase):
    """src/collector.py 收尾写 collect 事件。"""

    def test_collect_event_written_at_end(self):
        sink = _EventSink()
        with mock.patch("src.collector.events", sink):
            from src.collector import run_collection
            # 不连浏览器，直接让启动失败——收尾仍会写事件
            with mock.patch("src.collector.get_config") as cfg, \
                    mock.patch("src.collector.create_adapter") as mk, \
                    mock.patch("src.collector.BrowserManager") as bm:
                cfg.return_value = {"output_dir": tempfile.gettempdir()}
                mk.return_value.display_name = "假平台"
                mk.return_value.home_url.return_value = "https://fake.example"
                bm.return_value.try_connect_existing.return_value = False
                bm.return_value.launch.return_value = False
                run_collection(count=1, site="fake")
        rows = sink.of("collect")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["platform"], "fake")
        self.assertIn("count", rows[0])
        self.assertIn("skipped", rows[0])
        self.assertIn("excluded", rows[0])
        self.assertIn("file", rows[0])


class TestScreenEvent(unittest.TestCase):
    """src/ai/pipeline.py 的 build_plan 写 screen 事件。"""

    def test_screen_event_written_after_plan(self):
        sink = _EventSink()
        with tempfile.TemporaryDirectory() as root:
            jobs = os.path.join(root, "jobs_2026-01-01_x.json")
            with open(jobs, "w", encoding="utf-8") as f:
                json.dump([], f)

            def fake_platform_of(path):
                return "boss"

            with mock.patch("src.ai.pipeline.events", sink), \
                    mock.patch("src.ai.pipeline.platform_of_output_file",
                               side_effect=fake_platform_of), \
                    mock.patch("src.ai.pipeline.load_ai_config",
                               return_value={"base_url": "http://x", "api_key": "k",
                                             "model": "m", "min_score": 60,
                                             "concurrency": 1, "resumes": [],
                                             "default_resume": ""}), \
                    mock.patch("src.ai.pipeline.ResumeLibrary.from_config") as rl:
                rl.return_value.digest.return_value = "h"
                rl.return_value.pick.return_value = ("默认", "简历")
                rl.return_value.labels.return_value = ["默认"]
                plan = pipeline_mod.build_plan(jobs)

        rows = sink.of("screen")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["platform"], "boss")
        self.assertEqual(rows[0]["count"], len(plan["items"]))
        self.assertIn("planned", rows[0])
        self.assertIn("skipped", rows[0])
        self.assertIn("excluded", rows[0])
        self.assertTrue(rows[0]["file"].startswith("ai_plan_"))


class TestDraftedIsNotSubmitted(unittest.TestCase):
    """ADR-0003 硬要求：BOSS 填草稿只能记 drafted。"""

    def test_dispatch_records_drafted_not_submitted(self):
        """真跑 dispatch 的填充分支，检查事件里的 status。"""
        from src.ai import dispatch as dispatch_mod

        sink = _EventSink()
        item = {
            "encrypt_job_id": "E1", "security_id": "S1", "title": "后端",
            "company": "甲公司", "greeting": "做 Python 后端，想聊聊你们的检索方案。",
            "status": "planned",
        }

        class _Adapter:
            def pick_target(self, targets):
                return None

            def open_chat(self, eid):
                return {"ok": True, "reason": ""}

            def chat_input_ready(self):
                return True

            def open_conversation(self, hints=None, timeout=12.0):
                return {"ok": True, "input_ready": True, "text": "会话"}

            def fill_greeting(self, text, attempts=4):
                return {"ok": True, "reason": "", "length": len(text)}

            def chat_url(self):
                return "https://www.zhipin.com/web/geek/chat"

        class _Tracker:
            def all(self):
                return {}

            def get(self, key):
                return {}

            def set(self, key, status, note=""):
                return {"status": status, "note": note}

        class _BM:
            port = 0
            ws = None

            def list_pages(self):
                return []

            def evaluate(self, expr, *a, **kw):
                return ""

            def get_value(self, r):
                return ""

            def connect_ws(self, url):
                return True

            def disconnect(self):
                pass

            def bring_to_front(self):
                pass

        # dispatch 用 `import time`，模块属性就是全局 time 模块本身，
        # 直接 patch time.sleep 会连带 tracelink 的 SSE 后台线程热循环重连，
        # 测试凭空慢十几秒。这里换成一个假模块：sleep 不等，perf_counter 用真的
        # （事件要算 duration_ms）。
        import types
        fake_time = types.SimpleNamespace(sleep=lambda s: None,
                                          time=time.time,
                                          perf_counter=time.perf_counter)

        with mock.patch("src.ai.dispatch.events", sink), \
                mock.patch("src.ai.dispatch.open_browser", return_value=_BM()), \
                mock.patch("src.ai.dispatch.BossAdapter", return_value=_Adapter()), \
                mock.patch("src.ai.dispatch._ensure_page", return_value=True), \
                mock.patch("src.ai.dispatch.wait_chat_page", return_value=True), \
                mock.patch("src.ai.dispatch.read_activity",
                           return_value={"ok": False, "reason": "x"}), \
                mock.patch("src.ai.dispatch._blur_input"), \
                mock.patch("src.ai.dispatch.random.uniform", return_value=0.0), \
                mock.patch("src.ai.dispatch.time", fake_time):
            dispatch_mod.dispatch([item], tracker=_Tracker(), platform="boss")

        rows = sink.of("apply")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "drafted")
        self.assertNotEqual(rows[0]["status"], "submitted")
        self.assertEqual(rows[0]["platform"], "boss")
        self.assertEqual(rows[0]["job_id"], "E1")
        # 不该有 send_message 事件——BOSS 只填不发
        self.assertEqual(sink.of("send_message"), [])

    def test_dispatch_source_never_records_submitted(self):
        import inspect
        from src.ai import dispatch as dispatch_mod
        src = inspect.getsource(dispatch_mod.dispatch)
        self.assertIn('status="drafted"', src)
        self.assertNotIn('status="submitted"', src)


if __name__ == "__main__":
    unittest.main()
