"""FastAPI 后端：REST 控制接口 + WebSocket 实时事件流 + 静态前端托管。"""
import asyncio
import glob
import importlib
import json
import pkgutil
import threading
import uuid
import os
import pathlib
import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import src.adapters
from src.adapters.registry import create_adapter
from src.config import DEFAULT_PLATFORM, get_config, save_config, load_start_params, save_start_params
from src.core.cities import get_cities, refresh_from_browser


from .session import session
from .tracer import tracer

app = FastAPI(title="BOSS 直聘助手 GUI")

# 开发期前端跑在 Vite (5173)，放开跨域便于联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartParams(BaseModel):
    count: int = 20
    browser_type: str = "chrome"
    site: str = "boss"
    # 可选的平台别名；传了就覆盖 site（run_collection 只认 site）
    platform: str | None = None
    new_chrome: bool = False
    tag: str | None = None
    # 以下字段保留但不再由前端发起（默认关闭关键词路线）
    keyword_search: bool = False
    query: str = ""
    city_code: str | None = None
    city_name: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    tag_sync: bool = False
    safe_mode: bool = True
    fast: bool = False
    speed: str = "slow"
    job_type: str = ""
    degrees: list[str] = []
    experience: list[str] = []
    salary_fuzzy: bool = False


class AckBody(BaseModel):
    payload: str = ""


class ConfigBody(BaseModel):
    browser_type: str = "chrome"
    browser_path: str | None = None
    output_dir: str | None = None


def _dump(model: BaseModel) -> dict:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


_platform_cache: list[dict] | None = None


def platform_catalog() -> list[dict]:
    """已注册平台目录（名字 + 显示名）。

    导入 ``src/adapters`` 下的每个模块触发自注册，再用公开的 ``create_adapter``
    取显示名；``base`` / ``registry`` 这类不注册适配器的模块会被跳过。
    默认平台排第一，其余按名字排序。新增平台只需要建目录，这里不用改。
    """
    global _platform_cache
    if _platform_cache is not None:
        return _platform_cache

    names: list[str] = []
    for info in pkgutil.iter_modules(src.adapters.__path__):
        try:
            importlib.import_module(f"{src.adapters.__name__}.{info.name}")
            create_adapter(info.name)
        except Exception:
            continue
        names.append(info.name)

    names.sort()
    if DEFAULT_PLATFORM in names:
        names.remove(DEFAULT_PLATFORM)
        names.insert(0, DEFAULT_PLATFORM)
    _platform_cache = [
        {"name": name, "display_name": getattr(create_adapter(name), "display_name", "") or name}
        for name in names
    ]
    return _platform_cache


@app.get("/api/platforms")
def api_platforms():
    """给前端平台选择器用的平台列表。"""
    return {"ok": True, "platforms": platform_catalog()}


@app.get("/api/config")
def api_config(browser_type: str = "chrome"):
    cfg = get_config(browser_type)
    return {
        "browser_path": cfg.get("browser_path", ""),
        "profile_dir": cfg.get("profile_dir", ""),
        "output_dir": cfg.get("output_dir", ""),
        "humanize": cfg.get("humanize", {}),
        "running": session.running,
    }


@app.post("/api/config")
def api_save_config(body: ConfigBody):
    """写回 config.yaml（浏览器路径 / 输出目录），返回最新配置。"""
    save_config(
        body.browser_type,
        browser_path=body.browser_path,
        output_dir=body.output_dir,
    )
    cfg = get_config(body.browser_type)
    return {
        "ok": True,
        "browser_path": cfg.get("browser_path", ""),
        "output_dir": cfg.get("output_dir", ""),
    }


@app.get("/api/start-params")
def api_get_start_params():
    """返回已保存的运行参数（从 config.yaml 读取）。"""
    return load_start_params()


@app.post("/api/start-params")
def api_save_start_params(body: dict):
    """保存运行参数到 config.yaml。"""
    ok = save_start_params(body)
    return {"ok": ok}


@app.post("/api/start-params/reset")
def api_reset_start_params():
    """将运行参数重置为系统默认值。"""
    ok = save_start_params({})
    return {"ok": ok}


