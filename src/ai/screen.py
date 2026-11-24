"""按简历给岗位打分、判定是否投递，并生成招呼语。

一轮筛选 = 每个岗位一次模型调用。串行太慢，所以用线程池并发，
但并发度受 ai.concurrency 限制（本地代理扛不住太高并发）。
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.ai.resume import resume_digest

SYSTEM_PROMPT = """你是一名资深技术招聘顾问，同时替求职者做岗位初筛。

你的判断标准：
1. 硬性条件（技能栈、经验年限、学历、行业）优先，硬伤直接 skip。
2. 技术方向要对口：做过相似系统比堆关键词更重要。
3. 打招呼要说人话：具体、克制、有信息量，不要模板腔。

你只输出 JSON，不输出任何解释、前后缀或 markdown 围栏。"""

USER_TMPL = """## 求职者简历
{resume}

## 岗位
- 标题：{title}
- 公司：{company}（{stage}{scale}{industry}）
- 薪资：{salary}
- 经验 / 学历：{experience} / {degree}
- 地点：{location}
- 技能标签：{skills}
- 福利：{welfare}
- 公司介绍：{intro}
- 岗位描述：
{jd}

## 输出要求
严格输出这个 JSON 结构：
{{"score": 0, "verdict": "apply", "reasons": [], "gaps": [], "greeting": ""}}

- score：0-100 的匹配度整数
- verdict：apply（值得投）/ maybe（可以聊）/ skip（不投）
  * 硬性排除：JD 明确要求线下 / 现场面试或到岗面谈，或岗位本身就是实习（标题或岗位类型写明实习生 / 实习岗 / 暑期实习 / 日常实习）时，一律 skip，reasons 第一条写清命中点
  * 以下不算排除，不得因此 skip：线上面试 / 视频面试 / 远程面试 / 可线下面试；实习证明 / 实习期薪资 / 实习经历；带实习生 / 实习生导师 / 非实习 / 社招
- reasons：2-3 条，每条一句，必须引用 JD 里的具体要求，说明为什么匹配
- gaps：1-2 条主要不匹配点，没有就给空数组
- greeting：给 BOSS 直聘的第一条招呼语，80-120 字，严格不超过 140 字。要求：
  * 用「角色 + 技术栈」说明身份，例如「做 Agent 与 RAG 工程」，不写姓名
  * 严禁出现真实姓名（含「X先生」「X女士」这类姓氏称呼）、手机号、邮箱、微信号、住址等任何联系方式
  * 严禁使用「我是XXX」「我叫XXX」「您好，我是…」这类自我介绍句式
  * 说清我做过什么可对应的事、想聊什么
  * 至少提到 JD 里的 1 个具体要求，并给出简历里能对应的事实
  * 不堆形容词、不喊口号、不复述岗位标题
  * 直接进入技术内容，不要客套，结尾不要反问问句堆叠
- 简历中的真实姓名、手机号、邮箱、微信号、住址只用于你判断匹配度，禁止出现在 greeting 里。"""


def _brief(job: dict, jd_limit: int = 1200) -> dict:
    return {
        "title": job.get("title") or "",
        "company": job.get("company") or "",
        "stage": job.get("company_stage") or "",
        "scale": job.get("company_scale") or "",
        "industry": f" · {job['industry']}" if job.get("industry") else "",
        "salary": job.get("salary") or "",
        "experience": job.get("experience") or "不限",
        "degree": job.get("degree") or "不限",
        "location": job.get("location") or "",
        "skills": "、".join(job.get("skills") or []) or "未标注",
        "welfare": "、".join((job.get("welfare") or [])[:8]) or "未标注",
        "intro": (job.get("company_intro") or "")[:300],
        "jd": (job.get("jd") or "")[:jd_limit],
    }


def _blank_result(reason: str) -> dict:
    return {"score": 0, "verdict": "skip", "reasons": [reason], "gaps": [], "greeting": ""}


def analyze_job(client, job: dict, resume_text: str) -> dict:
    """单条岗位：一次模型调用，返回 score/verdict/reasons/gaps/greeting。"""
    if not (job.get("jd") or "").strip():
        return _blank_result("详情页没有 JD 正文（可能脱敏或未加载），无法判断，建议重新采集")

    brief = _brief(job)
    user = USER_TMPL.format(resume=resume_digest(resume_text), **brief)
    data = client.chat_json([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ], max_tokens=900)

    score = data.get("score")
    verdict = data.get("verdict")
    if not isinstance(score, (int, float)):
        score = 0
    score = max(0, min(100, int(score)))
    if verdict not in ("apply", "maybe", "skip"):
        verdict = "apply" if score >= 75 else ("maybe" if score >= 50 else "skip")
    return {
        "score": score,
        "verdict": verdict,
        "reasons": [str(x)[:120] for x in (data.get("reasons") or [])][:3],
        "gaps": [str(x)[:120] for x in (data.get("gaps") or [])][:2],
        "greeting": (data.get("greeting") or "").strip()[:400],
    }


def screen_jobs(client, jobs: list, resume_for, limit: int | None = None,
                concurrency: int = 4, on_event=None) -> list:
    """并发筛选。

    resume_for(job) -> (label, 简历正文)：每个岗位可以用不同的简历，
    由调用方决定路由规则（见 ResumeLibrary.pick）。
    返回与 jobs 同序的结果列表，每项带 resume 字段。
    """
    targets = jobs[:limit] if limit else list(jobs)
    results = [None] * len(targets)
    done = 0

    def _run(idx_job):
        idx, job = idx_job
        try:
            label, text = resume_for(job)
            data = analyze_job(client, job, text)
            data["resume"] = label
            return idx, data, None
        except Exception as exc:  # noqa: BLE001
            return idx, None, str(exc)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_run, pair) for pair in enumerate(targets)]
        for fut in as_completed(futures):
            idx, data, err = fut.result()
            done += 1
            if on_event:
                title = (targets[idx].get("title") or "?")[:20]
                if err:
                    on_event(f"[{done}/{len(targets)}] 失败 {title}: {err}")
                else:
                    on_event(f"[{done}/{len(targets)}] {data['score']:>3} 分 "
                             f"{data['verdict']:<5} [{data.get('resume', '')[:6]}] {title}")
            results[idx] = {**(data or _blank_result(f"模型调用失败: {err}"))}

    return results
