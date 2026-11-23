"""智联招聘适配器契约测试：只读 fixture，不联网、不开浏览器。"""
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from src.adapters.registry import create_adapter
from src.adapters.zhaopin import ZhaopinAdapter
from src.config import PROJECT_DIR, load_config
from src.utils.company_online import classify_online
from src.utils.salary import parse_salary

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "zhaopin_position_list.json")
JOB_ID = "CCL1480117890J40911564605"


def load_fixture():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


class FakePage:
    """只实现 evaluate / get_value 的页面门面。

    按注入脚本里的 marker 分派，返回 JSON 字符串，模拟 CDP 的返回值形态。
    """

    def __init__(self, state=None, url="https://www.zhaopin.com/jobs/?jl=653&kw=Java",
                 dom_jd=""):
        self.state = state if state is not None else {}
        self.url = url
        self.dom_jd = dom_jd
        self.calls = []

    def evaluate(self, expression, await_promise=False, timeout=30):
        self.calls.append(expression)
        if "zhaopin:list" in expression:
            return json.dumps(self.state.get("positionList") or [])
        if "zhaopin:item" in expression:
            return json.dumps(self._find_item(expression))
        if "zhaopin:click" in expression:
            return json.dumps(self._click(expression))
        if "zhaopin:login" in expression:
            return json.dumps(self._login())
        if "zhaopin:dom-jd" in expression:
            return json.dumps({"text": self.dom_jd})
        if "scrollY" in expression:
            return json.dumps({"scrollTop": 0})
        if "zhaopin:scroll" in expression:
            return json.dumps({"ok": True})
        return json.dumps(None)

    def get_value(self, result):
        return json.loads(result) if isinstance(result, str) else result

    @staticmethod
    def _target_id(expression):
        match = re.search(r"const id\s*=\s*(\S+);", expression)
        if not match:
            return ""
        try:
            return json.loads(match.group(1))
        except Exception:
            return ""

    def _find_item(self, expression):
        ident = self._target_id(expression)
        items = self.state.get("positionList") or []
        for item in items:
            if str(item.get("number")) == ident:
                return item
        for item in items:
            if str(item.get("jobId")) == ident:
                return item
        return None

    def _click(self, expression):
        ident = self._target_id(expression)
        items = self.state.get("positionList") or []
        index = next((i for i, x in enumerate(items) if str(x.get("number")) == ident), -1)
        if index < 0:
            index = next((i for i, x in enumerate(items) if str(x.get("jobId")) == ident), -1)
        return {"index": index, "total": len(items), "scrolled": index >= 0}

    def _login(self):
        if "zhaopin.com" not in self.url:
            return {"state": "unknown", "source": "not_zhaopin"}
        user = self.state.get("user")
        if isinstance(user, dict) and user:
            return {"state": "in", "source": "state_user"}
        if "passport" in self.url or "/login" in self.url:
            return {"state": "login", "source": "login_url"}
        return {"state": "in", "source": "guest_session"}


class TestZhaopinIdentity(unittest.TestCase):
    def test_create_adapter_discovers_platform(self):
        adapter = create_adapter("zhaopin")
        self.assertIsInstance(adapter, ZhaopinAdapter)
        self.assertEqual(adapter.display_name, "智联招聘")

    def test_search_url_city_and_query(self):
        adapter = ZhaopinAdapter()
        url = adapter.search_url({"city_code": "101210100", "query": "Java"})
        self.assertIn("jl=653", url)
        self.assertIn("kw=Java", url)

    def test_search_url_accepts_zhaopin_code(self):
        adapter = ZhaopinAdapter()
        url = adapter.search_url({"city_code": "653", "query": "Java"})
        self.assertIn("jl=653", url)

    def test_search_url_unknown_city_omits_jl(self):
        adapter = ZhaopinAdapter()
        # 北京是 BOSS 已知城市，但不在智联实测映射表里
        url = adapter.search_url({"city_code": "101010100", "query": "Java"})
        self.assertNotIn("jl=", url)
        self.assertIn("kw=Java", url)

    def test_matches_criteria_compares_kw_and_jl_only(self):
        adapter = ZhaopinAdapter()
        criteria = {"city_code": "101210100", "query": "Java", "job_type": "full"}
        self.assertTrue(adapter.matches_criteria(
            "https://www.zhaopin.com/jobs/?jl=653&kw=Java", criteria))
        self.assertFalse(adapter.matches_criteria(
            "https://www.zhaopin.com/jobs/?jl=530&kw=Java", criteria))
        self.assertFalse(adapter.matches_criteria(
            "https://www.zhaopin.com/jobdetail/CCL1.htm", criteria))


