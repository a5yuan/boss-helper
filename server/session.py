"""单任务会话管理。"""
import glob
import os
import threading

from src.control import GuiController
from src.collector import run_collection

from .tracer import tracer


def ai_after_collect(ctrl) -> None:
    """采集结束后按 ai.auto_after_collect 自动筛选 / 填充。

    off    不做任何事
    screen 只跑 AI 筛选，生成计划（安全，不点任何东西）
    fill   筛选 + 逐条点沟通并填招呼语（只填不发，但会产生真实沟通记录）
    """
    from src.ai.dispatch import dispatch
    from src.ai.pipeline import apply_outcomes, build_plan, plan_path_for, save_plan
    from src.config import get_config, load_ai_config

    cfg = load_ai_config()
    mode = str(cfg.get("auto_after_collect") or "off").lower()
    if mode not in ("screen", "fill"):
        return

    out_dir = get_config("chrome")["output_dir"]
    files = glob.glob(os.path.join(out_dir, "jobs_*.json"))
    if not files:
        ctrl.log("[AI] 没找到采集结果，跳过")
        return
    target = max(files, key=os.path.getmtime)
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
        stats = dispatch(todo, on_event=ctrl.log)

        # 回写执行状态：不回写的话计划永远显示 todo，下次会重复处理
        apply_outcomes(plan, stats)
        save_plan(plan, plan_path_for(target))

        ctrl.log(f"[AI] 填充完成: 成功 {stats['ok']} / 失败 {stats['failed']} / 跳过 {stats['skipped']}")
    except Exception as exc:  # noqa: BLE001
        tracer.entry("session.py:ai_after_collect", "AI 填充失败", {"error": str(exc)}, scope="error")
        ctrl.log(f"[AI] 填充失败: {exc}", level="error")


class Session:
    def __init__(self):
        self.controller: GuiController | None = None
        self.thread: threading.Thread | None = None
        self.last_params: dict | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, params: dict):
        if self.running:
            raise RuntimeError("已有任务在运行")
        self.last_params = params
        self.controller = GuiController()
        ctrl = self.controller

        def _run():
            try:
                tracer.span(
                    "BE-ENTRY",
                    "session.py:run_collection",
                    "执行数据整理主任务",
                    lambda: run_collection(controller=ctrl, **params),
                    scope="start-collection"
                )
                if not ctrl.should_stop():
                    ai_after_collect(ctrl)
            except Exception as exc:  # noqa: BLE001
                tracer.entry("session.py:_run", "分析线程异常", {"error": str(exc)}, scope="error")
                ctrl.log(f"[ERROR] 分析线程异常: {exc}", level="error")
                ctrl.status("error", str(exc))

        self.thread = threading.Thread(target=_run, name="helper_session", daemon=True)
        self.thread.start()

    def stop(self):
        if self.controller:
            tracer.entry("session.py:stop", "停止运行", {}, scope="stop-collection")
            self.controller.request_stop()

    def pause(self):
        if self.controller:
            tracer.entry("session.py:pause", "暂停任务", {}, scope="pause-collection")
            self.controller.request_pause()

    def resume(self):
        if self.controller:
            tracer.entry("session.py:resume", "继续任务", {}, scope="resume-collection")
            self.controller.request_resume()

    def ack(self, payload: str = ""):
        if self.controller:
            self.controller.ack_user(payload)


session = Session()
