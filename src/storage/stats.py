"""投递统计的聚合：把事件流按时间与平台聚合成页面要的数据。

分桶在服务端做完，前端只负责画图（ADR-0002）。

口径约定（页面上要能对得上，所以写在这里而不是散在各处）：

- **总投递数**只算 ``submitted``。BOSS 的 ``drafted`` 对方收不到，
  混进去数字会涨但没一家公司收到简历（ADR-0003）。
- **成功率** = 成功完成的投递动作 / 真正动过手的投递动作。
  闸门拦下的（``skipped: daily_limit`` / ``already_applied`` /
  ``unsupported:*``）从没碰过平台，不进分母——它们不是失败。
- **AI 花费**需要单价表。没配 ``ai.pricing`` 就返回 ``None``，
  页面显示 token 数而不是编一个金额出来。
"""
import os
from datetime import datetime, timedelta

from src.config import load_ai_config

RANGES = ("today", "24h", "7d", "30d", "all")

# 日历热力图最多回看多少天（GitHub 那种一年的格子）
HEATMAP_MAX_DAYS = 182

# 全部历史时的分桶上限，避免早年数据把柱子拉成一条线
ALL_MAX_BUCKETS = 400


def _parse_ts(value) -> datetime | None:
    """事件 ts 解析。坏时间戳返回 None（不当成 1970 年）。"""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def bucket_key(ts: datetime, granularity: str) -> str:
    """把时间点归到桶里。小时桶是 ``2026-11-25T14``，天桶是 ``2026-11-25``。"""
    if granularity == "hour":
        return ts.strftime("%Y-%m-%dT%H")
    return ts.strftime("%Y-%m-%d")


def _bucket_label(key: str, granularity: str) -> str:
    """桶的显示标签。小时桶只显示「14时」，天桶显示「11-25」。"""
    if granularity == "hour":
        return f"{key[11:]}时"
    return key[5:]


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _floor_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def window(range_key: str, now: datetime | None = None,
           earliest: datetime | None = None) -> tuple:
    """算出时间窗口与分桶。

    返回 ``(since, granularity, keys)``：

    - ``since`` 是 ISO 字符串，给 ``events.load(since=...)`` 用；
    - ``granularity`` 是 ``hour`` 或 ``day``；
    - ``keys`` 是有序的桶键列表（``all`` 且没有数据时为空）。
    """
    now = now or datetime.now()
    if range_key == "today":
        start = _floor_hour(now).replace(hour=0)
        keys = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H") for i in range(24)]
        return start.isoformat(timespec="seconds"), "hour", keys
    if range_key == "24h":
        start = _floor_hour(now - timedelta(hours=23))
        keys = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H") for i in range(24)]
        return start.isoformat(timespec="seconds"), "hour", keys
    if range_key == "7d":
        start = _floor_day(now - timedelta(days=6))
        keys = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        return start.isoformat(timespec="seconds"), "day", keys
    if range_key == "30d":
        start = _floor_day(now - timedelta(days=29))
        keys = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
        return start.isoformat(timespec="seconds"), "day", keys
    if range_key == "all":
        if earliest is None:
            return None, "day", []
        start = _floor_day(earliest)
        end = _floor_day(now)
        span = (end - start).days + 1
        if span > ALL_MAX_BUCKETS:
            start = end - timedelta(days=ALL_MAX_BUCKETS - 1)
            span = ALL_MAX_BUCKETS
        keys = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(span)]
        return start.isoformat(timespec="seconds"), "day", keys
    # 未知区间按 7 天处理，别静默返回全量
    return window("7d", now, earliest)


def _is_gate_skip(event: dict) -> bool:
    """这次「跳过」是闸门拦下的，还是真的动手了但没成。

    闸门拦下的从没碰过平台，不该算进成功率的分母。
    """
    reason = str(event.get("reason") or "")
    return reason.startswith("skipped: ") or reason.startswith("unsupported:")


def _empty_bucket() -> dict:
    return {"submitted": 0, "drafted": 0, "skipped": 0, "failed": 0,
            "by_platform": {}}


