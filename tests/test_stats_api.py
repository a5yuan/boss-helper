"""统计聚合与 /api/stats：区间过滤、平台过滤、分桶粒度。"""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from server import app as server_app
from src.storage.stats import aggregate, bucket_key, window


def _ev(ts, event="apply", platform="boss", **fields):
    rec = {"ts": ts, "platform": platform, "event": event}
    rec.update(fields)
    return rec


NOW = datetime(2026, 11, 25, 15, 30, 0)


class TestWindow(unittest.TestCase):
    def test_today_buckets_by_hour(self):
        since, gran, keys = window("today", NOW)
        self.assertEqual(gran, "hour")
        self.assertEqual(len(keys), 24)
        self.assertTrue(keys[0].endswith("T00"))
        self.assertTrue(keys[-1].endswith("T23"))

    def test_24h_buckets_by_hour(self):
        since, gran, keys = window("24h", NOW)
        self.assertEqual(gran, "hour")
        self.assertEqual(len(keys), 24)
        self.assertTrue(keys[0].endswith("T16"))

    def test_7d_buckets_by_day(self):
        since, gran, keys = window("7d", NOW)
        self.assertEqual(gran, "day")
        self.assertEqual(len(keys), 7)
        self.assertEqual(keys[0], "2026-11-19")
        self.assertEqual(keys[-1], "2026-11-25")

    def test_30d_buckets_by_day(self):
        since, gran, keys = window("30d", NOW)
        self.assertEqual(gran, "day")
        self.assertEqual(len(keys), 30)
        self.assertEqual(keys[0], "2026-10-27")

    def test_all_uses_earliest_event(self):
        earliest = datetime(2026, 11, 1, 8, 0, 0)
        since, gran, keys = window("all", NOW, earliest)
        self.assertEqual(gran, "day")
        self.assertEqual(keys[0], "2026-11-01")
        self.assertEqual(keys[-1], "2026-11-25")

    def test_all_without_events_has_no_buckets(self):
        since, gran, keys = window("all", NOW, None)
        self.assertEqual(keys, [])
        self.assertIsNone(since)

    def test_unknown_range_falls_back_to_7d(self):
        _, gran, keys = window("bogus", NOW)
        self.assertEqual(gran, "day")
        self.assertEqual(len(keys), 7)


class TestBucketKey(unittest.TestCase):
    def test_hour_and_day(self):
        ts = datetime(2026, 11, 25, 14, 35, 12)
        self.assertEqual(bucket_key(ts, "hour"), "2026-11-25T14")
        self.assertEqual(bucket_key(ts, "day"), "2026-11-25")


