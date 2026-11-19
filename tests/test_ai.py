"""AI 管线的纯逻辑测试：JSON 抠取 + 计划状态判定。不联网。"""
import os
import tempfile
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


class TestDispatchTrackerInjection(unittest.TestCase):
    def test_dry_run_uses_injected_tracker(self):
        from src.ai.dispatch import dispatch
        from src.tracking import Tracker

        with tempfile.TemporaryDirectory() as td:
            tracker = Tracker(path=os.path.join(td, "tracking.json"))
            tracker.set("enc-1", "applied")
            stats = dispatch(
                [{"encrypt_job_id": "enc-1", "security_id": "", "title": "x", "greeting": "你好"}],
                dry=True, tracker=tracker,
            )
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["total"], 0)


class TestLlmThrottle(unittest.TestCase):
    def test_semaphore_is_global_and_uses_configured_capacity(self):
        from src.ai.client import _llm_semaphore
        from src.config import load_ai_config

        sem = _llm_semaphore()
        self.assertIs(sem, _llm_semaphore())
        expected = max(1, int(load_ai_config().get("concurrency", 4)))
        self.assertEqual(sem._value, expected)


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


class TestCarryDispatch(unittest.TestCase):
    def test_carries_dispatch_record(self):
        from src.ai.pipeline import carry_dispatch
        old = {"dispatch": "done", "dispatch_at": "2026-11-18T09:55:27", "dispatch_note": ""}
        new = {"dispatch": "todo", "title": "x"}
        out = carry_dispatch(old, new)
        self.assertEqual(out["dispatch"], "done")
        self.assertEqual(out["dispatch_at"], "2026-11-18T09:55:27")

    def test_no_old_record_keeps_todo(self):
        from src.ai.pipeline import carry_dispatch
        out = carry_dispatch(None, {"dispatch": "todo"})
        self.assertEqual(out["dispatch"], "todo")

    def test_old_without_dispatch_does_not_blank_new(self):
        from src.ai.pipeline import carry_dispatch
        out = carry_dispatch({"title": "x"}, {"dispatch": "todo"})
        self.assertEqual(out["dispatch"], "todo")


class _FakeChatClient:
    """记录发出去的 messages，返回固定 payload。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat_json(self, messages, max_tokens=900):
        self.calls.append((messages, max_tokens))
        return dict(self.payload)


class TestGreetingPrompt(unittest.TestCase):
    """招呼语提示词边界：不得让模型把简历里的姓名 / 联系方式抄进 greeting。"""

    CANNED = {
        "score": 82,
        "verdict": "maybe",
        "reasons": ["要求 Python 后端", "做过 RAG 检索链路"],
        "gaps": ["没有 K8s 经验"],
        "greeting": "做 Agent 与 RAG 工程，用 Python/FastAPI 做过检索链路，想聊聊你们的召回方案。",
    }

    def _run(self):
        from src.ai.screen import analyze_job

        client = _FakeChatClient(self.CANNED)
        job = {
            "title": "Agent 开发工程师",
            "company": "测试公司",
            "company_stage": "B轮",
            "company_scale": "100-499人",
            "industry": "人工智能",
            "salary": "25-40K",
            "experience": "3-5年",
            "degree": "本科",
            "location": "杭州",
            "skills": ["Python", "RAG"],
            "welfare": ["五险一金"],
            "company_intro": "做企业级 Agent 平台",
            "jd": "负责 Agent 与 RAG 应用开发，要求熟悉 Python、FastAPI，有检索增强经验。",
        }
        resume = (
            "吴金远\n手机 13800138000\n邮箱 wuyj@example.com\n微信号 wjy_agent\n"
            "四年 Python 后端，做过 RAG 检索链路与 Agent 编排。"
        )
        return client, analyze_job(client, job, resume)

    def test_prompt_forbids_real_name_and_contact(self):
        client, _ = self._run()
        user = client.calls[0][0][1]["content"]
        for needle in ("角色 + 技术栈", "严禁出现真实姓名", "联系方式",
                       "我是XXX", "至少提到 JD 里的 1 个具体要求", "140"):
            self.assertIn(needle, user)
        self.assertNotIn("我是谁", user)
        # 旧模板允许「您好，我是…」以外都算客套，这条必须消失
        self.assertNotIn("以外的客套", user)

    def test_canned_score_verdict_reasons_gaps_pass_through(self):
        _, result = self._run()
        self.assertEqual(result["score"], self.CANNED["score"])
        self.assertEqual(result["verdict"], self.CANNED["verdict"])
        self.assertEqual(result["reasons"], self.CANNED["reasons"])
        self.assertEqual(result["gaps"], self.CANNED["gaps"])


class TestApplyOutcomes(unittest.TestCase):
    def _plan(self):
        return {"items": [
            {"encrypt_job_id": "a", "dispatch": "todo"},
            {"encrypt_job_id": "b", "dispatch": "todo"},
            {"encrypt_job_id": "c", "dispatch": "todo"},
        ]}

    def test_merges_ok_and_failed(self):
        from src.ai.pipeline import apply_outcomes
        plan = self._plan()
        stats = {"outcomes": [
            {"eid": "a", "ok": True, "reason": "", "at": "2026-11-18T10:09:41"},
            {"eid": "b", "ok": False, "reason": "没点到「立即沟通」", "at": "2026-11-18T10:09:50"},
        ]}
        n = apply_outcomes(plan, stats)
        self.assertEqual(n, 2)
        self.assertEqual(plan["items"][0]["dispatch"], "done")
        self.assertEqual(plan["items"][0]["dispatch_at"], "2026-11-18T10:09:41")
        self.assertEqual(plan["items"][1]["dispatch"], "failed")
        self.assertEqual(plan["items"][1]["dispatch_note"], "没点到「立即沟通」")
        self.assertEqual(plan["items"][2]["dispatch"], "todo")   # 没跑到的保持原状

    def test_empty_stats_is_noop(self):
        from src.ai.pipeline import apply_outcomes
        plan = self._plan()
        self.assertEqual(apply_outcomes(plan, {}), 0)
        self.assertEqual(plan["items"][0]["dispatch"], "todo")
