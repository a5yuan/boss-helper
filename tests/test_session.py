"""Session 的 task 索引与按平台判断。"""
import threading
import unittest
from unittest import mock

from server.session import Session


class TestSessionTasks(unittest.TestCase):
    def test_task_is_indexed_and_scoped_by_platform(self):
        release = threading.Event()

        def fake_run(**_kwargs):
            release.wait(3)
            return {"json": None}

        session = Session()
        with mock.patch("server.session.run_collection", side_effect=fake_run), \
                mock.patch("server.session.ai_after_collect"):
            task_id = session.start({"site": "boss", "browser_type": "chrome"})

            self.assertTrue(session.running)
            self.assertTrue(session.running_for("boss"))
            self.assertFalse(session.running_for("fake"))
            self.assertIs(session.controller(task_id), session.controller())
            self.assertEqual(session.params(task_id)["site"], "boss")

            with self.assertRaises(RuntimeError):
                session.start({"site": "fake", "browser_type": "chrome"})

            release.set()
            session.tasks[task_id]["thread"].join(3)

        self.assertFalse(session.running)
        self.assertFalse(session.running_for("boss"))


if __name__ == "__main__":
    unittest.main()
