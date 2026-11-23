"""智联招聘适配器：只读采集 + ``apply_then_chat`` 投递。

数据只来自浏览器已渲染页面里的 ``window.__INITIAL_STATE__``，Python 侧
不向 zhaopin.com 发任何 HTTP 请求。搜索页未登录也能读首屏 20 条与完整
JD，所以 ``probe_login`` 的 ``in`` 含义是「页面可读」，不是「账号已登录」。

投递：智联点「立即投递」会同时投简历 + 发平台预设打招呼语（不可逆），
之后弹窗「继续沟通」进聊天。只有配置里 ``apply.enabled`` 与
``apply.send_message`` 都打开，且页面已登录、岗位未投过时才允许点。

已知站点限制（实测，不再联网验证）：
- 搜索页只 SSR 首屏 20 条；加 ``p`` / ``page`` / ``pageIndex`` 或滚动都不会
  加载更多。
- 薪资 / 学历 / 经验下拉筛选没有可寻址编码，点了不改 URL 也不产生请求，
  所以 ``search_url`` 不拼这些参数。
- 点卡片不会更新 state 里的详情，详情直接读 ``positionList[i].jobDetailData``。
- 投递按钮 ``button.job-detail-summary__apply`` 只作用于右侧详情面板当前
  选中的岗位；点之前必须核对 ``selectedJobId`` 与目标一致。
- 投递状态字段是 ``hasAppliedPosition`` / ``alreadyApply`` / ``applyType``
  （游客页实测 20/20：``hasAppliedPosition=false``、``applyType="1"``）。
"""
import json
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
from src.adapters.zhaopin.cities import resolve_city_code
from src.config import load_apply_config
from src.core.browser import StopError
from src.core.js_loader import load_js
from src.focus_lock import foreground
from src.utils import chat_input
from src.utils.audit import write_audit

SEARCH_BASE = "https://www.zhaopin.com/jobs/"
HOME_URL = "https://www.zhaopin.com/"
LOGIN_URL = "https://passport.zhaopin.com/login"


def _dt(fn: str, msg: str, data: dict | None = None):
    """写入 tracer（延迟导入避免循环依赖；缺失时静默）。"""
    try:
        from server.tracer import tracer
        tracer.internal(f"zhaopin.py:{fn}", msg, data or {}, scope="zhaopin")
    except Exception:
        pass


def _json_value(raw, default):
    """页面脚本统一返回 JSON 字符串；兼容门面已经解析过的情况。"""
    if isinstance(raw, str):
        try:
            return json.loads(raw or "null")
        except json.JSONDecodeError:
            return default
    return raw if raw is not None else default


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _first(*values):
    """取第一个真值，全部为空时返回空串。"""
    for value in values:
        if value:
            return value
    return ""


