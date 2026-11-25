"""统计页的硬约束：不引图表库、全手写 SVG、草稿与已送达要有图例。

页面本身没有自动化渲染测试（那需要浏览器），但这些约束可以用源码扫描守住。
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "server", "stats.html")

# ADR-0002：手写 SVG，不引图表库
BANNED_LIBS = ("chart.js", "echarts", "uplot", "d3.js", "apexcharts", "plotly",
               "highcharts", "recharts", "visx", "nivo", "billboard.js")


def _read_page() -> str:
    with open(PAGE, "r", encoding="utf-8") as f:
        return f.read()


class TestStatsPageConstraints(unittest.TestCase):
    def setUp(self):
        self.src = _read_page()

    def test_no_chart_library(self):
        """ADR-0002：三种图全部手写 SVG，不引任何图表库。"""
        low = self.src.lower()
        for lib in BANNED_LIBS:
            self.assertNotIn(lib, low, f"统计页不应引入图表库: {lib}")

    def test_no_external_script_or_stylesheet(self):
        """页面不引外部资源——跟 /review 一个路子，纯静态。"""
        self.assertNotIn("<script src=", self.src)
        self.assertNotIn('<link rel="stylesheet"', self.src)

    def test_draws_svg_not_canvas(self):
        """图表用 SVG，不用 canvas。"""
        self.assertIn("createElementNS('http://www.w3.org/2000/svg'", self.src)
        self.assertNotIn("<canvas", self.src)

    def test_has_three_charts(self):
        """柱状图、折线图、热力图三个容器都在。"""
        for target in ('id="bar"', 'id="line"', 'id="heat"'):
            self.assertIn(target, self.src, f"缺少图表容器 {target}")

    def test_legend_distinguishes_submitted_and_drafted(self):
        """ADR-0003：草稿与已送达要有图例，不能只靠颜色区分。"""
        self.assertIn("submitted", self.src)
        self.assertIn("drafted", self.src)
        # 图例里两个都要有文字说明
        self.assertIn("已送达", self.src)
        self.assertIn("仅草稿", self.src)
        # 草稿还有虚线描边，不止靠颜色
        self.assertIn("stroke-dasharray", self.src)

    def test_empty_state_keeps_axes(self):
        """空数据时保留坐标轴和网格，只显示「暂无数据」。"""
        self.assertIn("暂无数据", self.src)
        self.assertIn("emptyNote", self.src)

    def test_range_options_are_exactly_five(self):
        """时间区域：今天 / 24小时 / 7天 / 30天 / 全部，不做自定义日期。"""
        found = re.findall(r'data-r="([^"]+)"', self.src)
        self.assertEqual(found, ["today", "24h", "7d", "30d", "all"])
        # 没有日期输入框
        self.assertNotIn('type="date"', self.src)

    def test_platform_select_is_single_choice(self):
        """平台单选 + 全部。"""
        self.assertIn('id="platform"', self.src)
        self.assertNotIn('type="radio"', self.src)   # 用下拉，不用单选按钮
        self.assertNotIn('type="checkbox"', self.src)

    def test_reuses_review_page_theme_variables(self):
        """主题跟 /review 一致：同一套 CSS 变量。"""
        with open(os.path.join(ROOT, "server", "review.html"), "r", encoding="utf-8") as f:
            review = f.read()
        for var in ("--bg", "--panel", "--panel2", "--line", "--fg", "--dim", "--accent"):
            self.assertIn(f"{var}:", self.src, f"统计页缺少主题变量 {var}")
            self.assertIn(f"{var}:", review, f"复核页缺少主题变量 {var}")

    def test_bucketing_is_server_side(self):
        """分桶在服务端做，前端不自己算。"""
        self.assertIn("/api/stats?range=", self.src)
        # 前端不按时间戳分桶
        self.assertNotIn("getHours()", self.src)
        self.assertNotIn("setHours(", self.src)


class TestStatsPageRoute(unittest.TestCase):
    def test_page_route_returns_html(self):
        from server import app as server_app
        resp = server_app.api_stats_page()
        self.assertEqual(resp.status_code, 200)
        body = resp.body.decode("utf-8")
        self.assertIn("投递统计", body)
        self.assertIn("/api/stats", body)


if __name__ == "__main__":
    unittest.main()