@app.get("/api/cities")
def api_get_cities():
    """返回城市列表（内置常用城市，缓存优先）。"""
    return {"cities": get_cities()}


@app.post("/api/cities/refresh")
def api_refresh_cities(browser_type: str = "chrome"):
    """基于已登录的浏览器获取完整城市列表，缓存后返回。"""
    cities, error = refresh_from_browser(browser_type)
    if error:
        return {"ok": False, "error": error, "cities": get_cities()}
    return {"ok": True, "cities": cities}


@app.post("/api/start")
def api_start(params: StartParams):
# 手动模式：用户已在浏览器里做完搜索/筛选，不在这里重复校验
    body = _dump(params)
    platform = body.pop("platform", None)
    if platform:
        body["site"] = platform
    trace_id = tracer.start_scope("collect-start")
    tracer.entry("app.py:api_start", "分析任务启动", params.model_dump(), scope="collect-start")
    try:
        task_id = session.start(body)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "task_id": task_id}


@app.post("/api/stop")
def api_stop(task_id: str | None = None):
    session.stop(task_id)
    return {"ok": True}


@app.post("/api/pause")
def api_pause(task_id: str | None = None):
    session.pause(task_id)
    return {"ok": True}


@app.post("/api/resume")
def api_resume(task_id: str | None = None):
    session.resume(task_id)
    return {"ok": True}


@app.post("/api/ack")
def api_ack(body: AckBody, task_id: str | None = None):
    session.ack(body.payload, task_id)
    return {"ok": True}


@app.get("/api/status")
def api_status(task_id: str | None = None):
    ctrl = session.controller(task_id)
    return {
        "task_id": task_id or session.current_task_id,
        "running": session.running,
        "state": ctrl.state if ctrl else "idle",
        "progress": ctrl.latest_progress if ctrl else {"done": 0, "total": 0, "stats": {}},
        "pending_action": ctrl.pending_action if ctrl else None,
    }


