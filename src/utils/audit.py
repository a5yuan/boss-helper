"""不可逆动作的留痕：一行一条 JSON，追加写到 output/{platform}/apply_audit.log。

投递和发消息都改不了、撤不回，事后必须能逐条核对。日志只记录结果与依据，
不记录页面 HTML、cookie 或完整话术。写盘失败不影响主流程。
"""
import json
import os
from datetime import datetime


def audit_path(platform: str) -> str:
    from src.config import get_config
    out = get_config("chrome", platform=platform)["output_dir"]
    return os.path.join(out, "apply_audit.log")


def write_audit(platform: str, event: str, **fields) -> str:
    """追加一行并返回路径；写失败返回空串（留痕失败不能反过来打断投递）。"""
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event}
    rec.update(fields)
    path = audit_path(platform)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        return ""
    return path
