"""筛选预筛的误伤边界：线上面试、实习证明这类正常岗位不能被排掉。"""
import unittest

from src.ai.exclude import check_job, exclusion_result


def _job(title="", jd="", welfare=None, job_labels=None):
    return {
        "title": title,
        "jd": jd,
        "welfare": welfare or [],
        "job_labels": job_labels or [],
    }


class _Base(unittest.TestCase):
    def assert_excluded(self, job, rule):
        hit = check_job(job)
        self.assertIsNotNone(hit, f"应排除却没有命中: {job}")
        self.assertEqual(hit["rule"], rule)
        self.assertTrue(hit["snippet"])
        return hit

    def assert_kept(self, job):
        self.assertIsNone(check_job(job), f"误伤: {job}")


class TestMustExclude(_Base):
    def test_offline_interview_in_title(self):
        hit = self.assert_excluded(
            _job(title="(线下面试）Java开发-agent方向"), "interview_offline")
        self.assertIn("线下面试", hit["snippet"])

    def test_onsite_interview_in_jd(self):
        self.assert_excluded(
            _job(jd="一、 岗位职责（需要现场面试）\n1、有企业商旅经验优先"),
            "interview_offline")

    def test_required_offline_phrases(self):
        for text in ["需线下面试", "现场面试", "到场面试", "需到岗面谈",
                     "面试地点：杭州市西湖区", "面试方式：线下", "到公司复试",
                     "非常需要现场面试", "需接受现场面试", "可接受现场面试",
                     "可以接受现场面试", "线下二面", "视频面试后到现场复试",
                     "Java（Agent，外包大厂，学信网，复试现场",
                     "线下面试不支持远程", "现场面试不提供视频面试",
                     "面试地点：杭州不支持线上", "不排除线下面试"]:
            with self.subTest(text=text):
                self.assert_excluded(_job(jd=text), "interview_offline")

    def test_internship_titles(self):
        for title in ["agent应用开发实习生", "Agent 系统开发实习生",
                      "AI Agent开发实习生", "暑期实习", "日常实习", "实习岗",
                      "Agent开发实习机会", "实习待遇优厚", "带薪实习生"]:
            with self.subTest(title=title):
                self.assert_excluded(_job(title=title), "internship")

    def test_internship_job_label(self):
        self.assert_excluded(_job(title="agent开发", job_labels=["实习生"]), "internship")


    # ── JD 正文里的实习承诺：标题没写实习、但要求候选人投入实习时间 ──
    def test_internship_commitment_in_jd(self):
        for text in ["实习周期不少于 3 个月",
                     "实习期不少于6个月",
                     "每周至少 4 天的实习时间",
                     "本岗位走实习转正通道，不直发秋招 offer"]:
            with self.subTest(text=text):
                self.assert_excluded(_job(title="agent开发", jd=text), "internship")

    def test_internship_commitment_variants(self):
        # 真实 JD 里的其他写法：顺序反的、说「连续实习」的、说「实习时间」的
        for text, rule in [("每周可实习 4 天", "internship"),
                           ("每周实习 3 天", "internship"),
                           ("能连续实习 3 个月", "internship"),
                           ("实习时间不少于 3 个月", "internship"),
                           ("实习可转正", "internship")]:
            with self.subTest(text=text):
                self.assert_excluded(_job(title="agent开发", jd=text), rule)

    def test_online_forbidden_after_offline_interview(self):
        # 「线下面试、线上面试勿投」是只接受线下，不是给了线上替代
        self.assert_excluded(
            _job(title="agent智能体开发",
                 jd="优先考虑在天津本地的⼈选，能参加 线下面试 、线上面试勿投"),
            "interview_offline")