class TestAggregate(unittest.TestCase):
    def test_drafted_not_counted_as_submitted(self):
        """ADR-0003：草稿对方收不到，不能混进总投递数。"""
        rows = [
            _ev("2026-11-25T10:00:00", status="submitted", duration_ms=1000),
            _ev("2026-11-25T11:00:00", status="drafted", duration_ms=2000),
        ]
        out = aggregate(rows, range_key="7d", now=NOW)
        self.assertEqual(out["totals"]["submitted"], 1)
        self.assertEqual(out["totals"]["drafted"], 1)
        self.assertEqual(out["totals"]["attempts"], 2)

    def test_gate_skips_excluded_from_success_rate_denominator(self):
        """闸门拦下的从没碰过平台，不算失败。"""
        rows = [
            _ev("2026-11-25T10:00:00", status="submitted"),
            _ev("2026-11-25T10:01:00", status="skipped", reason="skipped: daily_limit"),
            _ev("2026-11-25T10:02:00", status="skipped", reason="skipped: already_applied"),
            _ev("2026-11-25T10:03:00", status="skipped", reason="apply_unconfirmed"),
        ]
        out = aggregate(rows, range_key="7d", now=NOW)
        self.assertEqual(out["totals"]["attempts"], 2)   # submitted + 真的没成的那次
        self.assertEqual(out["totals"]["failed"], 1)
        self.assertEqual(out["totals"]["success_rate"], 0.5)

    def test_buckets_group_by_hour_for_today(self):
        rows = [
            _ev("2026-11-25T10:05:00", status="submitted"),
            _ev("2026-11-25T10:55:00", status="submitted"),
            _ev("2026-11-25T14:05:00", status="drafted"),
        ]
        out = aggregate(rows, range_key="today", now=NOW)
        self.assertEqual(out["granularity"], "hour")
        by = {b["key"]: b for b in out["buckets"]}
        self.assertEqual(by["2026-11-25T10"]["submitted"], 2)
        self.assertEqual(by["2026-11-25T14"]["drafted"], 1)
        self.assertEqual(len(out["buckets"]), 24)

    def test_buckets_group_by_day_for_7d(self):
        rows = [
            _ev("2026-11-20T10:05:00", status="submitted"),
            _ev("2026-11-20T23:05:00", status="submitted"),
            _ev("2026-11-21T10:05:00", status="drafted"),
        ]
        out = aggregate(rows, range_key="7d", now=NOW)
        self.assertEqual(out["granularity"], "day")
        by = {b["key"]: b for b in out["buckets"]}
        self.assertEqual(by["2026-11-20"]["submitted"], 2)
        self.assertEqual(by["2026-11-21"]["drafted"], 1)
        self.assertEqual(len(out["buckets"]), 7)

    def test_events_outside_window_are_dropped(self):
        rows = [
            _ev("2026-01-01T10:00:00", status="submitted"),
            _ev("2026-11-25T10:00:00", status="submitted"),
        ]
        out = aggregate(rows, range_key="7d", now=NOW)
        self.assertEqual(out["totals"]["submitted"], 1)

    def test_platform_filter(self):
        rows = [
            _ev("2026-11-25T10:00:00", status="submitted", platform="boss"),
            _ev("2026-11-25T11:00:00", status="submitted", platform="zhaopin"),
        ]
        self.assertEqual(aggregate(rows, range_key="7d", platform="boss", now=NOW)["totals"]["submitted"], 1)
        self.assertEqual(aggregate(rows, range_key="7d", platform="zhaopin", now=NOW)["totals"]["submitted"], 1)
        self.assertEqual(aggregate(rows, range_key="7d", platform="all", now=NOW)["totals"]["submitted"], 2)

    def test_bucket_by_platform_split(self):
        rows = [
            _ev("2026-11-25T10:00:00", status="submitted", platform="boss"),
            _ev("2026-11-25T10:00:00", status="drafted", platform="zhaopin"),
        ]
        out = aggregate(rows, range_key="7d", now=NOW)
        b = {x["key"]: x for x in out["buckets"]}["2026-11-25"]
        self.assertEqual(b["by_platform"]["boss"]["submitted"], 1)
        self.assertEqual(b["by_platform"]["zhaopin"]["drafted"], 1)

    def test_today_count(self):
        rows = [
            _ev("2026-11-25T10:00:00", status="submitted"),
            _ev("2026-11-24T10:00:00", status="submitted"),
        ]
        out = aggregate(rows, range_key="7d", now=NOW)
        self.assertEqual(out["totals"]["today_submitted"], 1)

    def test_avg_duration(self):
        rows = [
            _ev("2026-11-25T10:00:00", status="submitted", duration_ms=1000),
            _ev("2026-11-25T11:00:00", status="submitted", duration_ms=3000),
        ]
        out = aggregate(rows, range_key="7d", now=NOW)
        self.assertEqual(out["totals"]["avg_duration_ms"], 2000)

    def test_ai_call_tokens_summed(self):
        rows = [
            _ev("2026-11-25T10:00:00", event="ai_call", kind="screen",
                model="m", tokens_in=100, tokens_out=50, duration_ms=800),
            _ev("2026-11-25T11:00:00", event="ai_call", kind="screen",
                model="m", tokens_in=200, tokens_out=60, duration_ms=900),
        ]
        out = aggregate(rows, range_key="7d", now=NOW)
        self.assertEqual(out["totals"]["ai_calls"], 2)
        self.assertEqual(out["totals"]["tokens_in"], 300)
        self.assertEqual(out["totals"]["tokens_out"], 110)
        b = {x["key"]: x for x in out["buckets"]}["2026-11-25"]
        self.assertEqual(b["ai_calls"], 2)
        self.assertEqual(b["ai_duration_ms"], 1700)
        # 分桶也要带 token，折线图才有东西画（ADR-0004）
        self.assertEqual(b["tokens_in"], 300)
        self.assertEqual(b["tokens_out"], 110)
        self.assertGreater(b["tokens_in"] + b["tokens_out"], 0)
        self.assertEqual(
            sum(x["tokens_in"] + x["tokens_out"] for x in out["buckets"]),
            out["totals"]["tokens_in"] + out["totals"]["tokens_out"])

    def test_cost_is_none_without_pricing(self):
        rows = [_ev("2026-11-25T10:00:00", event="ai_call", model="m",
                    tokens_in=100, tokens_out=50)]
        out = aggregate(rows, range_key="7d", now=NOW, pricing={})
        self.assertIsNone(out["totals"]["cost"])

    def test_cost_computed_with_pricing(self):
        rows = [_ev("2026-11-25T10:00:00", event="ai_call", model="m",
                    tokens_in=1000, tokens_out=500)]
        out = aggregate(rows, range_key="7d", now=NOW,
                        pricing={"m": {"input": 1.0, "output": 2.0}})
        # 1000/1000 * 1.0 + 500/1000 * 2.0 = 2.0
        self.assertAlmostEqual(out["totals"]["cost"], 2.0)

    def test_collect_and_screen_events_are_bucketed(self):
        """采集与筛选也要进桶：历史数据里它们才是绝大多数，折线图得有东西画。"""
        rows = [
            _ev("2026-11-25T10:00:00", event="collect", count=5),
            _ev("2026-11-25T11:00:00", event="screen", count=3, planned=1),
        ]
        out = aggregate(rows, range_key="7d", now=NOW)
        b = {x["key"]: x for x in out["buckets"]}["2026-11-25"]
        self.assertEqual(b["collects"], 1)
        self.assertEqual(b["screens"], 1)
        self.assertEqual(out["totals"]["collects"], 1)
        self.assertEqual(out["totals"]["screens"], 1)

    def test_heatmap_has_day_cells(self):
        rows = [_ev("2026-11-25T10:00:00", status="submitted")]
        out = aggregate(rows, range_key="all", now=NOW)
        cells = out["heatmap"]["cells"]
        self.assertTrue(cells)
        last = cells[-1]
        self.assertEqual(last["date"], "2026-11-25")
        self.assertEqual(last["submitted"], 1)

    def test_empty_events_gives_empty_buckets_but_keeps_axis(self):
        out = aggregate([], range_key="7d", now=NOW)
        self.assertEqual(len(out["buckets"]), 7)
        self.assertEqual(out["totals"]["submitted"], 0)
        self.assertIsNone(out["totals"]["success_rate"])
        # 空桶也要有 token 字段（0），前端不用判空
        for b in out["buckets"]:
            self.assertEqual(b["tokens_in"], 0)
            self.assertEqual(b["tokens_out"], 0)


