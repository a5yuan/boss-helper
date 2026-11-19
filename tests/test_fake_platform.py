"""假平台验收：不碰网络、不开浏览器，跑通完整 run_collection。

核心判据：接入一个全新的平台时 ``src/collector.py`` 一行都不用改。
这里通过 ``site="fake"`` 让 registry 自动 import ``src.adapters.fake``，
再替换引擎里的浏览器工厂，验证采集主流程、查重、在线门禁、详情落库。
"""
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from src.collector import run_collection


class FakeBrowser:
    """页面门面的假实现：只记录 URL，不做任何 I/O。"""

    instances = []

    def __init__(self, config=None):
        self.config = config
        self.port = 0
        self.ws = None
        self.should_stop = None
        self.url = "https://fake.example/jobs?q=python"
        FakeBrowser.instances.append(self)

    def try_connect_existing(self):
        return True

    def launch(self, start_url=None):
        if start_url:
            self.url = start_url
        return True

    def find_target_pages(self):
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


class QuietController:
    """收集状态，避免测试输出刷屏。"""

    def __init__(self):
        self.logs = []
        self.final_state = None

    def log(self, msg="", level="info", end="\n"):
        self.logs.append(str(msg))

    def progress(self, done, total, stats=None):
        pass

    def status(self, state, detail=None):
        self.final_state = state

    def wait_user(self, reason, kind="confirm"):
        raise AssertionError(f"假平台流程不该等待人工输入: {reason}")

    def should_stop(self):
        return False

    def should_pause(self):
        return False


class TestFakePlatformRun(unittest.TestCase):
    def test_full_run_without_browser_writes_valid_json(self):
        from src.adapters import registry

        # 假平台必须靠目录自动发现，测试里不允许手工注册
        self.assertNotIn("fake", registry._FACTORIES)

        FakeBrowser.instances.clear()
        ctrl = QuietController()
        with tempfile.TemporaryDirectory() as out_dir:
            config = {"output_dir": out_dir}
            with mock.patch("src.collector.BrowserManager", FakeBrowser), \
                    mock.patch("src.collector.get_config", return_value=config):
                run_collection(
                    count=2, site="fake", query="python", keyword_search=True,
                    tag="fakecheck", speed="fast", controller=ctrl,
                )

            self.assertEqual(ctrl.final_state, "done")
            self.assertEqual(len(FakeBrowser.instances), 1)
            self.assertIn("fake", registry._FACTORIES)
            json_path = [p for p in os.listdir(out_dir) if p.endswith(".json")]
            self.assertEqual(len(json_path), 1)

            with open(os.path.join(out_dir, json_path[0]), encoding="utf-8") as f:
                saved = json.load(f)

        self.assertEqual([j["encrypt_job_id"] for j in saved], ["enc-1", "enc-2"])
        self.assertTrue(all(j["platform"] == "fake" for j in saved))
        self.assertTrue(all(j.get("collected_at") for j in saved))


class TestCollectorHasNoPlatformTokens(unittest.TestCase):
    """防回归：引擎不该再出现任何具体平台的痕迹。"""

    # boss_active 是详情契约的输出键，\bboss\b 不会命中它；
    # 其余 token 一旦出现在 collector.py 就说明平台知识又漏回了引擎。
    TOKENS = (
        r"zhipin",
        r"\bboss\b",
        r"bossadapter",
        r"securityid",
        r"security_id",
        r"boss-online-icon",
    )

    def test_collector_is_platform_neutral(self):
        path = os.path.join(os.path.dirname(__file__), "..", "src", "collector.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()

        hits = [tok for tok in self.TOKENS if re.search(tok, source, re.IGNORECASE)]
        self.assertEqual(hits, [], f"collector.py 出现平台专属 token: {hits}")


if __name__ == "__main__":
    unittest.main()
