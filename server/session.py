"""单任务会话管理。

UI 仍是单任务，但状态按 task_id 索引：不同平台可以同时运行，
停止 / 暂停 / 状态查询都只作用于目标任务，不会误伤别的任务。
"""
import os
import threading
import time
import uuid

from src.config import DEFAULT_PLATFORM
from src.control import GuiController
from src.collector import run_collection
from src.runtime import get_runtime

from .tracer import tracer

# 任务结束后保留终态记录的秒数，避免前端轮询瞬间查不到
TERMINAL_TTL = 300
# 终态记录条数上限
TERMINAL_LIMIT = 8


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
        # tasks 只放活任务；结束后移入 _terminal 保留一段时间
        self.tasks: dict[str, dict] = {}
        self._terminal: dict[str, tuple[dict, float]] = {}
        self._lock = threading.RLock()
        self.current_task_id: str | None = None
        self.last_params: dict | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return any(self._alive(t) for t in self.tasks.values())

    def running_for(self, platform: str | None) -> bool:
        key = platform or DEFAULT_PLATFORM
        with self._lock:
            return any(t["platform"] == key and self._alive(t) for t in self.tasks.values())

    @staticmethod
    def _alive(task: dict) -> bool:
        thread = task.get("thread")
        return thread is not None and thread.is_alive()

    def _find(self, task_id: str | None) -> dict | None:
        """先查活任务，再查终态记录；未传 task_id 时用 current_task_id。调用方需持锁。"""
        key = task_id or self.current_task_id or ""
        task = self.tasks.get(key)
        if task is not None:
            return task
        record = self._terminal.get(key)
        return record[0] if record else None

    def _prune_terminal(self) -> None:
        """清掉过期的终态记录。调用方需持锁。"""
        deadline = time.time() - TERMINAL_TTL
        expired = [tid for tid, (_, retired_at) in self._terminal.items()
                   if retired_at < deadline]
        for tid in expired:
            self._terminal.pop(tid, None)

    def _retire(self, task_id: str, task: dict) -> None:
        """任务结束后移入终态记录，保留 controller / params 供前端查询。"""
        with self._lock:
            if self.tasks.get(task_id) is task:
                del self.tasks[task_id]
            self._prune_terminal()
            terminal_task = {k: v for k, v in task.items() if k != "thread"}
            self._terminal[task_id] = (terminal_task, time.time())
            while len(self._terminal) > TERMINAL_LIMIT:
                oldest = min(self._terminal, key=lambda tid: self._terminal[tid][1])
                del self._terminal[oldest]

    def controller(self, task_id: str | None = None) -> GuiController | None:
        with self._lock:
            task = self._find(task_id)
        return task["controller"] if task else None

    def controllers(self) -> list[tuple[str, GuiController]]:
        """当前活任务的 (task_id, controller) 快照，保持 start 顺序。"""
        with self._lock:
            return [(task_id, task["controller"]) for task_id, task in self.tasks.items()]

    def drain_events(self) -> list[dict]:
        """取出所有活任务的事件，复制后追加 task_id，按任务顺序拼接。

        drain() 会在 controller 的队列上取事件，故意放在锁外，避免慢 controller 拖住会话锁。
        任务结束时最后一条 status 可能还没被轮询到就移出了 tasks，所以终态 controller
        也排空一次，否则前端收不到「done / stopped / error」这条收尾事件。
        """
        events: list[dict] = []
        pairs = self.controllers()
        with self._lock:
            pairs += [(task_id, record[0]["controller"])
                      for task_id, record in self._terminal.items()]
        for task_id, ctrl in pairs:
            for ev in ctrl.drain():
                events.append({**ev, "task_id": task_id})
        return events

    @staticmethod
    def _snapshot_for(task_id: str, ctrl: GuiController) -> list[dict]:
        """单个任务的 status / progress / need_action 快照，全部带 task_id。"""
        events = [
            {"type": "status", "state": ctrl.state, "task_id": task_id},
            {"type": "progress", **ctrl.latest_progress, "task_id": task_id},
        ]
        if ctrl.pending_action:
            events.append({"type": "need_action", **ctrl.pending_action, "task_id": task_id})
        return events

    def snapshot_events(self) -> list[dict]:
        """连接建立时推送的快照：先推所有活任务，没有活任务时退回最后一次的终态。"""
        pairs = self.controllers()
        if pairs:
            events: list[dict] = []
            for task_id, ctrl in pairs:
                events.extend(self._snapshot_for(task_id, ctrl))
            return events

        # 老行为：任务结束后前端刷新仍要能看到最后一次的进度与状态
        with self._lock:
            task_id = self.current_task_id
            record = self._terminal.get(task_id) if task_id else None
        if not record:
            return []
        return self._snapshot_for(task_id, record[0]["controller"])

    def params(self, task_id: str | None = None) -> dict | None:
        with self._lock:
            task = self._find(task_id)
        return task["params"] if task else None

    def start(self, params: dict) -> str:
        params = dict(params)
        platform = params.get("site") or DEFAULT_PLATFORM
        with self._lock:
            self._prune_terminal()
            # 同一平台只允许一个任务，不同平台可以并存
            if self.running_for(platform):
                raise RuntimeError(f"{platform} 已有任务在运行")
            task_id = uuid.uuid4().hex[:12]
            ctrl = GuiController()
            task = {
                "controller": ctrl,
                "thread": None,
                "params": params,
                "platform": platform,
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
                finally:
                    # 只移除本任务，不影响同进程里的其他任务
                    self._retire(task_id, task)

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
