"""Session 事件流：多任务 drain、快照与终态回退。"""
import time
import unittest

from src.control import GuiController
from server.session import Session


def _inject(session: Session, task_id: str, ctrl: GuiController, platform: str = "boss") -> None:
    """直接往 tasks 注入 controller，不走线程；事件流只依赖 controller。"""
    session.tasks[task_id] = {
        "controller": ctrl,
        "thread": None,
        "params": {"site": platform, "browser_type": "chrome"},
        "platform": platform,
    }
    session.current_task_id = task_id


class TestDrainEvents(unittest.TestCase):
    def test_drains_all_controllers_with_own_task_id(self):
        session = Session()
        boss, fake = GuiController(), GuiController()
        _inject(session, "t-boss", boss, "boss")
        _inject(session, "t-fake", fake, "fake")

        boss.log("老板平台日志")
        boss.progress(2, 10, {"ok": 1})
        fake.log("假平台日志", level="error")
        fake.status("running")

        events = session.drain_events()
        # 按 start 顺序拼接，每条事件都追加 task_id 与 platform
        self.assertEqual([e["task_id"] for e in events],
                         ["t-boss", "t-boss", "t-fake", "t-fake"])
        self.assertEqual([e["platform"] for e in events],
                         ["boss", "boss", "fake", "fake"])
        self.assertEqual(events[0]["msg"], "老板平台日志")
        self.assertEqual((events[1]["done"], events[1]["total"]), (2, 10))
        self.assertEqual(events[2]["level"], "error")
        self.assertEqual(events[3]["state"], "running")
        # 原字段一个不少
        self.assertEqual(events[1]["stats"], {"ok": 1})

        # drain 后队列为空，不重复投递
        self.assertEqual(session.drain_events(), [])

    def test_terminal_task_still_delivers_final_events(self):
        """线程在两次轮询之间结束：最后的 done 事件不能丢。"""
        session = Session()
        ctrl = GuiController()
        _inject(session, "t-old", ctrl)
        ctrl.status("done")
        # 模拟 _run 的 finally：任务移入终态，队列里还压着 done
        session._retire("t-old", session.tasks.pop("t-old"))

        events = session.drain_events()
        self.assertEqual([(e["type"], e.get("state"), e["task_id"], e["platform"]) for e in events],
                         [("status", "done", "t-old", "boss")])


class TestSnapshotEvents(unittest.TestCase):
    def test_snapshot_covers_all_live_tasks(self):
        session = Session()
        boss, fake = GuiController(), GuiController()
        _inject(session, "t-boss", boss, "boss")
        _inject(session, "t-fake", fake, "fake")
        boss.state = "running"
        boss.latest_progress = {"done": 3, "total": 10, "stats": {"ok": 2}}
        fake.state = "paused"
        fake.latest_progress = {"done": 1, "total": 5, "stats": {}}
        fake.pending_action = {"reason": "扫码", "kind": "confirm"}

        events = session.snapshot_events()
        by_task: dict[str, list[dict]] = {}
        for ev in events:
            by_task.setdefault(ev["task_id"], []).append(ev)

        # 两个活任务都要有快照，顺序与 start 一致
        self.assertEqual(list(by_task), ["t-boss", "t-fake"])

        boss_events = by_task["t-boss"]
        self.assertEqual([e["type"] for e in boss_events], ["status", "progress"])
        self.assertEqual(boss_events[0]["state"], "running")
        # 快照自带平台，前端刷新后按平台铺任务，不用再查一次
        self.assertTrue(all(e["platform"] == "boss" for e in boss_events))
        self.assertEqual((boss_events[1]["done"], boss_events[1]["total"]), (3, 10))
        self.assertEqual(boss_events[1]["stats"], {"ok": 2})

        # need_action 只在有 pending_action 时产出
        fake_events = by_task["t-fake"]
        self.assertEqual([e["type"] for e in fake_events],
                         ["status", "progress", "need_action"])
        self.assertEqual(fake_events[0]["state"], "paused")
        self.assertTrue(all(e["platform"] == "fake" for e in fake_events))
        self.assertEqual(fake_events[2]["reason"], "扫码")

    def test_snapshot_falls_back_to_terminal_task(self):
        session = Session()
        ctrl = GuiController()
        ctrl.state = "stopped"
        ctrl.latest_progress = {"done": 4, "total": 4, "stats": {"ok": 4}}
        ctrl.pending_action = {"reason": "扫码", "kind": "confirm"}
        # _terminal 存的是去掉 thread 的任务副本
        session._terminal["t-old"] = (
            {"controller": ctrl, "params": {}, "platform": "boss"},
            time.time(),
        )
        session.current_task_id = "t-old"

        events = session.snapshot_events()
        self.assertEqual([e["type"] for e in events],
                         ["status", "progress", "need_action"])
        self.assertTrue(all(e["task_id"] == "t-old" for e in events))
        self.assertEqual(events[0]["state"], "stopped")
        self.assertEqual((events[1]["done"], events[1]["total"]), (4, 4))

    def test_snapshot_empty_without_tasks(self):
        self.assertEqual(Session().snapshot_events(), [])


if __name__ == "__main__":
    unittest.main()