class ZhaopinAdapter:
    site = "zhaopin"
    display_name = "智联招聘"
    delivery_mode = "apply_then_chat"

    # 投递日志要用公司名，但 apply() 只收 job_id；apply 成功读到状态后记在这里，
    # send_message 紧接着取用。只在同一实例内、同一次投递流程内有效。
    _last_job: dict = {}

    def __init__(self, page: Page | None = None, click_timing: dict | None = None):
        self.page = page
        # 智联不点击卡片，速度档位只影响引擎自己的等待节奏；保留参数以符合构造约定。
        self._click_timing = dict(click_timing or {})
        self._last_job = {}

    # ── 选页与站点入口 ────────────────────────────────────────────────

    def owns_url(self, url: str) -> bool:
        return "zhaopin.com" in (url or "")

    def pick_target(self, targets: list[Tab]) -> Tab | None:
        """从 zhaopin 标签页里挑最像在用的那个。

        搜索页 > 详情页 > 首页；登录入口页降权，避免接到刚打开的 passport 页。
        """
        targets = [p for p in (targets or []) if self.owns_url(p.get("url", ""))]
        if not targets:
            return None

        def score(p):
            url = (p.get("url") or "").lower()
            s = 0
            if p.get("type") == "page":
                s += 10
            if "/jobs/" in url:
                s += 5
            if "jobdetail" in url:
                s += 2
            if "passport" in url or "login" in url:
                s -= 8
            return s

        return sorted(targets, key=score, reverse=True)[0]

    def home_url(self) -> str:
        return HOME_URL

    def login_url(self) -> str:
        return LOGIN_URL

    def reload(self) -> dict:
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        try:
            self.page.evaluate("location.reload()")
            return {"ok": True, "reason": ""}
        except StopError:
            raise
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    # ── 滚动 ──────────────────────────────────────────────────────────

    def _scroll(self, selector: str, scroll_window: bool) -> dict:
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        try:
            js = load_js("zhaopin_scroll.js", {
                "'__SELECTOR__'": f"'{selector}'",
                "__SCROLL_WINDOW__": "true" if scroll_window else "false",
            })
            raw = _json_value(self.page.get_value(self.page.evaluate(js)), {})
            if isinstance(raw, dict) and raw.get("ok") is False:
                return {"ok": False, "reason": str(raw.get("reason") or "scroll_failed")}
            return {"ok": True, "reason": ""}
        except StopError:
            raise
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    def scroll_list(self) -> dict:
        """滚到列表底部。

        实测智联只渲染首屏 20 条，滚动不会触发加载更多；这里只为与引擎
        的滚动节奏保持一致。
        """
        return self._scroll(".job-list-panel", scroll_window=True)

    def scroll_detail(self) -> dict:
        """把右侧详情面板滚到底。"""
        return self._scroll(".job-detail-panel", scroll_window=False)

    def scroll_position(self) -> dict:
        if self.page is None:
            return {}
        try:
            raw = _json_value(
                self.page.get_value(self.page.evaluate("JSON.stringify({scrollTop: window.scrollY})")),
                {},
            )
            return raw if isinstance(raw, dict) else {}
        except StopError:
            raise
        except Exception:
            return {}

    # ── 登录态 ────────────────────────────────────────────────────────

    def probe_login(self) -> LoginProbe:
        """返回 ``in / login / unknown`` 与判断依据。

        智联游客态就能读全量列表和完整 JD，因此 ``in`` 的含义是「页面可读」，
        不是「账号已登录」。只有真的落在 passport / 登录入口页才返回
        ``login``，避免引擎把可读的游客首页误判成需要扫码。
        """
        if self.page is None:
            return {"state": "unknown", "source": "no_page"}
        try:
            info = _json_value(self.page.get_value(self.page.evaluate(load_js("zhaopin_login.js"))), {})
            if isinstance(info, dict):
                return {
                    "state": info.get("state") or "unknown",
                    "source": info.get("source") or "?",
                }
        except StopError:
            raise
        except Exception:
            pass
        return {"state": "unknown", "source": "exception"}

    # ── 检索 ──────────────────────────────────────────────────────────

    def search_url(self, c: SearchCriteria) -> str:
        """拼搜索结果页 URL，只带 ``jl``（城市）与 ``kw``（关键词）。

        ``salary_*`` / ``job_type`` / ``degrees`` / ``experience`` 一律忽略：
        智联的筛选下拉没有可寻址参数，点了不改 URL 也不产生请求。
        城市码解析不到时省略 ``jl``，回落到站点默认城市。
        """
        params = []
        city = resolve_city_code(c.get("city_code"))
        if city:
            params.append(f"jl={city}")
        query = c.get("query") or ""
        if query:
            params.append(f"kw={quote(query)}")
        url = SEARCH_BASE
        if params:
            url += "?" + "&".join(params)
        return url

    def matches_criteria(self, url: str, c: SearchCriteria) -> bool:
        """路径含 ``/jobs`` 且 ``kw`` / ``jl`` 与期望一致；其余条件不参与。"""
        parsed = urlparse(url or "")
        if "/jobs" not in parsed.path:
            return False
        qs = parse_qs(parsed.query)
        current_kw = qs.get("kw", [""])[0]
        expected_kw = c.get("query") or ""
        current_jl = qs.get("jl", [""])[0]
        expected_jl = resolve_city_code(c.get("city_code")) or ""
        return current_kw == expected_kw and current_jl == expected_jl

    def wait_results(self, timeout: float = 14.0) -> Ready:
        """轮询列表；超时后用 ``probe_login`` 区分 timeout / login。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.5)
            jobs = self.list_jobs().get("jobs") or []
            if jobs:
                return {"ok": True, "state": "ready", "reason": ""}
        login = self.probe_login()
        state = "timeout" if login.get("state") == "in" else "login"
        return {"ok": False, "state": state, "reason": "results_not_loaded"}

    # ── 列表与详情 ────────────────────────────────────────────────────

    def list_jobs(self) -> ListResult:
        """读 ``window.__INITIAL_STATE__.positionList``，映射成 JobCard。"""
        if self.page is None:
            return {"ok": False, "jobs": [], "reason": "no_page"}
        try:
            raw = _json_value(self.page.get_value(self.page.evaluate(load_js("zhaopin_list.js"))), [])
            if isinstance(raw, dict) and raw.get("__error__"):
                raise RuntimeError(f"state_error:{raw.get('__error__')}")
            if raw is None:
                raw = []
            if not isinstance(raw, list):
                raise TypeError(f"unexpected list type: {type(raw).__name__}")
            cards = [self._to_card(item) for item in raw if isinstance(item, dict)]
            return {"ok": True, "jobs": cards, "reason": ""}
        except StopError:
            raise
        except Exception as exc:
            _dt("list_jobs", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            return {"ok": False, "jobs": [], "reason": f"evaluate_failed:{type(exc).__name__}"}

    @staticmethod
    def _to_card(item: dict) -> JobCard:
        return {
            "job_id": str(item.get("number") or ""),
            "title": item.get("name") or "",
            "salary": item.get("salary60") or "",
            "area": item.get("cityDistrict") or "",
            "company": item.get("companyName") or "",
            "raw": item,
        }

    def probe_online(self, job_id: str) -> OnlineProbe:
        """智联没有「公司在线」标识；返回 unknown 让引擎照常采集。"""
        return {
            "ok": False,
            "online": None,
            "source": "unsupported",
            "reason": "unsupported: no_company_online_indicator",
            "evidence": {},
        }

    def click_card(self, job_id: str) -> ClickResult:
        """定位卡片并滚到可视区，不点击。

        详情来自 ``positionList[i].jobDetailData``，点击对读数没有意义；
        这里只用于保持引擎 / 复核页的返回形状，并让「定位」至少把列表
        滚到目标卡片。``ok`` 恒为 True（页面可读即算成功），避免调用方
        回落到其他平台的定位逻辑。
        """
        if self.page is None:
            return {"ok": False, "index": -1, "total": 0, "reason": "no_page"}
        try:
            js = load_js("zhaopin_click.js", {
                "__JOB_ID__": json.dumps(str(job_id or ""), ensure_ascii=False),
            })
            info = _json_value(self.page.get_value(self.page.evaluate(js)), {})
            if not isinstance(info, dict):
                info = {}
            index = info.get("index")
            total = info.get("total")
            return {
                "ok": True,
                "index": index if isinstance(index, int) else -1,
                "total": total if isinstance(total, int) else 0,
                "reason": "state_only",
            }
        except StopError:
            raise
        except Exception as exc:
            _dt("click_card", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            return {"ok": True, "index": -1, "total": 0, "reason": "state_only"}

    def read_detail(self, job_id: str) -> dict:
        """从 ``positionList`` 里按 number（其次 jobId）读完整详情。

        JD 为空时再读一次详情面板 DOM 兜底。失败返回 ``{error, message}``。
        """
        if self.page is None:
            return {"error": "no_page", "message": "没有可用的页面"}
        ident = str(job_id or "")
        try:
            js = load_js("zhaopin_item.js", {
                "__JOB_ID__": json.dumps(ident, ensure_ascii=False),
            })
            item = _json_value(self.page.get_value(self.page.evaluate(js)), None)
            if isinstance(item, dict) and item.get("__error__"):
                return {"error": "evaluate_failed", "message": str(item.get("__error__"))}
            if not isinstance(item, dict):
                return {"error": "not_found", "message": f"positionList 中找不到 {ident}"}

            detail = self._to_detail(item)
            if not detail["jd"]:
                detail["jd"] = self._read_dom_jd()
            return detail
        except StopError:
            raise
        except Exception as exc:
            _dt("read_detail", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            return {"error": type(exc).__name__, "message": str(exc)}

    def _read_dom_jd(self) -> str:
        try:
            raw = _json_value(self.page.get_value(self.page.evaluate(load_js("zhaopin_dom_jd.js"))), {})
            if isinstance(raw, dict):
                return str(raw.get("text") or "").strip()
        except StopError:
            raise
        except Exception:
            pass
        return ""

    @staticmethod
    def _to_detail(item: dict) -> dict:
        """把 positionList 的一项映射成采集输出字典。

        所有字段拿不到就用空串 / 空列表，不从 DOM 文本里猜。
        """
        detail_data = _dict(item.get("jobDetailData"))
        position = _dict(detail_data.get("position"))
        base = _dict(position.get("base"))
        desc = _dict(position.get("desc"))
        work_location = _dict(position.get("workLocation"))
        staff = _dict(detail_data.get("staff"))

        city = item.get("workCity") or ""
        district = item.get("cityDistrict") or ""
        location = "·".join(part for part in (city, district) if part)

        tags = item.get("jobSkillTags")
        skills = []
        if isinstance(tags, list):
            skills = [t.get("name") for t in tags if isinstance(t, dict) and t.get("name")]
        if not skills:
            labels = item.get("skillLabel")
            if isinstance(labels, list):
                skills = [x.get("value") for x in labels if isinstance(x, dict) and x.get("value")]

        commercial = item.get("commercialLabel")
        job_labels = []
        if isinstance(commercial, list):
            job_labels = [
                label.get("typeName") for label in commercial
                if isinstance(label, dict) and label.get("typeName")
            ]

        welfare = item.get("welfareLabel")
        if not isinstance(welfare, list):
            welfare = []

        boss_active = staff.get("lastOnlineTimeText")
        if not boss_active:
            levels = staff.get("activityLevel")
            if isinstance(levels, list):
                boss_active = "、".join(str(level) for level in levels if level)
        boss_active = boss_active or ""

        return {
            "success": True,
            "source": "state.positionList",
            "encrypt_job_id": str(item.get("number") or ""),
            # 智联没有「同会话卡片 id」这一层，岗位号在页面内稳定，兼作定位键。
            # 持久化主键仍是 encrypt_job_id（track_key 优先取它），不会把
            # 会话 id 写进 tracking。
            "security_id": str(item.get("number") or ""),
            "title": item.get("name") or "",
            "salary": item.get("salary60") or "",
            "location": location,
            "experience": _first(item.get("workingExp"), base.get("positionWorkingExp")),
            "degree": _first(item.get("education"), base.get("education")),
            "jd": _first(desc.get("description"), item.get("jobDescription")),
            "skills": skills,
            "welfare": welfare,
            "job_labels": job_labels,
            "address": work_location.get("workAddress") or "",
            "longitude": work_location.get("longitude") or "",
            "latitude": work_location.get("latitude") or "",
            "boss_name": staff.get("staffName") or "",
            "boss_title": staff.get("hrJob") or "",
            "boss_active": boss_active,
            "company": _first(item.get("companyName"), staff.get("companyName")),
            "company_stage": item.get("financingStage") or "",
            "company_scale": item.get("companySize") or "",
            "industry": item.get("industryName") or "",
            "company_intro": "",
            "company_labels": list(job_labels),
            "platform": ZhaopinAdapter.site,
        }

    # ── 投递侧：apply_then_chat ──────────────────────────────────────

    def open_chat(self, job_id: str) -> dict:
        return {"ok": False, "reason": "unsupported: apply_flow_not_implemented"}

    def open_conversation(self, hints: list[str] | None = None, timeout: float = 12.0) -> dict:
        """投递后已进聊天页；这里只等输入框就绪，不再点任何东西。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.chat_input_ready():
                return {"ok": True, "input_ready": True, "reason": "", "text": self.chat_url()}
            time.sleep(0.5)
        return {"ok": False, "input_ready": False, "reason": "chat_input_not_ready"}

    def chat_input_ready(self) -> bool:
        return bool(self._chat_snapshot().get("input_ready"))

    def chat_url(self) -> str:
        if self.page is None:
            return ""
        try:
            url = self.page.get_value(self.page.evaluate("location.href")) or ""
            return url if "chat" in url else ""
        except StopError:
            raise
        except Exception:
            return ""

    def fill_greeting(self, text: str, attempts: int = 4) -> dict:
        """智联不走「只填草稿」：要么整条投递 + 发消息，要么什么都不动。"""
        return {"ok": False, "reason": "unsupported: apply_flow_not_implemented"}

    @staticmethod
    def _is_applied(state: dict) -> bool:
        if state.get("already_apply") is True or state.get("has_applied_position") is True:
            return True
        # 游客页实测 applyType 恒为 "1"（未投递）。遇到没见过的编码按已投处理：
        # 宁可漏投一次，也不能对同一家重复投。
        value = state.get("apply_type")
        return value is not None and str(value) not in ("", "0", "1")

    def apply_state(self, job_id: str) -> dict:
        """只读：岗位是否已投、是否已登录、详情面板是否选中目标、按钮在哪。"""
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        try:
            js = load_js("zhaopin_apply_state.js", {
                "__JOB_ID__": json.dumps(str(job_id or ""), ensure_ascii=False),
            })
            info = _json_value(self.page.get_value(self.page.evaluate(js)), {})
            if not isinstance(info, dict):
                return {"ok": False, "reason": "unexpected_state"}
            return info
        except StopError:
            raise
        except Exception as exc:
            _dt("apply_state", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}

    def apply(self, job_id: str) -> dict:
        """点「立即投递」并进聊天。三道闸 + 登录 + 幂等，任何一条不满足都不点。"""
        gates = load_apply_config()
        evidence: dict = {"gates": gates}
        job_id = str(job_id or "")

        def fail(reason: str, company: str = "") -> dict:
            return self._apply_result(job_id, company, False, False, reason, evidence)

        if not (gates["enabled"] and gates["send_message"]):
            return fail("unsupported: apply_disabled")
        if self.page is None:
            return fail("no_page")

        state = self.apply_state(job_id)
        evidence["state"] = state
        if not state.get("ok"):
            return fail(state.get("reason") or "state_failed")
        if not state.get("found"):
            return fail("job_not_in_list")

        company = state.get("company") or ""
        self._last_job = {"job_id": job_id, "company": company}
        if self._is_applied(state):
            return self._apply_result(job_id, company, True, False,
                                      "skipped: already_applied", evidence)
        if not state.get("logged_in"):
            return fail("unsupported: login_required", company)

        if not state.get("selected"):
            sel = self._select_job(job_id, state.get("index"))
            evidence["select"] = sel
            if not sel.get("ok"):
                return fail(sel.get("reason") or "not_selected", company)
            state = self.apply_state(job_id)
            evidence["state"] = state
            if not state.get("ok") or not state.get("selected"):
                return fail("not_selected", company)

        button = state.get("button") or {}
        if not button.get("found"):
            return fail("apply_button_not_found", company)
        if button.get("disabled"):
            return fail("apply_button_disabled", company)
        if "已投" in (button.get("text") or ""):
            return self._apply_result(job_id, company, True, False,
                                      "skipped: already_applied", evidence)

        # ── 从这里开始不可逆：只有前面全过才会走到 ──
        clicked = self._click(button)
        evidence["click"] = clicked
        if not clicked.get("ok"):
            return fail(clicked.get("reason") or "click_failed", company)

        modal = self._wait_apply_modal()
        evidence["modal"] = modal
        if not modal.get("confirmed"):
            if modal.get("login"):
                return fail("unsupported: login_required", company)
            return fail("apply_unconfirmed", company)

        evidence["chat"] = self._continue_to_chat(modal)
        return self._apply_result(job_id, company, True, True, "", evidence)

    def send_message(self, text: str) -> dict:
        """在聊天页发一条消息。只有回读到消息进入记录才返回 sent=True。"""
        gates = load_apply_config()
        body = text or ""
        evidence: dict = {"gates": gates}
        job = dict(self._last_job or {})
        job_id = job.get("job_id", "")
        company = job.get("company", "")

        def fail(reason: str) -> dict:
            return self._send_result(job_id, company, len(body), False, reason, evidence)

        if not (gates["enabled"] and gates["send_message"]):
            return fail("unsupported: apply_disabled")
        if self.page is None:
            return fail("no_page")
        if not body.strip():
            return fail("empty_text")

        before = self._chat_snapshot()
        evidence["before"] = {"ok": before.get("ok"),
                              "input_ready": before.get("input_ready"),
                              "input_len": before.get("input_len")}
        if not before.get("input_ready"):
            return fail("chat_input_not_ready")

        filled = chat_input.fill_chat_input(self.page, body)
        evidence["fill"] = filled
        if not filled.get("ok"):
            return fail(f"fill_failed: {filled.get('reason')}")

        button = (self._chat_snapshot().get("send") or {})
        evidence["button"] = button
        if not button.get("found"):
            return fail("send_button_not_found")

        clicked = self._click(button)
        evidence["click"] = clicked
        if not clicked.get("ok"):
            return fail(clicked.get("reason") or "click_failed")

        probe = body.strip()[:20]
        deadline = time.time() + 5.0
        last: dict = {}
        while time.time() < deadline:
            last = self._chat_snapshot()
            if not last.get("ok"):
                break
            if any(probe in str(m) for m in (last.get("messages") or [])):
                evidence["after"] = {"verified": True, "input_len": last.get("input_len")}
                return self._send_result(job_id, company, len(body), True, "", evidence)
            time.sleep(0.4)

        evidence["after"] = {
            "verified": False,
            "input_len": last.get("input_len"),
            "messages": (last.get("messages") or [])[-5:],
        }
        return fail("sent_unverified")

    # ── 投递辅助 ──────────────────────────────────────────────────────

    def _apply_result(self, job_id: str, company: str, ok: bool, submitted: bool,
                      reason: str, evidence: dict) -> dict:
        write_audit(self.site, "apply", job_id=job_id, company=company,
                    ok=bool(ok), submitted=bool(submitted), reason=reason or "")
        return {"ok": bool(ok), "reason": reason or "", "submitted": bool(submitted),
                "evidence": evidence}

    def _send_result(self, job_id: str, company: str, length: int, sent: bool,
                     reason: str, evidence: dict) -> dict:
        write_audit(self.site, "send_message", job_id=job_id, company=company,
                    length=int(length), sent=bool(sent), reason=reason or "")
        return {"ok": bool(sent), "reason": reason or "", "sent": bool(sent),
                "length": int(length), "evidence": evidence}

    def _click(self, rect: dict) -> dict:
        """切前台 + 设备级点击；坐标点击会抢窗口焦点，必须和别的平台串行。"""
        x, y = rect.get("x"), rect.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            return {"ok": False, "reason": "bad_rect"}
        try:
            with foreground():
                self.page.bring_to_front()
                self.page.native_click(x, y)
                time.sleep(0.6)
            return {"ok": True, "reason": ""}
        except StopError:
            raise
        except Exception as exc:
            _dt("_click", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            return {"ok": False, "reason": f"click_failed: {type(exc).__name__}"}

    def _select_job(self, job_id: str, index) -> dict:
        """点列表卡片切详情面板，并回读 selectedJobId 确认没点错岗位。"""
        if not isinstance(index, int) or index < 0:
            return {"ok": False, "reason": "job_not_in_list"}
        try:
            js = load_js("zhaopin_select.js", {"__INDEX__": str(index)})
            info = _json_value(self.page.get_value(self.page.evaluate(js)), {})
        except StopError:
            raise
        except Exception as exc:
            return {"ok": False, "reason": f"select_failed: {type(exc).__name__}"}
        if not isinstance(info, dict) or not info.get("ok"):
            return {"ok": False, "reason": str((info or {}).get("reason") or "card_not_found")}

        clicked = self._click(info)
        if not clicked.get("ok"):
            return clicked
        deadline = time.time() + 5.0
        while time.time() < deadline:
            state = self.apply_state(job_id)
            if state.get("ok") and state.get("selected"):
                return {"ok": True, "reason": ""}
            time.sleep(0.3)
        return {"ok": False, "reason": "select_unverified"}

    def _wait_apply_modal(self, timeout: float = 6.0) -> dict:
        last: dict = {}
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                info = _json_value(
                    self.page.get_value(self.page.evaluate(load_js("zhaopin_apply_modal.js"))), {})
            except StopError:
                raise
            except Exception as exc:
                last = {"confirmed": False, "reason": f"modal_failed: {type(exc).__name__}"}
                time.sleep(0.4)
                continue
            if isinstance(info, dict):
                last = info
                if info.get("confirmed") or info.get("login"):
                    return info
            time.sleep(0.4)
        return last or {"confirmed": False, "reason": "modal_timeout"}

    def _continue_to_chat(self, modal: dict) -> dict:
        button = modal.get("continue") or {}
        if not button.get("found"):
            return {"ok": False, "reason": "continue_button_not_found"}
        clicked = self._click(button)
        if not clicked.get("ok"):
            return clicked
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if self.chat_input_ready():
                return {"ok": True, "reason": "", "url": self.chat_url()}
            time.sleep(0.5)
        return {"ok": False, "reason": "chat_not_opened"}

    def _chat_snapshot(self) -> dict:
        if self.page is None:
            return {"ok": False, "reason": "no_page"}
        try:
            info = _json_value(
                self.page.get_value(self.page.evaluate(load_js("zhaopin_chat_read.js"))), {})
            return info if isinstance(info, dict) else {"ok": False, "reason": "unexpected_state"}
        except StopError:
            raise
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}


from src.adapters.registry import register_adapter  # noqa: E402

register_adapter("zhaopin", ZhaopinAdapter)
