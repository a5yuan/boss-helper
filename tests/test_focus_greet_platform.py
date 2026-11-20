"""复核页动作的平台路由：/api/focus 与 /api/greet 接受可选 platform。

判据：
- 请求体带 platform 时，浏览器操作走该平台；
- 不传时沿用岗位记录的 platform，再退回默认平台，行为与改动前一致；
- 目标平台浏览器没启动时返回可读错误，不抛栈。
"""
import unittest
from unittest import mock

from server import app as server_app
from server.app import FocusBody, GreetBody
from src.config import DEFAULT_PLATFORM


class _FakePage:
    """BrowserManager 替身：只按预设页面应答选页与连接。"""

    def __init__(self, pages):
        self.pages = pages
        self.connected = None

    def try_connect_existing(self):
        return True

    def list_pages(self):
        return self.pages

    def connect_ws(self, ws_url):
        self.connected = ws_url

    def disconnect(self):
        pass


class TestRoutePlatform(unittest.TestCase):
    """handler 把 body.platform 传给 _with_browser。"""

    def _call_focus(self, body, job):
        seen = {}

        def fake_with_browser(fn, prefer_chat=False, platform=None):
            seen["platform"] = platform
            seen["prefer_chat"] = prefer_chat
            return {"ok": True}

        with mock.patch.object(server_app, "_find_job", return_value=job), \
                mock.patch.object(server_app, "_with_browser", side_effect=fake_with_browser):
            result = server_app.api_focus(body)
        return result, seen

    def _call_greet(self, body, job):
        seen = {}

        def fake_with_browser(fn, prefer_chat=False, platform=None):
            seen["platform"] = platform
            seen["prefer_chat"] = prefer_chat
            return {"ok": True}

        with mock.patch.object(server_app, "_find_job", return_value=job), \
                mock.patch.object(server_app, "_with_browser", side_effect=fake_with_browser):
            result = server_app.api_greet(body)
        return result, seen

    def test_focus_body_platform_wins_over_job(self):
        body = FocusBody(encrypt_job_id="enc-2", platform="fake")
        result, seen = self._call_focus(body, {"platform": "boss"})
        self.assertTrue(result["ok"])
        self.assertEqual(seen["platform"], "fake")

    def test_focus_without_platform_keeps_job_platform(self):
        result, seen = self._call_focus(FocusBody(encrypt_job_id="enc-1"), {"platform": "fake"})
        self.assertTrue(result["ok"])
        self.assertEqual(seen["platform"], "fake")

    def test_focus_without_platform_and_job_falls_back_to_default(self):
        result, seen = self._call_focus(FocusBody(encrypt_job_id="enc-1"), {})
        self.assertTrue(result["ok"])
        self.assertEqual(seen["platform"], DEFAULT_PLATFORM)

    def test_focus_blank_platform_is_ignored(self):
        result, seen = self._call_focus(FocusBody(encrypt_job_id="enc-1", platform="   "),
                                        {"platform": "fake"})
        self.assertTrue(result["ok"])
        self.assertEqual(seen["platform"], "fake")

    def test_greet_body_platform_wins_over_job(self):
        body = GreetBody(encrypt_job_id="enc-2", platform="fake")
        result, seen = self._call_greet(body, {"platform": "boss"})
        self.assertTrue(result["ok"])
        self.assertEqual(seen["platform"], "fake")
        # 招呼语仍然优先连聊天标签页
        self.assertTrue(seen["prefer_chat"])

    def test_greet_without_platform_keeps_job_platform(self):
        result, seen = self._call_greet(GreetBody(encrypt_job_id="enc-1"), {"platform": "fake"})
        self.assertTrue(result["ok"])
        self.assertEqual(seen["platform"], "fake")


class TestWithBrowserPlatform(unittest.TestCase):
    """_with_browser 按平台选浏览器与标签页。"""

    def test_fake_platform_selects_fake_tab(self):
        pages = [
            {"type": "page", "url": "https://www.zhipin.com/web/geek/jobs", "webSocketDebuggerUrl": "ws://boss"},
            {"type": "page", "url": "https://fake.example/jobs", "webSocketDebuggerUrl": "ws://fake"},
        ]
        bm = _FakePage(pages)
        with mock.patch("src.core.browser.BrowserManager", return_value=bm), \
                mock.patch.object(server_app, "get_config", return_value={"output_dir": ""}):
            result = server_app._with_browser(lambda b, page: {"ok": True, "url": page["url"]},
                                              platform="fake")
        self.assertTrue(result["ok"])
        self.assertEqual(result["url"], "https://fake.example/jobs")
        self.assertEqual(bm.connected, "ws://fake")

    def test_default_platform_selects_boss_tab(self):
        pages = [
            {"type": "page", "url": "https://fake.example/jobs", "webSocketDebuggerUrl": "ws://fake"},
            {"type": "page", "url": "https://www.zhipin.com/web/geek/jobs", "webSocketDebuggerUrl": "ws://boss"},
        ]
        bm = _FakePage(pages)
        with mock.patch("src.core.browser.BrowserManager", return_value=bm), \
                mock.patch.object(server_app, "get_config", return_value={"output_dir": ""}):
            result = server_app._with_browser(lambda b, page: {"ok": True, "url": page["url"]})
        self.assertTrue(result["ok"])
        self.assertEqual(result["url"], "https://www.zhipin.com/web/geek/jobs")

    def test_browser_not_started_reports_platform(self):
        bm = mock.Mock()
        bm.try_connect_existing.return_value = False
        with mock.patch("src.core.browser.BrowserManager", return_value=bm), \
                mock.patch.object(server_app, "get_config", return_value={"output_dir": ""}):
            result = server_app._with_browser(lambda b, page: {"ok": True}, platform="fake")
        self.assertFalse(result["ok"])
        self.assertIn("假平台", result["error"])
        self.assertIn("尚未启动", result["error"])
        self.assertIn("先跑一次采集", result["error"])

    def test_unknown_platform_is_rejected_before_connecting(self):
        with mock.patch("src.core.browser.BrowserManager") as bm_cls:
            result = server_app._with_browser(lambda b, page: {"ok": True}, platform="nope")
        self.assertFalse(result["ok"])
        self.assertIn("未知平台", result["error"])
        bm_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
