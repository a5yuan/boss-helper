"""平台注册表的发现规则。"""
import unittest

from src.adapters import registry
from src.adapters.boss import BossAdapter
from src.adapters.registry import create_adapter


class TestAutoDiscovery(unittest.TestCase):
    def test_default_platform_uses_same_path(self):
        adapter = create_adapter()
        self.assertIsInstance(adapter, BossAdapter)

    def test_boss_registers_on_import(self):
        self.assertIs(registry._FACTORIES.get("boss"), BossAdapter)

    def test_unknown_platform_raises(self):
        with self.assertRaises(ValueError):
            create_adapter("definitely_missing_platform")


if __name__ == "__main__":
    unittest.main()
