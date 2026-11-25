"""平台目录与按平台读取结果的接口。"""
import json
import os
import tempfile
import unittest
from unittest import mock

from server import app as server_app


def _write_jobs(directory: str, name: str, titles: list[str]) -> None:
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, name), "w", encoding="utf-8") as f:
        json.dump([{"title": t} for t in titles], f, ensure_ascii=False)


class TestPlatformCatalog(unittest.TestCase):
    def setUp(self):
        server_app._platform_cache = None

    def tearDown(self):
        server_app._platform_cache = None

    def test_catalog_discovers_registered_adapters(self):
        platforms = server_app.platform_catalog()
        names = [p["name"] for p in platforms]
        # 默认平台排第一，其余按名字排序
        self.assertEqual(names[0], "boss")
        self.assertIn("zhaopin", names)
        self.assertEqual(names[1:], sorted(names[1:]))

        display = {p["name"]: p["display_name"] for p in platforms}
        self.assertEqual(display["boss"], "BOSS 直聘")
        self.assertEqual(display["zhaopin"], "智联招聘")

    def test_hidden_adapter_is_not_user_selectable(self):
        """fake 只给测试用，不该出现在用户能选的平台列表里。"""
        names = [p["name"] for p in server_app.platform_catalog()]
        self.assertNotIn("fake", names)
        # 但适配器本身仍然可用（测试要能实例化）
        from src.adapters.registry import create_adapter
        self.assertEqual(create_adapter("fake").display_name, "假平台")

    def test_catalog_skips_modules_without_adapter(self):
        names = [p["name"] for p in server_app.platform_catalog()]
        self.assertNotIn("base", names)
        self.assertNotIn("registry", names)

    def test_api_platforms_shape(self):
        result = server_app.api_platforms()
        self.assertTrue(result["ok"])
        self.assertTrue(all({"name", "display_name"} <= set(p) for p in result["platforms"]))


class TestResultsByPlatform(unittest.TestCase):
    def test_platform_picks_that_platform_output_dir(self):
        with tempfile.TemporaryDirectory() as root:
            _write_jobs(os.path.join(root, "boss"), "jobs_20260101.json", ["老板岗"])
            _write_jobs(os.path.join(root, "fake"), "jobs_20260102.json", ["假平台岗"])

            def fake_config(browser_type="chrome", platform=None):
                return {"output_dir": os.path.join(root, platform or "boss")}

            with mock.patch.object(server_app, "get_config", side_effect=fake_config):
                res = server_app.api_results(platform="fake")
                legacy = server_app.api_results()

        self.assertEqual([j["title"] for j in res["jobs"]], ["假平台岗"])
        self.assertEqual(res["file"], "jobs_20260102.json")
        self.assertEqual(res["files"], ["jobs_20260102.json"])
        # 不传 platform 时仍是默认平台
        self.assertEqual([j["title"] for j in legacy["jobs"]], ["老板岗"])

    def test_date_filter_with_platform(self):
        with tempfile.TemporaryDirectory() as root:
            _write_jobs(os.path.join(root, "fake"), "jobs_20260101.json", ["一"])
            _write_jobs(os.path.join(root, "fake"), "jobs_20260109.json", ["九"])

            def fake_config(browser_type="chrome", platform=None):
                return {"output_dir": os.path.join(root, platform or "boss")}

            with mock.patch.object(server_app, "get_config", side_effect=fake_config):
                res = server_app.api_results(date="20260101", platform="fake")

        self.assertEqual(res["file"], "jobs_20260101.json")
        self.assertEqual([j["title"] for j in res["jobs"]], ["一"])

    def test_output_dir_still_wins_without_platform(self):
        with tempfile.TemporaryDirectory() as root:
            _write_jobs(root, "jobs_1.json", ["旧调用"])

            def fake_config(browser_type="chrome", platform=None):
                raise AssertionError("不传 platform 且传 output_dir 时不该再解析平台")

            with mock.patch.object(server_app, "get_config", side_effect=fake_config):
                res = server_app.api_results(output_dir=root)

        self.assertEqual([j["title"] for j in res["jobs"]], ["旧调用"])


if __name__ == "__main__":
    unittest.main()
