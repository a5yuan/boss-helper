"""公司在线状态探针的纯逻辑测试：状态归类 + 证据格式化 + JS 注入契约。不联网。"""
import unittest

from src.core.js_loader import load_js
from src.utils.company_online import (
    STATE_OFFLINE,
    STATE_ONLINE,
    STATE_UNKNOWN,
    classify_online,
    format_evidence,
)


class TestClassifyOnline(unittest.TestCase):
    def test_dom_online(self):
        probe = {"ok": True, "online": True, "source": "dom", "evidence": {}}
        self.assertEqual(classify_online(probe), STATE_ONLINE)

    def test_dom_offline(self):
        probe = {"ok": True, "online": False, "source": "dom", "evidence": {}}
        self.assertEqual(classify_online(probe), STATE_OFFLINE)

    def test_vue_fallback(self):
        probe = {
            "ok": True, "online": True, "source": "vue",
            "evidence": {"span_scope": "none", "vue": True},
        }
        self.assertEqual(classify_online(probe), STATE_ONLINE)

    def test_dom_result_wins_over_vue_evidence(self):
        # 以顶层 online 为准，不看 evidence.vue，不做二次推断
        probe = {
            "ok": True, "online": True, "source": "dom",
            "evidence": {"span_scope": "logo", "vue": False},
        }
        self.assertEqual(classify_online(probe), STATE_ONLINE)

    def test_malformed_inputs_are_unknown(self):
        bad_probes = (
            None,
            [],
            "online",
            {},
            {"ok": True},                          # 缺 online
            {"online": True},                      # 缺 ok
            {"ok": False, "online": True},         # ok 不是 True
            {"ok": True, "online": "true"},        # online 不是布尔
            {"ok": True, "online": 1},             # 1 不是布尔
            {"ok": True, "online": None},
        )
        for bad in bad_probes:
            with self.subTest(bad=bad):
                self.assertEqual(classify_online(bad), STATE_UNKNOWN)


class TestFormatEvidence(unittest.TestCase):
    def test_fixed_key_order_and_values(self):
        probe = {"evidence": {
            "card_sel": ".job-card-box",
            "row_sel": "a.boss-info",
            "logo": True,
            "logo_cls": "boss-logo",
            "span_scope": "logo",
            "row_text_len": 12,
            "vue": True,
        }}
        line = format_evidence(probe)
        self.assertTrue(line.startswith("card_sel="))
        self.assertIn("logo=True", line)
        self.assertIn("span_scope=logo", line)
        self.assertIn("vue=True", line)
        # 固定键顺序
        self.assertLess(line.index("card_sel="), line.index("row_sel="))
        self.assertLess(line.index("row_sel="), line.index("logo="))
        self.assertLess(line.index("logo_cls="), line.index("span_scope="))
        self.assertLess(line.index("span_scope="), line.index("row_text_len="))
        self.assertLess(line.index("row_text_len="), line.index("vue="))

    def test_dirty_inputs_never_raise(self):
        dirty = (
            None,
            "x",
            [],
            {},
            {"evidence": None},
            {"evidence": "x"},
            {"evidence": {"logo_cls": None, "row_text_len": {"a": 1}}},
            {"evidence": {"logo_cls": "a\nb\tc", "span_scope": None}},
        )
        for probe in dirty:
            with self.subTest(probe=probe):
                line = format_evidence(probe)
                self.assertIsInstance(line, str)
                self.assertNotIn("\n", line)
                self.assertNotIn("\t", line)

    def test_length_limit(self):
        probe = {"evidence": {"logo_cls": "x" * 80, "card_sel": ".job-card-box"}}
        line = format_evidence(probe, limit=30)
        self.assertEqual(len(line), 30)

    def test_contains_all_fixed_keys(self):
        line = format_evidence({"evidence": {}})
        for key in ("card_sel=", "row_sel=", "logo=", "logo_cls=",
                    "span_scope=", "row_text_len=", "vue="):
            self.assertIn(key, line)


class TestReadCompanyOnlineJs(unittest.TestCase):
    def test_placeholder_injected_and_contract_kept(self):
        code = load_js("read_company_online.js", {"'__SID__'": "'abc123'"})
        self.assertNotIn("__SID__", code)
        self.assertIn("abc123", code)
        self.assertIn(".boss-online-icon", code)
        self.assertIn("bossOnline", code)
        # 同步 IIFE：顶层不带 async，避免 evaluate 需要 awaitPromise
        self.assertTrue(code.lstrip().startswith("(() =>"))
        self.assertNotIn("async", code)


if __name__ == "__main__":
    unittest.main()
