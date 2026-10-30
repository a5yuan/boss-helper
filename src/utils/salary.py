"""薪资字符串解析与范围匹配。

BOSS 的薪资是明文字符串，如 "15-22K"、"20-40K·16薪"、"8千-1.2万"、"面议"、
"300-500元/天"。本模块把它解析成以 K（千元/月）为单位的区间 (min, max)，
供初始筛选与结果表精筛复用。
"""
import re

_RANGE_K = re.compile(r"(\d+(?:\.\d+)?)\s*[-~―]\s*(\d+(?:\.\d+)?)\s*[Kk]")
_SINGLE_K = re.compile(r"(\d+(?:\.\d+)?)\s*[Kk]")
_RANGE_WAN = re.compile(r"(\d+(?:\.\d+)?)\s*万?\s*[-~―]\s*(\d+(?:\.\d+)?)\s*万")
_RANGE_QIAN = re.compile(r"(\d+(?:\.\d+)?)\s*千?\s*[-~―]\s*(\d+(?:\.\d+)?)\s*千")


def parse_salary(text):
    """把薪资字符串解析为 (min_k, max_k)，单位 K（千/月）。无法解析返回 (None, None)。

    仅处理「月薪」类（K / 千 / 万）；按天/小时计酬（如 元/天）无法折算月薪，返回 None。
    """
    if not text:
        return (None, None)
    s = str(text)

    # 日薪/时薪无法折算为月薪区间，视为不可解析
    if "元/天" in s or "元/时" in s or "元/小时" in s or "/天" in s or "/时" in s:
        return (None, None)

    m = _RANGE_K.search(s)
    if m:
        return (float(m.group(1)), float(m.group(2)))

    m = _RANGE_WAN.search(s)
    if m:
        return (float(m.group(1)) * 10, float(m.group(2)) * 10)

    m = _RANGE_QIAN.search(s)
    if m:
        return (float(m.group(1)), float(m.group(2)))

    m = _SINGLE_K.search(s)
    if m:
        v = float(m.group(1))
        return (v, v)

    return (None, None)


def salary_in_range(text, lo=None, hi=None):
    """岗位薪资是否与请求区间 [lo, hi]（单位 K）有交集。

    - lo / hi 为 None 表示该侧不设限。
    - 薪资无法解析（如「面议」）时返回 True：不主动丢弃，交由用户后续判断。
    """
    if lo is None and hi is None:
        return True
    jmin, jmax = parse_salary(text)
    if jmin is None:
        return True  # 不可解析（面议等）不过滤掉，避免误伤
    if lo is not None and jmax < lo:
        return False
    if hi is not None and jmin > hi:
        return False
    return True
