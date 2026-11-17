"""按计划在浏览器里逐条执行：打开详情 → 点「立即沟通」→ 填招呼语 → 跳聊天页。

只填不发送：所有操作止于把文本写进输入框，发送按钮永远由人点。
串行执行 + 间隔延时，不做并发——点「立即沟通」本身就是一次沟通，
风控看的就是这个动作的频率。
"""
import json
import random
import time

import requests

from src.config import get_config
from src.core.browser import BrowserManager
from src.core.js_loader import load_js
from src.tracking import Tracker, track_key

CHAT_PAGE = "https://www.zhipin.com/web/geek/chat"


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


def goto(bm, url: str) -> bool:
    bm.evaluate("location.href=" + json.dumps(url))
    time.sleep(0.8)
    return _wait_ready(bm)


def click_chat(bm, attempts: int = 3, interval: float = 0.6) -> dict:
    """点「立即沟通」：优先 CDP 原生点击（能触发 SPA 处理器），失败退回 element.click()。"""
    locate = load_js("locate_chat_button.js")
    js_click = load_js("click_chat.js")
    for _ in range(attempts):
        try:
            raw = bm.get_value(bm.evaluate(locate))
            info = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception as exc:  # noqa: BLE001
            info = {"ok": False, "reason": f"定位失败: {exc}"}
        if info.get("ok"):
            bm.bring_to_front()
            bm.native_click(info["x"], info["y"])
            time.sleep(1.0)
            return info
        time.sleep(interval)
    # 兜底：老办法，直接在页面里 click()
    try:
        raw = bm.get_value(bm.evaluate(js_click))
        return json.loads(raw) if isinstance(raw, str) else (raw or {"ok": False})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}
    last = {"ok": False, "reason": "未执行"}
    for _ in range(attempts):
        try:
            raw = bm.get_value(bm.evaluate(js))
            last = json.loads(raw) if isinstance(raw, str) else (raw or last)
        except Exception as exc:  # noqa: BLE001
            last = {"ok": False, "reason": f"执行异常: {exc}"}
            break
        if last.get("ok"):
            time.sleep(0.6)
            return last
        time.sleep(interval)
    return last


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


_OPEN_CONV_JS = r"""
(() => {
  const rows = Array.from(document.querySelectorAll('.user-list-content ul li'));
  if (!rows.length) return JSON.stringify({ ok: false, reason: '会话列表为空' });
  const hints = __HINTS__;
  const norm = el => (el.innerText || '').replace(/\s+/g, ' ');
  const hit = rows.find(r => hints.some(h => h && norm(r).includes(h)));
  const target = hit || rows[0];
  target.scrollIntoView({ block: 'center' });
  const r = target.getBoundingClientRect();
  if (r.width < 20 || r.height < 10) return JSON.stringify({ ok: false, reason: '会话条目不可见' });
  return JSON.stringify({
    ok: true, matched: !!hit,
    x: Math.round(r.left + r.width / 2),
    y: Math.round(r.top + r.height / 2),
    text: norm(target).slice(0, 60),
  });
})()
"""


def _input_ready(bm) -> bool:
    try:
        if "geek/chat" not in (bm.get_value(bm.evaluate("location.href")) or ""):
            return False
        raw = bm.get_value(bm.evaluate(
            "(() => { for (const e of document.querySelectorAll('textarea, [contenteditable=\'true\']')) {"
            " const r = e.getBoundingClientRect();"
            " if (r.width > 40 && r.height > 8) return true; } return false; })()"))
        return bool(raw)
    except Exception:
        return False


def open_conversation(bm, hints=None, timeout: float = 12.0) -> dict:
    """在聊天页点开会话，等输入框变成可见。

    li.click() 触发不了 Vue 的选择逻辑（实测点击后仍无选中态），
    必须用 CDP 设备级鼠标事件点坐标。新会话排在最前，优先按公司 /
    招聘者名字匹配，匹配不到退回第一条。
    """
    js = _OPEN_CONV_JS.replace("__HINTS__", json.dumps([h for h in (hints or []) if h],
                                                      ensure_ascii=False))
    try:
        raw = bm.get_value(bm.evaluate(js))
        res = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"定位会话失败: {exc}"}
    if not res.get("ok"):
        return res

    bm.bring_to_front()
    for attempt in range(3):
        bm.native_click(res["x"], res["y"])
        deadline = time.time() + timeout / 2
        while time.time() < deadline:
            if _input_ready(bm):
                return res | {"input_ready": True, "clicks": attempt + 1}
            time.sleep(0.4)
        time.sleep(0.5)
    return res | {"input_ready": False, "clicks": 3}


