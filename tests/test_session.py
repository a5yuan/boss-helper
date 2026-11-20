"""Session 的 task 索引、按平台准入与终态记录。"""
import threading
import unittest
from unittest import mock

from server.session import Session


class TestSessionTasks(unittest.TestCase):
    def test_same_platform_rejected_but_different_platforms_coexist(self):
        boss_release = threading.Event()
        fake_release = threading.Event()

        def fake_run(**kwargs):
            release = fake_release if kwargs.get("site") == "fake" else boss_release
            release.wait(3)
            return {"json": None}

        session = Session()
        with mock.patch("server.session.run_collection", side_effect=fake_run), \
                mock.patch("server.session.ai_after_collect"):
            boss_id = session.start({"site": "boss", "browser_type": "chrome"})

            self.assertTrue(session.running)
            self.assertTrue(session.running_for("boss"))
            self.assertFalse(session.running_for("fake"))
            self.assertIs(session.controller(boss_id), session.controller())
            self.assertEqual(session.params(boss_id)["site"], "boss")

            # 不同平台可以并存
            fake_id = session.start({"site": "fake", "browser_type": "chrome"})
            self.assertTrue(session.running_for("boss"))
            self.assertTrue(session.running_for("fake"))
            self.assertIsNot(session.controller(boss_id), session.controller(fake_id))
            # 未传 task_id 时仍指向最后一次 start 的任务
            self.assertIs(session.controller(), session.controller(fake_id))
            self.assertEqual(session.params()["site"], "fake")

            # 同一平台再 start 才拒绝
            with self.assertRaises(RuntimeError) as ctx:
                session.start({"site": "boss", "browser_type": "chrome"})
            self.assertIn("boss", str(ctx.exception))

            boss_thread = session.tasks[boss_id]["thread"]
            fake_thread = session.tasks[fake_id]["thread"]
            boss_release.set()
            fake_release.set()
            boss_thread.join(3)
            fake_thread.join(3)

        self.assertFalse(session.running)
        self.assertFalse(session.running_for("boss"))
        self.assertFalse(session.running_for("fake"))

    def test_stop_only_affects_target_task(self):
        releases = {"boss": threading.Event(), "fake": threading.Event()}

        def fake_run(**kwargs):
            releases[kwargs.get("site")].wait(3)
            return {"json": None}

        session = Session()
        with mock.patch("server.session.run_collection", side_effect=fake_run), \
                mock.patch("server.session.ai_after_collect"):
            boss_id = session.start({"site": "boss", "browser_type": "chrome"})
            fake_id = session.start({"site": "fake", "browser_type": "chrome"})
            boss_ctrl = session.controller(boss_id)
            fake_ctrl = session.controller(fake_id)

            session.stop(fake_id)
            self.assertTrue(fake_ctrl.should_stop())
            self.assertFalse(boss_ctrl.should_stop())
            self.assertTrue(session.running_for("boss"))

            boss_thread = session.tasks[boss_id]["thread"]
            fake_thread = session.tasks[fake_id]["thread"]
            releases["boss"].set()
            releases["fake"].set()
            boss_thread.join(3)
            fake_thread.join(3)

        self.assertFalse(session.running)

    def test_finished_task_keeps_terminal_controller(self):
        release = threading.Event()

        def fake_run(**_kwargs):
            release.wait(3)
            return {"json": None}

        session = Session()
        with mock.patch("server.session.run_collection", side_effect=fake_run), \
                mock.patch("server.session.ai_after_collect"):
            task_id = session.start({"site": "fake", "browser_type": "chrome"})
            ctrl = session.controller(task_id)
            thread = session.tasks[task_id]["thread"]

            release.set()
            thread.join(3)

        # 活任务表里已经没有它，但终态记录仍能查到 controller / params
        self.assertNotIn(task_id, session.tasks)
        self.assertIs(session.controller(task_id), ctrl)
        self.assertEqual(session.params(task_id)["site"], "fake")
        # 终态记录不会让 running 变真
        self.assertFalse(session.running)
        self.assertFalse(session.running_for("fake"))


if __name__ == "__main__":
    unittest.main()
