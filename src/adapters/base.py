"""平台适配器的公共契约。

适配器只碰页面：构造时注入一个页面门面（``Page``），门面只需要
BrowserManager 的 evaluate / get_value / bring_to_front / native_click /
send_cdp 这几个页面级方法，不碰端口、进程、标签页发现和文件。

失败语义：每个方法返回带 ``ok`` / ``reason`` 的字典，不向上抛异常。
唯一的例外是 ``StopError``——它是停止流程，必须继续向上冒泡。
"""
from typing import Any, Protocol, TypedDict


class Page(Protocol):
    """页面门面：BrowserManager 在页面层面的子集。"""

    def evaluate(self, expression: str, await_promise: bool = False, timeout: int = 30): ...

    def get_value(self, result): ...

    def bring_to_front(self): ...

    def native_click(self, x, y): ...

    def send_cdp(self, method: str, params: dict | None = None, timeout: int = 30,
                 stop_check=None): ...


# CDP /json 返回的标签页描述：url / type / webSocketDebuggerUrl
Tab = dict[str, Any]


class SearchCriteria(TypedDict, total=False):
    """一次采集的检索条件。键名沿用 run_collection 的参数名。"""

    query: str
    city_code: str | None
    job_type: str
    degrees: list[str]
    experience: list[str]
    salary_min: int | None
    salary_max: int | None
    salary_fuzzy: bool


class JobCard(TypedDict):
    """列表卡片。job_id 是平台内稳定 ID；BOSS 把 securityId 映射进来。"""

    job_id: str
    title: str
    salary: str
    area: str
    company: str
    raw: dict


class LoginProbe(TypedDict):
    state: str    # "in" / "login" / "unknown"
    source: str   # 判断依据，日志用


class Ready(TypedDict):
    ok: bool
    state: str    # "ready" / "login" / "timeout"
    reason: str


class ListResult(TypedDict):
    ok: bool
    jobs: list[JobCard]
    reason: str


class OnlineProbe(TypedDict, total=False):
    ok: bool
    online: bool
    source: str
    reason: str
    evidence: dict


class ClickResult(TypedDict):
    ok: bool
    index: int
    total: int
    reason: str


class ChatResult(TypedDict, total=False):
    ok: bool
    reason: str
    input_ready: bool
    text: str
    clicks: int


class FillResult(TypedDict, total=False):
    ok: bool
    reason: str
    length: int
    tag: str


class PlatformAdapter(Protocol):
    """一个招聘站点的页面操作全集。"""

    site: str
    display_name: str   # 日志与提示里显示的平台名

    def pick_target(self, targets: list[Tab]) -> Tab | None: ...

    def home_url(self) -> str: ...

    def login_url(self) -> str: ...

    def reload(self) -> dict: ...

    def scroll_list(self) -> dict: ...

    def scroll_detail(self) -> dict: ...

    def scroll_position(self) -> dict: ...

    def probe_login(self) -> LoginProbe: ...

    def search_url(self, c: SearchCriteria) -> str: ...

    def matches_criteria(self, url: str, c: SearchCriteria) -> bool: ...

    def wait_results(self, timeout: float = 14.0) -> Ready: ...

    def list_jobs(self) -> ListResult: ...

    def probe_online(self, job_id: str) -> OnlineProbe: ...

    def click_card(self, job_id: str) -> ClickResult: ...

    def read_detail(self, job_id: str) -> dict: ...

    def open_chat(self, job_id: str) -> ChatResult: ...

    # 点完「立即沟通」后页面/标签可能已经切换，重连由引擎负责；
    # 会话列表不响应合成点击，需要单独一次设备级点击（搬运时补的接口）。
    def open_conversation(self, hints: list[str], timeout: float = 12.0) -> ChatResult: ...

    def chat_input_ready(self) -> bool: ...

    def chat_url(self) -> str: ...

    def fill_greeting(self, text: str, attempts: int = 4) -> FillResult: ...
