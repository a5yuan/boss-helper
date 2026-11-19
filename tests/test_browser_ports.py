"""端口发现规则：默认平台可扫标准端口，二级平台只能读自己的端口文件。"""
import os
import tempfile
import unittest
from unittest import mock

from src.core.browser import BrowserManager


class TestPortDiscovery(unittest.TestCase):
    def test_secondary_platform_reads_saved_port_only(self):
        with tempfile.TemporaryDirectory() as td:
            port_file = os.path.join(td, ".cdp_port_fake_edge")
            with open(port_file, "w") as f:
                f.write("45678")
            bm = BrowserManager(config={
                "port_files": [port_file], "allow_port_scan": False,
            })
            with mock.patch("src.core.browser.requests.get",
                            return_value=mock.Mock(ok=True)) as get:
                self.assertTrue(bm.try_connect_existing())

        urls = [call.args[0] for call in get.call_args_list]
        self.assertEqual(len(urls), 1)
        self.assertIn("45678", urls[0])
        self.assertEqual(bm.port, 45678)

    def test_secondary_platform_does_not_scan_when_port_dead(self):
        with tempfile.TemporaryDirectory() as td:
            port_file = os.path.join(td, ".cdp_port_fake_edge")
            with open(port_file, "w") as f:
                f.write("45678")
            bm = BrowserManager(config={
                "port_files": [port_file], "allow_port_scan": False,
            })
            with mock.patch("src.core.browser.requests.get",
                            return_value=mock.Mock(ok=False)) as get:
                self.assertFalse(bm.try_connect_existing())

        self.assertEqual(len(get.call_args_list), 1)

    def test_default_platform_may_scan_standard_ports(self):
        with tempfile.TemporaryDirectory() as td:
            bm = BrowserManager(config={
                "port_files": [os.path.join(td, "missing")],
                "allow_port_scan": True,
            })

            def fake_get(url, timeout=0):
                return mock.Mock(ok=":9224/" in url)

            with mock.patch("src.core.browser.requests.get", side_effect=fake_get):
                self.assertTrue(bm.try_connect_existing())
        self.assertEqual(bm.port, 9224)


if __name__ == "__main__":
    unittest.main()
