import time
import random
import json

from src.core.js_loader import load_js


def _dt(fn: str, msg: str, data: dict | None = None):
    """写入 tracer（延迟导入避免循环依赖）。"""
    from server.tracer import tracer
    tracer.internal(f"browser_behavior.py:{fn}", msg, data or {})


class BrowserBehavior:
    """浏览器交互行为封装：点击卡片、滚动、间隔延迟。"""

    @staticmethod
    def get_browse_delay():
        dice = random.random()
        if dice < 0.35:
            wait = random.uniform(1.2, 2.8)
        elif dice > 0.85:
            wait = random.uniform(8.0, 15.0)
        else:
            wait = random.uniform(3.2, 6.0)
        return wait

    @staticmethod
    def click_job(chrome, security_id):
        """
        点击目标卡片，Vue clickJobCard() 优先，DOM card.click() 兜底。

        通过 securityId 精确匹配 Vue 组件并点击对应卡片。

        返回 (是否成功, 卡片在页面中的位置索引, 总卡片数)
        """
        sid_e = security_id.replace("\\", "\\\\").replace("'", "\\'")

        _dt("click_job", "vue_try", {"sid": security_id[:30]})
        vue_js = load_js("click_vue.js", {"'__SID__'": f"'{sid_e}'"})
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
            time.sleep(0.5)
            _dt("click_job", "vue_hit", {"index": info.get("index"), "total": info.get("total")})
            return True, info.get("index", 0), info.get("total", 0)

        _dt("click_job", "dom_try", {"sid": security_id[:30]})
        dom_js = load_js("click_dom.js", {"'__SID__'": f"'{sid_e}'"})
        r = chrome.evaluate(dom_js, await_promise=False)
        raw = chrome.get_value(r)
        if isinstance(raw, str):
            info = json.loads(raw or "{}")
        else:
            info = raw if raw is not None else {}
        if info.get("found"):
            time.sleep(0.5)
            _dt("click_job", "dom_hit", {"index": info.get("index"), "total": info.get("total")})
            return True, info.get("index", 0), info.get("total", 0)

        _dt("click_job", "not_found", {"sid": security_id[:30], "total": info.get("total", 0)})
        return False, -1, info.get("total", 0)

    @staticmethod
    def click_card_by_sid(chrome, security_id, job_name):
        """兼容旧接口，内部委托给 click_job"""
        return BrowserBehavior.click_job(chrome, security_id)

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

    @staticmethod
    def step_break():
        """每 N 条休息一次"""
        idle = random.uniform(8.0, 18.0)
        print(f"\n  [IDLE] 间隔休息 {idle:.1f}s ...")
        time.sleep(idle)
