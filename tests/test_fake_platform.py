"""假平台验收：不碰网络、不开浏览器，跑通完整 run_collection。

核心判据：接入一个全新的平台时 ``src/collector.py`` 一行都不用改。
这里通过 ``site="fake"`` 注册一个适配器，再替换引擎里的浏览器工厂，
验证采集主流程、查重、在线门禁、详情落库都能照常工作。
"""
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from src.adapters.registry import register_adapter
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


JOBS = {
    "fake-1": {
        "success": True, "title": "后端工程师", "salary": "20-30K",
        "company": "甲公司", "location": "杭州·西湖区", "area": "西湖区",
        "experience": "3-5年", "degree": "本科", "address": "西湖区文三路",
        "encrypt_job_id": "enc-1", "boss_active": "今日活跃", "platform": "fake",
        "jd": "负责服务端开发。", "skills": ["Python"], "welfare": ["双休"],
        "job_labels": ["急招"], "company_labels": ["A轮"], "company_stage": "A轮",
        "company_scale": "100-499人", "industry": "互联网", "boss_name": "王女士",
        "boss_title": "HR",
    },
    "fake-2": {
        "success": True, "title": "数据工程师", "salary": "25-35K",
        "company": "乙公司", "location": "杭州·滨江区", "area": "滨江区",
        "experience": "5-10年", "degree": "硕士", "address": "滨江区江南大道",
        "encrypt_job_id": "enc-2", "boss_active": "3日内活跃", "platform": "fake",
        "jd": "负责数据管道。", "skills": ["SQL"], "welfare": ["五险一金"],
        "job_labels": [], "company_labels": [], "company_stage": "B轮",
        "company_scale": "500-999人", "industry": "互联网", "boss_name": "李先生",
        "boss_title": "技术负责人",
    },
}


class FakePlatformAdapter:
    """零网络适配器：所有页面操作都返回固定结果。"""

    site = "fake"
    display_name = "假平台"

    def __init__(self, page=None, click_timing=None):
        self.page = page
        self.click_timing = click_timing

    def pick_target(self, targets):
        return targets[0] if targets else None

    def home_url(self):
        return "https://fake.example/jobs"

    def login_url(self):
        return "https://fake.example/login"

    def reload(self):
        return {"ok": True, "reason": ""}

    def scroll_list(self):
        return {"ok": True, "reason": ""}

    def scroll_detail(self):
        return {"ok": True, "reason": ""}

    def scroll_position(self):
        return {"ok": True, "scrollTop": 0}

    def probe_login(self):
        return {"state": "in", "source": "fake"}

    def search_url(self, criteria):
        return f"https://fake.example/jobs?q={criteria.get('query', '')}"

    def matches_criteria(self, url, criteria):
        return (criteria.get("query") or "") in (url or "")

    def wait_results(self, timeout=14.0):
        return {"ok": True, "state": "ready", "reason": ""}

    def list_jobs(self):
        return {
            "ok": True,
            "reason": "",
            "jobs": [
                {"job_id": jid, "title": d["title"], "salary": d["salary"],
                 "area": d["area"], "company": d["company"], "raw": {}}
                for jid, d in JOBS.items()
            ],
        }

    def probe_online(self, job_id):
        return {"ok": True, "online": True, "source": "fake", "evidence": {}}

    def click_card(self, job_id):
        return {"ok": True, "index": 0, "total": len(JOBS), "reason": ""}

    def read_detail(self, job_id):
        return dict(JOBS[job_id])

    def open_chat(self, job_id):
        return {"ok": True, "reason": ""}

    def open_conversation(self, hints, timeout=12.0):
        return {"ok": True, "input_ready": True}

    def chat_input_ready(self):
        return True

    def chat_url(self):
        return "https://fake.example/chat"

    def fill_greeting(self, text, attempts=4):
        return {"ok": True, "length": len(text)}


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
    @classmethod
    def setUpClass(cls):
        register_adapter("fake", FakePlatformAdapter)

    def test_full_run_without_browser_writes_valid_json(self):
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