def aggregate(events: list, range_key: str = "7d", platform: str = "all",
              now: datetime | None = None, pricing: dict | None = None) -> dict:
    """把事件聚合成页面要的数据。

    ``events`` 是 ``events.load()`` 的结果。``platform`` 为 ``all`` 表示不限平台。
    参数叫 ``range_key`` 而不是 ``range``——``range`` 会盖掉内置函数。
    """
    now = now or datetime.now()
    if range_key not in RANGES:
        range_key = "7d"

    rows = [e for e in events if isinstance(e, dict)]
    if platform and platform != "all":
        rows = [e for e in rows if str(e.get("platform") or "") == platform]

    stamps = [t for t in (_parse_ts(e.get("ts")) for e in rows) if t]
    earliest = min(stamps) if stamps else None

    since, granularity, keys = window(range_key, now, earliest)
    if since:
        cutoff = _parse_ts(since)
        rows = [e for e in rows
                if (t := _parse_ts(e.get("ts"))) is not None and t >= cutoff]

    bucket_map = {k: _empty_bucket() for k in keys}
    platforms: list[str] = []
    totals = {"submitted": 0, "drafted": 0, "skipped": 0, "failed": 0,
              "attempts": 0, "ai_calls": 0, "tokens_in": 0, "tokens_out": 0,
              "collects": 0, "screens": 0}
    durations: list[int] = []
    today = _floor_day(now)
    today_submitted = 0
    today_drafted = 0

    for e in rows:
        ev = str(e.get("event") or "")
        plat = str(e.get("platform") or "")
        if plat and plat not in platforms:
            platforms.append(plat)
        ts = _parse_ts(e.get("ts"))
        if ts is None:
            continue
        key = bucket_key(ts, granularity)

        if ev == "apply":
            status = str(e.get("status") or "")
            gate_skip = _is_gate_skip(e)
            if status == "submitted":
                totals["submitted"] += 1
                if _floor_day(ts) == today:
                    today_submitted += 1
            elif status == "drafted":
                totals["drafted"] += 1
                if _floor_day(ts) == today:
                    today_drafted += 1
            elif status == "skipped":
                totals["skipped"] += 1
                if not gate_skip:
                    totals["failed"] += 1

            # 成功率的分母：真的动过手的（成功 + 草稿 + 动手但没成）。
            # 闸门拦下的从没碰过平台，不算失败。
            if status in ("submitted", "drafted") or (status == "skipped" and not gate_skip):
                totals["attempts"] += 1

            dur = e.get("duration_ms")
            if isinstance(dur, (int, float)):
                durations.append(int(dur))

            if key in bucket_map:
                b = bucket_map[key]
                if status in ("submitted", "drafted", "skipped"):
                    b[status] += 1
                pb = b["by_platform"].setdefault(
                    plat, {"submitted": 0, "drafted": 0, "skipped": 0})
                if status in pb:
                    pb[status] += 1

        elif ev == "ai_call":
            totals["ai_calls"] += 1
            for field, key_name in (("tokens_in", "tokens_in"),
                                    ("tokens_out", "tokens_out")):
                val = e.get(field)
                if isinstance(val, (int, float)):
                    totals[key_name] += int(val)
            if key in bucket_map:
                bucket_map[key]["ai_calls"] = bucket_map[key].get("ai_calls", 0) + 1
                dur = e.get("duration_ms")
                if isinstance(dur, (int, float)):
                    bucket_map[key]["ai_duration_ms"] = (
                        bucket_map[key].get("ai_duration_ms", 0) + int(dur))

        elif ev in ("collect", "screen"):
            # 采集与筛选也进桶：柱状图看的是投递量，但折线图要有东西可画，
            # 而历史数据里 collect / screen 才是绝大多数。
            totals[ev + "s"] = totals.get(ev + "s", 0) + 1
            if key in bucket_map:
                bucket_map[key][ev + "s"] = bucket_map[key].get(ev + "s", 0) + 1
                if ev == "collect":
                    n = e.get("count")
                    if isinstance(n, (int, float)):
                        bucket_map[key]["collected_count"] = (
                            bucket_map[key].get("collected_count", 0) + int(n))

    success_rate = None
    if totals["attempts"]:
        done = totals["submitted"] + totals["drafted"]
        success_rate = round(done / totals["attempts"], 4)

    buckets = []
    for k in keys:
        b = bucket_map[k]
        buckets.append({
            "key": k,
            "label": _bucket_label(k, granularity),
            "submitted": b["submitted"],
            "drafted": b["drafted"],
            "skipped": b["skipped"],
            "ai_calls": b.get("ai_calls", 0),
            "ai_duration_ms": b.get("ai_duration_ms", 0),
            "collects": b.get("collects", 0),
            "screens": b.get("screens", 0),
            "collected_count": b.get("collected_count", 0),
            "by_platform": b["by_platform"],
        })

    return {
        "range": range_key,
        "platform": platform or "all",
        "granularity": granularity,
        "platforms": platforms,
        "buckets": buckets,
        "totals": {
            "submitted": totals["submitted"],
            "drafted": totals["drafted"],
            "skipped": totals["skipped"],
            "failed": totals["failed"],
            "attempts": totals["attempts"],
            "success_rate": success_rate,
            "today_submitted": today_submitted,
            "today_drafted": today_drafted,
            "avg_duration_ms": int(sum(durations) / len(durations)) if durations else None,
            "ai_calls": totals["ai_calls"],
            "collects": totals["collects"],
            "screens": totals["screens"],
            "tokens_in": totals["tokens_in"],
            "tokens_out": totals["tokens_out"],
            "cost": _cost(rows, pricing),
        },
        "heatmap": _heatmap(rows, now),
        "event_count": len(rows),
    }