@app.get("/api/results")
def api_results(date: str | None = None, output_dir: str | None = None,
                platform: str | None = None):
    """最新（或指定日期）岗位 JSON。

    传 ``platform`` 时按平台解析输出目录；不传时沿用旧行为（``output_dir`` 或默认平台）。
    """
    if platform:
        out = get_config("chrome", platform=platform).get("output_dir", "")
    elif output_dir:
        out = output_dir
    else:
        out = get_config("chrome").get("output_dir", "")
    files = sorted(glob.glob(os.path.join(out, "jobs_*.json")), reverse=True)
    if not files:
        return {"jobs": [], "file": None, "files": []}
    target = files[0]
    if date:
        for f in files:
            if date in os.path.basename(f):
                target = f
                break
    try:
        with open(target, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except Exception:
        jobs = []
    return {
        "jobs": jobs,
        "file": os.path.basename(target),
        "files": [os.path.basename(x) for x in files],
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    # 连接时先推活任务快照；没有活任务时退回最后一次终态，前端刷新后能恢复状态
    for ev in session.snapshot_events():
        await ws.send_json(ev)
    try:
        while True:
            # 一条连接转发所有平台的采集事件，每条事件自带 task_id
            for ev in session.drain_events():
                await ws.send_json(ev)
            await asyncio.sleep(0.15)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@app.post("/__debug_log")
async def api_debug_log(request: Request):
    """Vite 中间件端点：接收前端日志并写入标准 TraceLink"""
    try:
        body = await request.json()
        layer = body.get("layer", "FE-UI")
        fn = body.get("fn", "unknown")
        msg = body.get("msg", "")
        data = body.get("data", {})
        scope = body.get("scope")
        
        # 真正还原前端日志的层级并转发到标准 Tracer
        from tracelink import tracer as standard_tracer
        standard_tracer.custom(layer, fn, msg, data, scope=scope)
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/debug/status")
def api_debug_status():
    """返回调试追踪器状态"""
    return {
        "enabled": tracer.is_enabled(),
        "scopes": tracer.get_enabled_scopes(),
        "active": list(tracer.get_enabled_scopes()),
    }


@app.delete("/__debug_log")
def api_debug_clear():
    """清空日志文件"""
    tracer.clear()
    tracer.reset_files()
    return {"ok": True}


@app.get("/__debug_log")
def api_debug_read():
    """读取日志文件内容（供调试面板使用）"""
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[1]
    log_path = project_root / ".tracelink" / "trace.ndjson"
    try:
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return ""


class ScopesBody(BaseModel):
    scopes: list


class EnableBody(BaseModel):
    enabled: bool


@app.post("/api/debug/scopes")
def api_debug_set_scopes(body: ScopesBody):
    """设置启用的 Scope 列表"""
    scopes = set(body.scopes)
    tracer.enable_all_scopes()  # reset first
    if "*" in scopes:
        pass  # all enabled
    else:
        tracer.disable_all_scopes()
        for s in scopes:
            tracer.enable_scope(s)
    return {"ok": True}


@app.post("/api/debug/enable")
def api_debug_set_enable(body: EnableBody):
    """设置全局开关"""
    tracer.set_enabled(body.enabled)
    return {"ok": True}


@app.get("/__debug_panel")
def api_debug_panel():
    """返回调试面板 HTML"""
    panel_path = pathlib.Path(__file__).resolve().parents[1] / "webui" / "public" / "__debug_panel.html"
    try:
        with open(panel_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception:
        return HTMLResponse(content="<h1>Panel not found</h1>", status_code=404)


# ── 复核队列：状态跟踪 + 浏览器定位 + 招呼语填充 ────────────────────────────

from src.runtime import get_runtime  # noqa: E402
from src.tracking import TrackingError, track_key  # noqa: E402


class TrackBody(BaseModel):
    security_id: str = ""
    encrypt_job_id: str = ""
    status: str
    note: str = ""
    platform: str = ""


class FocusBody(BaseModel):
    security_id: str = ""
    encrypt_job_id: str = ""
    open_chat: bool = True  # 定位后自动点「立即沟通」打开聊天窗


class GreetBody(BaseModel):
    security_id: str = ""
    encrypt_job_id: str = ""
    text: str | None = None


def _job_files() -> list:
    """按时间倒序返回所有采集结果文件。"""
    out = get_config("chrome").get("output_dir", "")
    return sorted(glob.glob(os.path.join(out, "jobs_*.json")), reverse=True)


def _latest_jobs() -> list:
    files = _job_files()
    if not files:
        return []
    try:
        with open(files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _find_job(security_id: str = "", encrypt_job_id: str = "") -> dict | None:
    """优先在最新文件里找；复核历史文件时也能回退到旧文件。"""
    for path in _job_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for j in data:
            if encrypt_job_id and j.get("encrypt_job_id") == encrypt_job_id:
                return j
            if security_id and j.get("security_id") == security_id:
                return j
    return None


def _with_browser(fn, prefer_chat: bool = False, platform: str | None = None):
    """连接到正在运行的调试浏览器，执行 fn(bm, page)。"""
    if session.running_for(platform):
        return {"ok": False, "error": "该平台采集任务正在运行，请先停止再定位"}
    from src.core.browser import BrowserManager
    from src.adapters.boss import BossAdapter

    bm = BrowserManager(config=get_config("chrome", platform=platform))
    if not bm.try_connect_existing():
        return {"ok": False, "error": "没有正在运行的调试浏览器，请先跑一次采集"}
    adapter = BossAdapter()
    # 只考虑本平台真正的标签页；shared_worker 的 URL 里也含 geek-chat，不能选它
    pages = [p for p in bm.list_pages()
             if p.get("type") == "page" and adapter.owns_url(p.get("url", ""))]
    page = None
    if prefer_chat:
        chat = [p for p in pages if "chat" in p.get("url", "")]
        page = chat[-1] if chat else None
    if page is None:
        best = adapter.pick_target(bm.list_pages())
        page = best if (best and best.get("type") == "page") else (pages[0] if pages else None)
    if not page:
        return {"ok": False, "error": "没有找到 BOSS 标签页"}
    try:
        bm.connect_ws(page["webSocketDebuggerUrl"])
        return fn(bm, page)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            bm.disconnect()
        except Exception:
            pass


@app.get("/api/tracking")
def api_tracking(platform: str | None = None):
    return get_runtime(platform).tracker.all()


@app.post("/api/tracking")
def api_tracking_set(body: TrackBody):
    key = track_key(body.security_id, body.encrypt_job_id)
    if not key:
        return {"ok": False, "error": "缺少岗位 ID"}
    try:
        return {"ok": True, "record": get_runtime(body.platform or None).tracker.set(
            key, body.status, body.note)}
    except (ValueError, TrackingError) as exc:
        return {"ok": False, "error": str(exc)}


def _wait_ready(bm, timeout: float = 10.0) -> bool:
    """等待当前标签页导航完成（导航过程中 evaluate 可能短暂失败，忽略重试）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if bm.get_value(bm.evaluate("document.readyState")) == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _click_chat(bm, attempts: int = 6, interval: float = 0.35) -> dict:
    """定位后点「立即沟通」打开聊天窗；面板渲染有延迟，最多重试约 2 秒。"""
    from src.core.js_loader import load_js

    js = load_js("click_chat.js")
    last = {"ok": False, "reason": "未执行"}
    for _ in range(attempts):
        try:
            res = bm.evaluate(js)
            raw = bm.get_value(res)
            if isinstance(raw, str):
                try:
                    last = json.loads(raw)
                except Exception:
                    last = {"ok": False, "reason": raw}
            elif isinstance(raw, dict):
                last = raw
            else:
                last = {"ok": False, "reason": "无效返回值"}
        except Exception as exc:  # noqa: BLE001
            # 点击可能已触发页面跳转并销毁执行上下文，此时无法再确认结果
            last = {"ok": False, "reason": f"执行异常: {exc}"}
            break
        if last.get("ok"):
            time.sleep(0.5)  # 给聊天窗口打开留出时间
            return last
        time.sleep(interval)
    return last


@app.post("/api/focus")
def api_focus(body: FocusBody):
    if not (body.security_id or body.encrypt_job_id):
        return {"ok": False, "error": "缺少岗位 ID"}
    from src.adapters.boss import BossAdapter

    job = _find_job(body.security_id, body.encrypt_job_id) or {}
    platform = job.get("platform") or DEFAULT_PLATFORM
    eid = body.encrypt_job_id or job.get("encrypt_job_id") or ""

    def _run(bm, page):
        # ① 卡片还在当前页面上（同一会话内 securityId 才有效）：直接点，不打断列表
        clicked, pos, total = False, -1, 0
        if body.security_id:
            try:
                click = BossAdapter(bm).click_card(body.security_id)
                clicked, pos, total = click["ok"], click["index"], click["total"]
            except Exception:
                pass
        if clicked:
            result = {"ok": True, "mode": "click", "index": pos, "total": total}
        # ② 不在页面上（列表已刷新/翻页）：用 encryptJobId 直接打开详情页
        elif eid:
            url = f"https://www.zhipin.com/job_detail/{eid}.html"
            bm.evaluate("location.href=" + json.dumps(url))
            _wait_ready(bm, 12)
            result = {"ok": True, "mode": "url", "url": url}
        else:
            return {
                "ok": False,
                "error": "当前页面上找不到这张卡片，且该记录缺少 encryptJobId（旧数据）。重新采集一次即可修复。",
            }

        # ③ 定位后顺手点「立即沟通」，把聊天窗打开（只点按钮，不发消息）
        if body.open_chat:
            result["chat"] = _click_chat(bm)

        # 只切前台，但别插进另一个平台「填招呼语」的真实输入段
        from src.focus_lock import foreground
        with foreground():
            bm.bring_to_front()
        return result

    return _with_browser(_run, platform=platform)


def _default_greeting(job: dict) -> str:
    title = (job.get("title") or "这个岗位").strip()
    skills = [s for s in (job.get("skills") or []) if s][:2]
    if skills:
        return (
            f"您好，我对「{title}」这个岗位很感兴趣。"
            f"我在 {'、'.join(skills)} 方面有实际项目经验，和 JD 里提到的要求比较匹配，"
            f"方便的话想和您进一步聊聊。"
        )
    return f"您好，我对「{title}」这个岗位很感兴趣，方便的话想和您进一步聊聊。"


@app.post("/api/greet")
def api_greet(body: GreetBody):
    if not (body.security_id or body.encrypt_job_id):
        return {"ok": False, "error": "缺少岗位 ID"}
    job = _find_job(body.security_id, body.encrypt_job_id) or {}
    platform = job.get("platform") or DEFAULT_PLATFORM
    text = (body.text or "").strip() or _default_greeting(job)

    def _run(bm, page):
        from src.utils.chat_input import fill_chat_input

        res = fill_chat_input(bm, text)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("reason") or "填充失败"}
        time.sleep(0.5)  # 给平台存草稿留点时间（草稿是 focusout 后异步写的）
        return {"ok": True, "filled": text, "length": res.get("length")}

    return _with_browser(_run, prefer_chat=True, platform=platform)



# ===== AI 筛选 / 招呼语 / 批量填充 =====

class AiScreenBody(BaseModel):
    file: str = ""
    limit: int | None = None
    force: bool = False


class AiFillBody(BaseModel):
    file: str = ""
    browser_type: str | None = None
    platform: str | None = None
    limit: int | None = None
    gap_min: float | None = None   # 留空则用 config.yaml 的 ai.fill_gap_*
    gap_max: float | None = None


class AiGreetingBody(BaseModel):
    file: str = ""
    encrypt_job_id: str = ""
    greeting: str = ""


_ai_fills: dict[str, dict] = {}
_latest_fill_id: str | None = None


def _fill_state(task_id: str | None = None) -> dict | None:
    return _ai_fills.get(task_id or _latest_fill_id or "")


def _ai_plan_path(file_name: str) -> str:
    from src.ai.pipeline import plan_path_for
    cfg = get_config("chrome")
    out = cfg.get("output_dir", "")
    target = file_name or ""
    if not target:
        files = sorted(glob.glob(os.path.join(out, "jobs_*.json")), reverse=True)
        if not files:
            raise ValueError("还没有采集数据")
        target = os.path.basename(files[0])
    return plan_path_for(os.path.join(out, target))


@app.get("/api/ai/plan")
def api_ai_plan(file: str = ""):
    """读取某个采集文件对应的 AI 计划（没跑过就返回 exists=false）。"""
    from src.ai.pipeline import load_plan
    try:
        path = _ai_plan_path(file)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not os.path.exists(path):
        return {"ok": True, "exists": False, "file": os.path.basename(path), "items": []}
    try:
        plan = load_plan(path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "exists": True, "file": os.path.basename(path), **plan}


@app.post("/api/ai/screen")
def api_ai_screen(body: AiScreenBody):
    """对采集文件跑 AI 筛选，生成 ai_plan_*.json。"""
    if session.running:
        return {"ok": False, "error": "采集任务运行中，先停下再筛选"}
    from src.ai.pipeline import build_plan, load_plan
    cfg = get_config("chrome")
    out = cfg.get("output_dir", "")
    target = body.file
    if not target:
        files = sorted(glob.glob(os.path.join(out, "jobs_*.json")), reverse=True)
        if not files:
            return {"ok": False, "error": "还没有采集数据"}
        target = os.path.basename(files[0])
    src_path = os.path.join(out, target)
    if not os.path.exists(src_path):
        return {"ok": False, "error": f"文件不存在: {target}"}
    try:
        logs: list = []
        build_plan(src_path, limit=body.limit, force=body.force, on_event=logs.append)
        plan = load_plan(_ai_plan_path(target))
    except Exception as exc:  # noqa: BLE001
        tracer.entry("app.py:api_ai_screen", "AI 筛选失败", {"error": str(exc)}, scope="error")
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "file": target, "summary": plan.get("summary", {}),
            "items": plan.get("items", []), "log": logs[-40:]}


@app.post("/api/ai/greeting")
def api_ai_greeting(body: AiGreetingBody):
    """保存单条招呼语的编辑。"""
    from src.ai.pipeline import load_plan, save_plan
    try:
        path = _ai_plan_path(body.file)
        plan = load_plan(path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    hit = None
    for it in plan.get("items", []):
        if it.get("encrypt_job_id") == body.encrypt_job_id:
            hit = it
            break
    if not hit:
        return {"ok": False, "error": "计划里没有这条岗位"}
    hit["greeting"] = (body.greeting or "").strip()
    hit["status"] = "planned" if hit["greeting"] else "skip"
    save_plan(plan, path)
    return {"ok": True, "item": hit}


@app.post("/api/ai/fill")
def api_ai_fill(body: AiFillBody):
    """批量填充：逐条点「立即沟通」并把招呼语填进输入框（不发送）。"""
    if session.running:
        return {"ok": False, "error": "采集任务运行中，先停下再填充"}
    if any(state.get("running") for state in _ai_fills.values()):
        return {"ok": False, "error": "批量填充已在运行"}
    from src.ai.dispatch import dispatch
    from src.ai.pipeline import load_plan, save_plan
    try:
        path = _ai_plan_path(body.file)
        plan = load_plan(path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    items = [it for it in plan.get("items", [])
             if it.get("status") == "planned" and it.get("dispatch") != "done"]
    if body.limit:
        items = items[:body.limit]
    if not items:
        return {"ok": False, "error": "计划里没有待填充的岗位"}

    global _latest_fill_id
    fill_id = f"fill-{uuid.uuid4().hex[:10]}"
    state = {"task_id": fill_id, "running": True, "done": 0, "total": len(items),
             "ok": 0, "failed": 0, "log": [], "error": "", "finished": False}
    _ai_fills[fill_id] = state
    _latest_fill_id = fill_id

    def _run():
        def _log(msg):
            state["log"].append(str(msg)[:200])
            if len(state["log"]) > 200:
                state["log"] = state["log"][-100:]
        try:
            gap = (body.gap_min, body.gap_max) if (body.gap_min and body.gap_max) else None
            params = session.params() or {}
            bt = body.browser_type or params.get("browser_type") or "chrome"
            platform = body.platform or params.get("site") or DEFAULT_PLATFORM
            runtime = get_runtime(platform, bt)
            stats = dispatch(items, browser_type=bt, gap=gap, on_event=_log,
                             tracker=runtime.tracker, platform=platform)
            state["ok"] = stats.get("ok", 0)
            state["failed"] = stats.get("failed", 0)
            from src.ai.pipeline import apply_outcomes
            apply_outcomes(plan, stats)
            save_plan(plan, path)
        except Exception as exc:  # noqa: BLE001
            state["error"] = str(exc)
            tracer.entry("app.py:api_ai_fill", "批量填充失败", {"error": str(exc)}, scope="error")
        finally:
            state["running"] = False
            state["finished"] = True

    threading.Thread(target=_run, name=f"ai_fill:{fill_id}", daemon=True).start()
    return {"ok": True, "total": len(items), "task_id": fill_id}


@app.get("/api/ai/fill/status")
def api_ai_fill_status(task_id: str | None = None):
    state = _fill_state(task_id)
    if not state:
        # 与历史响应保持一致：ok 是成功条数，不是布尔值
        return {"ok": 0, "task_id": None, "running": False, "done": 0, "total": 0,
                "failed": 0, "log": [], "error": "", "finished": False}
    return {"ok": True, **state}


@app.get("/review")
def api_review_page():
    """复核队列页面（不依赖 Vue 构建产物）。"""
    page_path = pathlib.Path(__file__).resolve().parent / "review.html"
    try:
        with open(page_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception:
        return HTMLResponse(content="<h1>review.html not found</h1>", status_code=404)


# 生产模式：托管前端构建产物（webui/dist 复制到 server/static）
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
