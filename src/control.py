"""助手引擎控制器抽象。"""
import queue
import threading


class BaseController:
    def log(self, msg="", level="info", end="\n"):
        raise NotImplementedError

    def progress(self, done, total, stats=None):
        pass

    def status(self, state, detail=None):
        pass

    def wait_user(self, reason, kind="confirm"):
        return ""

    def should_stop(self) -> bool:
        return False

    def should_pause(self) -> bool:
        return False


class ConsoleController(BaseController):
    def log(self, msg="", level="info", end="\n"):
        print(msg, end=end, flush=True)

    def wait_user(self, reason, kind="confirm"):
        try:
            return input(reason)
        except EOFError:
            return ""

    def should_stop(self) -> bool:
        return False


class GuiController(BaseController):
    def __init__(self):
        self.events: "queue.Queue[dict]" = queue.Queue()
        self._stop = threading.Event()
        self._paused = threading.Event()     # set() = 已暂停，clear() = 运行中
        self._resume = threading.Event()
        self._action_payload = ""
        self.latest_progress = {"done": 0, "total": 0, "stats": {}}
        self.state = "idle"
        self.pending_action = None

    def log(self, msg="", level="info", end="\n"):
        text = str(msg)
        if not text.strip() and end == "":
            return
        self.events.put({"type": "log", "level": level, "msg": text})
        if level == "error":
            import server.tracer as dt
            dt.tracer.entry("control.py:GuiController.log", "引擎错误", {"msg": text[:200]}, scope="error")

    def progress(self, done, total, stats=None):
        self.latest_progress = {"done": done, "total": total, "stats": stats or {}}
        self.events.put({"type": "progress", "done": done, "total": total, "stats": stats or {}})
        import server.tracer as dt
        dt.tracer.internal("control.py:GuiController.progress", "进度更新", {"done": done, "total": total}, scope="collect-start")

    def status(self, state, detail=None):
        self.state = state
        self.events.put({"type": "status", "state": state, "detail": detail})
        import server.tracer as dt
        dt.tracer.internal("control.py:GuiController.status", f"状态切换: {state}", {"detail": str(detail)[:200] if detail else None}, scope="collect-start")

    def wait_user(self, reason, kind="confirm"):
        self._resume.clear()
        self._action_payload = ""
        self.pending_action = {"reason": reason, "kind": kind}
        self.events.put({"type": "need_action", "reason": reason, "kind": kind})
        while not self._resume.is_set():
            if self._stop.is_set():
                break
            if self._paused.is_set():
                self._paused.wait(0.2)
                continue
            self._resume.wait(0.2)
        self.pending_action = None
        return self._action_payload

    def should_stop(self) -> bool:
        return self._stop.is_set()

    def should_pause(self) -> bool:
        return self._paused.is_set()

    def _wait_paused(self):
        import server.tracer as dt
        dt.tracer.internal("control.py:GuiController._wait_paused", "已进入暂停状态，等待继续 ...", {}, scope="collect-start")
        while True:
            if self._stop.is_set():
                dt.tracer.internal("control.py:GuiController._wait_paused", "暂停中收到停止信号，退出", {}, scope="collect-start")
                return
            if not self._paused.is_set():
                dt.tracer.internal("control.py:GuiController._wait_paused", "收到继续信号，恢复运行", {}, scope="collect-start")
                return
            self._paused.wait(0.2)

    def request_stop(self):
        self._stop.set()
        self._resume.set()
        self._paused.clear()

    def request_pause(self):
        if not self._stop.is_set():
            import server.tracer as dt
            dt.tracer.internal("control.py:GuiController.request_pause", "收到暂停请求", {}, scope="collect-start")
            self._paused.set()
            self.status("paused")

    def request_resume(self):
        if self._paused.is_set():
            import server.tracer as dt
            dt.tracer.internal("control.py:GuiController.request_resume", "收到继续请求", {}, scope="collect-start")
        self._paused.clear()
        self.status("running")

    def ack_user(self, payload=""):
        self._action_payload = payload or ""
        self._resume.set()

    def drain(self):
        items = []
        while True:
            try:
                items.append(self.events.get_nowait())
            except queue.Empty:
                break
        return items
