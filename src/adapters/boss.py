"""BOSS 直聘适配器：页面级操作全集。

只依赖注入的页面门面，不处理端口、进程、标签页发现和文件。
登录重连、熔断、失败计数等策略留在引擎里。
"""
from urllib.parse import parse_qs, quote, urlparse

from src.adapters.base import LoginProbe, Page, SearchCriteria, Tab

SEARCH_BASE = "https://www.zhipin.com/web/geek/jobs"


# 在页面内判断登录态。Cookie 优先 + DOM 兜底。
# bst cookie 注销后立即消失，是最精准的已登录信号；DOM 元素作为兜底。
_LOGIN_PROBE_JS = """
(() => {
  try {
    // ① URL 守卫：不在 BOSS 域内直接返回 unknown，避免非 BOSS 页面抛异常
    const url = (location.href || '').toLowerCase();
    if (!url.includes('zhipin.com')) {
      return JSON.stringify({ state: 'unknown', source: 'not_boss', url: location.href });
    }

    // ② bst cookie（最优先）——注销后立即消失，最干净
    const cstr = document.cookie || '';
    const hasBst = /(?:^|;\\s*)bst=/.test(cstr);

    // ② ka=header-username（DOM 兜底1）——注销后消失，直接是人名文本
    const hasUsername = !!document.querySelector('[ka="header-username"]');

    // ③ ka=header-message（DOM 兜底2）——注销后消失
    const hasMessage = !!document.querySelector('[ka="header-message"]');

    if (hasBst || hasUsername || hasMessage) {
      return JSON.stringify({
        state: 'in',
        source: hasBst ? 'bst_cookie' : (hasUsername ? 'ka-header-username' : 'ka-header-message'),
        url: location.href
      });
    }

    // 未登录：Header文案 + 二维码组合判断
    const head = document.querySelector('header,.header,.nav-wrap,#header') || document.body;
    const t = (head.innerText || '').slice(0, 500);
    if (t.includes('登录/注册') || t.includes('登录 / 注册') || /(^|[\\s|])登录([\\s|]|$)/.test(t)) {
      return JSON.stringify({ state: 'login', source: 'header_text', url: location.href });
    }

    const loginSel = '[class*="qrcode" i],[class*="login-register" i],[class*="sign-form" i],'
      + '.login-pop,.sign-wrap,.btn-login,[ka="header-login"],[ka="header-register"]';
    if (document.querySelector(loginSel)) {
      return JSON.stringify({ state: 'login', source: 'qr_popup', url: location.href });
    }

    // 兜底：无法确认按未登录处理
    return JSON.stringify({ state: 'unknown', source: 'none', url: location.href });
  } catch (e) { return JSON.stringify({ state: 'unknown', source: 'error', error: String(e) }); }
})()
"""


def get_salary_code(salary_min, salary_max):
    # Normalize None / 0
    s_min = salary_min if salary_min is not None else 0
    s_max = salary_max if salary_max is not None else 0
    if s_min == 0 and s_max == 3:
        return "402"
    elif s_min == 3 and s_max == 5:
        return "403"
    elif s_min == 5 and s_max == 10:
        return "404"
    elif s_min == 10 and s_max == 20:
        return "405"
    elif s_min == 20 and s_max == 50:
        return "406"
    elif s_min == 50 and s_max == 0:
        return "407"
    return None


class BossAdapter:
    site = "boss"

    def __init__(self, page: Page | None = None):
        self.page = page

    def pick_target(self, targets: list[Tab]) -> Tab | None:
        """从 zhipin 标签页里挑"最像在用"的那个，避免连到失效目标。

        优先级：可见的 geek 招聘页 > 任意 zhipin 普通页 > 任意 zhipin 目标。
        """
        if not targets:
            return None

        def score(p):
            url = p.get("url", "")
            s = 0
            if p.get("type") == "page":
                s += 10
            if "/web/geek/" in url:
                s += 5
            if "jobs" in url:
                s += 2
            if "login" in url or "/web/user" in url:
                s -= 8
            return s

        return sorted(targets, key=score, reverse=True)[0]

    def probe_login(self) -> LoginProbe:
        """返回 state（in / login / unknown）与判断依据 source。"""
        if self.page is None:
            return {"state": "unknown", "source": "no_page"}
        try:
            info = self.page.get_value(self.page.evaluate(_LOGIN_PROBE_JS))
            if isinstance(info, dict):
                return {"state": info.get("state") or "unknown",
                        "source": info.get("source") or "?"}
        except Exception:
            pass
        return {"state": "unknown", "source": "exception"}

    def search_url(self, c: SearchCriteria) -> str:
        """按关键词（+城市等筛选）拼搜索结果页 URL。"""
        params = []
        city_code = c.get("city_code")
        query = c.get("query") or ""
        salary_min = c.get("salary_min")
        salary_max = c.get("salary_max")
        if city_code:
            params.append(f"city={city_code}")
        if query:
            params.append(f"query={quote(query)}")
        if not c.get("salary_fuzzy"):
            if salary_code := get_salary_code(salary_min, salary_max):
                params.append(f"salary={salary_code}")
        if c.get("job_type"):
            params.append(f"jobType={c['job_type']}")
        if c.get("degrees"):
            deg_str = ",".join(str(d) for d in c["degrees"] if d)
            if deg_str:
                params.append(f"degree={deg_str}")
        if c.get("experience"):
            exp_str = ",".join(str(e) for e in c["experience"] if e)
            if exp_str:
                params.append(f"experience={exp_str}")

        url = SEARCH_BASE
        if params:
            url += "?" + "&".join(params)
        return url

    def matches_criteria(self, url: str, c: SearchCriteria) -> bool:
        """当前页面是否已经满足检索条件（query / city / salary / jobType / degree / experience）。"""
        if "zhipin.com/web/geek/job" not in url:
            return False
        qs = parse_qs(urlparse(url).query)

        # 1. Query match (comparing decoded query string)
        current_query = qs.get("query", [""])[0]
        query_match = current_query == (c.get("query") or "")

        # 2. City match
        current_city = qs.get("city", [""])[0]
        expected_city = str(c["city_code"]) if c.get("city_code") else ""
        city_match = current_city == expected_city

        # 3. Salary match
        if c.get("salary_fuzzy"):
            expected_salary_code = ""
        else:
            expected_salary_code = get_salary_code(c.get("salary_min"), c.get("salary_max")) or ""
        current_salary = qs.get("salary", [""])[0]
        salary_match = current_salary == expected_salary_code

        # 4. Job Type match
        expected_job_type = str(c["job_type"]) if c.get("job_type") else ""
        current_job_type = qs.get("jobType", [""])[0]
        job_type_match = current_job_type == expected_job_type

        # 5. Degree match
        current_degree_str = qs.get("degree", [""])[0]
        current_degrees = [d for d in current_degree_str.split(",") if d] if current_degree_str else []
        expected_degrees = [str(d) for d in (c.get("degrees") or []) if d]
        degree_match = set(current_degrees) == set(expected_degrees)

        # 6. Experience match
        current_exp_str = qs.get("experience", [""])[0]
        current_exps = [e for e in current_exp_str.split(",") if e] if current_exp_str else []
        expected_exps = [str(e) for e in (c.get("experience") or []) if e]
        experience_match = set(current_exps) == set(expected_exps)

        return (query_match and city_match and salary_match and
                job_type_match and degree_match and experience_match)
