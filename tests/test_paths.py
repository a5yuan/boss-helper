"""平台 + 浏览器 的运行路径生成。"""
import os
import unittest

from src.config import PROJECT_DIR, get_config


class TestPlatformPaths(unittest.TestCase):
    def test_boss_keeps_legacy_profile_and_port(self):
        cfg = get_config("edge", platform="boss")
        self.assertEqual(cfg["profile_dir"],
                         os.path.join(PROJECT_DIR, "profiles", "edge_profile"))
        self.assertEqual(cfg["port_file"],
                         os.path.join(PROJECT_DIR, ".cdp_port_boss_edge"))
        self.assertIn(os.path.join(PROJECT_DIR, ".cdp_port_edge"),
                      cfg["port_files"])
        self.assertEqual(cfg["output_dir"],
                         os.path.join(PROJECT_DIR, "output", "boss"))
        self.assertEqual(cfg["tracking_file"],
                         os.path.join(PROJECT_DIR, "output", "boss", "tracking.json"))
        self.assertEqual(cfg["legacy_tracking_file"],
                         os.path.join(PROJECT_DIR, "output", "tracking.json"))
        self.assertTrue(cfg["allow_port_scan"])

    def test_secondary_platform_is_isolated(self):
        cfg = get_config("chrome", platform="fake")
        self.assertEqual(cfg["profile_dir"],
                         os.path.join(PROJECT_DIR, "profiles", "fake", "chrome"))
        self.assertEqual(cfg["port_file"],
                         os.path.join(PROJECT_DIR, ".cdp_port_fake_chrome"))
        self.assertEqual(cfg["port_files"], [cfg["port_file"]])
        self.assertEqual(cfg["output_dir"],
                         os.path.join(PROJECT_DIR, "output", "fake"))
        self.assertEqual(cfg["tracking_file"],
                         os.path.join(PROJECT_DIR, "output", "fake", "tracking.json"))
        self.assertIsNone(cfg["legacy_tracking_file"])
        self.assertFalse(cfg["allow_port_scan"])

    def test_default_platform_is_boss(self):
        cfg = get_config("chrome")
        self.assertEqual(cfg["platform"], "boss")
        self.assertEqual(cfg["output_dir"],
                         os.path.join(PROJECT_DIR, "output", "boss"))


if __name__ == "__main__":
    unittest.main()
