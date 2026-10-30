"""投递状态跟踪：以 securityId 为主键，记录每条岗位的人工处理结果。

状态取值：
    new         尚未处理
    shortlisted 已标记，待投
    skipped     主动跳过
    applied     已投递（人工在浏览器里点过「立即沟通」）
"""
import json
import os
import threading
from datetime import datetime

VALID_STATUS = {"new", "shortlisted", "skipped", "applied"}


class Tracker:
    def __init__(self, path: str | None = None):
        self._path = path
        self._lock = threading.Lock()

    @property
    def path(self) -> str:
        if self._path:
            return self._path
        # 延迟导入，避免与 config 的模块级初始化互相牵扯
        from src.config import get_config
        out = get_config("chrome")["output_dir"]
        return os.path.join(out, "tracking.json")

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def all(self) -> dict:
        return self._load()

    def get(self, sid: str) -> dict:
        return self._load().get(sid, {})

    def set(self, sid: str, status: str, note: str = "") -> dict:
        if not sid:
            raise ValueError("securityId 不能为空")
        if status not in VALID_STATUS:
            raise ValueError(f"非法状态: {status}")
        with self._lock:
            data = self._load()
            rec = dict(data.get(sid) or {})
            rec["status"] = status
            rec["note"] = note
            rec["updated_at"] = datetime.now().isoformat(timespec="seconds")
            data[sid] = rec
            self._save(data)
            return rec


tracker = Tracker()