class TestZhaopinListAndDetail(unittest.TestCase):
    def setUp(self):
        self.items = load_fixture()
        self.page = FakePage({"positionList": self.items, "user": {}})
        self.adapter = ZhaopinAdapter(self.page)

    def test_list_jobs_maps_cards(self):
        result = self.adapter.list_jobs()
        self.assertTrue(result["ok"])
        jobs = result["jobs"]
        self.assertEqual(len(jobs), 3)
        self.assertEqual([j["job_id"] for j in jobs],
                         [str(item["number"]) for item in self.items])
        self.assertEqual(jobs[0]["title"], self.items[0]["name"])
        self.assertEqual(jobs[0]["salary"], "1.2-2.4万·14薪")
        self.assertNotIn("**-**", jobs[0]["salary"])
        self.assertEqual(jobs[0]["area"], "滨江")
        self.assertEqual(jobs[0]["company"], self.items[0]["companyName"])

    def test_read_detail_maps_full_state(self):
        detail = self.adapter.read_detail(JOB_ID)
        self.assertTrue(detail["success"])
        self.assertEqual(detail["platform"], "zhaopin")
        self.assertEqual(detail["encrypt_job_id"], JOB_ID)
        # 智联没有会话内卡片 id，岗位号兼作定位键；/api/focus 靠它走 click 分支，
        # 不会落到 server/app.py 里写死的 BOSS 详情 URL。
        self.assertEqual(detail["security_id"], JOB_ID)
        self.assertEqual(detail["location"], "杭州·滨江")
        self.assertGreater(len(detail["jd"]), len(self.items[0]["jobDescription"]))
        lo, hi = parse_salary(detail["salary"])
        self.assertIsNotNone(lo)
        self.assertIsNotNone(hi)
        self.assertEqual(detail["skills"], ["Java", "Python", "Shell", "Golang", "C/C++"])
        self.assertEqual(detail["job_labels"], ["劳务派遣", "新发布"])
        self.assertEqual(detail["address"], "滨江华为技术有限公司杭州研究所11")
        self.assertEqual(detail["boss_name"], "刘女士")
        self.assertEqual(detail["boss_title"], "人事经理")
        self.assertEqual(detail["boss_active"], "3分钟前回复、今日回复50+次、高回复率")
        self.assertEqual(detail["company"], self.items[0]["companyName"])
        self.assertEqual(detail["industry"], self.items[0]["industryName"])

    def test_read_detail_missing_district_keeps_city_only(self):
        detail = self.adapter.read_detail("CCL1342438610J40812175406")
        self.assertTrue(detail["success"])
        self.assertEqual(detail["location"], "杭州")

    def test_read_detail_falls_back_to_dom_when_jd_empty(self):
        items = json.loads(json.dumps(self.items, ensure_ascii=False))
        items[0]["jobDetailData"]["position"]["desc"]["description"] = ""
        items[0]["jobDescription"] = ""
        page = FakePage({"positionList": items}, dom_jd="DOM 兜底正文")
        detail = ZhaopinAdapter(page).read_detail(JOB_ID)
        self.assertEqual(detail["jd"], "DOM 兜底正文")

    def test_read_detail_not_found_returns_error(self):
        detail = self.adapter.read_detail("NOPE")
        self.assertNotIn("success", detail)
        self.assertEqual(detail["error"], "not_found")

    def test_click_card_returns_state_only(self):
        click = self.adapter.click_card(JOB_ID)
        self.assertTrue(click["ok"])
        self.assertIsInstance(click["index"], int)
        self.assertEqual(click["index"], 0)
        self.assertIsInstance(click["total"], int)
        self.assertEqual(click["total"], 3)
        self.assertEqual(click["reason"], "state_only")


