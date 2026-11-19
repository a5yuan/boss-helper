"""单任务会话管理。

UI 仍是单任务，但状态按 task_id 索引：以后并发跑不同平台时，
停止 / 暂停 / 状态查询都只作用于目标任务，不会误伤别的任务。
"""
import os
import threading
import uuid

from src.config import DEFAULT_PLATFORM
from src.control import GuiController
from src.collector import run_collection
from src.runtime import get_runtime

from .tracer import tracer


def ai_after_collect(ctrl, source_path: str | None,
                     browser_type: str = "chrome", platform: str | None = None) -> None:
    """采集结束后按 ai.auto_after_collect 自动筛选 / 填充。

    off    不做任何事
    screen 只跑 AI 筛选，生成计划（安全，不点任何东西）
    fill   筛选 + 逐条点沟通并填招呼语（只填不发，但会产生真实沟通记录）

    source_path 是本次采集实际写出的文件，不再 glob 最新文件。
    """
    from src.ai.dispatch import dispatch
    from src.ai.pipeline import apply_outcomes, build_plan, plan_path_for, save_plan
    from src.config import load_ai_config

    cfg = load_ai_config()
    mode = str(cfg.get("auto_after_collect") or "off").lower()
    if mode not in ("screen", "fill"):
        return

    if not source_path or not os.path.exists(source_path):
        ctrl.log("[AI] 没有可用的采集结果，跳过")
        return
    target = source_path
    ctrl.log(f"\n[AI] 开始筛选: {os.path.basename(target)}")

    try:
        plan = build_plan(target, on_event=ctrl.log)
    except Exception as exc:  # noqa: BLE001
        tracer.entry("session.py:ai_after_collect", "AI 筛选失败", {"error": str(exc)}, scope="error")
        ctrl.log(f"[AI] 筛选失败: {exc}", level="error")
        return

    todo = [it for it in plan.get("items", [])
            if it.get("status") == "planned" and it.get("dispatch") != "done"]
    ctrl.log(f"[AI] 计划: {len(todo)} 条可投")
    if mode != "fill" or not todo:
        return

    ctrl.log(f"[AI] 开始填充 {len(todo)} 条（只填不发）")
    try:
        runtime = get_runtime(platform, browser_type)
        stats = dispatch(todo, browser_type=browser_type, on_event=ctrl.log,
                         tracker=runtime.tracker, platform=platform)

        # 回写执行状态：不回写的话计划永远显示 todo，下次会重复处理
        apply_outcomes(plan, stats)
        save_plan(plan, plan_path_for(target))

        ctrl.log(f"[AI] 填充完成: 成功 {stats['ok']} / 失败 {stats['failed']} / 跳过 {stats['skipped']}")
    except Exception as exc:  # noqa: BLE001
        tracer.entry("session.py:ai_after_collect", "AI 填充失败", {"error": str(exc)}, scope="error")
        ctrl.log(f"[AI] 填充失败: {exc}", level="error")


class Session:
    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.current_task_id: str | None = None
        self.last_params: dict | None = None

    @property
    def running(self) -> bool:
        return any(self._alive(t) for t in self.tasks.values())

    def running_for(self, platform: str | None) -> bool:
        key = platform or DEFAULT_PLATFORM
        return any(t["platform"] == key and self._alive(t) for t in self.tasks.values())

    @staticmethod
    def _alive(task: dict) -> bool:
        thread = task.get("thread")
        return thread is not None and thread.is_alive()

    def controller(self, task_id: str | None = None) -> GuiController | None:
        task = self.tasks.get(task_id or self.current_task_id or "")
        return task["controller"] if task else None

    def params(self, task_id: str | None = None) -> dict | None:
        task = self.tasks.get(task_id or self.current_task_id or "")
        return task["params"] if task else None

    def start(self, params: dict) -> str:
        if self.running:
            raise RuntimeError("已有任务在运行")
        task_id = uuid.uuid4().hex[:12]
        ctrl = GuiController()
        params = dict(params)
        task = {
            "controller": ctrl,
            "thread": None,
            "params": params,
            "platform": params.get("site") or DEFAULT_PLATFORM,
        }
        self.tasks[task_id] = task
        self.current_task_id = task_id
        self.last_params = params

        def _run():
            try:
                result = tracer.span(
                    "BE-ENTRY",
                    "session.py:run_collection",
                    "执行数据整理主任务",
                    lambda: run_collection(controller=ctrl, **params),
                    scope="start-collection"
                )
                if not ctrl.should_stop():
                    ai_after_collect(
                        ctrl,
                        (result or {}).get("json"),
                        params.get("browser_type", "chrome"),
                        params.get("site"),
                    )
            except Exception as exc:  # noqa: BLE001
                tracer.entry("session.py:_run", "分析线程异常", {"error": str(exc)}, scope="error")
                ctrl.log(f"[ERROR] 分析线程异常: {exc}", level="error")
                ctrl.status("error", str(exc))

        thread = threading.Thread(target=_run, name=f"helper_session:{task_id}", daemon=True)
        task["thread"] = thread
        thread.start()
        return task_id

    def stop(self, task_id: str | None = None):
        ctrl = self.controller(task_id)
        if ctrl:
            tracer.entry("session.py:stop", "停止运行", {}, scope="stop-collection")
            ctrl.request_stop()

    def pause(self, task_id: str | None = None):
        ctrl = self.controller(task_id)
        if ctrl:
            tracer.entry("session.py:pause", "暂停任务", {}, scope="pause-collection")
            ctrl.request_pause()

    def resume(self, task_id: str | None = None):
        ctrl = self.controller(task_id)
        if ctrl:
            tracer.entry("session.py:resume", "继续任务", {}, scope="resume-collection")
            ctrl.request_resume()

    def ack(self, payload: str = "", task_id: str | None = None):
        ctrl = self.controller(task_id)
        if ctrl:
            ctrl.ack_user(payload)


session = Session()
