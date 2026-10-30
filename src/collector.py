import json
import re
import time
from urllib.parse import quote


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


from src.config import get_config
from src.core.browser import BrowserManager
from src.core.extractor import VueExtractor, DetailPanelReader
from src.utils.browser_behavior import BrowserBehavior
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


# 在页面内判断登录态。Cookie 优先 + DOM 兜底。
# bst cookie 注销后立即消失，是最精准的已登录信号；DOM 元素作为兜底。
_LOGIN_PROBE_JS = """
(() => {
  try {
    // ① URL 守卫：不在 BOSS 域内直接返回 unknown，避免非 BOSS 页面抛异常
    const url = (location.href || '').toLowerCase();
    if (!url.includes('zhipin.com')) {
      return JSON.stringify({ state: 'unknown', source: 'not_boss', url: location.href });
    }

    // ② bst cookie（最优先）——注销后立即消失，最干净
    const cstr = document.cookie || '';
    const hasBst = /(?:^|;\\s*)bst=/.test(cstr);

    // ② ka=header-username（DOM 兜底1）——注销后消失，直接是人名文本
    const hasUsername = !!document.querySelector('[ka="header-username"]');

    // ③ ka=header-message（DOM 兜底2）——注销后消失
    const hasMessage = !!document.querySelector('[ka="header-message"]');

    if (hasBst || hasUsername || hasMessage) {
      return JSON.stringify({
        state: 'in',
        source: hasBst ? 'bst_cookie' : (hasUsername ? 'ka-header-username' : 'ka-header-message'),
        url: location.href
      });
    }

    // 未登录：Header文案 + 二维码组合判断
    const head = document.querySelector('header,.header,.nav-wrap,#header') || document.body;
    const t = (head.innerText || '').slice(0, 500);
    if (t.includes('登录/注册') || t.includes('登录 / 注册') || /(^|[\\s|])登录([\\s|]|$)/.test(t)) {
      return JSON.stringify({ state: 'login', source: 'header_text', url: location.href });
    }

    const loginSel = '[class*="qrcode" i],[class*="login-register" i],[class*="sign-form" i],'
      + '.login-pop,.sign-wrap,.btn-login,[ka="header-login"],[ka="header-register"]';
    if (document.querySelector(loginSel)) {
      return JSON.stringify({ state: 'login', source: 'qr_popup', url: location.href });
    }

    // 兜底：无法确认按未登录处理
    return JSON.stringify({ state: 'unknown', source: 'none', url: location.href });
  } catch (e) { return JSON.stringify({ state: 'unknown', source: 'error', error: String(e) }); }
})()
"""


def _probe_login(browser):
    """返回 'in' / 'login' / 'unknown'，source 指出判断依据。"""
    try:
        info = browser.get_value(browser.evaluate(_LOGIN_PROBE_JS))
        if isinstance(info, dict):
            return info.get("state") or "unknown", info.get("source") or "?"
    except Exception:
        pass
    return "unknown", "exception"


