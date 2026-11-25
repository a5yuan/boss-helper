"""投递事件流：按平台分文件的 append-only JSONL。

一条事件描述「某时刻发生了一件什么事」。事件一旦写入不修改、不删除。
文件位置 ``output/{platform}/events.jsonl``，一行一条 JSON。

这是旁路：统计失败绝不能拖垮投递。所以 ``record()`` 写失败只记日志，
不向上抛异常；``load()`` 遇到坏行跳过并计数，不会因为一行坏了整个文件读不出来。

字段口径见 docs/subsystems/stats.md，语义见 GLOSSARY.md。
"""
import json
import os
import threading
from datetime import datetime

from src.config import get_config, known_platforms

EVENT_FILE = "events.jsonl"

# 同一平台可能多线程写（采集线程 + AI 线程），进程内串行化一下，
# 避免两行交叉写坏。
_WRITE_LOCK = threading.Lock()


def event_path(platform: str) -> str:
    """某平台的事件文件路径。与 apply_audit.log 同目录。"""
    out = get_config("chrome", platform=platform)["output_dir"]
    return os.path.join(out, EVENT_FILE)


def _log(fn: str, msg: str, data: dict | None = None) -> None:
    """写事件失败时的唯一去处：tracer。tracer 自己也挂了就放弃。"""
    try:
        from server.tracer import tracer
        tracer.internal(f"events.py:{fn}", msg, data or {}, scope="stats")
    except Exception:
        pass


def now_ts() -> str:
    """事件时间戳：ISO 到秒（2026-11-25T09:30:26）。"""
    return datetime.now().isoformat(timespec="seconds")


def record(event: str, platform: str, ts: str | None = None, **fields) -> None:
    """追加一条事件。

    ``ts`` 默认自动填成当前时间（到秒），调用方不用传。只有回填 / 迁移
    这种「事件其实发生在过去」的场景才显式带上原始时间。

    写失败只记日志，不抛异常——统计是旁路，不能拖垮投递。
    """
    if not event or not platform:
        return
    rec = {"ts": ts or now_ts(), "platform": platform, "event": event}
    rec["ok"] = bool(fields.pop("ok", True))
    for key, value in fields.items():
        if value is None:
            continue
        rec[key] = value

    try:
        line = json.dumps(rec, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        _log("record", "事件序列化失败", {"event": event, "exc": str(exc)})
        return

    try:
        path = event_path(platform)
        with _WRITE_LOCK:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as exc:  # noqa: BLE001
        _log("record", "事件写入失败（已忽略）", {"event": event, "exc": str(exc)})


class EventList(list):
    """事件列表，附带读取时的坏行计数。

    仍然是 list，可以当普通列表用；``bad_lines`` 是这次读取里跳过的坏行数。
    """

    def __init__(self, items=(), bad_lines: int = 0):
        super().__init__(items)
        self.bad_lines = bad_lines


def _read_file(path: str, platform: str) -> tuple[list[dict], int]:
    """读一个事件文件。返回 (事件列表, 坏行数)。读不了文件当作空。"""
    rows: list[dict] = []
    bad = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    bad += 1
                    continue
                if not isinstance(rec, dict):
                    bad += 1
                    continue
                rec.setdefault("platform", platform)
                rows.append(rec)
    except FileNotFoundError:
        return [], 0
    except Exception as exc:  # noqa: BLE001
        _log("_read_file", "事件文件读取失败", {"path": path, "exc": str(exc)})
        return rows, bad
    return rows, bad


def load(platform: str | None = None, since: str | None = None) -> EventList:
    """读事件流。

    ``platform`` 给 None 表示读所有平台；``since`` 是 ISO 时间戳，
    只保留 ``ts >= since`` 的事件。坏行跳过并计数，不影响其余行。
    """
    platforms = [platform] if platform else known_platforms()
    rows: list[dict] = []
    bad = 0
    for name in platforms:
        if not name:
            continue
        got, bad_count = _read_file(event_path(name), name)
        rows.extend(got)
        bad += bad_count

    if since:
        rows = [r for r in rows if str(r.get("ts") or "") >= since]
    rows.sort(key=lambda r: str(r.get("ts") or ""))
    return EventList(rows, bad_lines=bad)


def dedup_key(event: dict) -> str:
    """回填幂等用的去重键。

    任务书写的是 ``ts + event + file``。但 ``jobs_*.json`` 是**累积**文件——
    同一个文件会被多次采集追加内容，每次回填算出的最新 ``collected_at`` 都
    不同，用 ``ts`` 做键会让同一份文件每次回填都产生一条新事件。

    所以回填来的事件用 ``event + file`` 做键：一个文件一条事件。
    真实运行时记的事件没有 ``file`` 字段，退回 ``ts + event + job_id``。
    """
    if event.get("file"):
        return "|".join([str(event.get("event") or ""), str(event.get("file"))])
    parts = [
        str(event.get("ts") or ""),
        str(event.get("event") or ""),
        str(event.get("file") or event.get("job_id") or ""),
    ]
    return "|".join(parts)


def existing_keys(platform: str) -> set[str]:
    """某平台已有事件的去重键集合。"""
    return {dedup_key(r) for r in load(platform)}


def migrate_legacy_audit(platform: str = "zhaopin") -> int:
    """把旧的 ``output/{platform}/apply_audit.log`` 迁进事件流。

    旧文件保留不删——它是不可逆动作的原始留痕，只是不再是统计口径。
    重复跑不会产生重复事件（按 ts + event + job_id 去重）。
    """
    out = get_config("chrome", platform=platform)["output_dir"]
    legacy = os.path.join(out, "apply_audit.log")
    if not os.path.exists(legacy):
        return 0
    try:
        with open(legacy, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as exc:  # noqa: BLE001
        _log("migrate_legacy_audit", "旧留痕读取失败", {"path": legacy, "exc": str(exc)})
        return 0

    have = existing_keys(platform)
    migrated = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(rec, dict):
            continue
        event = rec.get("event")
        if event not in ("apply", "send_message"):
            continue

        ts = str(rec.get("ts") or "")
        job_id = str(rec.get("job_id") or "")
        key = "|".join([ts, str(event), job_id])
        if key in have:
            continue

        fields = {"job_id": job_id, "company": rec.get("company") or "",
                  "reason": rec.get("reason") or ""}
        if event == "apply":
            submitted = bool(rec.get("submitted"))
            fields["status"] = "submitted" if submitted else "drafted"
            fields["ok"] = submitted
        else:
            fields["length"] = rec.get("length")
            fields["sent"] = bool(rec.get("sent"))
            fields["ok"] = bool(rec.get("sent"))

        record(event, platform, ts=ts or None,
               **{k: v for k, v in fields.items() if v not in (None, "")})
        have.add(key)
        migrated += 1
    return migrated
