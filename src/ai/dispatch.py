"""按计划在浏览器里逐条执行：打开详情 → 点「立即沟通」→ 填招呼语 → 跳聊天页。

只填不发送：所有操作止于把文本写进输入框，发送按钮永远由人点。
串行执行 + 间隔延时，不做并发——点「立即沟通」本身就是一次沟通，
风控看的就是这个动作的频率。
"""
import json
import random
import time
from datetime import datetime

import requests

from src.adapters.boss import BossAdapter
from src.config import get_config, load_ai_config
from src.core.browser import BrowserManager
from src.core.js_loader import load_js
from src.ai.activity import is_offline, parse_active_days
from src.runtime import get_runtime
from src.tracking import track_key
from src.utils import chat_input


def _ts() -> str:
    """日志用时间前缀，事后能对上平台上的沟通时间。"""
    return datetime.now().strftime("%H:%M:%S")


class DispatchError(Exception):
    pass


def _wait_ready(bm, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if (bm.get_value(bm.evaluate("document.readyState")) or "") == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _pages(bm) -> list:
    try:
        resp = requests.get(f"http://127.0.0.1:{bm.port}/json", timeout=3)
        return [p for p in resp.json() if p.get("type") == "page"]
    except Exception:
        return []


def _reconnect(bm, page: dict) -> bool:
    try:
        if getattr(bm, "ws", None):
            try:
                bm.ws.close()
            except Exception:
                pass
        return bm.connect_ws(page.get("webSocketDebuggerUrl", ""))
    except Exception:
        return False


def _ensure_page(bm, prefer=("/job_detail/",)) -> bool:
    """挑一个可复用的 zhipin 标签页（优先详情页），避免每轮新开标签。"""
    pages = [p for p in _pages(bm) if "zhipin.com" in (p.get("url") or "")]
    if not pages:
        return False
    for key in prefer:
        for p in pages:
            if key in (p.get("url") or ""):
                return _reconnect(bm, p)
    return _reconnect(bm, pages[0])


def plan_quota(contacted_today: int, daily_limit: int, want: int) -> int:
    """今天还能点几家。daily_limit <= 0 表示不限。"""
    if daily_limit <= 0:
        return want
    return max(0, min(want, daily_limit - contacted_today))


def read_activity(bm) -> dict:
    """读详情页招聘者的活跃状态。读不到返回 ok=False，调用方应放行。"""
    try:
        raw = bm.get_value(bm.evaluate(load_js("read_boss_active.js")))
        return json.loads(raw) if isinstance(raw, str) else (raw or {"ok": False})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}


def goto(bm, url: str) -> bool:
    bm.evaluate("location.href=" + json.dumps(url))
    time.sleep(0.8)
    return _wait_ready(bm)


def connect_chat_tab(bm, timeout: float = 6.0) -> bool:
    """点沟通后可能开新标签：找到 URL 含 geek/chat 的页面并重连。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for p in _pages(bm):
            if "geek/chat" in (p.get("url") or ""):
                if _reconnect(bm, p):
                    _wait_ready(bm, 8)
                    return True
        time.sleep(0.8)
    return False


def wait_chat_page(bm, timeout: float = 10.0) -> bool:
    """点完沟通后页面会整页跳到 /web/geek/chat，旧 WS 随 target 一起失效。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for p in _pages(bm):
            if "geek/chat" in (p.get("url") or ""):
                _reconnect(bm, p)
                time.sleep(1.0)
                return True
        try:
            if "geek/chat" in (bm.get_value(bm.evaluate("location.href")) or ""):
                time.sleep(0.5)
                return True
        except Exception:
            pass  # 跳转中 context 被销毁，正常
        time.sleep(0.5)
    return False


def _blur_input(bm) -> None:
    """失焦——BOSS 的草稿靠 focusout 保存。"""
    chat_input.blur(bm)


def _connect_one(browser_type: str, platform: str | None = None) -> BrowserManager:
    cfg = get_config(browser_type, platform=platform)
    bm = BrowserManager(config=cfg)
    if not bm.try_connect_existing():
        raise DispatchError(f"没有可连接的 {browser_type}")
    page = BossAdapter().pick_target(bm.list_pages())
    if not page:
        raise DispatchError(f"{browser_type} 里没有 zhipin.com 页面")
    if not bm.connect_ws(page.get("webSocketDebuggerUrl", "")):
        raise DispatchError(f"{browser_type} WebSocket 连接失败")
    return bm


