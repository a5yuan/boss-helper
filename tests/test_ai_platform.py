"""AI 筛选与计划读写按平台隔离：路径解析、筛选落盘、招呼语保存。"""
import json
import os
import tempfile
import unittest
from unittest import mock

from server import app as server_app


def _fake_config(root):
    def config(browser_type="chrome", platform=None):
        return {"output_dir": os.path.join(root, platform or "boss")}
    return config


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


class TestPlanPath(unittest.TestCase):
    def test_platform_selects_that_output_dir(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(server_app, "get_config", side_effect=_fake_config(root)):
                fake2 = server_app._ai_plan_path("jobs_x.json", "fake2")
                default = server_app._ai_plan_path("jobs_x.json")
        self.assertEqual(fake2, os.path.join(root, "fake2", "ai_plan_x.json"))
        self.assertEqual(default, os.path.join(root, "boss", "ai_plan_x.json"))


class TestPlanReadByPlatform(unittest.TestCase):
    def test_reads_plan_from_requested_platform(self):
        with tempfile.TemporaryDirectory() as root:
            _write_json(os.path.join(root, "fake2", "ai_plan_x.json"),
                        {"items": [{"encrypt_job_id": "e1"}], "summary": {"total": 1}})
            with mock.patch.object(server_app, "get_config", side_effect=_fake_config(root)):
                hit = server_app.api_ai_plan(file="jobs_x.json", platform="fake2")
                miss = server_app.api_ai_plan(file="jobs_x.json")
        self.assertTrue(hit["ok"])
        self.assertTrue(hit["exists"])
        self.assertEqual([i["encrypt_job_id"] for i in hit["items"]], ["e1"])
        # 不传 platform 仍读默认平台，不会串到 fake2
        self.assertTrue(miss["ok"])
        self.assertFalse(miss["exists"])


class TestScreenByPlatform(unittest.TestCase):
    def test_screen_resolves_source_and_writes_plan_under_platform(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "fake2", "jobs_x.json")
            _write_json(src, [{"title": "假平台岗位", "platform": "fake2"}])
            seen = {}

            def fake_build(source_path, **kwargs):
                from src.ai.pipeline import plan_path_for
                seen["src"] = source_path
                plan = {"items": [{"encrypt_job_id": "e1", "status": "planned"}],
                        "summary": {"total": 1, "planned": 1}}
                _write_json(plan_path_for(source_path), plan)
                return plan

            with mock.patch.object(server_app, "get_config", side_effect=_fake_config(root)), \
                    mock.patch("src.ai.pipeline.build_plan", side_effect=fake_build), \
                    mock.patch.object(server_app, "session") as sess:
                sess.running = False
                res = server_app.api_ai_screen(server_app.AiScreenBody(
                    file="jobs_x.json", platform="fake2"))

            self.assertTrue(res["ok"])
            self.assertEqual(seen["src"], src)
            self.assertTrue(os.path.exists(os.path.join(root, "fake2", "ai_plan_x.json")))
            self.assertFalse(os.path.exists(os.path.join(root, "boss", "ai_plan_x.json")))
            self.assertEqual(res["summary"]["planned"], 1)


class TestGreetingSaveByPlatform(unittest.TestCase):
    def test_saves_into_requested_platform_plan(self):
        with tempfile.TemporaryDirectory() as root:
            plan_path = os.path.join(root, "fake2", "ai_plan_x.json")
            _write_json(plan_path, {"items": [{"encrypt_job_id": "e1", "greeting": "",
                                               "status": "skip"}],
                                    "summary": {}})
            with mock.patch.object(server_app, "get_config", side_effect=_fake_config(root)):
                res = server_app.api_ai_greeting(server_app.AiGreetingBody(
                    file="jobs_x.json", encrypt_job_id="e1",
                    greeting="您好", platform="fake2"))
            with open(plan_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

        self.assertTrue(res["ok"])
        self.assertEqual(res["item"]["greeting"], "您好")
        self.assertEqual(saved["items"][0]["status"], "planned")


if __name__ == "__main__":
    unittest.main()
