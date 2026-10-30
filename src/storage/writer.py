import os
import json
from datetime import datetime

class OutputWriter:
    """JSON + Markdown 双格式输出"""
    
    def __init__(self, output_dir, tag=None):
        os.makedirs(output_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        suffix = f"_{tag}" if tag else ""
        self.json_path = os.path.join(output_dir, f"jobs_{today}{suffix}.json")
        self.md_path = os.path.join(output_dir, f"jobs_{today}{suffix}.md")
        self.all_jobs = self._load_existing()
    
    def _load_existing(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return []
    
    def is_duplicate(self, title, company):
        """内存查重"""
        for x in self.all_jobs:
            if x.get('title') == title and x.get('company') == company:
                return True
        return False
    
    @staticmethod
    def clean_text(text):
        if not text: return ""
        return "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t").strip()
    
    def save_job(self, job_data, index):
        for key in ["jd", "company_intro", "title"]:
            if key in job_data:
                job_data[key] = self.clean_text(job_data[key])
        
        job_data["collected_at"] = datetime.now().isoformat()
        self.all_jobs.append(job_data)
        
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self.all_jobs, f, ensure_ascii=False, indent=2)
        
        self._append_md(job_data, index)
    
    def _append_md(self, r, index):
        if not os.path.exists(self.md_path):
            with open(self.md_path, "w", encoding="utf-8") as f:
                f.write(f"# BOSS 直聘岗位分析报告 (V14)\n\n")
                f.write(f"> 整理时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
                f.write("---\n\n")
        
        skills_str = ", ".join(r.get("skills", [])) or "未标注"
        welfare_str = ", ".join(r.get("welfare", [])[:8]) or "未标注"
        job_labels_str = ", ".join(r.get("job_labels", [])) or "未标注"
        labels_str = ", ".join(r.get("company_labels", [])[:5]) or "未标注"
        
        with open(self.md_path, "a", encoding="utf-8") as f:
            f.write(f"## {index}. {r.get('title')} | {r.get('company')} | {r.get('salary')}\n\n")
            f.write(f"| 项目 | 内容 |\n")
            f.write(f"|:-----|:-----|\n")
            f.write(f"| 职位 | **{r.get('title')}** |\n")
            f.write(f"| 薪资 | **{r.get('salary')}** |\n")
            addr = r.get('address') or r.get('location', '未提供')
            f.write(f"| 地址 | {addr} |\n")
            f.write(f"| 经验/学历 | {r.get('experience')} / {r.get('degree')} |\n")
            f.write(f"| 公司 | **{r.get('company')}** ({r.get('company_stage')}) {r.get('company_scale')} |\n")
            f.write(f"| 城市 | {r.get('location')} |\n")
            f.write(f"| 行业 | {r.get('industry')} |\n")
            f.write(f"| 技能要求 | `{skills_str}` |\n")
            f.write(f"| 福利标签 | {welfare_str} |\n")
            f.write(f"| 职位标签 | {job_labels_str} |\n")
            f.write(f"| 招聘者 | {r.get('boss_name')} - {r.get('boss_title')} ({r.get('boss_active')}) |\n")
            f.write(f"| 公司标签 | {labels_str} |\n\n")
            f.write(f"### 职位描述\n\n")
            f.write(f"```text\n{r.get('jd', '未提供')}\n```\n\n")
            if r.get("company_intro"):
                f.write(f"### 公司简介\n\n")
                f.write(f"> {r.get('company_intro', '')[:300]}\n\n")
            f.write("---\n\n")