def open_browser(browser_type: str = "chrome", platform: str | None = None) -> BrowserManager:
    """连已启动的浏览器。采集用哪个浏览器不确定时，两个都试一遍。"""
    order = [browser_type] + [b for b in ("chrome", "edge") if b != browser_type]
    errors = []
    for bt in order:
        try:
            return _connect_one(bt, platform)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    raise DispatchError(
        "没有可连接的浏览器（试过 " + " / ".join(order) + "）：" + "；".join(errors)
    )


def dispatch(items: list, browser_type: str = "chrome", gap=None,
             on_event=None, dry: bool = False, interactive: bool = False,
             wait_open: float = 90.0, force_refill: bool = False,
             tracker=None, platform: str | None = None) -> dict:
    """执行计划。items 需含 encrypt_job_id / title / greeting。

    dry=True 只打印将要做什么，不连接浏览器。tracker 由 runtime 注入，
    不传时取该平台的共享实例，保证配额与状态锁只有一个。
    """
    log = on_event or (lambda msg: None)
    todo = [it for it in items if (it.get("greeting") or "").strip()]
    stats = {"ok": 0, "failed": 0, "skipped": 0, "total": len(todo), "outcomes": []}
    tracker = tracker or get_runtime(platform, browser_type).tracker

    # ---- 硬约束：每日额度 + 不重复联系 ----
    # 点「立即沟通」对方能收到通知，还有人挂自动回复按学历筛人。
    # 所以宁可少投，也不能把同一批岗位反复点、或一天点太多。
    today = datetime.now().strftime("%Y-%m-%d")
    already = tracker.all()
    contacted_today = sum(
        1 for v in already.values()
        if str(v.get("updated_at", "")).startswith(today)
        and v.get("status") in ("applied", "shortlisted")
    )
    _ai_cfg = load_ai_config()
    if gap is None:
        gap = (_ai_cfg.get("fill_gap_min", 8.0), _ai_cfg.get("fill_gap_max", 15.0))
    gap = (float(gap[0]), float(gap[1]))
    daily_limit = _ai_cfg.get("daily_limit", 0)   # 0 或负数 = 不限
    max_inactive_days = _ai_cfg.get("max_inactive_days", 3)
    unlimited = daily_limit <= 0
    remaining = plan_quota(contacted_today, daily_limit, len(todo))

    fresh = []
    for it in todo:
        key = track_key(it.get("security_id") or "", it.get("encrypt_job_id") or "")
        if not force_refill and (already.get(key) or {}).get("status") in ("applied", "shortlisted"):
            stats["skipped"] += 1
            continue
        fresh.append(it)

    if len(fresh) != len(todo):
        log(f"[*] 跳过 {len(todo) - len(fresh)} 条已联系过的岗位")
    todo = fresh[:remaining] if remaining else []
    stats["total"] = len(todo)
    if not unlimited and remaining <= 0:
        log(f"[!] 今日已联系 {contacted_today} 家，达到上限 {daily_limit}，今天不再点")
        return stats
    if force_refill:
        log("[*] --force-refill：跳过「已联系过」过滤，只为补回草稿")
    if unlimited:
        log(f"[*] 今日已联系 {contacted_today} 家，未设上限，本次处理 {len(todo)} 家")
    else:
        log(f"[*] 今日已联系 {contacted_today} 家，本次最多再点 {remaining} 家（上限 {daily_limit}）")

    if dry:
        for i, it in enumerate(todo, 1):
            log(f"[dry] {i}/{len(todo)} {(it.get('title') or '?')[:20]} → "
                f"job_detail/{it.get('encrypt_job_id')} → 点沟通 → 填 {len(it['greeting'])} 字")
        return stats

    if not todo:
        log("计划里没有可执行的岗位")
        return stats

    bm = open_browser(browser_type, platform)
    adapter = BossAdapter(bm)
    if not _ensure_page(bm):
        log("[!] 找不到可复用的 BOSS 标签页")
    try:
        for i, it in enumerate(todo, 1):
            title = (it.get("title") or "?")[:20]
            eid = it.get("encrypt_job_id") or ""
            sid = it.get("security_id") or ""
            if not eid and not sid:
                stats["skipped"] += 1
                stats["outcomes"].append({"eid": eid, "ok": False, "reason": "缺岗位 ID"})
                log(f"  [{i}/{len(todo)}] 缺岗位 ID，跳过: {title}")
                continue

            log(f"  {_ts()} [{i}/{len(todo)}] {title} ...")
            if not _ensure_page(bm):
                stats["failed"] += 1
                stats["outcomes"].append({"eid": eid, "ok": False, "reason": "没有可用标签页"})
                log("     [-] 没有可用标签页")
                continue

            if eid:
                url = f"https://www.zhipin.com/job_detail/{eid}.html"
                if not goto(bm, url):
                    log("     [!] 详情页加载超时，继续尝试")
            else:
                log("     [!] 缺少 encryptJobId，无法直接打开详情页")

            # 招聘者不在线就别点：对方收不到、还可能被自动回复筛掉
            act = read_activity(bm)
            if act.get("ok"):
                days = parse_active_days(act.get("text", ""))
                if days is None:
                    log(f"     [.] 活跃时间读不出（{act.get('text', '')[:24]}），照常投")
                elif is_offline(act.get("text", ""), max_inactive_days):
                    stats["skipped"] += 1
                    stats["outcomes"].append({"eid": eid, "ok": False,
                                              "reason": f"招聘者已 {days} 天未活跃",
                                              "at": datetime.now().isoformat(timespec="seconds")})
                    log(f"     {_ts()} [-] 跳过：招聘者已 {days} 天未活跃")
                    time.sleep(random.uniform(*gap))
                    continue
                else:
                    log(f"     [.] 招聘者 {days} 天内活跃过")

            chat = adapter.open_chat(eid)
            # 点中按钮后页面会整页跳到聊天页（旧 WS 失效），必须先等/重连
            if not wait_chat_page(bm):
                if not chat.get("ok"):
                    stats["failed"] += 1
                    stats["outcomes"].append({"eid": eid, "ok": False,
                                              "reason": f"没点到「立即沟通」: {chat.get('reason')}"})
                    log(f"     [-] 没点到「立即沟通」: {chat.get('reason')}")
                    time.sleep(random.uniform(*gap))
                    continue
                log("     [!] 没跳到聊天页，尝试直接用当前页")

            # 点完「立即沟通」后会话一般会自己打开；输入框可能是 textarea 也可能是 contenteditable
            ready = False
            deadline = time.time() + 15
            while time.time() < deadline:
                if adapter.chat_input_ready():
                    ready = True
                    break
                time.sleep(0.5)

            conv = {"ok": True, "input_ready": ready}
            if not ready:
                conv = adapter.open_conversation(hints=[it.get("company") or "", it.get("boss") or ""])
            if not conv.get("input_ready") and interactive:
                # 会话列表不响应合成点击：转人工点开，我们只负责等和填
                log(f"     [人] 请在浏览器里点开「{title}」这个会话"
                    f"（最多等 {int(wait_open)}s）...")
                deadline = time.time() + wait_open
                while time.time() < deadline:
                    if adapter.chat_input_ready():
                        conv = {"ok": True, "input_ready": True}
                        break
                    time.sleep(0.8)
                else:
                    log("     [-] 超时，没等到会话打开")
            if not conv.get("ok") or not conv.get("input_ready"):
                stats["failed"] += 1
                stats["outcomes"].append({"eid": eid, "ok": False,
                                          "reason": f"打不开会话: {conv.get('reason')}"})
                log(f"     [-] 打不开会话: {conv.get('reason')}")
                time.sleep(random.uniform(*gap))
                continue
            log(f"     [.] 会话: {conv.get('text', '')[:28]}")

            filled = adapter.fill_greeting(it["greeting"])
            if not filled.get("ok"):
                stats["failed"] += 1
                stats["outcomes"].append({"eid": eid, "ok": False,
                                          "reason": f"填写失败: {filled.get('reason')}"})
                log(f"     [-] 填写失败: {filled.get('reason')}")
            else:
                stats["ok"] += 1
                stats["outcomes"].append({"eid": eid, "ok": True, "reason": "",
                                          "at": datetime.now().isoformat(timespec="seconds")})
                _blur_input(bm)                              # 失焦才会触发草稿保存
                time.sleep(_ai_cfg.get("fill_settle", 2.5))  # 再等一会儿，别急着导航
                log(f"     {_ts()} [+] 已填 {filled.get('length', len(it['greeting']))} 字，未发送")
                try:
                    tracker.set(track_key(sid, eid), "shortlisted", it["greeting"][:80])
                except Exception:
                    pass

            time.sleep(random.uniform(*gap))
    finally:
        try:
            _ensure_page(bm)
            cur = ""
            try:
                cur = bm.get_value(bm.evaluate("location.href")) or ""
            except Exception:
                pass
            chat_url = adapter.chat_url()
            if "geek/chat" in cur:
                log("[*] 已在聊天页，不再刷新（避免清空草稿）")
            else:
                bm.evaluate("location.href=" + json.dumps(chat_url))
                time.sleep(1.0)
                log(f"[*] 已跳到聊天页: {chat_url}")
            bm.bring_to_front()
        except Exception as exc:  # noqa: BLE001
            log(f"[!] 跳转聊天页失败: {exc}")
        bm.disconnect()

    return stats
