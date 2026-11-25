"""一次性回填脚本：把历史采集与筛选结果补进事件流。

用法（项目根目录）：

    .venv/Scripts/python scripts/backfill_events.py            # 所有平台
    .venv/Scripts/python scripts/backfill_events.py --platform boss
    .venv/Scripts/python scripts/backfill_events.py --dry-run

回填什么：

- ``output/{platform}/jobs_*.json`` → ``collect`` 事件
- ``output/{platform}/ai_plan_*.json`` → ``screen`` 事件

**投递类不回填**。当时就没记，没有可以还原的依据——编出来的是假数据，
比空着更糟。

幂等：去重键是 ``ts + event + file``。重复跑不会产生重复事件。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import known_platforms, platform_output_dir  # noqa: E402
from src.storage import events  # noqa: E402
from src.storage.stats import backfill_collect_events, backfill_plan_events  # noqa: E402


def backfill_platform(platform: str, dry_run: bool = False,
                      out_dir: str | None = None) -> dict:
    """回填一个平台。返回这次写了多少条、跳过了多少条。

    ``out_dir`` 一般不传，默认取该平台的输出目录。
    """
    out_dir = out_dir if out_dir is not None else platform_output_dir(platform)
    candidates = (backfill_collect_events(out_dir, platform)
                  + backfill_plan_events(out_dir, platform))

    have = events.existing_keys(platform)
    written = 0
    skipped = 0
    for rec in candidates:
        key = events.dedup_key(rec)
        if key in have:
            skipped += 1
            continue
        have.add(key)
        if dry_run:
            written += 1
            continue
        events.record(rec["event"], rec["platform"], ts=rec.get("ts") or None,
                      **{k: v for k, v in rec.items()
                         if k not in ("ts", "platform", "event")})
        written += 1
    return {"platform": platform, "written": written, "skipped": skipped,
            "candidates": len(candidates)}


def main() -> int:
    ap = argparse.ArgumentParser(description="回填历史采集与筛选事件")
    ap.add_argument("--platform", default="", help="只回填指定平台（默认全部）")
    ap.add_argument("--dry-run", action="store_true", help="只统计会写多少条，不落盘")
    args = ap.parse_args()

    platforms = [args.platform] if args.platform else known_platforms()
    if not platforms:
        print("没有可回填的平台")
        return 1

    total_written = 0
    for platform in platforms:
        result = backfill_platform(platform, dry_run=args.dry_run)
        total_written += result["written"]
        print(f"[{platform}] 候选 {result['candidates']} 条，"
              f"新增 {result['written']} 条，已存在 {result['skipped']} 条")

    print(f"\n合计新增 {total_written} 条" + ("（dry-run，未落盘）" if args.dry_run else ""))

    if not args.dry_run:
        counts = {}
        for platform in platforms:
            for e in events.load(platform):
                key = e.get("event") or "?"
                counts[key] = counts.get(key, 0) + 1
        print("事件分布：" + json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
