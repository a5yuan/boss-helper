"""城市列表归一化：同名去重、直辖市保留市级编码、全国置顶。"""
import unittest

from src.core.cities import NATIONAL_CITY, normalize_cities


class TestNormalizeCities(unittest.TestCase):
    def test_duplicate_labels_collapse_to_one(self):
        # BOSS 的 city.json 里直辖市有省级和市级两条，label 相同 code 不同
        raw = [
            {"label": "北京", "value": "101010000"},
            {"label": "北京", "value": "101010100"},
            {"label": "上海", "value": "101020000"},
            {"label": "上海", "value": "101020100"},
        ]
        out = normalize_cities(raw)
        labels = [it["label"] for it in out]
        self.assertEqual(labels.count("北京"), 1)
        self.assertEqual(labels.count("上海"), 1)

    def test_municipality_keeps_city_level_code(self):
        raw = [
            {"label": "北京", "value": "101010000"},   # 省级
            {"label": "北京", "value": "101010100"},   # 市级
        ]
        out = normalize_cities(raw)
        self.assertEqual([it for it in out if it["label"] == "北京"][0]["value"],
                         "101010100")

    def test_city_level_wins_even_when_it_comes_later(self):
        raw = [
            {"label": "天津", "value": "101030100"},   # 市级先出现
            {"label": "天津", "value": "101030000"},   # 省级后出现
        ]
        out = normalize_cities(raw)
        self.assertEqual([it for it in out if it["label"] == "天津"][0]["value"],
                         "101030100")

    def test_national_is_added_at_front_when_missing(self):
        raw = [{"label": "杭州", "value": "101210100"}]
        out = normalize_cities(raw)
        self.assertEqual(out[0], NATIONAL_CITY)
        self.assertEqual(out[1]["label"], "杭州")

    def test_national_existing_entry_is_moved_to_front(self):
        raw = [
            {"label": "杭州", "value": "101210100"},
            {"label": "全国", "value": "100010000"},
        ]
        out = normalize_cities(raw)
        self.assertEqual(out[0]["label"], "全国")
        self.assertEqual(len([it for it in out if it["label"] == "全国"]), 1)

    def test_bad_entries_are_dropped_not_crashed(self):
        raw = [None, {}, {"label": "", "value": "1"}, {"label": "杭州"},
               {"label": "杭州", "value": "101210100"}]
        out = normalize_cities(raw)
        self.assertEqual([it["label"] for it in out if it["label"] != "全国"],
                         ["杭州"])

    def test_order_is_preserved(self):
        raw = [{"label": n, "value": str(101000000 + i * 100)}
               for i, n in enumerate(["杭州", "宁波", "温州"])]
        out = normalize_cities(raw)
        self.assertEqual([it["label"] for it in out][1:], ["杭州", "宁波", "温州"])


if __name__ == "__main__":
    unittest.main()
