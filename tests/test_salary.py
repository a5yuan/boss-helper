"""薪资解析与区间匹配的单元测试（纯逻辑，无浏览器依赖）。

运行：
    .venv/Scripts/python -m unittest discover -s tests -v
"""
import unittest

from src.utils.salary import parse_salary, salary_in_range


class TestParseSalary(unittest.TestCase):
    def test_k_range(self):
        self.assertEqual(parse_salary("15-22K"), (15.0, 22.0))

    def test_k_range_with_annual_suffix(self):
        self.assertEqual(parse_salary("20-40K·16薪"), (20.0, 40.0))

    def test_mixed_units(self):
        # 文档承诺支持「8千-1.2万」，两端单位不同
        self.assertEqual(parse_salary("8千-1.2万"), (8.0, 12.0))

    def test_wan_range(self):
        self.assertEqual(parse_salary("1.2万-2万"), (12.0, 20.0))

    def test_qian_range(self):
        self.assertEqual(parse_salary("10-20千"), (10.0, 20.0))

    def test_single_k(self):
        self.assertEqual(parse_salary("15K"), (15.0, 15.0))

    def test_negotiable_is_unparseable(self):
        self.assertEqual(parse_salary("面议"), (None, None))

    def test_daily_wage_is_unparseable(self):
        self.assertEqual(parse_salary("300-500元/天"), (None, None))

    def test_empty(self):
        self.assertEqual(parse_salary(""), (None, None))
        self.assertEqual(parse_salary(None), (None, None))


class TestSalaryInRange(unittest.TestCase):
    def test_overlap(self):
        self.assertTrue(salary_in_range("15-22K", 20, 30))

    def test_below_requested_range(self):
        self.assertFalse(salary_in_range("15-22K", 30, 40))

    def test_above_requested_range(self):
        self.assertFalse(salary_in_range("35-45K", 20, 30))

    def test_unparseable_is_not_filtered(self):
        self.assertTrue(salary_in_range("面议", 20, 30))

    def test_no_bounds(self):
        self.assertTrue(salary_in_range("15-22K"))
        self.assertTrue(salary_in_range("15-22K", None, None))

    def test_one_sided_bound(self):
        self.assertTrue(salary_in_range("15-22K", 20, None))
        self.assertTrue(salary_in_range("15-22K", None, 20))
        self.assertFalse(salary_in_range("15-22K", 25, None))


if __name__ == "__main__":
    unittest.main()
