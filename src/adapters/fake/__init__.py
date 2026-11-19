"""零网络假平台：只给测试与契约验收用，永远不触碰真实页面。

``create_adapter("fake")`` 会 import 本包，底部的 ``register_adapter``
完成自注册；测试里不需要任何手工注册。
"""

JOBS = {
    "fake-1": {
        "success": True, "title": "后端工程师", "salary": "20-30K",
        "company": "甲公司", "location": "杭州·西湖区", "area": "西湖区",
        "experience": "3-5年", "degree": "本科", "address": "西湖区文三路",
        "encrypt_job_id": "enc-1", "boss_active": "今日活跃", "platform": "fake",
        "jd": "负责服务端开发。", "skills": ["Python"], "welfare": ["双休"],
        "job_labels": ["急招"], "company_labels": ["A轮"], "company_stage": "A轮",
        "company_scale": "100-499人", "industry": "互联网", "boss_name": "王女士",
        "boss_title": "HR",
    },
    "fake-2": {
        "success": True, "title": "数据工程师", "salary": "25-35K",
        "company": "乙公司", "location": "杭州·滨江区", "area": "滨江区",
        "experience": "5-10年", "degree": "硕士", "address": "滨江区江南大道",
        "encrypt_job_id": "enc-2", "boss_active": "3日内活跃", "platform": "fake",
        "jd": "负责数据管道。", "skills": ["SQL"], "welfare": ["五险一金"],
        "job_labels": [], "company_labels": [], "company_stage": "B轮",
        "company_scale": "500-999人", "industry": "互联网", "boss_name": "李先生",
        "boss_title": "技术负责人",
    },
}


class FakePlatformAdapter:
    """所有页面操作都返回固定结果的适配器。"""

    site = "fake"
    display_name = "假平台"

    def __init__(self, page=None, click_timing=None):
        self.page = page
        self.click_timing = click_timing

    def owns_url(self, url):
        return "fake.example" in (url or "")

    def pick_target(self, targets):
        targets = [p for p in (targets or []) if self.owns_url(p.get("url", ""))]
        return targets[0] if targets else None

    def home_url(self):
        return "https://fake.example/jobs"

    def login_url(self):
        return "https://fake.example/login"

    def reload(self):
        return {"ok": True, "reason": ""}

    def scroll_list(self):
        return {"ok": True, "reason": ""}

    def scroll_detail(self):
        return {"ok": True, "reason": ""}

    def scroll_position(self):
        return {"ok": True, "scrollTop": 0}

    def probe_login(self):
        return {"state": "in", "source": "fake"}

    def search_url(self, criteria):
        return f"https://fake.example/jobs?q={criteria.get('query', '')}"

    def matches_criteria(self, url, criteria):
        return (criteria.get("query") or "") in (url or "")

    def wait_results(self, timeout=14.0):
        return {"ok": True, "state": "ready", "reason": ""}

    def list_jobs(self):
        return {
            "ok": True,
            "reason": "",
            "jobs": [
                {"job_id": jid, "title": d["title"], "salary": d["salary"],
                 "area": d["area"], "company": d["company"], "raw": {}}
                for jid, d in JOBS.items()
            ],
        }

    def probe_online(self, job_id):
        return {"ok": True, "online": True, "source": "fake", "evidence": {}}

    def click_card(self, job_id):
        return {"ok": True, "index": 0, "total": len(JOBS), "reason": ""}

    def read_detail(self, job_id):
        return dict(JOBS[job_id])

    def open_chat(self, job_id):
        return {"ok": True, "reason": ""}

    def open_conversation(self, hints, timeout=12.0):
        return {"ok": True, "input_ready": True}

    def chat_input_ready(self):
        return True

    def chat_url(self):
        return "https://fake.example/chat"

    def fill_greeting(self, text, attempts=4):
        return {"ok": True, "length": len(text)}


from src.adapters.registry import register_adapter  # noqa: E402

register_adapter("fake", FakePlatformAdapter)
