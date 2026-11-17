import time
import random
import json

from src.core.js_loader import load_js


def _dt(fn: str, msg: str, data: dict | None = None):
    """写入 tracer（延迟导入避免循环依赖）。"""
    from server.tracer import tracer
    tracer.internal(f"browser_behavior.py:{fn}", msg, data or {})


VALID_SPEEDS = ("slow", "normal", "fast")

# 速度档位：bands 为 (累计概率, 下限秒, 上限秒)，按顺序命中；最后一段兜底。
# slow 保持原安全模式节奏，normal / fast 只调整本地等待，不改变读取方式。
SPEED_PROFILES = {
    "slow": {
        "label": "慢速",
        "bands": ((0.35, 1.2, 2.8), (0.85, 3.2, 6.0), (1.0, 8.0, 15.0)),
        "step_break_every": 12,
        "step_break_range": (8.0, 18.0),
        "scroll_detail": True,
        "scroll_wait_ms": 600,
        "click_delay_ms": 300,
        "click_settle_s": 0.5,
    },
    "normal": {
        "label": "中速",
        "bands": ((0.50, 0.8, 1.8), (1.0, 2.0, 4.0)),
        "step_break_every": 25,
        "step_break_range": (4.0, 8.0),
        "scroll_detail": True,
        "scroll_wait_ms": 450,
        "click_delay_ms": 200,
        "click_settle_s": 0.3,
    },
    "fast": {
        "label": "快速",
        "bands": ((1.0, 0.3, 0.8),),
        "step_break_every": 0,
        "step_break_range": (0.0, 0.0),
        "scroll_detail": False,
        "scroll_wait_ms": 250,
        "click_delay_ms": 100,
        "click_settle_s": 0.1,
    },
}

DEFAULT_SPEED = "slow"


def resolve_speed(speed=None, safe_mode=True, fast=False):
    """把 speed / safe_mode / fast 归一成一个档位。

    speed 显式传入时优先；否则兼容旧参数：fast 或关闭 safe_mode 视为 fast。
    """
    if speed in VALID_SPEEDS:
        return speed
    if fast or not safe_mode:
        return "fast"
    return DEFAULT_SPEED


class BrowserBehavior:
    """浏览器交互行为封装：点击卡片、滚动、间隔延迟。"""

    def __init__(self, speed=None, safe_mode=True, fast=False):
        self.speed = resolve_speed(speed, safe_mode, fast)
        self.profile = SPEED_PROFILES[self.speed]

    def get_browse_delay(self):
        dice = random.random()
        for threshold, lo, hi in self.profile["bands"]:
            if dice < threshold:
                return random.uniform(lo, hi)
        threshold, lo, hi = self.profile["bands"][-1]
        return random.uniform(lo, hi)

    def should_scroll_detail(self):
        return bool(self.profile["scroll_detail"])

    def maybe_step_break(self, success_count, sleep_fn=None):
        """按档位在每 N 条后休息；返回是否真的休息了。"""
        every = self.profile["step_break_every"]
        if not every or success_count <= 0 or success_count % every:
            return False
        idle = random.uniform(*self.profile["step_break_range"])
        print(f"\n  [IDLE] 间隔休息 {idle:.1f}s ...")
        if sleep_fn:
            sleep_fn(idle)
        else:
            time.sleep(idle)
        return True

    @staticmethod
    def click_job(chrome, security_id, scroll_wait_ms=600, click_delay_ms=300, settle_s=0.5):
        """
        点击目标卡片，Vue clickJobCard() 优先，DOM card.click() 兜底。

        通过 securityId 精确匹配 Vue 组件并点击对应卡片。
        scroll_wait_ms / click_delay_ms / settle_s 控制点击前后的等待，由速度档位决定。

        返回 (是否成功, 卡片在页面中的位置索引, 总卡片数)
        """
        sid_e = security_id.replace("\\", "\\\\").replace("'", "\\'")
        subs = {
            "'__SID__'": f"'{sid_e}'",
            "__SCROLL_WAIT__": str(int(scroll_wait_ms)),
            "__CLICK_DELAY__": str(int(click_delay_ms)),
        }

        _dt("click_job", "vue_try", {"sid": security_id[:30]})
        vue_js = load_js("click_vue.js", subs)
        r = chrome.evaluate(vue_js, await_promise=False)
        raw = chrome.get_value(r)
        if isinstance(raw, str):
            try:
                info = json.loads(raw or "{}")
            except:
                info = {}
        else:
            info = raw if raw is not None else {}
        if isinstance(info, dict) and info.get("ok"):
            if settle_s:
                time.sleep(settle_s)
            _dt("click_job", "vue_hit", {"index": info.get("index"), "total": info.get("total")})
            return True, info.get("index", 0), info.get("total", 0)

        _dt("click_job", "dom_try", {"sid": security_id[:30]})
        dom_js = load_js("click_dom.js", subs)
        r = chrome.evaluate(dom_js, await_promise=False)
        raw = chrome.get_value(r)
        if isinstance(raw, str):
            info = json.loads(raw or "{}")
        else:
            info = raw if raw is not None else {}
        if info.get("found"):
            if settle_s:
                time.sleep(settle_s)
            _dt("click_job", "dom_hit", {"index": info.get("index"), "total": info.get("total")})
            return True, info.get("index", 0), info.get("total", 0)

        _dt("click_job", "not_found", {"sid": security_id[:30], "total": info.get("total", 0)})
        return False, -1, info.get("total", 0)

    def click_card_by_sid(self, chrome, security_id, job_name):
        """兼容旧接口，按当前速度档位的点击等待委托给 click_job"""
        return self.click_job(
            chrome,
            security_id,
            scroll_wait_ms=self.profile["scroll_wait_ms"],
            click_delay_ms=self.profile["click_delay_ms"],
            settle_s=self.profile["click_settle_s"],
        )

    @staticmethod
    def get_scroll_position(chrome):
        """获取当前左侧列表的滚动位置（调试用）"""
        _dt("get_scroll_position", "call", {})
        try:
            result = chrome.evaluate(load_js("scroll_position.js"))
            raw = chrome.get_value(result)
            if isinstance(raw, str):
                data = json.loads(raw or "{}")
            else:
                data = raw if raw is not None else {}
            _dt("get_scroll_position", "ok", data)
            return data
        except Exception as exc:
            _dt("get_scroll_position", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            raise

    @staticmethod
    def scroll_detail(chrome):
        """滚动浏览右侧详情面板"""
        _dt("scroll_detail", "call", {})
        try:
            chrome.evaluate(load_js("scroll_detail.js"))
            _dt("scroll_detail", "ok", {})
        except Exception as exc:
            _dt("scroll_detail", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            raise

    @staticmethod
    def auto_scroll_list(chrome):
        """列表为空时触发懒加载：向下滚动一段距离，激活 BOSS 原生无限滚动加载"""
        _dt("auto_scroll_list", "start", {})
        try:
            # 不用 await_promise=True：滚动 JS 里 async 触发 XHR 懒加载，
            # CDP 若等 Promise resolve，网络慢时会直接断开连接导致误判。
            # 这里只关心是否抛异常，不关心返回值。
            result = chrome.evaluate(load_js("scroll_list.js"), await_promise=False)
            raw = chrome.get_value(result)
            _dt("auto_scroll_list", "ok", {"raw": str(raw)[:100]})
        except Exception as exc:
            _dt("auto_scroll_list", "exception", {"exc_type": type(exc).__name__, "exc": str(exc)})
            raise
        time.sleep(0.5)

