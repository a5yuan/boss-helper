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