def _cost(rows: list, pricing: dict | None) -> float | None:
    """AI 花费。没配单价就返回 None——不编金额。"""
    if not pricing:
        pricing = load_ai_config().get("pricing") or {}
    if not pricing:
        return None
    total = 0.0
    seen = False
    for e in rows:
        if str(e.get("event") or "") != "ai_call":
            continue
        model = str(e.get("model") or "")
        price = pricing.get(model) or pricing.get("*")
        if not price:
            continue
        t_in = e.get("tokens_in")
        t_out = e.get("tokens_out")
        if not isinstance(t_in, (int, float)) and not isinstance(t_out, (int, float)):
            continue
        pin = float(price.get("input") or 0)
        pout = float(price.get("output") or 0)
        total += (float(t_in or 0) / 1000.0) * pin + (float(t_out or 0) / 1000.0) * pout
        seen = True
    if not seen:
        return None
    return round(total, 4)


def _heatmap(rows: list, now: datetime) -> dict:
    """日历热力图：按天格子，含每天各平台的投递数。

    回看窗口最多 ``HEATMAP_MAX_DAYS`` 天，更早的数据不画。
    """
    end = _floor_day(now)
    start = end - timedelta(days=HEATMAP_MAX_DAYS - 1)
    days = {}
    for i in range(HEATMAP_MAX_DAYS):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        days[d] = {"date": d, "submitted": 0, "drafted": 0, "skipped": 0,
                   "by_platform": {}}

    for e in rows:
        if str(e.get("event") or "") != "apply":
            continue
        ts = _parse_ts(e.get("ts"))
        if ts is None:
            continue
        d = ts.strftime("%Y-%m-%d")
        cell = days.get(d)
        if cell is None:
            continue
        status = str(e.get("status") or "")
        if status in ("submitted", "drafted", "skipped"):
            cell[status] += 1
            plat = str(e.get("platform") or "")
            pb = cell["by_platform"].setdefault(
                plat, {"submitted": 0, "drafted": 0, "skipped": 0})
            if status in pb:
                pb[status] += 1

    cells = [days[k] for k in sorted(days)]
    # 从最早有数据的那天开始截，前面全是空格子没意义
    first = 0
    for i, c in enumerate(cells):
        if c["submitted"] or c["drafted"] or c["skipped"]:
            first = i
            break
    else:
        first = len(cells)
    cells = cells[first:]
    return {
        "start": cells[0]["date"] if cells else "",
        "end": cells[-1]["date"] if cells else "",
        "cells": cells,
    }


def backfill_plan_events(output_dir: str, platform: str) -> list:
    """从 ``ai_plan_*.json`` 造 ``screen`` 事件的候选（不写盘）。

    幂等靠调用方按 ``ts + event + file`` 去重。
    """
    out = []
    if not os.path.isdir(output_dir):
        return out
    for name in sorted(os.listdir(output_dir)):
        if not (name.startswith("ai_plan_") and name.endswith(".json")):
            continue
        path = os.path.join(output_dir, name)
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                plan = json.load(f)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(plan, dict):
            continue
        summary = plan.get("summary") or {}
        ts = plan.get("generated_at") or ""
        out.append({
            "ts": ts,
            "platform": platform,
            "event": "screen",
            "count": summary.get("total"),
            "planned": summary.get("planned"),
            "skipped": summary.get("skipped"),
            "excluded": summary.get("excluded"),
            "file": name,
            "ok": True,
        })
    return out


def backfill_collect_events(output_dir: str, platform: str) -> list:
    """从 ``jobs_*.json`` 造 ``collect`` 事件的候选（不写盘）。

    ``skipped`` / ``excluded`` 当年没记，留空——不编。
    时间取文件里最晚的 ``collected_at``，对齐真采集在收尾时写事件的口径。
    """
    out = []
    if not os.path.isdir(output_dir):
        return out
    for name in sorted(os.listdir(output_dir)):
        if not (name.startswith("jobs_") and name.endswith(".json")):
            continue
        path = os.path.join(output_dir, name)
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                jobs = json.load(f)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(jobs, list):
            continue
        stamps = [str(j.get("collected_at") or "") for j in jobs if isinstance(j, dict)]
        stamps = [s for s in stamps if s]
        ts = max(stamps) if stamps else ""
        out.append({
            "ts": ts,
            "platform": platform,
            "event": "collect",
            "count": len(jobs),
            "file": name,
            "ok": len(jobs) > 0,
        })
    return out
