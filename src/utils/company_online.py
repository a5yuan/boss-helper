"""公司在线状态的纯逻辑：三态归类与证据格式化。

只做纯函数，不接触浏览器；探针结果由 ``CompanyOnlineReader`` 从页面读取。
"""

STATE_ONLINE = "online"
STATE_OFFLINE = "offline"
STATE_UNKNOWN = "unknown"

# evidence 的固定键顺序，format_evidence 按此输出，便于日志比对
_EVIDENCE_KEYS = (
    "card_sel",
    "row_sel",
    "logo",
    "logo_cls",
    "span_scope",
    "row_text_len",
    "vue",
)


def classify_online(probe):
    """把探针结果归为 online / offline / unknown。

    只认 ``ok is True`` 且 ``online`` 是布尔值的探针，其余一律 unknown，
    不做任何推测。
    """
    if not isinstance(probe, dict):
        return STATE_UNKNOWN
    if probe.get("ok") is not True:
        return STATE_UNKNOWN
    online = probe.get("online")
    if not isinstance(online, bool):
        return STATE_UNKNOWN
    return STATE_ONLINE if online else STATE_OFFLINE


def format_evidence(probe, limit=140):
    """把探针的 evidence 压成一行稳定的 k=v 字符串，永不抛异常。

    键顺序固定，缺省键输出空值；换行和连续空白压成单空格；总长截到 ``limit``。
    """
    try:
        raw = probe.get("evidence") if isinstance(probe, dict) else None
        evidence = raw if isinstance(raw, dict) else {}
        parts = []
        for key in _EVIDENCE_KEYS:
            value = evidence.get(key, "")
            text = "" if value is None else str(value)
            text = " ".join(text.split())  # 保证日志只有一行
            parts.append(f"{key}={text}")
        line = " ".join(parts)
        if isinstance(limit, int) and len(line) > limit:
            line = line[:max(0, limit)]
        return line
    except Exception:
        return ""
