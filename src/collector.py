import json
import re
import time


def _dt(scope: str, fn: str, msg: str, data: dict | None = None):
    """写入 tracer（延迟导入避免循环依赖）。"""
    from server.tracer import tracer
    tracer.internal(f"collector.py:{fn}", msg, data or {}, scope=scope)


def _trace_span(layer: str, fn: str, msg: str, scope: str = None):
    """用于包裹执行函数的 TraceLink 追踪装饰器。"""
    def decorator(func):
        from server.tracer import tracer
        import functools
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return tracer.span(layer, fn, msg, lambda: func(*args, **kwargs), scope=scope)
        return wrapper
    return decorator


from src.adapters.base import SearchCriteria
from src.adapters.registry import create_adapter
from src.config import get_config
from src.core.browser import BrowserManager
from src.utils.browser_behavior import BrowserBehavior, resolve_speed
from src.utils.company_online import (
    STATE_OFFLINE,
    STATE_UNKNOWN,
    classify_online,
    format_evidence,
)
from src.utils.salary import salary_in_range
from src.storage.writer import OutputWriter
from src.control import ConsoleController


def _safe_tag(text):
    """把搜索关键词转成可用于文件名的标记（去除非法字符）。"""
    if not text:
        return None
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", str(text)).strip("_")
    return cleaned or None


def _append_location_tag(tag, city_name, salary_min, salary_max):
    """在已有 tag 后面追加城市和薪资范围，格式：_城市_薪资K"""
    parts = []
    if city_name:
        parts.append(_safe_tag(city_name))
    if salary_min is not None or salary_max is not None:
        if salary_min and salary_max:
            parts.append(f"{salary_min}-{salary_max}K")
        elif salary_min:
            parts.append(f"{salary_min}K+")
        elif salary_max:
            parts.append(f"upTo{salary_max}K")
    if not parts:
        return tag
    suffix = "_".join(parts)
    return f"{tag}_{suffix}" if tag else suffix


def _build_output_tag(query, city_name, salary_min, salary_max):
    """生成完整的文件名前缀，包含关键词+城市+薪资范围。"""
    parts = []
    if query:
        parts.append(_safe_tag(query))
    return _append_location_tag("_".join(parts) or None, city_name, salary_min, salary_max)


def _interruptible_sleep(ctrl, seconds):
    """可被停止/暂停指令中断的 sleep。"""
    end = time.time() + seconds
    while True:
        remaining = end - time.time()
        if remaining <= 0 or ctrl.should_stop():
            return
        if ctrl.should_pause():
            ctrl._wait_paused()
            if ctrl.should_stop():
                return
        time.sleep(min(0.2, remaining))


def _current_url(browser):
    try:
        return browser.get_value(browser.evaluate("location.href")) or ""
    except Exception:
        return ""


def _reconnect_page(browser, adapter, ctrl):
    """重新定位活跃的目标标签页并重连 CDP。

    登录/验证后浏览器常切换或新开标签页，原 CDP 目标会失效，导致后续
    导航/取数"无反应"。每次人工介入后都重连，连到真正在用的那个页面。
    返回 True 表示已连上可用页面。
    """
    page = adapter.pick_target(browser.find_target_pages())
    if not page:
        _dt("H1", "_reconnect_page", "no_target_page")
        return False
    ws_url = page.get("webSocketDebuggerUrl", "")
    if not ws_url:
        _dt("H1", "_reconnect_page", "no_ws_url")
        return False
    try:
        browser.disconnect()
    except Exception:
        pass
    try:
        if not browser.connect_ws(ws_url):
            _dt("H1", "_reconnect_page", "connect_ws_failed", {"ws_url": ws_url[:50]})
            return False
    except Exception as exc:
        ctrl.log(f"    [!] 重连页面失败: {exc}")
        _dt("H1", "_reconnect_page", "connect_ws_exception", {"exc": str(exc)})
        return False
    _dt("H1", "_reconnect_page", "connected", {"ws_url": ws_url[:50], "page_url": page.get('url','')[:60]})
    return True


