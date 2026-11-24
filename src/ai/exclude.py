"""确定性预筛：调模型前排除明确要求线下面试、或本身就是实习岗的岗位。

误伤比漏排更贵，所以这里只认明确的短语，且每次命中都要看前后文：

- 「线上面试」「视频面试」「远程面试」「可线下面试」不算线下面试；
- 「非实习」「不招实习生」「实习证明」「实习期薪资」「带实习生」不是实习岗；
- 只有标题（或岗位类型标签）明确写实习，才按实习岗排除，JD 正文提到实习不算。
"""
import re

# 线下面试：只认「面试 / 面谈 / 复试 / 终面」和线下语义紧邻的写法。
# 第三个元素是命中后写进 skip_reason 的原因。
_OFFLINE_PATTERNS = [
    ("线下面试", re.compile(r"线下面(?:试|谈)"), "要求线下面试"),
    ("现场面试", re.compile(r"现场面(?:试|谈)"), "要求现场面试"),
    ("到场面试", re.compile(r"到场面(?:试|谈)"), "要求到场面试"),
    ("当面面试", re.compile(r"当面面(?:试|谈)"), "要求当面面试"),
    ("到岗面谈", re.compile(r"到岗面(?:试|谈)"), "要求到岗面谈"),
    ("到公司面试", re.compile(r"(?:到|来)(?:公司|现场|总部|办公|司)(?:面试|面谈|复试)"),
     "要求到公司面试"),
    ("线下复试", re.compile(r"线下(?:初面|[一二三四五]面|终面|复试)"), "要求线下复试"),
    ("现场复试", re.compile(r"现场(?:初面|[一二三四五]面|终面|复试|笔试)"), "要求现场复试"),
    ("复试现场", re.compile(r"(?:初面|复试|终面)\s*现场"), "要求现场复试"),
    ("面试地点", re.compile(r"面试地点\s*[:：]"), "标注了面试地点"),
    ("面试方式线下", re.compile(r"面试(?:方式|形式)\s*[:：]\s*(?:线下|现场|到面)"),
     "面试方式为线下"),
]

# 命中点之前出现这些词，说明是否定，不算要求线下
_NEG_BEFORE = re.compile(
    r"(?:不需要|无需|不需|不用|不要|不要求|不安排|不接受|不提供|不进行|拒绝|谢绝)"
    r"[^，。；;、\n]{0,5}$|不$|非$"
)
# 命中点之前出现这些词，说明线下只是可选项，线上也能面。
# 「可接受 / 可需要 / 可要求」是要求能接受，不是线上也行，不能当可选项。
_OPT_BEFORE = re.compile(
    r"(?:可(?!.{0,2}(?:接受|需要|要求|必须))|或|支持|允许|/|、)[^，。；;、\n]{0,4}$"
)
# 命中点之后紧跟「也可线上 / 线上均可」这类写法，同样按可选项处理。
# 中间夹了「不支持 / 不提供」时是线上-only 的否定，不能当可选项。
_ONLINE_AFTER = re.compile(
    r"^([^，。；;\n]{0,8})(?:也可|可以|可改|可转|支持|接受|或|/|、)?\s*"
    r"(?:线上|视频|远程|电话|网络|在线|飞书|腾讯会议|微信视频)"
)
_ONLINE_NEG = re.compile(r"(?:不支持|不提供|不允许|不安排|不含|不要|不|无|非|拒绝|没有)")
# 「面试地点：」后面的值直接写线上，不算线下
_ONLINE_VALUE = re.compile(r"^(?:线上|视频|远程|电话|网络|在线|飞书|腾讯会议|微信视频)")

