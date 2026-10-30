"""FastAPI 后端：REST 控制接口 + WebSocket 实时事件流 + 静态前端托管。"""
import asyncio
import glob
import json
import os
import pathlib
import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import get_config, save_config, load_start_params, save_start_params
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
    if session.running:
        return {"ok": False, "error": "已有任务在运行"}
    trace_id = tracer.start_scope("collect-start")
    tracer.entry("app.py:api_start", "分析任务启动", params.model_dump(), scope="collect-start")
    session.start(_dump(params))
    return {"ok": True}


@app.post("/api/stop")
def api_stop():
    session.stop()
    return {"ok": True}


@app.post("/api/pause")
def api_pause():
    session.pause()
    return {"ok": True}


@app.post("/api/resume")
def api_resume():
    session.resume()
    return {"ok": True}


@app.post("/api/ack")
def api_ack(body: AckBody):
    session.ack(body.payload)
    return {"ok": True}


@app.get("/api/status")
def api_status():
    ctrl = session.controller
    return {
        "running": session.running,
        "state": ctrl.state if ctrl else "idle",
        "progress": ctrl.latest_progress if ctrl else {"done": 0, "total": 0, "stats": {}},
        "pending_action": ctrl.pending_action if ctrl else None,
    }


@app.get("/api/results")
def api_results(date: str | None = None, output_dir: str | None = None):
    cfg = get_config("chrome")
    out = output_dir if output_dir else cfg.get("output_dir", "")
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
    # 连接时先推送当前快照，便于前端刷新后恢复状态
    ctrl = session.controller
    if ctrl:
        await ws.send_json({"type": "status", "state": ctrl.state})
        await ws.send_json({"type": "progress", **ctrl.latest_progress})
        if ctrl.pending_action:
            await ws.send_json({"type": "need_action", **ctrl.pending_action})
    try:
        while True:
            ctrl = session.controller
            if ctrl:
                for ev in ctrl.drain():
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

from src.tracking import tracker  # noqa: E402


class TrackBody(BaseModel):
    security_id: str = ""
    encrypt_job_id: str = ""
    status: str
    note: str = ""


class FocusBody(BaseModel):
    security_id: str = ""
    encrypt_job_id: str = ""


class GreetBody(BaseModel):
    security_id: str = ""
    encrypt_job_id: str = ""
    text: str | None = None


def _track_key(security_id: str, encrypt_job_id: str) -> str:
    """encryptJobId 跨页面加载稳定，优先用它做主键。"""
    return encrypt_job_id or security_id


def _latest_jobs() -> list:
    out = get_config("chrome").get("output_dir", "")
    files = sorted(glob.glob(os.path.join(out, "jobs_*.json")), reverse=True)
    if not files:
        return []
    try:
        with open(files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _find_job(security_id: str = "", encrypt_job_id: str = "") -> dict | None:
    for j in _latest_jobs():
        if encrypt_job_id and j.get("encrypt_job_id") == encrypt_job_id:
            return j
        if security_id and j.get("security_id") == security_id:
            return j
    return None


def _with_browser(fn, prefer_chat: bool = False):
    """连接到正在运行的调试浏览器，执行 fn(bm, page)。"""
    if session.running:
        return {"ok": False, "error": "采集任务正在运行，请先停止再定位"}
    from src.core.browser import BrowserManager

    bm = BrowserManager(config=get_config("chrome"))
    if not bm.try_connect_existing():
        return {"ok": False, "error": "没有正在运行的调试浏览器，请先跑一次采集"}
    # 只考虑真正的标签页；shared_worker 的 URL 里也含 geek-chat，不能选它
    pages = [p for p in bm.find_boss_pages() if p.get("type") == "page"]
    page = None
    if prefer_chat:
        chat = [p for p in pages if "chat" in p.get("url", "")]
        page = chat[-1] if chat else None
    if page is None:
        best = bm.find_boss_page()
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
def api_tracking():
    return tracker.all()


@app.post("/api/tracking")
def api_tracking_set(body: TrackBody):
    key = _track_key(body.security_id, body.encrypt_job_id)
    if not key:
        return {"ok": False, "error": "缺少岗位 ID"}
    try:
        return {"ok": True, "record": tracker.set(key, body.status, body.note)}
    except ValueError as exc:
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


@app.post("/api/focus")
def api_focus(body: FocusBody):
    if not (body.security_id or body.encrypt_job_id):
        return {"ok": False, "error": "缺少岗位 ID"}
    from src.utils.browser_behavior import BrowserBehavior

    job = _find_job(body.security_id, body.encrypt_job_id) or {}
    eid = body.encrypt_job_id or job.get("encrypt_job_id") or ""

    def _run(bm, page):
        # ① 卡片还在当前页面上（同一会话内 securityId 才有效）：直接点，不打断列表
        clicked, pos, total = False, -1, 0
        if body.security_id:
            try:
                clicked, pos, total = BrowserBehavior.click_job(bm, body.security_id)
            except Exception:
                pass
        if clicked:
            bm.bring_to_front()
            return {"ok": True, "mode": "click", "index": pos, "total": total}

        # ② 不在页面上（列表已刷新/翻页）：用 encryptJobId 直接打开详情页
        if eid:
            url = f"https://www.zhipin.com/job_detail/{eid}.html"
            bm.evaluate("location.href=" + json.dumps(url))
            _wait_ready(bm, 12)
            bm.bring_to_front()
            return {"ok": True, "mode": "url", "url": url}

        return {
            "ok": False,
            "error": "当前页面上找不到这张卡片，且该记录缺少 encryptJobId（旧数据）。重新采集一次即可修复。",
        }

    return _with_browser(_run)


_GREET_JS = r"""
(() => {
  const text = __TEXT__;
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 40 && r.height > 8; };
  const nodes = Array.from(document.querySelectorAll('textarea, [contenteditable="true"]')).filter(vis);
  if (!nodes.length) {
    return JSON.stringify({ok:false, reason:'页面上没有可输入的聊天框，请先在浏览器里点「立即沟通」打开聊天'});
  }
  const el = nodes[nodes.length - 1];
  el.focus();
  if (el.tagName === 'TEXTAREA') {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(el, text);
  } else {
    el.innerText = text;
    el.dispatchEvent(new InputEvent('input', {bubbles:true, data:text, inputType:'insertText'}));
  }
  el.dispatchEvent(new Event('input', {bubbles:true}));
  el.dispatchEvent(new Event('change', {bubbles:true}));
  return JSON.stringify({ok:true, tag: el.tagName, placeholder: el.getAttribute('placeholder') || ''});
})()
"""


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
    text = (body.text or "").strip() or _default_greeting(job)

    def _run(bm, page):
        js = _GREET_JS.replace("__TEXT__", json.dumps(text, ensure_ascii=False))
        res = bm.evaluate(js)
        exc = (res.get("result") or {}).get("exceptionDetails")
        if exc:
            desc = (exc.get("exception") or {}).get("description") or exc.get("text") or "JS 执行异常"
            return {"ok": False, "error": desc}
        raw = bm.get_value(res)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {"ok": False, "reason": raw}
        if not raw.get("ok"):
            return {"ok": False, "error": raw.get("reason") or "填充失败"}
        return {"ok": True, "filled": text, "placeholder": raw.get("placeholder", "")}

    return _with_browser(_run, prefer_chat=True)


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
