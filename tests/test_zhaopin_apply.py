"""投递契约测试：能力分支、三道闸、幂等、失败不吞错。全部零网络。"""
import json
import unittest
from contextlib import contextmanager
from unittest import mock

from src.adapters.boss import BossAdapter
from src.adapters.fake import FakePlatformAdapter
from src.adapters.zhaopin import ZhaopinAdapter
from src.ai.apply import DELIVERY_MODES, delivery_mode_of, readiness, run_apply

GATES_ON = {"enabled": True, "send_message": True, "daily_limit": 0}
GATES_OFF = {"enabled": False, "send_message": False, "daily_limit": 0}
JOB_ID = "CCL1405333700J40911854305"


class ApplyPage:
    """只实现页面门面的测试替身；按注入脚本里的 marker 返回固定状态。"""

    def __init__(self, state):
        self.state = state
        self.clicks = []
        self.expressions = []

    def evaluate(self, expression, await_promise=False, timeout=30):
        self.expressions.append(expression)
        if "zhaopin:apply-state" in expression:
            return json.dumps(self.state.get("apply_state") or {})
        if "zhaopin:select" in expression:
            return json.dumps(self.state.get("select") or {"ok": True, "x": 1, "y": 2})
        if "zhaopin:apply-modal" in expression:
            return json.dumps(self.state.get("modal") or {"confirmed": False})
        if "zhaopin:chat-read" in expression:
            return json.dumps(self.state.get("chat") or {})
        if "location.href" in expression:
            return self.state.get("url", "")
        return json.dumps(None)

    def get_value(self, result):
        return json.loads(result) if isinstance(result, str) else result

    def bring_to_front(self):
        pass

    def native_click(self, x, y):
        self.clicks.append((x, y))

    def send_cdp(self, method, params=None, timeout=30, stop_check=None):
        return {}


def apply_state(**over):
    base = {
        "ok": True, "found": True, "index": 0,
        "company": "甲公司", "title": "后端工程师",
        "logged_in": True, "selected": True,
        "already_apply": False, "has_applied_position": False, "apply_type": "1",
        "button": {"found": True, "text": "立即投递", "disabled": False, "x": 10, "y": 20},
    }
    base.update(over)
    return base


@contextmanager
def fast_clock():
    """把适配器里的轮询时间压成 0，避免测试真的等 5~6 秒。"""
    tick = {"t": 0.0}

    def now():
        tick["t"] += 1.0
        return tick["t"]

    def sleep(seconds):
        tick["t"] += max(float(seconds or 0), 0.1)

    with mock.patch("src.adapters.zhaopin.time.time", side_effect=now), \
            mock.patch("src.adapters.zhaopin.time.sleep", side_effect=sleep):
        yield


class TestDeliveryModes(unittest.TestCase):
    def test_declared_modes(self):
        self.assertEqual(BossAdapter().delivery_mode, "prefill_chat")
        self.assertEqual(FakePlatformAdapter().delivery_mode, "prefill_chat")
        self.assertEqual(ZhaopinAdapter().delivery_mode, "apply_then_chat")

    def test_unknown_mode_is_unsupported(self):
        self.assertEqual(delivery_mode_of(object()), "unsupported")

        class Weird:
            delivery_mode = "auto_magic"
        self.assertEqual(delivery_mode_of(Weird()), "unsupported")

    def test_mode_set_is_closed(self):
        self.assertEqual(DELIVERY_MODES, {"prefill_chat", "apply_then_chat", "unsupported"})

    def test_boss_apply_side_stays_unsupported(self):
        adapter = BossAdapter()
        applied = adapter.apply("x")
        sent = adapter.send_message("你好")
        self.assertIs(applied["ok"], False)
        self.assertIs(applied["submitted"], False)
        self.assertTrue(applied["reason"].startswith("unsupported:"))
        self.assertIs(sent["ok"], False)
        self.assertIs(sent["sent"], False)
        self.assertTrue(sent["reason"].startswith("unsupported:"))