# 实习岗只看标题 / 岗位类型：明确写实习才算
_INTERN = re.compile(
    r"实习(?:生|岗|工程师|开发|算法|产品|运营|设计|测试)|暑期实习|日常实习|寒假实习|春季实习|"
    r"实习(?!证明|薪资|工资|时间|经历|经验|期(?:薪资|工资|待遇))"
)
# 「非实习」「不招实习生」「带实习生」这类是否定或正式岗，不能当实习岗。
# 「带薪实习生」是真实习，不能因为前面有「带」就放过。
_INTERN_NEG_BEFORE = re.compile(
    r"(?:非|不招|不招聘|不需要|无需|免|拒绝|谢绝|带(?!薪)|培养|指导)"
    r"[^，。；;、\n]{0,4}$|不$|非$"
)
# 「实习生导师 / 实习生管理」是带实习生的正式岗，不是实习岗
_INTERN_NEG_AFTER = re.compile(r"^(?:导师|带教|指导|培养|管理)")


def _online_alternative(after: str) -> bool:
    """命中点后面是否给了线上替代，且没有「不支持线上」这类否定。"""
    match = _ONLINE_AFTER.match(after)
    return bool(match) and not _ONLINE_NEG.search(match.group(1))


def _snippet(text: str, start: int, end: int, radius: int = 18) -> str:
    """截命中点前后各 radius 个字，压掉换行，方便人核对原文。"""
    s = max(0, start - radius)
    e = min(len(text), end + radius)
    frag = re.sub(r"\s+", " ", text[s:e]).strip()
    return ("…" if s else "") + frag + ("…" if e < len(text) else "")


def _scan_offline(field: str, text: str):
    if not text:
        return None
    for label, pattern, reason in _OFFLINE_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            before = text[max(0, start - 12):start]
            if _NEG_BEFORE.search(before) or _OPT_BEFORE.search(before):
                continue
            if _online_alternative(text[end:end + 16]):
                continue
            if label == "面试地点":
                value = text[end:end + 14].lstrip(" ：:")
                if _ONLINE_VALUE.match(value):
                    continue
            return {
                "rule": "interview_offline",
                "reason": reason,
                "field": field,
                "snippet": _snippet(text, start, end),
            }
    return None


def _scan_internship(field: str, text: str):
    if not text:
        return None
    for match in _INTERN.finditer(text):
        start = match.start()
        before = text[max(0, start - 10):start]
        if _INTERN_NEG_BEFORE.search(before):
            continue
        end = match.end()
        if _INTERN_NEG_AFTER.match(text[end:end + 4]):
            continue
        return {
            "rule": "internship",
            "reason": "实习岗位",
            "field": field,
            "snippet": _snippet(text, start, end),
        }
    return None


def check_job(job: dict):
    """返回命中信息 {rule, reason, field, snippet}；不该排除返回 None。"""
    title = job.get("title") or ""
    hit = _scan_offline("title", title)
    if hit:
        return hit
    hit = _scan_internship("title", title)
    if hit:
        return hit

    labels = job.get("job_labels")
    label_text = "；".join(str(x) for x in labels) if isinstance(labels, list) else (labels or "")
    hit = _scan_internship("job_labels", label_text)
    if hit:
        return hit

    # JD 与福利里只查线下面试；实习只在标题 / 岗位类型里判断，避免误伤
    for field in ("jd", "welfare", "job_labels"):
        value = job.get(field)
        text = "；".join(str(x) for x in value) if isinstance(value, list) else (value or "")
        hit = _scan_offline(field, text)
        if hit:
            return hit
    return None


def exclusion_result(hit: dict) -> dict:
    """把命中信息转成 screen 同款结果，让计划里的字段保持一致。"""
    snippet = hit["snippet"]
    return {
        "score": 0,
        "verdict": "skip",
        "reasons": [f"预筛排除：{hit['reason']}（{snippet}）"],
        "gaps": [],
        "greeting": "",
        "skip_reason": f"{hit['reason']}：{snippet}",
        "excluded_by": hit["rule"],
        "exclude_field": hit["field"],
        "exclude_snippet": snippet,
    }
