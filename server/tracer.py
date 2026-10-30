"""
Boss 助手 TraceLink 追踪入口

直接导出标准 tracelink Python SDK 的 tracer 单例。
开发环境自动连接 Dashboard Receiver。
"""
import os
from tracelink import tracer


def _trace_enabled() -> bool:
    configured = os.getenv("TRACELINK_ENABLED")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("BOSS_GUI_DEV") == "1"


# 连接 Dashboard Receiver
receiver_port = os.getenv("TRACELINK_PORT", "5174")
receiver_endpoint = f"http://127.0.0.1:{receiver_port}/__debug_log"
tracer.configure(
    enabled=_trace_enabled(),
    http_endpoint=receiver_endpoint,
    http_timeout_ms=2000,
    file_enabled=False,
    scope_sync_endpoint=f"{receiver_endpoint}/scopes",
)