class TestMustNotExclude(_Base):
    def test_online_interview_titles(self):
        for title in ["AI Agent软件开发岗-0经验-可培养-线上面试",
                      "agent开发（线上面试）",
                      "白象Agent开发+双休不加班+线上面试"]:
            with self.subTest(title=title):
                self.assert_kept(_job(title=title))

    def test_online_interview_jd(self):
        for text in ["全程线上面试", "飞书视频面试3轮", "可远程面试",
                     "面试地点：线上", "面试方式：视频面试",
                     "不需要现场面试", "不要求线下面试", "非现场面试", "可线下面试",
                     "线上面试或线下面试均可", "线上、线下面试都可以"]:
            with self.subTest(text=text):
                self.assert_kept(_job(jd=text))

    def test_interview_rating_is_not_interview_format(self):
        self.assert_kept(_job(jd="薪资根据面试定级定薪"))

    def test_internship_signal_in_jd_is_not_internship_job(self):
        # 「实习转正通道」原本按「社招岗」保留；产品确认这类岗实质是实习入口，
        # 已移到 TestMustExclude.test_internship_commitment_in_jd。
        for text in ["非实习岗，社招", "提供实习证明", "实习期薪资 6K",
                     "实习生导师带教", "带实习生", "实习、课程、竞赛、个人项目均可",
                     "本岗位同时还招聘AI agent实习生岗位，实习周期不少于3个月"]:
            with self.subTest(text=text):
                self.assert_kept(_job(title="大模型 Agent 开发工程师", jd=text))

    def test_intern_mentor_titles_are_full_time_roles(self):
        for title in ["实习生导师", "实习生管理岗", "实习生带教", "Agent开发-带实习生"]:
            with self.subTest(title=title):
                self.assert_kept(_job(title=title))

    def test_internship_pay_phrase_in_title_is_not_role(self):
        self.assert_kept(_job(title="Agent开发工程师（实习期薪资 8K）"))

    def test_negated_internship_title(self):
        for title in ["非实习岗", "不招实习生", "社招-非实习"]:
            with self.subTest(title=title):
                self.assert_kept(_job(title=title))

    def test_welfare_mentions_are_ignored_for_internship(self):
        self.assert_kept(_job(title="Agent开发工程师",
                              welfare=["提供实习证明", "实习期薪资"]))

    def test_jd_intern_mention_without_commitment(self):
        for text in ["标准职责（不招聘实习岗）",
                     "本岗位同时还招聘AI agent实习生岗位，实习周期不少于3个月",
                     # 限定写在命中点后面，也要挡住
                     "实习周期不少于3个月，本岗位同时还招聘实习生",
                     "要求至少一个完整项目经历（实习、课程、竞赛、个人项目均可）",
                     "可立即实习的优先考虑"]:
            with self.subTest(text=text):
                self.assert_kept(_job(title="agent开发", jd=text))


class TestSplitCached(unittest.TestCase):
    def test_excluded_items_keep_dispatch_but_not_model_cache(self):
        from src.ai.pipeline import _split_cached

        items = [
            {"encrypt_job_id": "a", "verdict": "apply", "dispatch": "done"},
            {"encrypt_job_id": "b", "verdict": "skip", "excluded_by": "internship",
             "dispatch": "done", "dispatch_at": "2026-11-24T10:00:00"},
        ]
        old_by_eid, cached = _split_cached(items)
        self.assertIn("a", cached)
        self.assertNotIn("b", cached)
        self.assertEqual(old_by_eid["b"]["dispatch"], "done")
        self.assertEqual(old_by_eid["b"]["dispatch_at"], "2026-11-24T10:00:00")


class TestPlanReadsExclusion(unittest.TestCase):
    def test_load_plan_tolerates_exclusion_fields(self):
        import json
        import os
        import tempfile

        from src.ai.pipeline import load_plan

        plan = {"items": [{
            "index": 1, "encrypt_job_id": "x", "status": "skip", "verdict": "skip",
            "skip_reason": "实习岗位：agent应用开发实习生",
            "excluded_by": "internship", "exclude_field": "title",
            "exclude_snippet": "agent应用开发实习生",
        }]}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "ai_plan.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False)
            got = load_plan(path)
        self.assertEqual(got["items"][0]["excluded_by"], "internship")


class TestExclusionResult(unittest.TestCase):
    def test_result_is_skip_and_traceable(self):
        hit = check_job(_job(title="(线下面试）Java开发-agent方向"))
        res = exclusion_result(hit)
        self.assertEqual(res["verdict"], "skip")
        self.assertEqual(res["score"], 0)
        self.assertEqual(res["greeting"], "")
        self.assertEqual(res["excluded_by"], "interview_offline")
        self.assertEqual(res["exclude_field"], "title")
        self.assertIn("线下面试", res["exclude_snippet"])
        self.assertIn("要求线下面试", res["skip_reason"])


if __name__ == "__main__":
    unittest.main()
