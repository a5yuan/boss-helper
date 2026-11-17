"""AI 管线的纯逻辑测试：JSON 抠取 + 计划状态判定。不联网。"""
import unittest

from src.ai.client import LLMError, extract_json
from src.ai.pipeline import decide_status


class TestExtractJson(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(extract_json('{"score": 80}'), {"score": 80})

    def test_with_code_fence(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_with_leading_prose(self):
        self.assertEqual(extract_json('好的，结果如下：{"a": {"b": 2}} 以上'), {"a": {"b": 2}})

    def test_braces_inside_string(self):
        self.assertEqual(extract_json('{"greeting": "我做过 {RAG} 项目"}')["greeting"],
                         "我做过 {RAG} 项目")

    def test_escaped_quote_inside_string(self):
        self.assertEqual(extract_json(r'{"a": "他说\"好\""}')["a"], '他说"好"')

    def test_empty_raises(self):
        with self.assertRaises(LLMError):
            extract_json("")

    def test_no_json_raises(self):
        with self.assertRaises(LLMError):
            extract_json("抱歉，我无法回答")

    def test_unclosed_raises(self):
        with self.assertRaises(LLMError):
            extract_json('{"a": 1')


class TestDecideStatus(unittest.TestCase):
    def test_apply_above_threshold_is_planned(self):
        self.assertEqual(decide_status("apply", 80, "你好", 60), "planned")

    def test_below_threshold_is_skip(self):
        self.assertEqual(decide_status("apply", 40, "你好", 60), "skip")

    def test_verdict_skip_wins_even_with_high_score(self):
        self.assertEqual(decide_status("skip", 95, "你好", 60), "skip")

    def test_empty_greeting_is_skip(self):
        self.assertEqual(decide_status("apply", 90, "   ", 60), "skip")

    def test_maybe_above_threshold_is_planned(self):
        self.assertEqual(decide_status("maybe", 65, "你好", 60), "planned")


if __name__ == "__main__":
    unittest.main()


class TestResumeLibrary(unittest.TestCase):
    def _lib(self):
        import os
        import tempfile
        from src.ai.resume import ResumeLibrary

        td = tempfile.mkdtemp()
        a = os.path.join(td, "agent.md")
        b = os.path.join(td, "fe.md")
        with open(a, "w", encoding="utf-8") as f:
            f.write("# 我\n做 Agent / RAG / 大模型应用，四年经验。" * 3)
        with open(b, "w", encoding="utf-8") as f:
            f.write("# 我\n做前端 Vue / React / TypeScript，页面还原。" * 3)
        return ResumeLibrary([
            {"label": "Agent", "path": a, "keywords": ["agent", "rag", "大模型"]},
            {"label": "前端", "path": b, "keywords": ["前端", "vue", "react"]},
        ], default_label="Agent")

    def test_pick_by_title(self):
        lib = self._lib()
        self.assertEqual(lib.pick({"title": "前端开发工程师", "skills": [], "jd": ""})[0], "前端")
        self.assertEqual(lib.pick({"title": "Agent 开发", "skills": [], "jd": ""})[0], "Agent")

    def test_title_outweighs_jd(self):
        lib = self._lib()
        # JD 里堆前端词，但标题是 Agent 方向，标题权重 3 应压过 JD 的 1
        label, _ = lib.pick({"title": "Agent 工程师", "skills": [], "jd": "vue react 前端 页面"})
        self.assertEqual(label, "Agent")

    def test_empty_job_falls_back_to_default(self):
        lib = self._lib()
        self.assertEqual(lib.pick({"title": "", "skills": [], "jd": ""})[0], "Agent")

    def test_digest_changes_with_content(self):
        lib = self._lib()
        first = lib.digest()
        self.assertEqual(first, lib.digest())
        self.assertEqual(len(first), 12)


class TestActivity(unittest.TestCase):
    def test_just_now(self):
        from src.ai.activity import parse_active_days
        self.assertEqual(parse_active_days("杨女士 在线 卓越际联 · 招聘专员"), 0)
        self.assertEqual(parse_active_days("朱慧政 刚刚活跃 阿里云 · 招聘专员"), 0)
        self.assertEqual(parse_active_days("今日活跃"), 0)

    def test_days_weeks_months(self):
        from src.ai.activity import parse_active_days
        self.assertEqual(parse_active_days("5天前活跃"), 5)
        self.assertEqual(parse_active_days("2周前活跃"), 14)
        self.assertEqual(parse_active_days("3月前活跃"), 90)
        self.assertEqual(parse_active_days("6个月前活跃"), 180)
        self.assertEqual(parse_active_days("半年前活跃"), 180)

    def test_unparsable_returns_none(self):
        from src.ai.activity import parse_active_days
        self.assertIsNone(parse_active_days(""))
        self.assertIsNone(parse_active_days("外企德科数字 · 招聘专员"))

    def test_offline_threshold(self):
        from src.ai.activity import is_offline
        self.assertFalse(is_offline("刚刚活跃", 3))
        self.assertFalse(is_offline("昨日活跃", 3))
        self.assertTrue(is_offline("5天前活跃", 3))
        self.assertTrue(is_offline("半年前活跃", 3))
        # 读不出活跃时间时不拦截，交给人判断
        self.assertFalse(is_offline("外企德科数字 · 招聘专员", 3))


class TestQuota(unittest.TestCase):
    def test_zero_means_unlimited(self):
        from src.ai.dispatch import plan_quota
        self.assertEqual(plan_quota(500, 0, 30), 30)

    def test_negative_means_unlimited(self):
        from src.ai.dispatch import plan_quota
        self.assertEqual(plan_quota(500, -1, 7), 7)

    def test_positive_limit_truncates(self):
        from src.ai.dispatch import plan_quota
        self.assertEqual(plan_quota(14, 20, 30), 6)
        self.assertEqual(plan_quota(20, 20, 30), 0)
        self.assertEqual(plan_quota(25, 20, 30), 0)

    def test_want_smaller_than_quota(self):
        from src.ai.dispatch import plan_quota
        self.assertEqual(plan_quota(0, 20, 3), 3)
