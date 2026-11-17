"""招聘者活跃状态解析。

BOSS 详情页 `.job-boss-info` 里带一段活跃描述，常见的几种：
    刚刚活跃 / 今日活跃 / 3天前活跃 / 本周活跃 / 本月活跃 / 3月前活跃 / 半年前活跃
把它折成「大概几天前」，用来在点「立即沟通」之前判断值不值得投。

解析不出来时返回 None —— 调用方应当放行并记一条日志，不要因为读不到就静默跳过。
"""
import re

# 语义区间 → 估算天数（取区间上界，宁可保守）
_BUCKETS = (
    (r"刚刚|在线|当前在线", 0),
    (r"今日|今天", 0),
    (r"昨日|昨天", 1),
    (r"本周|这周", 3),
    (r"本月|这个月", 15),
    (r"半年", 180),
    (r"一年", 365),
)


def parse_active_days(text: str):
    """把活跃描述折成天数；无法判断返回 None。"""
    if not text:
        return None
    s = str(text).replace(" ", "")

    m = re.search(r"(\d+)\s*天前", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*周前", s)
    if m:
        return int(m.group(1)) * 7
    m = re.search(r"(\d+)\s*个?月?前", s)
    if m:
        return int(m.group(1)) * 30
    m = re.search(r"(\d+)\s*年前", s)
    if m:
        return int(m.group(1)) * 365

    for pattern, days in _BUCKETS:
        if re.search(pattern, s):
            return days
    return None


def is_offline(text: str, max_days: int) -> bool:
    """超过 max_days 天没活跃就算不在线；解析不出来不算。"""
    days = parse_active_days(text)
    if days is None:
        return False
    return days > max_days