def fill_greeting(bm, text: str, attempts: int = 6) -> dict:
    js = load_js("fill_greeting.js", {"__TEXT__": json.dumps(text, ensure_ascii=False)})
    last = {"ok": False, "reason": "未执行"}
    for _ in range(attempts):
        try:
            raw = bm.get_value(bm.evaluate(js))
            last = json.loads(raw) if isinstance(raw, str) else (raw or last)
        except Exception as exc:  # noqa: BLE001
            last = {"ok": False, "reason": f"执行异常: {exc}"}
        if last.get("ok"):
            return last
        time.sleep(0.6)
    return last


def open_browser(browser_type: str = "chrome") -> BrowserManager:
    cfg = get_config(browser_type)
    bm = BrowserManager(config=cfg)
    if not bm.try_connect_existing():
        raise DispatchError("没有可连接的浏览器。先启动程序并登录 BOSS，再执行 dispatch。")
    page = bm.find_boss_page()
    if not page:
        raise DispatchError("浏览器里没有 zhipin.com 页面，请先打开并登录 BOSS。")
    if not bm.connect_ws(page.get("webSocketDebuggerUrl", "")):
        raise DispatchError("WebSocket 连接失败")
    return bm


def dispatch(items: list, browser_type: str = "chrome", gap=(8.0, 15.0),
             on_event=None, dry: bool = False, interactive: bool = False,
             wait_open: float = 90.0) -> dict:
    """执行计划。items 需含 encrypt_job_id / title / greeting。

    dry=True 只打印将要做什么，不连接浏览器。
    """
    log = on_event or (lambda msg: None)
    todo = [it for it in items if (it.get("greeting") or "").strip()]
    stats = {"ok": 0, "failed": 0, "skipped": 0, "total": len(todo), "outcomes": []}

    if dry:
        for i, it in enumerate(todo, 1):
            log(f"[dry] {i}/{len(todo)} {(it.get('title') or '?')[:20]} → "
                f"job_detail/{it.get('encrypt_job_id')} → 点沟通 → 填 {len(it['greeting'])} 字")
        return stats

    if not todo:
        log("计划里没有可执行的岗位")
        return stats

    bm = open_browser(browser_type)
    tracker = Tracker()
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

            log(f"  [{i}/{len(todo)}] {title} ...")
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

            chat = click_chat(bm)
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
                if _input_ready(bm):
                    ready = True
                    break
                time.sleep(0.5)

            conv = {"ok": True, "input_ready": ready}
            if not ready:
                conv = open_conversation(bm, hints=[it.get("company") or "", it.get("boss") or ""])
            if not conv.get("input_ready") and interactive:
                # 会话列表不响应合成点击：转人工点开，我们只负责等和填
                log(f"     [人] 请在浏览器里点开「{title}」这个会话"
                    f"（最多等 {int(wait_open)}s）...")
                deadline = time.time() + wait_open
                while time.time() < deadline:
                    if _input_ready(bm):
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

            filled = fill_greeting(bm, it["greeting"])
            if not filled.get("ok"):
                stats["failed"] += 1
                stats["outcomes"].append({"eid": eid, "ok": False,
                                          "reason": f"填写失败: {filled.get('reason')}"})
                log(f"     [-] 填写失败: {filled.get('reason')}")
            else:
                stats["ok"] += 1
                stats["outcomes"].append({"eid": eid, "ok": True, "reason": ""})
                time.sleep(2.5)  # 等平台把草稿存下来，太快导航会丢
                log(f"     [+] 已填 {filled.get('length', len(it['greeting']))} 字，未发送")
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
            if "geek/chat" in cur:
                log("[*] 已在聊天页，不再刷新（避免清空草稿）")
            else:
                bm.evaluate("location.href=" + json.dumps(CHAT_PAGE))
                time.sleep(1.0)
                log(f"[*] 已跳到聊天页: {CHAT_PAGE}")
            bm.bring_to_front()
        except Exception as exc:  # noqa: BLE001
            log(f"[!] 跳转聊天页失败: {exc}")
        bm.disconnect()

    return stats