def _wait_search_ready(browser, timeout=14.0):
    """导航后等待搜索结果列表渲染。

    返回：
      'ok'      已读取到卡片（已登录且有结果）
      'login'   疑似未登录（兜底：非明确已登录都归此类）
      'timeout' 已登录但暂无结果 / 加载较慢
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        # [H2] 每个轮询轮次都记录
        _dt("H2", "_wait_search_ready", "poll", {"elapsed": f"{max(0,deadline-time.time()):.1f}s_left"})
        try:
            jobs = VueExtractor.extract(browser)
            _dt("H2", "_wait_search_ready", "vue_result", {"job_count": len(jobs) if jobs else 0})
            if jobs:
                return "ok"
        except Exception as exc:
            _dt("H2", "_wait_search_ready", "vue_exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            pass
    # 没读取到卡片：判定登录态。明确已登录才算 timeout，否则按未登录（兜底）
    login_state, _ = _probe_login(browser)
    _dt("H2", "_wait_search_ready", "timeout_probe", {"login_state": login_state})
    return "timeout" if login_state == "in" else "login"


def _current_url(browser):
    try:
        return browser.get_value(browser.evaluate("location.href")) or ""
    except Exception:
        return ""


def _reconnect_boss(browser, ctrl):
    """重新定位活跃的 BOSS 标签页并重连 CDP。

    登录/验证后浏览器常切换或新开标签页，原 CDP 目标会失效，导致后续
    导航/取数"无反应"。每次人工介入后都重连，连到真正在用的那个页面。
    返回 True 表示已连上可用页面。
    """
    page = browser.find_boss_page()
    if not page:
        _dt("H1", "_reconnect_boss", "no_boss_page")
        return False
    ws_url = page.get("webSocketDebuggerUrl", "")
    if not ws_url:
        _dt("H1", "_reconnect_boss", "no_ws_url")
        return False
    try:
        browser.disconnect()
    except Exception:
        pass
    try:
        if not browser.connect_ws(ws_url):
            _dt("H1", "_reconnect_boss", "connect_ws_failed", {"ws_url": ws_url[:50]})
            return False
    except Exception as exc:
        ctrl.log(f"    [!] 重连页面失败: {exc}")
        _dt("H1", "_reconnect_boss", "connect_ws_exception", {"exc": str(exc)})
        return False
    _dt("H1", "_reconnect_boss", "connected", {"ws_url": ws_url[:50], "page_url": page.get('url','')[:60]})
    return True


def get_salary_code(salary_min, salary_max):
    # Normalize None / 0
    s_min = salary_min if salary_min is not None else 0
    s_max = salary_max if salary_max is not None else 0
    if s_min == 0 and s_max == 3:
        return "402"
    elif s_min == 3 and s_max == 5:
        return "403"
    elif s_min == 5 and s_max == 10:
        return "404"
    elif s_min == 10 and s_max == 20:
        return "405"
    elif s_min == 20 and s_max == 50:
        return "406"
    elif s_min == 50 and s_max == 0:
        return "407"
    return None


@_trace_span("BE-INTERNAL", "collector.py:_goto_search", "执行搜索结果页导航", scope="collect-start")
def _goto_search(browser, query, city_code, ctrl, job_type="", degrees=None, experience=None, salary_min=None, salary_max=None, salary_fuzzy=False):
    """按关键词（+城市等筛选）导航到 BOSS 搜索结果页，并等待列表。返回 _wait_search_ready 的状态。"""
    params = []
    if city_code:
        params.append(f"city={city_code}")
    if query:
        params.append(f"query={quote(query)}")
    if not salary_fuzzy:
        if salary_code := get_salary_code(salary_min, salary_max):
            params.append(f"salary={salary_code}")
    if job_type:
        params.append(f"jobType={job_type}")
    if degrees:
        deg_str = ",".join(str(d) for d in degrees if d)
        if deg_str:
            params.append(f"degree={deg_str}")
    if experience:
        exp_str = ",".join(str(e) for e in experience if e)
        if exp_str:
            params.append(f"experience={exp_str}")

    url = "https://www.zhipin.com/web/geek/jobs"
    if params:
        url += "?" + "&".join(params)

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
        return "login"
    # 给页面一点跳转时间，再确认实际落地的 URL，便于发现"没跳成功"
    time.sleep(1.0)
    landed = _current_url(browser)
    if landed:
        # [H3] 记录实际落地的 URL（判断跳转是否成功）
        _dt("H3", "_goto_search", "landed_url", {"landed": landed[:100], "matches_query": query in landed})
        ctrl.log(f"    当前页面: {landed[:80]}")
    status = _wait_search_ready(browser)
    # [H2/H3] 记录最终状态
    _dt("H3", "_goto_search", "wait_search_done", {"status": status})
    return status


# ============ 主流程调度器 ============
def run_collection(count=20, safe_mode=True, fast=False, new_chrome=False,
                   browser_type="chrome", tag=None, controller=None,
                   keyword_search=True, query="", city_code=None, city_name=None,
                   salary_min=None, salary_max=None, tag_sync=False,
                   job_type="", degrees=None, experience=None, salary_fuzzy=False):
    ctrl = controller or ConsoleController()

    if fast:
        safe_mode = False

    query = (query or "").strip()
    # 关键词路线 vs 手动路线彻底解耦：关闭关键词搜索时清空 query，下游一律走手动路线
    if not keyword_search:
        query = ""
    keyword_mode = bool(query)

    # 动态获取配置
    config = get_config(browser_type)

    ctrl.status("running")
    ctrl.log("=" * 60)
    ctrl.log(f"BOSS 直聘 V14 助手引擎 ({browser_type.capitalize()} 驱动)")
    mode_str = "安全模式" if safe_mode else "快速模式"
    ctrl.log(f"   目标: {count} 条 | 模式: {mode_str}")
    ctrl.log("=" * 60)

    # 确定文件名前缀：自定义 tag > query 关键词
    base_tag = tag if tag else (_safe_tag(query) if query else None)

    # 统一追加城市+薪资范围
    out_tag = _append_location_tag(base_tag, city_name, salary_min, salary_max)
    ctrl.log(f"   输出前缀: {out_tag or '(default)'}")

    browser = BrowserManager(config=config)
    browser.should_stop = ctrl.should_stop  # send_cdp 里每 2s 检查一次，让 Ctrl+C 有机会生效
    writer = OutputWriter(config["output_dir"], tag=out_tag)
    behavior = BrowserBehavior()

    ctrl.log(f"\n   已有数据: {len(writer.all_jobs)} 条")
    ctrl.log(f"   输出路径: {config['output_dir']}")

    # ===== Step 1: 启动或复用浏览器 =====
    ctrl.log(f"\n[Step 1] 连接 {browser_type.capitalize()} ...")

    connected = False
    if not new_chrome:
        connected = browser.try_connect_existing()

    if not connected:
        ctrl.log(f"   [-] 未找到已有 {browser_type.capitalize()}，启动新实例 ...")
        if not browser.launch("https://www.zhipin.com/web/geek/job"):
            ctrl.log(f"[-] {browser_type.capitalize()} 启动失败")
            ctrl.status("error", "browser launch failed")
            return
        ctrl.log(f"   [+] 新 {browser_type.capitalize()} 就绪")

    # ===== 检查是否已有 BOSS 页面 =====
    boss_page = browser.find_boss_page()

    if keyword_mode:
        # ---- 关键词路线：不做"直接分析该页面"确认，稍后自动导航搜索页 ----
        if boss_page:
            ctrl.log(f"\n   [+] 发现 BOSS 页面: {boss_page['url'][:60]}（将自动按关键词搜索）")
        else:
            # 少见：浏览器已起但还没有 zhipin 标签页，提示打开并登录
            ctrl.wait_user(
                "请在浏览器中打开并登录 BOSS 直聘（https://www.zhipin.com），"
                "完成后点「我已完成，继续」。",
                kind="login",
            )
            boss_page = browser.find_boss_page()
            if not boss_page:
                ctrl.log("[-] 未找到 zhipin.com 页面")
                ctrl.status("error", "no zhipin page")
                return
    else:
        # ---- 手动路线（CLI 类交互）：用户自行搜索/滚动后再分析当前页面 ----
        if boss_page:
            ctrl.log(f"\n   [+] 发现 BOSS 页面: {boss_page['url'][:60]}")
            user_input = ctrl.wait_user(
                "   直接分析该页面? [回车=是 / 输入 wait 手动操作后再分析]: ",
                kind="page_confirm",
            ).strip()
            if user_input.lower() == "wait":
                boss_page = None

        if not boss_page:
            ctrl.log("\n" + "=" * 60)
            ctrl.log("[*] 请在浏览器中操作:")
            ctrl.log("    1. 登录 BOSS 直聘: https://www.zhipin.com/web/geek/job")
            ctrl.log("    2. 搜索你想要的岗位关键词")
            ctrl.log("    3. 尽量往下滚动，加载更多岗位")
            ctrl.log("    4. 回到终端按回车")
            ctrl.log("=" * 60)
            ctrl.wait_user("\n[等待中...按回车开始分析]: ", kind="confirm")

            boss_page = browser.find_boss_page()
            if not boss_page:
                ctrl.log("[-] 未找到 zhipin.com 页面")
                ctrl.status("error", "no zhipin page")
                return

    # ===== Step 2: 连接 WebSocket =====
    ctrl.log("\n[Step 2] 连接 WebSocket ...")
    ws_url = boss_page.get("webSocketDebuggerUrl", "")
    ctrl.log(f"   页面: {boss_page['url'][:60]}")

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
            # ── L3: 先强制导航到 BOSS，确保在正确域内再 probe ───────────
            _dt("L3", "_ensure_logged_in", "pre_nav_to_boss")
            try:
                browser.evaluate("location.href='https://www.zhipin.com/web/geek/job'")
                _dt("L3", "_ensure_logged_in", "pre_nav_ok")
            except Exception as exc:
                _dt("L3", "_ensure_logged_in", "pre_nav_exc", {"exc": str(exc)})
            time.sleep(1.5)

            _dt("L2", "_ensure_logged_in", "probe_start")
            state, source = _probe_login(browser)
            _dt("L2", "_ensure_logged_in", "probe_result", {"state": state, "source": source})

            # 容错：probe 返回 "login"（JS 误判：已登录页残留登录入口元素）时重检一次
            if state == "login":
                _dt("L2", "_ensure_logged_in", "probe_retry")
                state, source = _probe_login(browser)
                _dt("L2", "_ensure_logged_in", "probe_retry_result", {"state": state, "source": source})

            if state == "in":
                _dt("L2", "_ensure_logged_in", "already_logged_in")
                ctrl.log("   [+] 登录态确认：已登录")
                return True

            # 未登录或未知 → 进入扫码登录循环
            _dt("L2", "_ensure_logged_in", "need_login", {"probe_state": state})
            ctrl.log("   [!] 检测到尚未登录 BOSS（或登录态无法确认）")

            while True:
                if ctrl.should_stop():
                    _dt("L2", "_ensure_logged_in", "stopped_by_user")
                    return False

                # ── L2a: 主动导航到登录入口页（确保浏览器在正确的扫码页面）────
                _dt("L3", "_ensure_logged_in", "nav_to_login_page")
                try:
                    browser.evaluate("location.href='https://www.zhipin.com/web/user/?ka=header-login'")
                    _dt("L3", "_ensure_logged_in", "nav_to_login_page_ok")
                except Exception as exc:
                    _dt("L3", "_ensure_logged_in", "nav_to_login_page_exc", {"exc": str(exc)})
                time.sleep(1.5)

                ctrl.log("   [*] 请在浏览器中扫码登录 BOSS 直聘")
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
                if not _reconnect_boss(browser, ctrl):
                    ctrl.log("   [!] 未找到可用的 BOSS 标签页，请确认浏览器未被关闭")
                    _dt("L1", "_ensure_logged_in", "reconnect_failed")
                    continue

                # ── L2b: 强制刷新页面后再检测（避免旧 DOM 导致 probe 误判）────
                _dt("L3", "_ensure_logged_in", "reload_before_probe")
                try:
                    browser.evaluate("location.reload()")
                    _dt("L3", "_ensure_logged_in", "reload_ok")
                except Exception as exc:
                    _dt("L3", "_ensure_logged_in", "reload_exc", {"exc": str(exc)})
                time.sleep(2.0)

                state, source = _probe_login(browser)
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

        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(current)

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

        if "zhipin.com/web/geek/job" in current:
            qs = parse_qs(parsed_url.query)
            
            # 1. Query match (comparing decoded query string)
            current_query = qs.get("query", [""])[0]
            query_match = (current_query == query)
            
            # 2. City match
            current_city = qs.get("city", [""])[0]
            expected_city = str(city_code) if city_code else ""
            city_match = (current_city == expected_city)
            
            # 3. Salary match
            if salary_fuzzy:
                expected_salary_code = ""
            else:
                expected_salary_code = get_salary_code(salary_min, salary_max) or ""
            current_salary = qs.get("salary", [""])[0]
            salary_match = (current_salary == expected_salary_code)
            
            # 4. Job Type match
            expected_job_type = str(job_type) if job_type else ""
            current_job_type = qs.get("jobType", [""])[0]
            job_type_match = (current_job_type == expected_job_type)
            
            # 5. Degree match
            current_degree_str = qs.get("degree", [""])[0]
            current_degrees = [d for d in current_degree_str.split(",") if d] if current_degree_str else []
            expected_degrees = [str(d) for d in (degrees or []) if d]
            degree_match = (set(current_degrees) == set(expected_degrees))
            
            # 6. Experience match
            current_exp_str = qs.get("experience", [""])[0]
            current_exps = [e for e in current_exp_str.split(",") if e] if current_exp_str else []
            expected_exps = [str(e) for e in (experience or []) if e]
            experience_match = (set(current_exps) == set(expected_exps))

            _dt("collect-start", "run_collection.page_reuse_check", "match_results", {
                "query_match": query_match,
                "city_match": city_match,
                "salary_match": salary_match,
                "job_type_match": job_type_match,
                "degree_match": degree_match,
                "experience_match": experience_match
            })
            
            if (query_match and city_match and salary_match and 
                    job_type_match and degree_match and experience_match):
                login_state, login_src = _probe_login(browser)
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
            nav_status = "ok"
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

            nav_status = _goto_search(
                browser, query, city_code, ctrl,
                job_type=job_type,
                degrees=degrees,
                experience=experience,
                salary_min=salary_min,
                salary_max=salary_max,
                salary_fuzzy=salary_fuzzy
            )
            _dt("L3", "run_collection", "goto_search_done", {"status": nav_status})

        # ── L4: 搜索结果等待循环（重连后 / 验证后 / 页面卡住时复用）────
        while nav_status != "ok":
            if ctrl.should_stop():
                ctrl.log("\n[*] 已停止")
                browser.disconnect()
                ctrl.status("stopped")
                return

            if nav_status == "login":
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
                        browser.evaluate("location.href='https://www.zhipin.com/web/user/?ka=header-login'")
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
                    if not _reconnect_boss(browser, ctrl):
                        ctrl.log("   [!] 未找到可用的 BOSS 标签页，请确认浏览器未被关闭")
                        continue

                    # ── L3b: 强制刷新后再 probe ───────────────────────────────
                    _dt("L3", "run_collection", "login_loop_reload_before_probe")
                    try:
                        browser.evaluate("location.reload()")
                        _dt("L3", "run_collection", "login_loop_reload_ok")
                    except Exception as exc:
                        _dt("L3", "run_collection", "login_loop_reload_exc", {"exc": str(exc)})
                    time.sleep(2.0)

                    state, source = _probe_login(browser)
                    _dt("L2", "run_collection", "reprobe_after_relogin", {"state": state, "source": source})

                    if state == "in":
                        _dt("L2", "run_collection", "relogin_confirmed")
                        ctrl.log("   [+] 重新登录确认")
                        break
                    else:
                        ctrl.log("   [!] 仍未确认登录态，请确认扫码成功并在 APP 端点击确认")

                # L2→L3: 登录确认后重新导航
                _dt("L3", "run_collection", "relayout_after_relogin", {"query": query})
                nav_status = _goto_search(
                    browser, query, city_code, ctrl,
                    job_type=job_type,
                    degrees=degrees,
                    experience=experience,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_fuzzy=salary_fuzzy
                )
                _dt("L3", "run_collection", "relayout_done", {"status": nav_status})
            else:
                # timeout：已登录但页面加载慢
                _dt("L4", "run_collection", "status_timeout_wait_user")
                ctrl.log("   [!] 已登录但搜索结果尚未加载出来")
                ctrl.wait_user(
                    "请在【浏览器窗口】中确认页面后点「我已完成，继续」 ...",
                    kind="page_confirm",
                )
                _dt("L1", "run_collection", "reconnect_after_timeout_wait")
                if not _reconnect_boss(browser, ctrl):
                    ctrl.log("   [!] 未找到可用的 BOSS 标签页，请确认浏览器未被关闭")
                nav_status = _goto_search(
                    browser, query, city_code, ctrl,
                    job_type=job_type,
                    degrees=degrees,
                    experience=experience,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_fuzzy=salary_fuzzy
                )
                _dt("L3", "run_collection", "relayout_after_timeout", {"status": nav_status})

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
    vue_hit = 0       # Vue 面板直读成功次数 (本地读取)
    start_idx = len(writer.all_jobs) + 1
    processed_sids = set()
    last_scroll_top = -1  # 追踪滚动位置

    def _emit_progress():
        ctrl.progress(success_count, count, {
            "success": success_count, "fail": fail_count, "skip": skip_count,
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
        jobs = VueExtractor.extract(browser)
        if not jobs:
            ctrl.log("   [*] 页面上未探测到岗位，尝试向下滚动加载 ...")
            behavior.auto_scroll_list(browser)
            _interruptible_sleep(ctrl, 2)
            # 再次检查
            jobs = VueExtractor.extract(browser)
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
                    jobs = VueExtractor.extract(browser)
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
                    _reconnect_boss(browser, ctrl)
                    _goto_search(
                        browser, query, city_code, ctrl,
                        job_type=job_type,
                        degrees=degrees,
                        experience=experience,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        salary_fuzzy=salary_fuzzy
                    )
                continue

        # 遍历当前列表中的岗位
        for job_meta in jobs:
            if success_count >= count:
                break
            if ctrl.should_stop():
                break
            if ctrl.should_pause():
                ctrl._wait_paused()
                if ctrl.should_stop():
                    break

            sid = job_meta.get("securityId")
            if not sid or sid in processed_sids:
                continue

            # === 熔断检测：登录失效/数据脱敏 ===
            salary_desc = job_meta.get("salaryDesc", "")
            if not salary_desc or "****" in salary_desc:
                ctrl.log(f"\n  [BREAK] 熔断保护: 检测到异常薪资数据 ('{salary_desc}')")
                ctrl.log(f"      这通常意味着登录已过期或页面未完全加载。")
                ctrl.log(f"      请在浏览器中确认登录状态，【手动刷新页面】。")
                ctrl.wait_user("  [>] 处理完成后按回车，程序将重新扫描页面 ...", kind="login")
                # 跳出 for 循环，回到 while 开头重新执行 VueExtractor.extract(browser)
                break

            processed_sids.add(sid)
            job_name = job_meta.get("jobName", "?")
            brand_name = job_meta.get("brandName", "")

            # === 薪资粗筛：列表 salaryDesc 超出请求区间则跳过（在提取详情前，省时间）===
            if (salary_min is not None or salary_max is not None) and \
                    not salary_in_range(salary_desc, salary_min, salary_max):
                skip_count += 1
                ctrl.log(f"  [SKIP] 薪资不符: {job_name[:20]} ({salary_desc})")
                _emit_progress()
                continue

            # === 查重 ===
            if writer.is_duplicate(job_name, brand_name):
                skip_count += 1
                ctrl.log(f"  [SKIP] 重复: {job_name[:20]} | {brand_name[:10]}")
                _emit_progress()
                continue

            # === 记录点击前滚动位置 ===
            scroll_before = behavior.get_scroll_position(browser)
            scroll_top_before = scroll_before.get("scrollTop", 0)

            # === 通过 securityId 精确点击卡片 (不再用名字匹配) ===
            clicked, card_pos, card_total = behavior.click_card_by_sid(browser, sid, job_name)

            if not clicked:
                fail_count += 1
                ctrl.log(f"  [-] 未找到卡片: {job_name[:25]} (页面共{card_total}张)")
                _emit_progress()
                continue

            # === 检测回跳 ===
            scroll_after = behavior.get_scroll_position(browser)
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
            detail = DetailPanelReader.read_detail(browser, sid, max_wait=1.5)

            if detail.get("success"):
                vue_hit += 1
                source = "vue-panel"

                total_idx = start_idx + success_count
                writer.save_job(detail, total_idx)
                success_count += 1

                # === 数据读取后的延时等待（可被中止）===
                if safe_mode:
                    behavior.scroll_detail(browser)
                    delay = behavior.get_browse_delay()
                    _interruptible_sleep(ctrl, delay)
                else:
                    _interruptible_sleep(ctrl, 0.5)

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

            # === 间隔休息 ===
            if safe_mode and success_count > 0 and success_count % 12 == 0:
                behavior.step_break()

        # === for 结束后：如果没有任何进展（全部跳过），触发滚动加载更多 ===
        if success_count == prev_success_count and not ctrl.should_stop():
            _dt("H4", "run_collection", "scroll_for_more_start", {"success": success_count, "prev": prev_success_count})
            ctrl.log(f"   [*] 本批已处理完，滚动加载更多 ...")
            behavior.auto_scroll_list(browser)
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
        ctrl.log(f"   跳过:   {skip_count} 条 (重复)")
    ctrl.log(f"   -------")
    ctrl.log(f"   Vue面板直读(currentJob): {vue_hit} 次")
    ctrl.log(f"   JSON:   {writer.json_path}")
    ctrl.log(f"   MD:     {writer.md_path}")
    ctrl.log(f"   累计:   {len(writer.all_jobs)} 条")
    ctrl.log("=" * 60)
    ctrl.log(f"\n   [*] {browser_type.capitalize()} 保持运行 (端口 {browser.port})，下次可复用")

    browser.disconnect()
    ctrl.status("stopped" if stopped else "done", {
        "success": success_count, "fail": fail_count, "skip": skip_count,
        "json": writer.json_path, "md": writer.md_path, "total": len(writer.all_jobs),
    })
