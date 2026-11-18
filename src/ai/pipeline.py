"""计划编排：把采集结果变成一份 ai_plan_*.json。

plan 是 dispatch 的唯一输入——人不改计划，就不执行。
"""
import hashlib
import json
import os
from datetime import datetime

from src.ai.client import LLMClient
from src.ai.resume import ResumeLibrary, load_resume
from src.ai.screen import screen_jobs
from src.config import get_config, load_ai_config


class PlanError(Exception):
    pass


def load_jobs(path: str) -> list:
    if not os.path.exists(path):
        raise PlanError(f"采集文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        jobs = json.load(f)
    if not isinstance(jobs, list):
        raise PlanError(f"{path} 不是 jobs 数组")
    return jobs


def plan_path_for(source_path: str) -> str:
    """jobs_2026-11-17_RAG_杭州.json → output/ai_plan_2026-11-17_RAG_杭州.json"""
    out_dir = get_config("chrome")["output_dir"]
    name = os.path.basename(source_path)
    stem = name[len("jobs_"):] if name.startswith("jobs_") else name
    if stem.endswith(".json"):
        stem = stem[:-5]
    return os.path.join(out_dir, f"ai_plan_{stem}.json")


def decide_status(verdict: str, score: int, greeting: str, min_score: int) -> str:
    """计划里一条岗位的处置：只有判定不跳过、分数够、且招呼语非空才进 planned。"""
    if verdict == "skip" or score < min_score or not (greeting or "").strip():
        return "skip"
    return "planned"


def carry_dispatch(old: dict | None, new: dict) -> dict:
    """把旧计划里的执行记录带到新条目上。

    重新筛选会重建整个 items，如果不显式搬过来，dispatch / dispatch_at 就丢了，
    结果是把已经联系过的人再点一遍。
    """
    old = old or {}
    for key in ("dispatch", "dispatch_at", "dispatch_note"):
        if old.get(key):
            new[key] = old[key]
    return new


def _resume_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def build_plan(source_path: str, limit: int | None = None, min_score: int | None = None,
               force: bool = False, on_event=None, resume_path: str | None = None) -> dict:
    """读采集结果 → 逐条选简历 → 调模型 → 写 ai_plan_*.json。

    resume_path 给定时全部岗位共用这份简历；否则按 ai.resumes 的关键词路由。
    """
    log = on_event or (lambda msg: None)
    ai_cfg = load_ai_config()
    if not ai_cfg["base_url"] or not ai_cfg["model"]:
        raise PlanError("未配置 AI：请在 config.yaml 的 ai 段填写 base_url / model（api_key 视服务而定）")

    jobs = load_jobs(source_path)
    targets = jobs[:limit] if limit is not None else jobs
    min_score = ai_cfg["min_score"] if min_score is None else min_score
    out_path = plan_path_for(source_path)

    # ---- 简历来源 ----
    if resume_path:
        single_text = load_resume(resume_path)
        resume_hash = _resume_hash(single_text)

        def resume_for(_job):
            return "自定义", single_text
        log("[*] 使用指定简历: " + os.path.basename(resume_path))
    else:
        library = ResumeLibrary.from_config(ai_cfg)
        resume_hash = library.digest()
        resume_for = library.pick
        log("[*] 简历库: " + " / ".join(library.labels()))

    # ---- 复用已有计划 ----
    cached = {}
    if os.path.exists(out_path) and not force:
        try:
            old = json.load(open(out_path, "r", encoding="utf-8"))
            if old.get("resume_hash") == resume_hash and old.get("source_file") == os.path.basename(source_path):
                cached = {it.get("encrypt_job_id"): it for it in old.get("items", [])
                          if it.get("encrypt_job_id") and it.get("verdict")}
                log(f"[*] 读到旧计划 {len(cached)} 条")
        except Exception:
            cached = {}

    # ---- 逐条定简历，决定哪些要重新分析 ----
    picked = {}
    pending = []
    for job in targets:
        eid = job.get("encrypt_job_id") or ""
        label, text = resume_for(job)
        picked[eid] = (label, text)
        old = cached.get(eid)
        if old and old.get("resume") == label:
            continue
        pending.append(job)

    results = {}
    if pending:
        client = LLMClient.from_config()
        log(f"[*] 待分析 {len(pending)} 条，模型 {ai_cfg['model']}")
        screened = screen_jobs(client, pending, resume_for, limit=None,
                              concurrency=ai_cfg["concurrency"], on_event=log)
        for job, res in zip(pending, screened):
            results[job.get("encrypt_job_id")] = res
    else:
        log("[*] 没有需要重新分析的岗位")

    items = []
    for idx, job in enumerate(targets, 1):
        eid = job.get("encrypt_job_id") or ""
        label = picked.get(eid, ("", ""))[0]
        res = results.get(eid) or cached.get(eid) or {}
        verdict = res.get("verdict") or "skip"
        score = res.get("score") or 0
        greeting = res.get("greeting") or ""
        old_item = cached.get(eid) or {}
        items.append({
            "index": idx,
            "security_id": job.get("security_id") or "",
            "encrypt_job_id": eid,
            "title": job.get("title") or "",
            "company": job.get("company") or "",
            "salary": job.get("salary") or "",
            "location": job.get("location") or "",
            "resume": label,
            "score": score,
            "verdict": verdict,
            "reasons": res.get("reasons") or [],
            "gaps": res.get("gaps") or [],
            "greeting": greeting,
            "status": decide_status(verdict, score, greeting, min_score),
            "dispatch": "todo",
        })
        items[-1] = carry_dispatch(old_item, items[-1])

    by_resume = {}
    for it in items:
        if it["status"] == "planned":
            by_resume[it["resume"]] = by_resume.get(it["resume"], 0) + 1

    plan = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": os.path.basename(source_path),
        "model": ai_cfg["model"],
        "resume_hash": resume_hash,
        "min_score": min_score,
        "summary": {
            "total": len(items),
            "planned": sum(1 for it in items if it["status"] == "planned"),
            "skipped": sum(1 for it in items if it["status"] == "skip"),
            "by_resume": by_resume,
        },
        "items": items,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    log(f"[+] 计划已写入 {out_path}")
    return plan


def save_plan(plan: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


def load_plan(path: str) -> dict:
    if not os.path.exists(path):
        raise PlanError(f"计划文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    if not isinstance(plan.get("items"), list):
        raise PlanError(f"{path} 不是有效的计划文件")
    return plan