class TestStatsApi(unittest.TestCase):
    def test_api_returns_aggregated_shape(self):
        rows = [
            _ev("2026-11-25T10:00:00", status="submitted", platform="boss"),
            _ev("2026-11-25T11:00:00", status="drafted", platform="boss"),
        ]
        with mock.patch("src.storage.events.load", return_value=rows):
            res = server_app.api_stats(range="7d", platform="all")
        self.assertTrue(res["ok"])
        self.assertEqual(res["range"], "7d")
        self.assertEqual(res["granularity"], "day")
        self.assertEqual(res["totals"]["submitted"], 1)
        self.assertEqual(res["totals"]["drafted"], 1)
        self.assertEqual(len(res["buckets"]), 7)

    def test_api_today_uses_hour_buckets(self):
        with mock.patch("src.storage.events.load", return_value=[]):
            res = server_app.api_stats(range="today", platform="all")
        self.assertEqual(res["granularity"], "hour")
        self.assertEqual(len(res["buckets"]), 24)

    def test_api_rejects_unknown_range_by_falling_back(self):
        with mock.patch("src.storage.events.load", return_value=[]):
            res = server_app.api_stats(range="bogus", platform="all")
        self.assertEqual(res["range"], "7d")

    def test_api_platform_filter(self):
        rows = [
            _ev("2026-11-25T10:00:00", status="submitted", platform="boss"),
            _ev("2026-11-25T11:00:00", status="submitted", platform="zhaopin"),
        ]
        with mock.patch("src.storage.events.load", return_value=rows):
            res = server_app.api_stats(range="7d", platform="zhaopin")
        self.assertEqual(res["totals"]["submitted"], 1)

    def test_api_returns_error_instead_of_raising(self):
        with mock.patch("src.storage.events.load", side_effect=OSError("挂了")):
            res = server_app.api_stats(range="7d", platform="all")
        self.assertTrue(res["ok"])
        self.assertEqual(res["totals"]["submitted"], 0)


if __name__ == "__main__":
    unittest.main()
