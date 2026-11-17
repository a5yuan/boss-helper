"""CLI：python -m src.ai <screen|dispatch|ping>

    screen   读 jobs_*.json → 调模型打分 → 写 ai_plan_*.json（不碰浏览器）
    dispatch 读 ai_plan_*.json → 逐条点沟通 + 填招呼语 → 跳聊天页（只填不发）
    ping     验证模型通道
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.ai.pipeline import build_plan, load_plan, plan_path_for, save_plan
from src.config import load_ai_config


def _print_table(items):
    print(f"\n{'#':>2} {'分':>3} {'判定':<5} {'状态':<8} 标题 | 公司 | 薪资")
    print("-" * 78)
    for it in items:
        print(f"{it['index']:>2} {it['score']:>3} {it['verdict']:<5} {it['status']:<8} "
              f"{(it.get('resume') or '')[:12]:<12} "
              f"{(it['title'] or '?')[:20]:<20} | {(it['company'] or '')[:12]:<12} | {it['salary']}")


def cmd_ping(_args):
    cfg = load_ai_config()
    print(f"base_url: {cfg['base_url'] or '(未配置)'}")
    print(f"model:    {cfg['model'] or '(未配置)'}")
    print(f"api_key:  {'已配置' if cfg['api_key'] else '(空)'}")
    from src.ai.client import LLMClient
    client = LLMClient.from_config()
    reply = client.chat([{"role": "user", "content": "只回复两个字：收到"}], max_tokens=20)
    print(f"回复: {reply.strip()[:40]}")


def cmd_screen(args):
    plan = build_plan(args.file, limit=args.limit, min_score=args.min_score,
                      force=args.force, on_event=print, resume_path=args.resume)
    _print_table(plan["items"])
    s = plan["summary"]
    print(f"\n计划: {s['planned']} 条可投 / {s['skipped']} 条跳过 / 共 {s['total']} 条")
    print(f"文件: {plan_path_for(args.file)}")


def cmd_dispatch(args):
    from src.ai.dispatch import dispatch
    plan = load_plan(args.plan)
    items = [it for it in plan["items"]
             if it.get("status") == "planned" and it.get("dispatch") != "done"]
    done_before = sum(1 for it in plan["items"] if it.get("dispatch") == "done")
    if done_before:
        print(f"（跳过已执行过的 {done_before} 条）")
    if args.max:
        items = items[:args.max]
    if not items:
        print("计划里没有 planned 状态的岗位")
        return 1

    gap = (args.gap_min, args.gap_max)
    if args.dry:
        print(f"[dry] 将执行 {len(items)} 条，间隔 {gap[0]}~{gap[1]}s")
        dispatch(items, gap=gap, on_event=print, dry=True)
        print("[dry] 未连接浏览器")
        return 0

    print(f"即将对 {len(items)} 条岗位点「立即沟通」并填招呼语（不会发送）。")
    print(f"条间间隔 {gap[0]}~{gap[1]}s，预计 {int(len(items) * (sum(gap) / 2 + 6) / 60)} 分钟。")
    if not args.yes:
        ans = input("继续? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("已取消")
            return 0

    stats = dispatch(items, gap=gap, on_event=print,
                     interactive=args.interactive, wait_open=args.wait_open)
    print(f"\n完成: 成功 {stats['ok']} / 失败 {stats['failed']} / 跳过 {stats['skipped']}")
    return 0 if stats["failed"] == 0 else 2


def main():
    ap = argparse.ArgumentParser(prog="python -m src.ai", description="BOSS-Helper AI 筛选与招呼语")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ping", help="验证模型通道")
    p.set_defaults(fn=cmd_ping)

    p = sub.add_parser("screen", help="筛岗 + 生成招呼语，不碰浏览器")
    p.add_argument("--file", required=True, help="output/jobs_*.json")
    p.add_argument("--limit", type=int, default=None, help="只处理前 N 条")
    p.add_argument("--min-score", type=int, default=None, help="低于该分不投（默认取 config）")
    p.add_argument("--force", action="store_true", help="忽略缓存重新分析")
    p.add_argument("--resume", default=None, help="简历文件路径（默认取 config ai.resume_path）")
    p.set_defaults(fn=cmd_screen)

    p = sub.add_parser("dispatch", help="执行计划：点沟通 + 填招呼语")
    p.add_argument("--plan", required=True, help="output/ai_plan_*.json")
    p.add_argument("--max", type=int, default=None, help="本次最多执行几条")
    p.add_argument("--gap-min", type=float, default=8.0)
    p.add_argument("--gap-max", type=float, default=15.0)
    p.add_argument("--dry", action="store_true", help="只打印，不连浏览器")
    p.add_argument("--yes", action="store_true", help="跳过确认")
    p.add_argument("--interactive", action="store_true",
                   help="会话列表点不开时，转人工点会话，脚本等着填")
    p.add_argument("--wait-open", type=float, default=90.0,
                   help="交互模式下每条等待人工打开会话的秒数")
    p.set_defaults(fn=cmd_dispatch)

    args = ap.parse_args()
    sys.exit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
