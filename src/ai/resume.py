"""简历读取：只支持纯文本（md / txt）。

PDF / docx 请先转成文本再放进来——解析二进制格式要额外依赖，不值得。
"""
import os

MAX_RESUME_CHARS = 6000


class ResumeError(Exception):
    pass


def load_resume(path: str) -> str:
    if not path:
        raise ResumeError("未配置简历路径（ai.resume_path 或 --resume）")
    if not os.path.exists(path):
        raise ResumeError(
            f"简历文件不存在: {path}\n"
            "把简历正文（markdown 或纯文本）保存成该文件后再试。"
        )
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    text = text.strip()
    if len(text) < 50:
        raise ResumeError(f"简历内容太短（{len(text)} 字），检查一下文件是否写错了")
    if len(text) > MAX_RESUME_CHARS:
        text = text[:MAX_RESUME_CHARS] + "\n...(已截断)"
    return text


def resume_digest(text: str, limit: int = 1500) -> str:
    """给模型看的简历摘要：压掉多余空行，控制长度。"""
    lines = [ln.rstrip() for ln in text.splitlines()]
    packed, blank = [], False
    for ln in lines:
        if not ln.strip():
            if not blank:
                packed.append("")
            blank = True
        else:
            packed.append(ln)
            blank = False
    out = "\n".join(packed).strip()
    return out[:limit]


# ---------- 简历库：按岗位方向选不同简历 ----------

class ResumeLibrary:
    """多份简历 + 关键词路由。

    每份简历配一组 keywords；挑简历时按「标题权重 3 / 技能 2 / JD 1」
    统计命中关键词的种类数，命中最多者胜出，平局或零命中走 default。
    """

    def __init__(self, entries: list, default_label: str | None = None):
        self.entries = [e for e in entries if e.get("path")]
        if not self.entries:
            raise ResumeError("简历库为空，请在 config.yaml 的 ai.resumes 里配置")
        labels = [e["label"] for e in self.entries]
        self.default_label = default_label if default_label in labels else labels[0]
        self._cache = {}

    @classmethod
    def from_config(cls, ai_cfg: dict) -> "ResumeLibrary":
        return cls(ai_cfg.get("resumes") or [], ai_cfg.get("default_resume"))

    def labels(self) -> list:
        return [e["label"] for e in self.entries]

    def load(self, label: str) -> str:
        if label in self._cache:
            return self._cache[label]
        entry = next((e for e in self.entries if e["label"] == label), self.entries[0])
        text = load_resume(entry["path"])
        self._cache[entry["label"]] = text
        return text

    def digest(self) -> str:
        """整库指纹：任一份简历内容变化都会改变它。"""
        import hashlib
        h = hashlib.sha256()
        for e in self.entries:
            h.update(e["label"].encode("utf-8"))
            h.update(self.load(e["label"]).encode("utf-8"))
        return h.hexdigest()[:12]

    @staticmethod
    def _score(keywords: list, title: str, skills: str, jd: str) -> int:
        title, skills, jd = (title or "").lower(), (skills or "").lower(), (jd or "").lower()
        score = 0
        for kw in keywords:
            kw = (kw or "").lower()
            if not kw:
                continue
            if kw in title:
                score += 3
            if kw in skills:
                score += 2
            if kw in jd:
                score += 1
        return score

    def pick(self, job: dict) -> tuple:
        """返回 (label, 简历正文)。"""
        title = job.get("title") or ""
        skills = "、".join(job.get("skills") or [])
        jd = job.get("jd") or ""
        best_label, best_score = self.default_label, 0
        for entry in self.entries:
            s = self._score(entry.get("keywords") or [], title, skills, jd)
            if s > best_score:
                best_label, best_score = entry["label"], s
        return best_label, self.load(best_label)