class TestZhaopinProbes(unittest.TestCase):
    def test_probe_online_is_unknown(self):
        adapter = ZhaopinAdapter(FakePage())
        self.assertEqual(classify_online(adapter.probe_online(JOB_ID)), "unknown")

    def test_login_state_user_is_in(self):
        page = FakePage({"positionList": [], "user": {"id": 1}})
        self.assertEqual(ZhaopinAdapter(page).probe_login(),
                         {"state": "in", "source": "state_user"})

    def test_login_guest_page_is_readable(self):
        # 游客态（user 为空、页面有列表）也必须报 in，不能进扫码循环
        page = FakePage({"positionList": load_fixture()})
        self.assertEqual(ZhaopinAdapter(page).probe_login(),
                         {"state": "in", "source": "guest_session"})

    def test_passport_url_is_login(self):
        page = FakePage({}, url="https://passport.zhaopin.com/login")
        self.assertEqual(ZhaopinAdapter(page).probe_login(),
                         {"state": "login", "source": "login_url"})

    def test_non_zhaopin_url_is_unknown(self):
        page = FakePage({}, url="https://www.zhipin.com/web/geek/job")
        self.assertEqual(ZhaopinAdapter(page).probe_login(),
                         {"state": "unknown", "source": "not_zhaopin"})


class TestZhaopinUnsupportedApply(unittest.TestCase):
    def setUp(self):
        self.adapter = ZhaopinAdapter(FakePage())

    def test_prefill_methods_are_unsupported(self):
        # 智联走 apply_then_chat，不提供 BOSS 式「只填草稿」入口
        results = [
            self.adapter.open_chat(JOB_ID),
            self.adapter.fill_greeting("你好"),
        ]
        for result in results:
            self.assertIs(result["ok"], False)
            self.assertTrue(result["reason"].startswith("unsupported:"))

    def test_open_conversation_waits_for_input_box(self):
        # 投递后进聊天页时用：只等输入框，不点任何东西
        result = self.adapter.open_conversation(["某公司"], timeout=0.1)
        self.assertIs(result["ok"], False)
        self.assertIs(result["input_ready"], False)

    def test_chat_input_and_url(self):
        self.assertIs(self.adapter.chat_input_ready(), False)
        self.assertEqual(self.adapter.chat_url(), "")

    def test_scroll_position_returns_dict(self):
        self.assertIsInstance(self.adapter.scroll_position(), dict)


class TestZhaopinConfigSection(unittest.TestCase):
    def test_platform_section_overrides_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "zp-out")
            cfg = {
                "chrome": {"path": "C:/default-chrome.exe"},
                "zhaopin": {
                    "path": "C:/zp-chrome.exe",
                    "profile_dir": "C:/zp-profile",
                    "output_dir": out_dir,
                    "port_file": "zp-port",
                },
            }
            with mock.patch("src.config._read_yaml", return_value=cfg), \
                    mock.patch("src.config._find_chrome", return_value="C:/found-chrome.exe"):
                conf = load_config("chrome", platform="zhaopin")

        self.assertEqual(conf["browser_path"], "C:/zp-chrome.exe")
        self.assertEqual(conf["profile_dir"], "C:/zp-profile")
        self.assertEqual(conf["output_dir"], out_dir)
        self.assertEqual(conf["port_file"], os.path.join(PROJECT_DIR, "zp-port"))

    def test_boss_without_platform_section_keeps_legacy_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"chrome": {"path": "C:/default-chrome.exe"}}
            with mock.patch("src.config._read_yaml", return_value=cfg), \
                    mock.patch("src.config._find_chrome", return_value="C:/found-chrome.exe"), \
                    mock.patch("src.config._default_output_dir", return_value=tmp):
                conf = load_config("chrome", platform="boss")

        self.assertEqual(conf["browser_path"], "C:/default-chrome.exe")
        self.assertEqual(conf["output_dir"], os.path.join(tmp, "boss"))
        self.assertTrue(conf["profile_dir"].endswith(os.path.join("profiles", "chrome_profile")))
        self.assertTrue(conf["port_file"].endswith(".cdp_port_boss_chrome"))


if __name__ == "__main__":
    unittest.main()