@_trace_span("BE-INTERNAL", "collector.py:_goto_search", "执行搜索结果页导航", scope="collect-start")
def _goto_search(browser, adapter, criteria, ctrl):
    """按检索条件导航到搜索结果页，并等待列表。返回 Ready 字典。"""
    query = criteria.get("query") or ""
    url = adapter.search_url(criteria)

    ctrl.log(f"    导航至: {url}")
    # [H3] 记录导航开始
    _dt("H3", "_goto_search", "nav_start", {"url": url})
    try:
        # [H3] 记录 evaluate 发送
        _dt("H3", "_goto_search", "eval_send", {"expr": f"location.href={url[:40]}..."})
        browser.evaluate("location.href=" + json.dumps(url))
        # [H3] 记录 evaluate 正常返回
        _dt("H3", "_goto_search", "eval_ok")
    except Exception as exc:
        # [H3] 记录异常（超时被误判为 login 的关键证据）
        _dt("H3", "_goto_search", "eval_exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
        ctrl.log(f"    [!] 导航指令发送失败（页面可能已切换）: {exc}")
        return {"ok": False, "state": "login", "reason": "navigation_failed"}
    # 给页面一点跳转时间，再确认实际落地的 URL，便于发现"没跳成功"
    time.sleep(1.0)
    landed = _current_url(browser)
    if landed:
        # [H3] 记录实际落地的 URL（判断跳转是否成功）
        _dt("H3", "_goto_search", "landed_url", {"landed": landed[:100], "matches_query": query in landed})
        ctrl.log(f"    当前页面: {landed[:80]}")
    ready = adapter.wait_results()
    # [H2/H3] 记录最终状态
    _dt("H3", "_goto_search", "wait_search_done", {"status": ready.get("state")})
    return ready


# ============ 主流程调度器 ============
def run_collection(count=20, safe_mode=True, fast=False, new_chrome=False,
                   browser_type="chrome", tag=None, controller=None,
                   keyword_search=True, query="", city_code=None, city_name=None,
                   salary_min=None, salary_max=None, tag_sync=False,
                   job_type="", degrees=None, experience=None, salary_fuzzy=False,
                   speed=None, site=None):
    ctrl = controller or ConsoleController()

    # speed 显式传入时优先；旧的 fast / safe_mode 参数继续兼容
    speed = resolve_speed(speed, safe_mode=safe_mode, fast=fast)

    query = (query or "").strip()
    # 关键词路线 vs 手动路线彻底解耦：关闭关键词搜索时清空 query，下游一律走手动路线
    if not keyword_search:
        query = ""
    keyword_mode = bool(query)

    # 动态获取配置
    config = get_config(browser_type, platform=site)

    browser = BrowserManager(config=config)
    browser.should_stop = ctrl.should_stop  # send_cdp 里每 2s 检查一次，让 Ctrl+C 有机会生效
    behavior = BrowserBehavior(speed)
    adapter = create_adapter(site, browser, behavior.profile)

    ctrl.status("running")
    ctrl.log("=" * 60)
    ctrl.log(f"{adapter.display_name} V14 助手引擎 ({browser_type.capitalize()} 驱动)")
    speed_label = {"slow": "慢速", "normal": "中速", "fast": "快速"}[speed]
    ctrl.log(f"   目标: {count} 条 | 速度: {speed_label}")
    ctrl.log("=" * 60)

    # 确定文件名前缀：自定义 tag > query 关键词
    base_tag = tag if tag else (_safe_tag(query) if query else None)

    # 统一追加城市+薪资范围
    out_tag = _append_location_tag(base_tag, city_name, salary_min, salary_max)
    ctrl.log(f"   输出前缀: {out_tag or '(default)'}")

    writer = OutputWriter(config["output_dir"], tag=out_tag)

    criteria = SearchCriteria(
        query=query,
        city_code=city_code,
        job_type=job_type,
        degrees=list(degrees or []),
        experience=list(experience or []),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_fuzzy=salary_fuzzy,
    )

    ctrl.log(f"\n   已有数据: {len(writer.all_jobs)} 条")
    ctrl.log(f"   输出路径: {config['output_dir']}")

    # ===== Step 1: 启动或复用浏览器 =====
    ctrl.log(f"\n[Step 1] 连接 {browser_type.capitalize()} ...")

    connected = False
    if not new_chrome:
        connected = browser.try_connect_existing()

    if not connected:
        ctrl.log(f"   [-] 未找到已有 {browser_type.capitalize()}，启动新实例 ...")
        if not browser.launch(adapter.home_url()):
            ctrl.log(f"[-] {browser_type.capitalize()} 启动失败")
            ctrl.status("error", "browser launch failed")
            return
        ctrl.log(f"   [+] 新 {browser_type.capitalize()} 就绪")

    # ===== 检查是否已有目标平台页面 =====
    target_page = adapter.pick_target(browser.find_target_pages())

    if keyword_mode:
        # ---- 关键词路线：不做"直接分析该页面"确认，稍后自动导航搜索页 ----
        if target_page:
            ctrl.log(f"\n   [+] 发现目标页面: {target_page['url'][:60]}（将自动按关键词搜索）")
        else:
            # 少见：浏览器已起但还没有目标平台标签页，提示打开并登录
            ctrl.wait_user(
                f"请在浏览器中打开并登录 {adapter.display_name}（{adapter.home_url()}），"
                "完成后点「我已完成，继续」。",
                kind="login",
            )
            target_page = adapter.pick_target(browser.find_target_pages())
            if not target_page:
                ctrl.log("[-] 未找到目标平台页面")
                ctrl.status("error", "no target page")
                return
    else:
        # ---- 手动路线（CLI 类交互）：用户自行搜索/滚动后再分析当前页面 ----
        if target_page:
            ctrl.log(f"\n   [+] 发现目标页面: {target_page['url'][:60]}")
            user_input = ctrl.wait_user(
                "   直接分析该页面? [回车=是 / 输入 wait 手动操作后再分析]: ",
                kind="page_confirm",
            ).strip()
            if user_input.lower() == "wait":
                target_page = None

        if not target_page:
            ctrl.log("\n" + "=" * 60)
            ctrl.log("[*] 请在浏览器中操作:")
            ctrl.log(f"    1. 登录 {adapter.display_name}: {adapter.home_url()}")
            ctrl.log("    2. 搜索你想要的岗位关键词")
            ctrl.log("    3. 尽量往下滚动，加载更多岗位")
            ctrl.log("    4. 回到终端按回车")
            ctrl.log("=" * 60)
            ctrl.wait_user("\n[等待中...按回车开始分析]: ", kind="confirm")

            target_page = adapter.pick_target(browser.find_target_pages())
            if not target_page:
                ctrl.log("[-] 未找到目标平台页面")
                ctrl.status("error", "no target page")
                return

    # ===== Step 2: 连接 WebSocket =====
    ctrl.log("\n[Step 2] 连接 WebSocket ...")
    ws_url = target_page.get("webSocketDebuggerUrl", "")
    ctrl.log(f"   页面: {target_page['url'][:60]}")

    if not browser.connect_ws(ws_url):
        ctrl.log("[-] WebSocket 连接失败")
        ctrl.status("error", "ws failed")
        return
    ctrl.log("   [+] WebSocket 已连接 (调试通道激活)")

    # ===== Step 2.5: 登录态检测 → 导航 → 等待结果（仅关键词路线）=====
    # L1: Browser/CDP | L2: Login | L3: Navigation | L4: SearchReady | L5: CollectionLoop
    if keyword_mode:
        _dt("L3", "run_collection", "step_25_enter", {"query": query, "city": city_name or city_code or "current"})

        # ── L2: 登录态检测（前置）───────────────────────────────────
        @_trace_span("BE-INTERNAL", "collector.py:_ensure_logged_in", "检测与确认登录状态", scope="collect-start")
        def _ensure_logged_in():
            """检测登录态，未登录则循环等待用户扫码登录，直到确认已登录才返回。"""
            # ── L3: 先强制导航到平台首页，确保在正确域内再 probe ───────────
            _dt("L3", "_ensure_logged_in", "pre_nav_home")
            try:
                browser.evaluate("location.href=" + json.dumps(adapter.home_url()))
                _dt("L3", "_ensure_logged_in", "pre_nav_ok")
            except Exception as exc:
                _dt("L3", "_ensure_logged_in", "pre_nav_exc", {"exc": str(exc)})
            time.sleep(1.5)

            _dt("L2", "_ensure_logged_in", "probe_start")
            probe = adapter.probe_login()
            state, source = probe["state"], probe["source"]
            _dt("L2", "_ensure_logged_in", "probe_result", {"state": state, "source": source})

            # 容错：probe 返回 "login"（JS 误判：已登录页残留登录入口元素）时重检一次
            if state == "login":
                _dt("L2", "_ensure_logged_in", "probe_retry")
                probe = adapter.probe_login()
                state, source = probe["state"], probe["source"]
                _dt("L2", "_ensure_logged_in", "probe_retry_result", {"state": state, "source": source})

            if state == "in":
                _dt("L2", "_ensure_logged_in", "already_logged_in")
                ctrl.log("   [+] 登录态确认：已登录")
                return True

            # 未登录或未知 → 进入扫码登录循环
            _dt("L2", "_ensure_logged_in", "need_login", {"probe_state": state})
            ctrl.log(f"   [!] 检测到尚未登录 {adapter.display_name}（或登录态无法确认）")

            while True:
                if ctrl.should_stop():
                    _dt("L2", "_ensure_logged_in", "stopped_by_user")
                    return False

                # ── L2a: 主动导航到登录入口页（确保浏览器在正确的扫码页面）────
                _dt("L3", "_ensure_logged_in", "nav_to_login_page")
                try:
                    browser.evaluate("location.href=" + json.dumps(adapter.login_url()))
                    _dt("L3", "_ensure_logged_in", "nav_to_login_page_ok")
                except Exception as exc:
                    _dt("L3", "_ensure_logged_in", "nav_to_login_page_exc", {"exc": str(exc)})
                time.sleep(1.5)

                ctrl.log(f"   [*] 请在浏览器中扫码登录 {adapter.display_name}")
                ctrl.log("   [*] 扫码后在 APP 确认，完成后点「我已完成，继续」")

                # 等待用户在 app 确认（GUI）或按回车（CLI）
                _dt("L2", "_ensure_logged_in", "wait_user_ack")
                ctrl.wait_user(
                    "扫码登录完成后点「我已完成，继续」 ...",
                    kind="login",
                )

                if ctrl.should_stop():
                    _dt("L2", "_ensure_logged_in", "stopped_after_wait")
                    return False

                # ── L1: 登录后标签页/CDP 目标可能已切换，先重连 ──────────────
                _dt("L1", "_ensure_logged_in", "reconnect_after_scan")
                if not _reconnect_page(browser, adapter, ctrl):
                    ctrl.log("   [!] 未找到可用的目标标签页，请确认浏览器未被关闭")
                    _dt("L1", "_ensure_logged_in", "reconnect_failed")
                    continue

                # ── L2b: 强制刷新页面后再检测（避免旧 DOM 导致 probe 误判）────
                _dt("L3", "_ensure_logged_in", "reload_before_probe")
                reloaded = adapter.reload()
                if reloaded.get("ok"):
                    _dt("L3", "_ensure_logged_in", "reload_ok")
                else:
                    _dt("L3", "_ensure_logged_in", "reload_exc", {"exc": reloaded.get("reason")})
                time.sleep(2.0)

                probe = adapter.probe_login()
                state, source = probe["state"], probe["source"]
                _dt("L2", "_ensure_logged_in", "reprobe_after_login", {"state": state, "source": source})
                ctrl.log(f"   [*] 登录态复检: {state} (via {source})")

                if state == "in":
                    _dt("L2", "_ensure_logged_in", "login_confirmed")
                    ctrl.log("   [+] 登录确认完成")
                    return True

                # 仍未登录，继续循环等待
                ctrl.log("   [!] 仍未确认登录态，请确认扫码成功并在 APP 端点击确认")

        # 检查当前浏览器是否已经处于目标搜索页，避免重新载入页面
        current = _current_url(browser)
        is_already_on_target = False

        _dt("collect-start", "run_collection.page_reuse_check", "check_begin", {
            "current_url": current,
            "query": query,
            "city_code": city_code,
            "job_type": job_type,
            "degrees": degrees,
            "experience": experience,
            "salary_min": salary_min,
            "salary_max": salary_max
        })

        matched = adapter.matches_criteria(current, criteria)
        _dt("collect-start", "run_collection.page_reuse_check", "match_results", {"matched": matched})

        if matched:
            login = adapter.probe_login()
            login_state, login_src = login["state"], login["source"]
            _dt("collect-start", "run_collection.page_reuse_check", "login_check", {
                "login_state": login_state,
                "login_src": login_src
            })
            if login_state == "in":
                is_already_on_target = True

        _dt("collect-start", "run_collection.page_reuse_check", "check_end", {
            "is_already_on_target": is_already_on_target
        })

        if is_already_on_target:
            ctrl.log("   [+] [智能优化] 浏览器已处于目标页面，跳过页面重载，已激活「无缝续接」整理模式！")
            nav_status = {"ok": True, "state": "ready", "reason": ""}
            if hasattr(ctrl, "events"):
                ctrl.events.put({"type": "seamless_mode", "enabled": True})
        else:
            # ── L2 → L3: 前置登录检测通过后，才进入导航 ─────────────────
            if not _ensure_logged_in():
                ctrl.log("\n[*] 已停止")
                browser.disconnect()
                ctrl.status("stopped")
                return

            _dt("L3", "run_collection", "navigation_start", {"query": query, "city": city_name or city_code or "current"})
            ctrl.log(f"\n[*] 自动搜索: 关键词='{query}' 城市='{city_name or city_code or '当前城市'}'")

            nav_status = _goto_search(browser, adapter, criteria, ctrl)
            _dt("L3", "run_collection", "goto_search_done", {"status": nav_status.get("state")})

        # ── L4: 搜索结果等待循环（重连后 / 验证后 / 页面卡住时复用）────
        while nav_status.get("state") != "ready":
            if ctrl.should_stop():
                ctrl.log("\n[*] 已停止")
                browser.disconnect()
                ctrl.status("stopped")
                return

            if nav_status.get("state") == "login":
                # L4→L2 回环：检测到未登录，重新进入扫码登录
                _dt("L4", "run_collection", "status_login_loop_back")
                ctrl.log("   [!] 检测到登录态已失效，请重新扫码登录")

                while True:
                    if ctrl.should_stop():
                        ctrl.log("\n[*] 已停止")
                        browser.disconnect()
                        ctrl.status("stopped")
                        return

                    # ── L3a: 主动导航到登录入口页 ──────────────────────────────
                    _dt("L3", "run_collection", "login_loop_nav_to_login")
                    try:
                        browser.evaluate("location.href=" + json.dumps(adapter.login_url()))
                        _dt("L3", "run_collection", "login_loop_nav_ok")
                    except Exception as exc:
                        _dt("L3", "run_collection", "login_loop_nav_exc", {"exc": str(exc)})
                    time.sleep(1.5)

                    ctrl.log("   [*] 登录页已打开，请在浏览器中扫码登录")
                    _dt("L2", "run_collection", "login_loop_wait_user")
                    ctrl.wait_user("扫码登录完成后点「我已完成，继续」 ...", kind="login")

                    if ctrl.should_stop():
                        ctrl.log("\n[*] 已停止")
                        browser.disconnect()
                        ctrl.status("stopped")
                        return

                    # ── L1: 重连 ─────────────────────────────────────────────
                    _dt("L1", "run_collection", "reconnect_before_reprobe")
                    if not _reconnect_page(browser, adapter, ctrl):
                        ctrl.log("   [!] 未找到可用的目标标签页，请确认浏览器未被关闭")
                        continue

                    # ── L3b: 强制刷新后再 probe ───────────────────────────────
                    _dt("L3", "run_collection", "login_loop_reload_before_probe")
                    reloaded = adapter.reload()
                    if reloaded.get("ok"):
                        _dt("L3", "run_collection", "login_loop_reload_ok")
                    else:
                        _dt("L3", "run_collection", "login_loop_reload_exc", {"exc": reloaded.get("reason")})
                    time.sleep(2.0)

                    probe = adapter.probe_login()
                    state, source = probe["state"], probe["source"]
                    _dt("L2", "run_collection", "reprobe_after_relogin", {"state": state, "source": source})

                    if state == "in":
                        _dt("L2", "run_collection", "relogin_confirmed")
                        ctrl.log("   [+] 重新登录确认")
                        break
                    else:
                        ctrl.log("   [!] 仍未确认登录态，请确认扫码成功并在 APP 端点击确认")

                # L2→L3: 登录确认后重新导航
                _dt("L3", "run_collection", "relayout_after_relogin", {"query": query})
                nav_status = _goto_search(browser, adapter, criteria, ctrl)
                _dt("L3", "run_collection", "relayout_done", {"status": nav_status.get("state")})
            else:
                # timeout：已登录但页面加载慢
                _dt("L4", "run_collection", "status_timeout_wait_user")
                ctrl.log("   [!] 已登录但搜索结果尚未加载出来")
                ctrl.wait_user(
                    "请在【浏览器窗口】中确认页面后点「我已完成，继续」 ...",
                    kind="page_confirm",
                )
                _dt("L1", "run_collection", "reconnect_after_timeout_wait")
                if not _reconnect_page(browser, adapter, ctrl):
                    ctrl.log("   [!] 未找到可用的目标标签页，请确认浏览器未被关闭")
                nav_status = _goto_search(browser, adapter, criteria, ctrl)
                _dt("L3", "run_collection", "relayout_after_timeout", {"status": nav_status.get("state")})

        # ── L4: 搜索结果已加载，继续 Step 3 ─────────────────────────
        _dt("L4", "run_collection", "search_results_ready")
        ctrl.log("    [+] 搜索结果已加载")
        if salary_min is not None or salary_max is not None:
            lo = salary_min if salary_min is not None else "-"
            hi = salary_max if salary_max is not None else "-"
            ctrl.log(f"    [*] 初始薪资过滤: {lo}K ~ {hi}K")
        if job_type or degrees or experience:
            ctrl.log(f"    [*] 初始条件过滤: 工作性质={job_type or '不限'} 学历={degrees or '不限'} 经验={experience or '不限'}")

    # ===== Step 3: 准备数据提取层 =====
    ctrl.log("\n[Step 3] 初始化数据提取 ...")
    ctrl.log("   [+] Vue 面板读取器就绪")

    # ===== Step 4: 开始数据整理循环 =====
    ctrl.log(f"\n[Step 4] 开始运行数据整理 ...\n")

    success_count = 0
    fail_count = 0
    skip_count = 0
    offline_count = 0        # 公司不在线、主动跳过
    online_unknown_count = 0 # 在线状态读不出、放行采集
    vue_hit = 0       # Vue 面板直读成功次数 (本地读取)
    start_idx = len(writer.all_jobs) + 1
    processed_sids = set()
    last_scroll_top = -1  # 追踪滚动位置

    def _emit_progress():
        ctrl.progress(success_count, count, {
            "success": success_count, "fail": fail_count, "skip": skip_count,
            "offline": offline_count, "online_unknown": online_unknown_count,
            "vue_hit": vue_hit,
        })

    _emit_progress()

    while success_count < count:
        if ctrl.should_stop():
            break
        if ctrl.should_pause():
            ctrl._wait_paused()
            if ctrl.should_stop():
                break

        prev_success_count = success_count

        # 每次循环开始都重新提取一次列表，确保数据是最新的
        jobs = adapter.list_jobs().get("jobs") or []
        if not jobs:
            ctrl.log("   [*] 页面上未探测到岗位，尝试向下滚动加载 ...")
            adapter.scroll_list()
            _interruptible_sleep(ctrl, 2)
            # 再次检查
            jobs = adapter.list_jobs().get("jobs") or []
            if not jobs:
                ctrl.log(f"\n   [!] 仍无新数据。还差 {count - success_count} 条。")
                result = ctrl.wait_user(
                    "   [>] 请在浏览器中确认页面状态后点「继续」 ...",
                    kind="page_check" if keyword_mode else "page_confirm",
                )
                # [H4] 记录空列表分支
                _dt("H4", "run_collection", "empty_jobs_branch", {"keyword_mode": keyword_mode, "result": result})

                if result == "manual_scroll":
                    # 用户已在浏览器手动滚动/翻页 → 立即重新提取，有数据就直接采集
                    jobs = adapter.list_jobs().get("jobs") or []
                    if jobs:
                        _dt("H4", "run_collection", "manual_scroll_recovered", {"count": len(jobs)})
                        ctrl.log(f"   [+] 检测到 {len(jobs)} 条，继续采集")
                        # 不 continue，正常进入下方遍历逻辑
                    else:
                        # 仍然没有，重走弹窗流程
                        continue

                if keyword_mode and not ctrl.should_stop():
                    # 关键词路线：继续时重连活跃页面 + 按关键词重新导航，避免读到无关页面
                    _dt("H4", "run_collection", "empty_jobs_reconnect")
                    _reconnect_page(browser, adapter, ctrl)
                    _goto_search(browser, adapter, criteria, ctrl)
                continue

        # 遍历当前列表中的岗位
        for card in jobs:
            if success_count >= count:
                break
            if ctrl.should_stop():
                break
            if ctrl.should_pause():
                ctrl._wait_paused()
                if ctrl.should_stop():
                    break

            sid = card.get("job_id")
            if not sid or sid in processed_sids:
                continue

            # === 熔断检测：登录失效/数据脱敏 ===
            salary_desc = card.get("salary", "")
            if not salary_desc or "****" in salary_desc:
                ctrl.log(f"\n  [BREAK] 熔断保护: 检测到异常薪资数据 ('{salary_desc}')")
                ctrl.log(f"      这通常意味着登录已过期或页面未完全加载。")
                ctrl.log(f"      请在浏览器中确认登录状态，【手动刷新页面】。")
                ctrl.wait_user("  [>] 处理完成后按回车，程序将重新扫描页面 ...", kind="login")
                # 跳出 for 循环，回到 while 开头重新执行 adapter.list_jobs()
                break

            processed_sids.add(sid)
            job_name = card.get("title", "?")
            brand_name = card.get("company", "")

            # === 薪资粗筛：列表 salaryDesc 超出请求区间则跳过（在提取详情前，省时间）===
            if (salary_min is not None or salary_max is not None) and \
                    not salary_in_range(salary_desc, salary_min, salary_max):
                skip_count += 1
                ctrl.log(f"  [SKIP] 薪资不符: {job_name[:20]} ({salary_desc})")
                _emit_progress()
                continue

            # === 查重（title + company + 区域；区域缺失时回退旧口径）===
            if writer.is_duplicate(job_name, brand_name, card.get("area", "")):
                skip_count += 1
                ctrl.log(f"  [SKIP] 重复: {job_name[:20]} | {brand_name[:10]}")
                _emit_progress()
                continue

            # === 公司在线状态门禁：离线不点击卡片、不读详情 ===
            # 放在 processed_sids.add 之后，跳过的卡片本轮不会再被探测。
            probe = adapter.probe_online(sid)
            online_state = classify_online(probe)
            evidence = probe.get("evidence") if isinstance(probe.get("evidence"), dict) else {}
            trace_data = {"sid": sid[:12], "brand": brand_name[:10]}
            trace_data.update(evidence)

            if online_state == STATE_OFFLINE:
                offline_count += 1
                ctrl.log(
                    f"  [SKIP] 公司离线: {job_name[:20]} | {brand_name[:10]} | "
                    f"{format_evidence(probe)}"
                )
                _dt("L5", "run_collection", "offline_skip", trace_data)
                _emit_progress()
                continue

            if online_state == STATE_UNKNOWN:
                online_unknown_count += 1
                ctrl.log(
                    f"  [.] 在线状态未知: {probe.get('reason', '?')} | "
                    f"{format_evidence(probe)} | 照常采集"
                )
                _dt("L5", "run_collection", "online_unknown", trace_data)
                _emit_progress()
                # 未知不拦截，继续走正常采集
            # online 不打日志、不计数

            # === 记录点击前滚动位置 ===
            scroll_before = adapter.scroll_position()
            scroll_top_before = scroll_before.get("scrollTop", 0)

            # === 通过岗位 ID 精确点击卡片 (不再用名字匹配) ===
            click = adapter.click_card(sid)
            clicked, card_pos, card_total = click["ok"], click["index"], click["total"]

            if not clicked:
                fail_count += 1
                ctrl.log(f"  [-] 未找到卡片: {job_name[:25]} (页面共{card_total}张)")
                _emit_progress()
                continue

            # === 检测回跳 ===
            scroll_after = adapter.scroll_position()
            scroll_top_after = scroll_after.get("scrollTop", 0)

            # 位置信息
            task_num = success_count + 1
            pos_info = f"卡片{card_pos+1}/{card_total}"

            # 回跳检测：如果卡片序号是递增的但 scrollTop 反而大幅减少
            if last_scroll_top > 0 and scroll_top_after < last_scroll_top - 300:
                ctrl.log(f"  [!!] 回跳! scroll: {last_scroll_top} -> {scroll_top_after} (差 {last_scroll_top - scroll_top_after})")

            last_scroll_top = scroll_top_after

            # === 点击卡片 ===
            ctrl.log(f"  [RUN] #{task_num}/{count} [{pos_info}] {job_name[:25]}", end="")

            # === Vue 面板直读（本地读取，仅从页面 Vue 状态提取）===
            detail = adapter.read_detail(sid)

            if detail.get("success"):
                # 详情拿到 encryptJobId 后再精确查一次，防止跨区域/跨文件重复
                if writer.has_job_id(detail.get("encrypt_job_id")):
                    skip_count += 1
                    ctrl.log(f"  [SKIP] 重复(encryptJobId): {job_name[:20]}")
                    _emit_progress()
                    continue

                vue_hit += 1
                source = "vue-panel"

                total_idx = start_idx + success_count
                writer.save_job(detail, total_idx)
                success_count += 1

                # === 数据读取后的延时等待（按速度档位，可被中止）===
                if behavior.should_scroll_detail():
                    adapter.scroll_detail()
                _interruptible_sleep(ctrl, behavior.get_browse_delay())

                title = detail.get("title", "?")[:25]
                salary = detail.get("salary", "?")
                address = detail.get("address", "") or detail.get("location", "")
                address_short = address[:18]
                exp = detail.get("experience", "")
                degree = detail.get("degree", "")
                company = detail.get("company", "?")[:15]
                city = detail.get("location", "")
                active = detail.get("boss_active", "")

                ctrl.log(f" -> OK (vue)")
                ctrl.log(f"  [>] #{success_count}/{count} (累计#{total_idx}) {title} | {company} | {salary} | {address_short} | {exp} | {degree} | {city} | {active}")
                _emit_progress()

            else:
                fail_count += 1
                err = detail.get("error", "未知")
                msg = detail.get("message", "")
                ctrl.log(f" -> 失败: {err}")
                if msg:
                    ctrl.log(f"      {msg}")
                _emit_progress()

            # === 间隔休息（按速度档位）===
            behavior.maybe_step_break(success_count, lambda s: _interruptible_sleep(ctrl, s))

        # === for 结束后：如果没有任何进展（全部跳过），触发滚动加载更多 ===
        if success_count == prev_success_count and not ctrl.should_stop():
            _dt("H4", "run_collection", "scroll_for_more_start", {"success": success_count, "prev": prev_success_count})
            ctrl.log(f"   [*] 本批已处理完，滚动加载更多 ...")
            adapter.scroll_list()
            _interruptible_sleep(ctrl, 2)
            _dt("H4", "run_collection", "scroll_for_more_done", {})

    # ===== Step 5: 总结 =====
    stopped = ctrl.should_stop()
    ctrl.log(f"\n[Step 5] {'已停止' if stopped else '分析完毕'}")
    ctrl.log("=" * 60)
    ctrl.log(f"   成功:   {success_count} 条")
    if fail_count:
        ctrl.log(f"   失败:   {fail_count} 条")
    if skip_count:
        ctrl.log(f"   跳过:   {skip_count} 条 (重复/薪资)")
    if offline_count:
        ctrl.log(f"   离线:   {offline_count} 条 (公司不在线)")
    if online_unknown_count:
        ctrl.log(f"   状态未知: {online_unknown_count} 条 (已放行)")
    ctrl.log(f"   -------")
    ctrl.log(f"   Vue面板直读(currentJob): {vue_hit} 次")
    ctrl.log(f"   JSON:   {writer.json_path}")
    ctrl.log(f"   MD:     {writer.md_path}")
    ctrl.log(f"   累计:   {len(writer.all_jobs)} 条")
    ctrl.log("=" * 60)
    ctrl.log(f"\n   [*] {browser_type.capitalize()} 保持运行 (端口 {browser.port})，下次可复用")

    browser.disconnect()
    result = {
        "success": success_count, "fail": fail_count, "skip": skip_count,
        "offline": offline_count, "online_unknown": online_unknown_count,
        "json": writer.json_path, "md": writer.md_path, "total": len(writer.all_jobs),
    }
    ctrl.status("stopped" if stopped else "done", result)
    return result
