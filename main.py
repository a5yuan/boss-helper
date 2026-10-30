"""手动模式浏览器辅助工具 - CLI 入口

本工具**不主动**向 zhipin.com 发送任何 HTTP 请求。它通过 Chrome DevTools Protocol
连接到用户**已经打开**的浏览器，读取当前页面的 Vue 组件状态（BOSS 的安全渲染层），
将当前可见的岗位信息导出为本地 JSON / Markdown。

用法:
    python main.py            # 启动浏览器（若需要）并连接到 zhipin.com
    python main.py --new      # 强制启动新 Chrome（不复用已有实例）
    python main.py -b edge    # 使用 Edge 浏览器
    python main.py -n 50      # 目标 50 条（手动模式仅记录当前页可见数）
    python main.py -t finance # 输出文件标记

设计原则：
    1. 浏览器辅助：完全依赖用户在浏览器中正常的浏览和交互操作。
    2. 安全合规：基于用户已有的浏览器登录状态及安全上下文，遵循平台安全机制。
    3. 人机协同：由用户主导检索过程，工具仅协助进行结构化整理和本地分析。
    4. 零额外负载：数据从用户当前页面解析，不额外消耗目标服务器任何接口资源。
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.collector import run_collection


def main():
    parser = argparse.ArgumentParser(description="BOSS-Helper 手动模式浏览器辅助工具")
    parser.add_argument("-n", "--count", type=int, default=20, help="目标条数（手动模式下仅记录当前页可见数）")
    parser.add_argument("--new", action="store_true", help="强制启动新浏览器（不复用）")
    parser.add_argument("-b", "--browser", type=str, default="chrome", choices=["chrome", "edge"], help="选择浏览器: chrome 或 edge (默认 chrome)")
    parser.add_argument("-t", "--tag", type=str, default=None, help="输出文件标记（例: manual)")
    # 提示：为遵循 zhipin.com/robots.txt 规范，不在此处提供 --query 等主动搜索参数

    args = parser.parse_args()

    run_collection(
        count=args.count,
        new_chrome=args.new,
        browser_type=args.browser,
        tag=args.tag,
        keyword_search=False,
        query="",
    )


if __name__ == "__main__":
    main()
