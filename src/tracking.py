"""投递状态跟踪：以 securityId 为主键，记录每条岗位的人工处理结果。

状态取值：
    new         尚未处理
    shortlisted 已标记，待投
    skipped     主动跳过
    applied     已投递（人工在浏览器里点过「立即沟通」）
"""
import json
import os
import shutil
import threading
from datetime import datetime

VALID_STATUS = {"new", "shortlisted", "skipped", "applied"}


class TrackingError(RuntimeError):
    """状态写盘失败（Windows 上文件被读句柄占用等）。"""


def track_key(security_id: str, encrypt_job_id: str) -> str:
    """encryptJobId 跨页面加载稳定，优先用它做主键；securityId 仅作会话内兜底。"""
    return encrypt_job_id or security_id


class Tracker:
    def __init__(self, path: str | None = None, legacy_path: str | None = None):
        self._path = path
        self._legacy_path = legacy_path
        self._lock = threading.Lock()
        self._migrate_legacy()

    @property
    def path(self) -> str:
        if self._path:
            return self._path
        # 延迟导入，避免与 config 的模块级初始化互相牵扯
        from src.config import DEFAULT_PLATFORM, get_config
        out = get_config("chrome", platform=DEFAULT_PLATFORM)["output_dir"]
        return os.path.join(out, "tracking.json")

    def _migrate_legacy(self) -> None:
        """新路径还没数据时，从老 tracking 复制一份，别让已联系记录消失。"""
        if not self._legacy_path:
            return
        try:
            if os.path.exists(self.path) or not os.path.exists(self._legacy_path):
                return
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            shutil.copy2(self._legacy_path, self.path)
        except OSError:
            pass

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError as exc:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise TrackingError(f"写入 {self.path} 失败: {exc}") from exc

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
