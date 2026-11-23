"""按投递能力执行的引擎侧入口。

适配器只声明能力（``delivery_mode``），这里按能力分支，不看站点名：

    prefill_chat     只填草稿，永不在聊天里发消息（BOSS，走 ai.dispatch）
    apply_then_chat  点投递 → 进聊天 → 发一条消息（智联）
    unsupported      不支持投递

不可逆动作只有 ``apply_then_chat`` 会真的执行，且必须同时满足：
配置两个开关都开、传了 tracker（否则无法查重与计数）、未超过日限额。
没有 tracker 时直接拒绝，避免出现「投了但没人记得」的状态。
"""
from datetime import datetime

from src.adapters.base import PlatformAdapter
from src.adapters.registry import create_adapter
from src.config import get_config, load_apply_config
from src.core.browser import BrowserManager
from src.tracking import Tracker, track_key

DELIVERY_MODES = {"prefill_chat", "apply_then_chat", "unsupported"}


def delivery_mode_of(adapter) -> str:
    """未知/缺省能力按不支持处理，绝不默认允许投递。"""
    mode = getattr(adapter, "delivery_mode", "unsupported")
    return mode if mode in DELIVERY_MODES else "unsupported"


def connect(platform: str, browser_type: str = "chrome") -> tuple[BrowserManager, PlatformAdapter]:
    """连该平台已启动的浏览器，返回 (BrowserManager, 适配器)。只连接，不动页面。"""
    cfg = get_config(browser_type, platform=platform)
    bm = BrowserManager(config=cfg)
    if not bm.try_connect_existing():
        raise RuntimeError(f"{platform} 的浏览器还没启动，先跑一次采集")
    adapter = create_adapter(platform, bm)
    page = adapter.pick_target(bm.list_pages())
    if not page:
        raise RuntimeError(f"{browser_type} 里没有 {platform} 页面")
    if not bm.connect_ws(page.get("webSocketDebuggerUrl", "")):
        raise RuntimeError(f"{browser_type} WebSocket 连接失败")
    return bm, adapter


def readiness(adapter, job_id: str) -> dict:
    """只读体检：离真投还差什么。不点任何按钮。"""
    mode = delivery_mode_of(adapter)
    gates = load_apply_config()
    missing: list[str] = []

    if mode != "apply_then_chat":
        return {"ok": False, "delivery_mode": mode, "gates": gates,
                "state": None, "missing": [f"delivery_mode={mode}"]}

    state = adapter.apply_state(job_id) or {}
    applied = bool(state.get("already_apply") or state.get("has_applied_position"))
    if not gates["enabled"]:
        missing.append("apply.enabled=false")
    if not gates["send_message"]:
        missing.append("apply.send_message=false")
    if not state.get("ok"):
        missing.append(f"页面状态读取失败: {state.get('reason') or 'unknown'}")
    elif not state.get("found"):
        missing.append("岗位不在当前列表")
    else:
        if not state.get("logged_in"):
            missing.append("未登录")
        if not state.get("selected"):
            missing.append("岗位未在详情面板选中（执行时会先点卡片）")
        else:
            button = state.get("button") or {}
            if not button.get("found"):
                missing.append("定位不到「立即投递」按钮")
            elif button.get("disabled"):
                missing.append("「立即投递」按钮不可点")
        if applied:
            missing.append("该岗位已投递过")

    return {"ok": not missing, "delivery_mode": mode, "gates": gates,
            "state": state, "applied": applied, "missing": missing}


def applied_today(tracker, today: str | None = None) -> int:
    today = today or datetime.now().strftime("%Y-%m-%d")
    return sum(
        1 for v in tracker.all().values()
        if v.get("status") == "applied"
        and str(v.get("updated_at", "")).startswith(today)
    )


def run_apply(adapter, job: dict, text: str, tracker: Tracker | None = None,
              config: dict | None = None, on_event=None) -> dict:
    """执行一条投递：能力闸 → 配置闸 → 日限额 → apply → tracking → send_message。

    返回的 ``submitted`` / ``sent`` 都来自适配器对页面的实际确认，不由这里推断。
    """
    log = on_event or (lambda msg: None)
    mode = delivery_mode_of(adapter)
    job_id = str(job.get("job_id") or job.get("encrypt_job_id") or "")
    company = job.get("company") or ""

    if mode != "apply_then_chat":
        return {"ok": False, "mode": mode, "submitted": False, "sent": False,
                "reason": f"unsupported: delivery_mode_{mode}"}

    cfg = config or load_apply_config()
    if not (cfg.get("enabled") and cfg.get("send_message")):
        return {"ok": False, "mode": mode, "submitted": False, "sent": False,
                "reason": "unsupported: apply_disabled"}

    # 没有 tracker 就不投：查重和计数都靠它，否则会出现「投了但没人记得」。
    if tracker is None:
        return {"ok": False, "mode": mode, "submitted": False, "sent": False,
                "reason": "unsupported: no_tracker"}

    limit = int(cfg.get("daily_limit") or 0)
    if limit > 0 and applied_today(tracker) >= limit:
        return {"ok": False, "mode": mode, "submitted": False, "sent": False,
                "reason": "skipped: daily_limit"}

    result = dict(adapter.apply(job_id) or {})
    result["mode"] = mode
    if not result.get("submitted"):
        return result

    try:
        tracker.set(track_key("", job_id), "applied",
                    f"{company} {job.get('title') or ''}".strip())
    except Exception as exc:  # noqa: BLE001
        # 投递已经发生，状态写不进去只能留日志，不能让调用方误以为没投。
        log(f"[apply] 投递已确认，但写 tracking 失败: {exc}")

    body = (text or "").strip()
    if not body:
        result.update({"sent": False, "send_reason": "no_text"})
        return result

    sent = dict(adapter.send_message(body) or {})
    result["sent"] = bool(sent.get("sent"))
    result["send"] = sent
    return result
