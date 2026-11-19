"""BOSS 直聘适配器：页面级操作全集。

只依赖注入的页面门面，不处理端口、进程、标签页发现和文件。
登录重连、熔断、失败计数等策略留在引擎里。
"""
import json
import sys
import time
from urllib.parse import parse_qs, quote, urlparse

from src.adapters.base import (
    ClickResult,
    JobCard,
    ListResult,
    LoginProbe,
    OnlineProbe,
    Page,
    Ready,
    SearchCriteria,
    Tab,
)
from src.core.browser import StopError
from src.core.js_loader import load_js
from src.utils import chat_input

SEARCH_BASE = "https://www.zhipin.com/web/geek/jobs"
CHAT_URL = "https://www.zhipin.com/web/geek/chat"

# 在聊天页点开会话：li.click() 触发不了 Vue 的选择逻辑，只负责定位坐标。
_OPEN_CONV_JS = r"""
(() => {
  const rows = Array.from(document.querySelectorAll('.user-list-content ul li'));
  if (!rows.length) return JSON.stringify({ ok: false, reason: '会话列表为空' });
  const hints = __HINTS__;
  const norm = el => (el.innerText || '').replace(/\s+/g, ' ');
  const hit = rows.find(r => hints.some(h => h && norm(r).includes(h)));
  const target = hit || rows[0];
  target.scrollIntoView({ block: 'center' });
  const r = target.getBoundingClientRect();
  if (r.width < 20 || r.height < 10) return JSON.stringify({ ok: false, reason: '会话条目不可见' });
  return JSON.stringify({
    ok: true, matched: !!hit,
    x: Math.round(r.left + r.width / 2),
    y: Math.round(r.top + r.height / 2),
    text: norm(target).slice(0, 60),
  });
})()
"""

# 点击卡片的本地等待，默认值与 browser_behavior.click_job 的历史默认值一致；
# 引擎按速度档位覆盖。
DEFAULT_CLICK_TIMING = {"scroll_wait_ms": 600, "click_delay_ms": 300, "click_settle_s": 0.5}