class TestZhaopinApply(unittest.TestCase):
    def setUp(self):
        self.audit = []
        patcher = mock.patch("src.adapters.zhaopin.write_audit",
                             side_effect=lambda *a, **kw: self.audit.append((a, kw)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.page = ApplyPage({})
        self.adapter = ZhaopinAdapter(self.page)

    def _gates(self, gates):
        p = mock.patch("src.adapters.zhaopin.load_apply_config", return_value=gates)
        p.start()
        self.addCleanup(p.stop)

    def test_gates_closed_never_touches_page(self):
        self._gates(GATES_OFF)
        self.page.state["apply_state"] = apply_state()
        result = self.adapter.apply(JOB_ID)
        self.assertIs(result["ok"], False)
        self.assertIs(result["submitted"], False)
        self.assertEqual(result["reason"], "unsupported: apply_disabled")
        self.assertEqual(self.page.clicks, [])
        self.assertEqual(self.page.expressions, [])
        self.assertEqual(self.audit[-1][1]["reason"], "unsupported: apply_disabled")

    def test_already_applied_is_skipped_without_click(self):
        self._gates(GATES_ON)
        self.page.state["apply_state"] = apply_state(has_applied_position=True)
        result = self.adapter.apply(JOB_ID)
        self.assertIs(result["submitted"], False)
        self.assertEqual(result["reason"], "skipped: already_applied")
        self.assertEqual(self.page.clicks, [])

    def test_unknown_apply_type_counts_as_applied(self):
        self._gates(GATES_ON)
        self.page.state["apply_state"] = apply_state(apply_type="9")
        result = self.adapter.apply(JOB_ID)
        self.assertEqual(result["reason"], "skipped: already_applied")
        self.assertEqual(self.page.clicks, [])

    def test_guest_session_is_refused_before_click(self):
        self._gates(GATES_ON)
        self.page.state["apply_state"] = apply_state(logged_in=False)
        result = self.adapter.apply(JOB_ID)
        self.assertEqual(result["reason"], "unsupported: login_required")
        self.assertIs(result["submitted"], False)
        self.assertEqual(self.page.clicks, [])

    def test_missing_button_is_refused(self):
        self._gates(GATES_ON)
        self.page.state["apply_state"] = apply_state(button={"found": False})
        result = self.adapter.apply(JOB_ID)
        self.assertEqual(result["reason"], "apply_button_not_found")
        self.assertEqual(self.page.clicks, [])

    def test_wrong_selection_is_refused(self):
        self._gates(GATES_ON)
        # 选中失败：点完卡片后 apply_state 仍然说没选中
        self.page.state["apply_state"] = apply_state(selected=False)
        with fast_clock():
            result = self.adapter.apply(JOB_ID)
        self.assertEqual(result["reason"], "select_unverified")
        self.assertIs(result["submitted"], False)
        # 只点了卡片，没有点投递按钮
        self.assertEqual(len(self.page.clicks), 1)

    def test_happy_path_confirms_submission(self):
        self._gates(GATES_ON)
        self.page.state["apply_state"] = apply_state()
        self.page.state["modal"] = {
            "confirmed": True, "login": False, "text": "已向对方发送简历和打招呼语",
            "continue": {"found": True, "x": 30, "y": 40},
        }
        self.page.state["chat"] = {"ok": True, "input_ready": True, "input_len": 0}
        result = self.adapter.apply(JOB_ID)
        self.assertIs(result["submitted"], True)
        self.assertIs(result["ok"], True)
        # 投递按钮 + 「继续沟通」各点一次
        self.assertEqual(len(self.page.clicks), 2)
        self.assertEqual(self.audit[-1][1]["submitted"], True)

    def test_unconfirmed_click_is_not_reported_as_submitted(self):
        self._gates(GATES_ON)
        self.page.state["apply_state"] = apply_state()
        with mock.patch.object(ZhaopinAdapter, "_wait_apply_modal",
                               return_value={"confirmed": False, "reason": "modal_timeout"}):
            result = self.adapter.apply(JOB_ID)
        self.assertIs(result["submitted"], False)
        self.assertEqual(result["reason"], "apply_unconfirmed")
        self.assertEqual(len(self.page.clicks), 1)


class TestZhaopinSendMessage(unittest.TestCase):
    def setUp(self):
        self.audit = []
        patcher = mock.patch("src.adapters.zhaopin.write_audit",
                             side_effect=lambda *a, **kw: self.audit.append((a, kw)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.page = ApplyPage({})
        self.adapter = ZhaopinAdapter(self.page)

    def _gates(self, gates):
        p = mock.patch("src.adapters.zhaopin.load_apply_config", return_value=gates)
        p.start()
        self.addCleanup(p.stop)

    def test_gates_closed_is_unsupported(self):
        self._gates(GATES_OFF)
        result = self.adapter.send_message("你好")
        self.assertIs(result["sent"], False)
        self.assertEqual(result["reason"], "unsupported: apply_disabled")

    def test_input_not_ready_fails_loudly(self):
        self._gates(GATES_ON)
        self.page.state["chat"] = {"ok": True, "input_ready": False}
        result = self.adapter.send_message("你好")
        self.assertIs(result["sent"], False)
        self.assertEqual(result["reason"], "chat_input_not_ready")

    def test_fill_failure_keeps_reason(self):
        self._gates(GATES_ON)
        self.page.state["chat"] = {"ok": True, "input_ready": True, "input_len": 0,
                                   "send": {"found": True, "x": 5, "y": 6}}
        with mock.patch("src.adapters.zhaopin.chat_input.fill_chat_input",
                        return_value={"ok": False, "reason": "输入失败: boom"}):
            result = self.adapter.send_message("你好")
        self.assertIs(result["sent"], False)
        self.assertIn("boom", result["reason"])
        self.assertIn("boom", result["evidence"]["fill"]["reason"])

    def test_missing_send_button_is_not_sent(self):
        self._gates(GATES_ON)
        self.page.state["chat"] = {"ok": True, "input_ready": True, "input_len": 0,
                                   "send": {"found": False}}
        with mock.patch("src.adapters.zhaopin.chat_input.fill_chat_input",
                        return_value={"ok": True, "length": 2}):
            result = self.adapter.send_message("你好")
        self.assertIs(result["sent"], False)
        self.assertEqual(result["reason"], "send_button_not_found")

    def test_unverified_message_is_not_sent(self):
        self._gates(GATES_ON)
        self.page.state["chat"] = {"ok": True, "input_ready": True, "input_len": 0,
                                   "messages": [], "send": {"found": True, "x": 5, "y": 6}}
        with mock.patch("src.adapters.zhaopin.chat_input.fill_chat_input",
                        return_value={"ok": True, "length": 2}), fast_clock():
            result = self.adapter.send_message("你好")
        self.assertIs(result["sent"], False)
        self.assertEqual(result["reason"], "sent_unverified")
        self.assertIs(result["evidence"]["after"]["verified"], False)

    def test_verified_message_is_sent(self):
        self._gates(GATES_ON)
        self.page.state["chat"] = {"ok": True, "input_ready": True, "input_len": 0,
                                   "messages": ["你好，我看了岗位很有兴趣"],
                                   "send": {"found": True, "x": 5, "y": 6}}
        with mock.patch("src.adapters.zhaopin.chat_input.fill_chat_input",
                        return_value={"ok": True, "length": 2}):
            result = self.adapter.send_message("你好")
        self.assertIs(result["sent"], True)
        self.assertEqual(len(self.page.clicks), 1)
        self.assertEqual(result["length"], 2)
        self.assertEqual(self.audit[-1][1]["sent"], True)


class StubAdapter:
    def __init__(self, mode="apply_then_chat", submitted=True, sent=True):
        self.delivery_mode = mode
        self.submitted = submitted
        self.sent = sent
        self.apply_calls = []
        self.send_calls = []

    def apply(self, job_id):
        self.apply_calls.append(job_id)
        return {"ok": self.submitted, "reason": "" if self.submitted else "apply_unconfirmed",
                "submitted": self.submitted, "evidence": {}}

    def send_message(self, text):
        self.send_calls.append(text)
        return {"ok": self.sent, "reason": "" if self.sent else "sent_unverified",
                "sent": self.sent, "length": len(text), "evidence": {}}

    def apply_state(self, job_id):
        return apply_state()


class FakeTracker:
    def __init__(self, data=None):
        self.data = data or {}
        self.set_calls = []

    def all(self):
        return self.data

    def set(self, key, status, note=""):
        self.set_calls.append((key, status, note))
        return {"status": status, "note": note}


class TestApplyEngine(unittest.TestCase):
    def _gates(self, gates, target="src.ai.apply.load_apply_config"):
        p = mock.patch(target, return_value=gates)
        p.start()
        self.addCleanup(p.stop)

    def test_prefill_and_unsupported_modes_never_apply(self):
        for mode in ("prefill_chat", "unsupported"):
            adapter = StubAdapter(mode=mode)
            result = run_apply(adapter, {"job_id": JOB_ID}, "你好",
                               tracker=FakeTracker(), config=GATES_ON)
            self.assertIs(result["submitted"], False)
            self.assertEqual(result["reason"], f"unsupported: delivery_mode_{mode}")
            self.assertEqual(adapter.apply_calls, [])

    def test_config_gate_blocks_apply(self):
        adapter = StubAdapter()
        result = run_apply(adapter, {"job_id": JOB_ID}, "你好",
                           tracker=FakeTracker(), config=GATES_OFF)
        self.assertEqual(result["reason"], "unsupported: apply_disabled")
        self.assertEqual(adapter.apply_calls, [])

    def test_no_tracker_blocks_apply(self):
        adapter = StubAdapter()
        result = run_apply(adapter, {"job_id": JOB_ID}, "你好", tracker=None,
                           config=GATES_ON)
        self.assertEqual(result["reason"], "unsupported: no_tracker")
        self.assertEqual(adapter.apply_calls, [])

    def test_daily_limit_blocks_apply(self):
        adapter = StubAdapter()
        tracker = FakeTracker({
            "a": {"status": "applied", "updated_at": "2999-01-01T10:00:00"},
        })
        cfg = dict(GATES_ON, daily_limit=1)
        with mock.patch("src.ai.apply.datetime") as fake_dt:
            fake_dt.now.return_value.strftime.return_value = "2999-01-01"
            result = run_apply(adapter, {"job_id": JOB_ID}, "你好", tracker=tracker, config=cfg)
        self.assertEqual(result["reason"], "skipped: daily_limit")
        self.assertEqual(adapter.apply_calls, [])

    def test_submit_writes_applied_status_and_sends(self):
        adapter = StubAdapter()
        tracker = FakeTracker()
        result = run_apply(adapter, {"job_id": JOB_ID, "company": "甲公司", "title": "后端"},
                           "你好", tracker=tracker, config=GATES_ON)
        self.assertIs(result["submitted"], True)
        self.assertIs(result["sent"], True)
        self.assertEqual(tracker.set_calls[0][0], JOB_ID)
        self.assertEqual(tracker.set_calls[0][1], "applied")
        self.assertEqual(adapter.send_calls, ["你好"])

    def test_unsubmitted_never_writes_tracking(self):
        adapter = StubAdapter(submitted=False)
        tracker = FakeTracker()
        result = run_apply(adapter, {"job_id": JOB_ID}, "你好",
                           tracker=tracker, config=GATES_ON)
        self.assertIs(result["submitted"], False)
        self.assertEqual(tracker.set_calls, [])
        self.assertEqual(adapter.send_calls, [])


class TestReadiness(unittest.TestCase):
    def test_reports_every_missing_gate(self):
        adapter = StubAdapter(mode="apply_then_chat")
        adapter.apply_state = lambda job_id: apply_state(logged_in=False)
        with mock.patch("src.ai.apply.load_apply_config", return_value=GATES_OFF):
            result = readiness(adapter, JOB_ID)
        self.assertIs(result["ok"], False)
        self.assertIn("apply.enabled=false", result["missing"])
        self.assertIn("apply.send_message=false", result["missing"])
        self.assertIn("未登录", result["missing"])

    def test_ready_when_all_conditions_hold(self):
        adapter = StubAdapter(mode="apply_then_chat")
        with mock.patch("src.ai.apply.load_apply_config", return_value=GATES_ON):
            result = readiness(adapter, JOB_ID)
        self.assertIs(result["ok"], True)
        self.assertEqual(result["missing"], [])

    def test_non_apply_mode_is_not_ready(self):
        result = readiness(StubAdapter(mode="prefill_chat"), JOB_ID)
        self.assertIs(result["ok"], False)
        self.assertEqual(result["missing"], ["delivery_mode=prefill_chat"])


if __name__ == "__main__":
    unittest.main()
