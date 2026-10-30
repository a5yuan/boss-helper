"""单任务会话管理。"""
import threading

from src.control import GuiController
from src.collector import run_collection

from .tracer import tracer


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