def _dt(scope: str, fn: str, msg: str, data: dict | None = None):
    """写入 tracer（延迟导入避免循环依赖）。"""
    from server.tracer import tracer
    tracer.internal(f"boss.py:{fn}", msg, data or {}, scope=scope)


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
    display_name = "BOSS 直聘"

    def __init__(self, page: Page | None = None, click_timing: dict | None = None):
        self.page = page
        self._click_timing = dict(DEFAULT_CLICK_TIMING)
        if click_timing:
            for key in self._click_timing:
                if key in click_timing:
                    self._click_timing[key] = click_timing[key]

    def owns_url(self, url: str) -> bool:
        return "zhipin.com" in (url or "")

    def pick_target(self, targets: list[Tab]) -> Tab | None:
        """从 zhipin 标签页里挑"最像在用"的那个，避免连到失效目标。

        优先级：可见的 geek 招聘页 > 任意 zhipin 普通页 > 任意 zhipin 目标。
        """
        targets = [p for p in (targets or []) if self.owns_url(p.get("url", ""))]
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

    def home_url(self) -> str:
        """启动与登录前导航的落地页。"""
        return "https://www.zhipin.com/web/geek/job"

    def login_url(self) -> str:
        """扫码登录入口页。"""
        return "https://www.zhipin.com/web/user/?ka=header-login"

    def reload(self) -> dict:
        """强制刷新当前页，用于登录后重新探测。"""
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        try:
            self.page.evaluate("location.reload()")
            return {"ok": True, "reason": ""}
        except StopError:
            raise
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    def scroll_list(self) -> dict:
        """向下滚动列表，触发懒加载。

        滚动脚本内部会异步发 XHR，不等 Promise；0.5s 是给懒加载触发留的
        结算时间，属于平台行为，不放进引擎的 humanize 节奏。
        """
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        _dt("H4", "scroll_list", "start")
        try:
            result = self.page.evaluate(load_js("scroll_list.js"), await_promise=False)
            self.page.get_value(result)
            time.sleep(0.5)
            return {"ok": True, "reason": ""}
        except StopError:
            raise
        except Exception as exc:
            _dt("H4", "scroll_list", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    def scroll_detail(self) -> dict:
        """滚动浏览右侧详情面板。"""
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        try:
            self.page.evaluate(load_js("scroll_detail.js"))
            return {"ok": True, "reason": ""}
        except StopError:
            raise
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    def scroll_position(self) -> dict:
        """当前列表滚动位置，用于回跳检测。"""
        if self.page is None:
            return {}
        try:
            raw = self.page.get_value(self.page.evaluate(load_js("scroll_position.js")))
            if isinstance(raw, str):
                return json.loads(raw or "{}")
            return raw if isinstance(raw, dict) else {}
        except StopError:
            raise
        except Exception:
            return {}

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

    def wait_results(self, timeout: float = 14.0) -> Ready:
        """导航后等待搜索结果列表渲染。

        state：
          ready   已读取到卡片（已登录且有结果）
          login   疑似未登录（兜底：非明确已登录都归此类）
          timeout 已登录但暂无结果 / 加载较慢
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.5)
            # [H2] 每个轮询轮次都记录
            _dt("H2", "wait_results", "poll", {"elapsed": f"{max(0, deadline - time.time()):.1f}s_left"})
            result = self.list_jobs()
            jobs = result.get("jobs") or []
            _dt("H2", "wait_results", "vue_result", {"job_count": len(jobs)})
            if jobs:
                return {"ok": True, "state": "ready", "reason": ""}
        # 没读取到卡片：判定登录态。明确已登录才算 timeout，否则按未登录（兜底）
        login = self.probe_login()
        login_state = login.get("state")
        _dt("H2", "wait_results", "timeout_probe", {"login_state": login_state})
        state = "timeout" if login_state == "in" else "login"
        return {"ok": False, "state": state, "reason": "results_not_loaded"}

    def list_jobs(self) -> ListResult:
        """从 Vue 组件树取当前列表，映射成 JobCard。"""
        if self.page is None:
            return {"ok": False, "jobs": [], "reason": "no_page"}
        try:
            raw = self.page.get_value(self.page.evaluate(load_js("extract_list.js")))
            if isinstance(raw, str):
                raw = json.loads(raw or "[]")
            if raw is None:
                raw = []
            if not isinstance(raw, list):
                raise TypeError(f"unexpected list type: {type(raw).__name__}")
            cards = [self._to_card(item) for item in raw if isinstance(item, dict)]
            return {"ok": True, "jobs": cards, "reason": ""}
        except StopError:
            raise
        except Exception as exc:
            _dt("L5", "list_jobs", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            return {"ok": False, "jobs": [], "reason": f"evaluate_failed:{type(exc).__name__}"}

    @staticmethod
    def _to_card(item: dict) -> JobCard:
        return {
            "job_id": item.get("securityId") or "",
            "title": item.get("jobName", "?"),
            "salary": item.get("salaryDesc", ""),
            "area": item.get("areaDistrict", ""),
            "company": item.get("brandName", ""),
            "raw": item,
        }

    def probe_online(self, job_id: str) -> OnlineProbe:
        """读取单张卡片的公司在线状态（仅本地 DOM / Vue，不发请求）。"""
        if self.page is None:
            return {"ok": False, "reason": "no_page", "evidence": {}}
        try:
            # 转义方式与点击卡片的脚本一致
            sid_e = job_id.replace("\\", "\\\\").replace("'", "\\'")
            js = load_js("read_company_online.js", {"'__SID__'": f"'{sid_e}'"})
            result = self.page.evaluate(js)
            raw = self.page.get_value(result)
            if isinstance(raw, str):
                return json.loads(raw or "{}")
            if not isinstance(raw, dict):
                # 页面返回了无法解释的类型，转成异常走统一失败分支
                raise TypeError(f"unexpected probe type: {type(raw).__name__}")
            return raw
        except StopError:
            raise
        except Exception as exc:
            return {
                "ok": False,
                "reason": f"evaluate_failed:{type(exc).__name__}",
                "evidence": {},
            }

    def click_card(self, job_id: str) -> ClickResult:
        """点击目标卡片，Vue clickJobCard() 优先，DOM card.click() 兜底。

        index 是卡片在页面中的位置，total 是本页卡片总数。
        """
        if self.page is None:
            return {"ok": False, "index": -1, "total": 0, "reason": "no_page"}
        sid_e = job_id.replace("\\", "\\\\").replace("'", "\\'")
        subs = {
            "'__SID__'": f"'{sid_e}'",
            "__SCROLL_WAIT__": str(int(self._click_timing["scroll_wait_ms"])),
            "__CLICK_DELAY__": str(int(self._click_timing["click_delay_ms"])),
        }
        settle_s = self._click_timing["click_settle_s"]
        try:
            _dt("click_job", "vue_try", {"sid": job_id[:30]})
            vue_js = load_js("click_vue.js", subs)
            r = self.page.evaluate(vue_js, await_promise=False)
            raw = self.page.get_value(r)
            if isinstance(raw, str):
                try:
                    info = json.loads(raw or "{}")
                except Exception:
                    info = {}
            else:
                info = raw if raw is not None else {}
            if isinstance(info, dict) and info.get("ok"):
                if settle_s:
                    time.sleep(settle_s)
                _dt("click_job", "vue_hit", {"index": info.get("index"), "total": info.get("total")})
                return {"ok": True, "index": info.get("index", 0),
                        "total": info.get("total", 0), "reason": ""}

            _dt("click_job", "dom_try", {"sid": job_id[:30]})
            dom_js = load_js("click_dom.js", subs)
            r = self.page.evaluate(dom_js, await_promise=False)
            raw = self.page.get_value(r)
            if isinstance(raw, str):
                info = json.loads(raw or "{}")
            else:
                info = raw if raw is not None else {}
            if info.get("found"):
                if settle_s:
                    time.sleep(settle_s)
                _dt("click_job", "dom_hit", {"index": info.get("index"), "total": info.get("total")})
                return {"ok": True, "index": info.get("index", 0),
                        "total": info.get("total", 0), "reason": ""}

            _dt("click_job", "not_found", {"sid": job_id[:30], "total": info.get("total", 0)})
            return {"ok": False, "index": -1, "total": info.get("total", 0), "reason": "not_found"}
        except StopError:
            raise
        except Exception as exc:
            _dt("click_job", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            return {"ok": False, "index": -1, "total": 0,
                    "reason": f"evaluate_failed:{type(exc).__name__}"}

    def read_detail(self, job_id: str, max_wait: float = 1.5) -> dict:
        """从页面 Vue 状态（$data.currentJob / $data.jobDetail）读取详情。

        关键发现（来自 find_jd_company_intro.py 诊断）：
          - $data.currentJob           → ✅ 同步到位（薪资/boss/品牌/技能/福利）
          - $data.jobDetail.jobInfo    → ✅ 异步稍晚（JD 明文 postDescription）
          - $data.jobDetail.brandComInfo → ✅ 异步稍晚（公司介绍 introduce）

        两者是同一个 .page-jobs-main 组件里的平行属性，加载时机不同。
        提取策略：
          1. 先读 currentJob（150ms 轮询，~1-2 轮即命中）
          2. currentJob 命中后，继续等待 jobDetail（最多再等 2s）
          3. jobDetail 就位后合并 JD + 公司介绍
        """
        STEP = 0.15
        try:
            if self.page is None:
                return {"error": "no_page", "message": "没有可用的页面"}
            sys.stdout.write("      [")
            sys.stdout.flush()

            # --- 阶段1: 快速探测 currentJob ---
            elapsed = 0.0
            base_data = None
            while elapsed < max_wait:
                js = self._make_panel_js(job_id, include_job_detail=False)
                result = self.page.evaluate(js)
                raw = self.page.get_value(result)
                if isinstance(raw, str):
                    parsed = json.loads(raw or "{}")
                else:
                    parsed = raw if raw is not None else {}

                if parsed.get("found"):
                    base_data = parsed
                    break

                time.sleep(STEP)
                elapsed += STEP

            if not base_data:
                sys.stdout.write("超时]\n")
                sys.stdout.flush()
                return {"error": "timeout", "message": f"详情面板未更新 ({max_wait}s)"}

            # --- 阶段2: 探测异步到位的 jobDetail (JD/介绍) ---
            # 即使 base_data 到了，JD 可能还在路上，我们再给点缓冲时间
            jd_max_wait = 2.0
            jd_elapsed = 0.0
            final_data = base_data

            while jd_elapsed < jd_max_wait:
                js2 = self._make_panel_js(job_id, include_job_detail=True)
                result2 = self.page.evaluate(js2)
                raw2 = self.page.get_value(result2)
                if isinstance(raw2, str):
                    parsed2 = json.loads(raw2 or "{}")
                else:
                    parsed2 = raw2 if raw2 is not None else {}

                if parsed2.get("found") and (parsed2.get("postDescription") or parsed2.get("introduce")):
                    final_data = parsed2
                    break

                time.sleep(STEP)
                jd_elapsed += STEP

            sys.stdout.write(f"OK {elapsed+jd_elapsed:.1f}s]\n")
            sys.stdout.flush()

            return {
                "success": True,
                "source": "currentJob+jobDetail",
                "security_id": final_data.get("sid", ""),
                "encrypt_job_id": final_data.get("encryptJobId", ""),
                "title":       final_data.get("jobName", ""),
                "salary":      final_data.get("salaryDesc", ""),
                "location":    final_data.get("locationName", ""),
                "experience":  final_data.get("experienceName", ""),
                "degree":      final_data.get("degreeName", ""),
                "jd":          final_data.get("postDescription", "") or final_data.get("jobDescription", ""),
                "skills":      final_data.get("skills", []),
                "welfare":     final_data.get("welfareList", []),
                "job_labels":  final_data.get("jobLabels", []),
                "address":     final_data.get("address", ""),
                "longitude":   final_data.get("longitude"),
                "latitude":    final_data.get("latitude"),
                "boss_name":   final_data.get("bossName", ""),
                "boss_title":  final_data.get("bossTitle", ""),
                "boss_active": final_data.get("bossActiveTime", ""),
                "company":     final_data.get("brandName", ""),
                "company_stage":  final_data.get("brandStageName", ""),
                "company_scale":  final_data.get("brandScaleName", ""),
                "industry":    final_data.get("industryName") or final_data.get("brandIndustry", ""),
                "company_intro": final_data.get("introduce", ""),
                "company_labels": final_data.get("labels") or final_data.get("brandLabels", []),
                "platform":    self.site,
            }
        except StopError:
            raise
        except Exception as exc:
            sys.stdout.write(f"异常]\n")
            sys.stdout.flush()
            return {"error": "exception", "message": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _make_panel_js(target_sid, include_job_detail=False):
        sid_e = target_sid.replace("\\", "\\\\").replace("'", "\\'")
        extra = load_js("read_panel_extra.js") if include_job_detail else ""
        return load_js("read_panel.js", {"'__SID__'": f"'{sid_e}'", "__EXTRA__": extra})

    def open_chat(self, job_id: str) -> dict:
        """点「立即沟通」：优先 CDP 原生点击（能触发 SPA 处理器），失败退回 element.click()。"""
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        locate = load_js("locate_chat_button.js")
        js_click = load_js("click_chat.js")
        for _ in range(3):
            try:
                raw = self.page.get_value(self.page.evaluate(locate))
                info = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except StopError:
                raise
            except Exception as exc:
                info = {"ok": False, "reason": f"定位失败: {exc}"}
            if info.get("ok"):
                self.page.bring_to_front()
                self.page.native_click(info["x"], info["y"])
                time.sleep(1.0)
                return info
            time.sleep(0.6)
        # 兜底：老办法，直接在页面里 click()
        try:
            raw = self.page.get_value(self.page.evaluate(js_click))
            return json.loads(raw) if isinstance(raw, str) else (raw or {"ok": False})
        except StopError:
            raise
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def open_conversation(self, hints: list[str] | None = None, timeout: float = 12.0) -> dict:
        """在聊天页点开会话，等输入框变成可见。

        li.click() 触发不了 Vue 的选择逻辑（实测点击后仍无选中态），
        必须用 CDP 设备级鼠标事件点坐标。新会话排在最前，优先按公司 /
        招聘者名字匹配，匹配不到退回第一条。
        """
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        js = _OPEN_CONV_JS.replace("__HINTS__", json.dumps(
            [h for h in (hints or []) if h], ensure_ascii=False))
        try:
            raw = self.page.get_value(self.page.evaluate(js))
            res = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except StopError:
            raise
        except Exception as exc:
            return {"ok": False, "reason": f"定位会话失败: {exc}"}
        if not res.get("ok"):
            return res

        self.page.bring_to_front()
        for attempt in range(3):
            self.page.native_click(res["x"], res["y"])
            deadline = time.time() + timeout / 2
            while time.time() < deadline:
                if self.chat_input_ready():
                    return res | {"input_ready": True, "clicks": attempt + 1}
                time.sleep(0.4)
            time.sleep(0.5)
        return res | {"input_ready": False, "clicks": 3}

    def chat_input_ready(self) -> bool:
        """聊天页的最后一个可见输入框是否就绪。"""
        if self.page is None:
            return False
        try:
            if "geek/chat" not in (self.page.get_value(self.page.evaluate("location.href")) or ""):
                return False
            raw = self.page.get_value(self.page.evaluate(
                "(() => { for (const e of document.querySelectorAll('textarea, [contenteditable=\'true\']')) {"
                " const r = e.getBoundingClientRect();"
                " if (r.width > 40 && r.height > 8) return true; } return false; })()"))
            return bool(raw)
        except StopError:
            raise
        except Exception:
            return False

    def chat_url(self) -> str:
        return CHAT_URL

    def fill_greeting(self, text: str, attempts: int = 4) -> dict:
        """填招呼语。实际写入统一走 src/utils/chat_input.fill_chat_input。"""
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        last = {"ok": False, "reason": "未执行"}
        for _ in range(attempts):
            last = chat_input.fill_chat_input(self.page, text)
            if last.get("ok"):
                return last
            time.sleep(0.8)
        return last


from src.adapters.registry import register_adapter  # noqa: E402

register_adapter("boss", BossAdapter)
