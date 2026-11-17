"""速度档位的单元测试。

运行：
    .venv/Scripts/python -m unittest discover -s tests -v
"""
import unittest

from src.utils.browser_behavior import (
    DEFAULT_SPEED,
    SPEED_PROFILES,
    BrowserBehavior,
    resolve_speed,
)


class TestResolveSpeed(unittest.TestCase):
    def test_explicit_speed_wins(self):
        self.assertEqual(resolve_speed("normal", safe_mode=True, fast=False), "normal")
        self.assertEqual(resolve_speed("fast", safe_mode=True, fast=False), "fast")

    def test_legacy_fast_flag(self):
        self.assertEqual(resolve_speed(None, safe_mode=True, fast=True), "fast")

    def test_legacy_safe_mode_off(self):
        self.assertEqual(resolve_speed(None, safe_mode=False, fast=False), "fast")

    def test_default_is_slow(self):
        self.assertEqual(resolve_speed(None, safe_mode=True, fast=False), DEFAULT_SPEED)
        self.assertEqual(DEFAULT_SPEED, "slow")

    def test_unknown_speed_falls_back(self):
        self.assertEqual(resolve_speed("turbo", safe_mode=True, fast=False), "slow")
        self.assertEqual(resolve_speed("turbo", safe_mode=False, fast=False), "fast")


class TestBrowserBehavior(unittest.TestCase):
    def test_delay_within_profile_bounds(self):
        for speed, profile in SPEED_PROFILES.items():
            lo = min(b[1] for b in profile["bands"])
            hi = max(b[2] for b in profile["bands"])
            behavior = BrowserBehavior(speed)
            for _ in range(200):
                delay = behavior.get_browse_delay()
                self.assertGreaterEqual(delay, lo)
                self.assertLessEqual(delay, hi)

    def test_fast_mode_is_actually_faster(self):
        fast = BrowserBehavior("fast")
        self.assertLessEqual(max(fast.get_browse_delay() for _ in range(200)), 0.8)
        self.assertFalse(fast.should_scroll_detail())

    def test_slow_mode_scrolls_detail(self):
        self.assertTrue(BrowserBehavior("slow").should_scroll_detail())
        self.assertTrue(BrowserBehavior("normal").should_scroll_detail())

    def test_step_break_disabled_in_fast_mode(self):
        behavior = BrowserBehavior("fast")
        slept = []
        self.assertFalse(behavior.maybe_step_break(12, slept.append))
        self.assertEqual(slept, [])

    def test_click_wait_shrinks_with_speed(self):
        for key in ("scroll_wait_ms", "click_delay_ms", "click_settle_s"):
            self.assertGreater(
                SPEED_PROFILES["slow"][key], SPEED_PROFILES["normal"][key], key
            )
            self.assertGreater(
                SPEED_PROFILES["normal"][key], SPEED_PROFILES["fast"][key], key
            )

    def test_click_js_placeholders_are_replaced(self):
        from src.core.js_loader import load_js

        subs = {
            "'__SID__'": "'sid'",
            "__SCROLL_WAIT__": "250",
            "__CLICK_DELAY__": "100",
        }
        for name in ("click_vue.js", "click_dom.js"):
            js = load_js(name, subs)
            for placeholder in ("__SID__", "__SCROLL_WAIT__", "__CLICK_DELAY__"):
                self.assertNotIn(placeholder, js, f"{name}: {placeholder}")

    def test_step_break_only_on_interval(self):
        behavior = BrowserBehavior("normal")
        slept = []
        self.assertFalse(behavior.maybe_step_break(1, slept.append))
        self.assertEqual(slept, [])
        self.assertTrue(behavior.maybe_step_break(25, slept.append))
        self.assertEqual(len(slept), 1)
        self.assertGreaterEqual(slept[0], 4.0)
        self.assertLessEqual(slept[0], 8.0)


if __name__ == "__main__":
    unittest.main()
