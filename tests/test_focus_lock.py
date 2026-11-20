"""前台锁行为：真实前台段串行，纯 CDP 调用不被挡住。

不碰浏览器、零网络。假页面只记录事件序列，用 Event 控制交错点，
不靠 sleep 抢时序。
"""
import json
import threading
import time
import unittest

from src.utils import chat_input


class FakePage:
    """只记录前台相关动作的假页面。locate / 读长度是只读 JS，不进序列。"""

    def __init__(self, name, events, on_front=None):
        self.name = name
        self.events = events
        self.on_front = on_front
        self._mu = threading.Lock()

    def _record(self, action):
        with self._mu:
            self.events.append(f"{self.name}:{action}")

    def evaluate(self, expression, await_promise=False, timeout=30):
        if "activeElement" in expression:
            self._record("blur")
        return expression

    def get_value(self, result):
        if result == chat_input.LOCATE_JS:
            return json.dumps({"ok": True, "tag": "TEXTAREA", "x": 10, "y": 20})
        if result == chat_input.LENGTH_JS:
            return 30
        return "blurred"

    def bring_to_front(self):
        self._record("front")
        if self.on_front:
            self.on_front()

    def native_click(self, x, y):
        self._record("click")

    def send_cdp(self, method, params=None, timeout=30, stop_check=None):
        if method == "Input.dispatchKeyEvent":
            self._record("key")
        elif method == "Input.insertText":
            self._record("insert")
        return {}


def _critical_block(name):
    """一次 fill_chat_input 在锁内应留下的完整事件序列。"""
    return [f"{name}:front", f"{name}:click",
            f"{name}:key", f"{name}:key", f"{name}:key", f"{name}:key",
            f"{name}:insert", f"{name}:blur"]


class TestFocusLock(unittest.TestCase):
    def test_fill_critical_sections_do_not_interleave(self):
        """A 在临界段暂停时，B 必须卡在锁上；最终两段各自完整、不交错。"""
        events = []
        a_inside = threading.Event()
        release_a = threading.Event()
        results = {}

        def pause_a():
            a_inside.set()
            # 主线程确认 B 已卡在锁上后再放行；2s 只是防挂死兜底
            release_a.wait(2.0)

        page_a = FakePage("A", events, on_front=pause_a)
        page_b = FakePage("B", events)

        def fill(page):
            results[page.name] = chat_input.fill_chat_input(page, "x" * 30)

        ta = threading.Thread(target=fill, args=(page_a,), daemon=True)
        tb = threading.Thread(target=fill, args=(page_b,), daemon=True)
        ta.start()
        self.assertTrue(a_inside.wait(2.0), "A 没能进入临界段")

        tb.start()
        # A 仍持锁：B 若没被挡住，会在这段时间里跑完自己的整段
        tb.join(0.3)
        self.assertTrue(tb.is_alive(), "B 在 A 持锁期间就完成了，说明前台锁没生效")

        release_a.set()
        ta.join(2.0)
        tb.join(2.0)
        self.assertFalse(ta.is_alive(), "A 没有正常结束")
        self.assertFalse(tb.is_alive(), "B 没有正常结束")

        self.assertTrue(results["A"]["ok"])
        self.assertTrue(results["B"]["ok"])
        # 两段必须首尾相接，中间不允许插入对方的事件
        self.assertEqual(events, _critical_block("A") + _critical_block("B"))

    def test_plain_evaluate_does_not_wait_for_foreground_lock(self):
        """只做 CDP evaluate 的线程不该被持锁方挡住。"""
        events = []
        inside = threading.Event()
        release = threading.Event()

        def pause():
            inside.set()
            release.wait(2.0)

        filler = FakePage("A", events, on_front=pause)
        t = threading.Thread(
            target=chat_input.fill_chat_input, args=(filler, "x" * 30), daemon=True)
        t.start()
        self.assertTrue(inside.wait(2.0), "A 没能进入临界段")

        probe = FakePage("P", events)
        started = time.monotonic()
        value = probe.evaluate("1 + 1")
        elapsed = time.monotonic() - started

        release.set()
        t.join(2.0)
        self.assertFalse(t.is_alive())

        self.assertEqual(value, "1 + 1")
        self.assertLess(elapsed, 0.5, "纯 CDP evaluate 被前台锁挡住了")


if __name__ == "__main__":
    unittest.main()
