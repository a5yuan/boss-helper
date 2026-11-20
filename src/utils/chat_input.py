"""往聊天输入框写内容——唯一正确入口。

BOSS 的聊天输入区是 contenteditable，草稿在 focusout 时写入服务端。所以必须：

    定位 -> 点击聚焦 -> Ctrl+A 清空 -> CDP Input.insertText -> blur -> 等一下

直接改 `innerText` / `value` 只动 DOM，不触发框架的输入处理，Vue 状态不更新，
草稿存不下来（见 LESSONS.md「往 BOSS 聊天框写内容必须走真实输入」）。

任何需要填聊天框的代码都调这里的 fill_chat_input，不要自己写 JS 赋值。
tests/test_input_policy.py 会扫描这个模式的违规写法。
"""
import json
import time

from src.focus_lock import foreground

LOCATE_JS = r"""
(() => {
  const vis = el => {
    const r = el.getBoundingClientRect();
    return r.width > 40 && r.height > 8;
  };
  const nodes = Array.from(document.querySelectorAll('textarea, [contenteditable="true"]')).filter(vis);
  if (!nodes.length) return JSON.stringify({ ok: false, reason: '页面上没有可输入的聊天框' });
  const el = nodes[nodes.length - 1];
  el.focus();
  const r = el.getBoundingClientRect();
  return JSON.stringify({
    ok: true,
    tag: el.tagName,
    x: Math.round(r.left + r.width / 2),
    y: Math.round(r.top + r.height / 2),
  });
})()
"""

LENGTH_JS = r"""
(() => {
  const n = document.querySelector('[contenteditable="true"]');
  if (n) return (n.innerText || '').length;
  const t = document.querySelector('textarea');
  return t ? (t.value || '').length : -1;
})()
"""


def _key(chrome, key, code, vk, modifiers=0):
    for kind in ("rawKeyDown", "keyUp"):
        chrome.send_cdp("Input.dispatchKeyEvent", {
            "type": kind, "modifiers": modifiers, "key": key, "code": code,
            "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk,
        })


def locate(chrome):
    raw = chrome.get_value(chrome.evaluate(LOCATE_JS))
    return json.loads(raw) if isinstance(raw, str) else (raw or {"ok": False})


def blur(chrome):
    """失焦——草稿保存靠的就是这一下。"""
    try:
        chrome.get_value(chrome.evaluate(
            "(() => { const a = document.activeElement;"
            " if (a && a.blur) { a.blur(); return 'blurred'; } return 'none'; })()"))
        return True
    except Exception:
        return False


def read_length(chrome) -> int:
    val = chrome.get_value(chrome.evaluate(LENGTH_JS))
    val = val.get("value") if isinstance(val, dict) else val
    return val if isinstance(val, int) else -1


def fill_chat_input(chrome, text: str, blur_after: bool = True) -> dict:
    """写入并（默认）失焦。调用方负责在失焦后给平台留出保存时间。

    locate 是只读 JS，不占前台锁；从 bring_to_front 开始到 blur 结束
    这一段会抢窗口焦点，必须和另一个平台串行（见 src/focus_lock.py）。
    """
    info = locate(chrome)
    if not info.get("ok"):
        return info
    with foreground():
        try:
            chrome.bring_to_front()
            chrome.native_click(info["x"], info["y"])
            _key(chrome, "a", "KeyA", 65, modifiers=2)      # Ctrl+A
            _key(chrome, "Backspace", "Backspace", 8)       # 清空
            chrome.send_cdp("Input.insertText", {"text": text})
            time.sleep(0.3)
            got = read_length(chrome)
            if got < 20:
                return {"ok": False, "reason": f"输入后长度异常: {got}"}
            if blur_after:
                blur(chrome)
            return {"ok": True, "tag": info.get("tag", ""), "length": got}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"输入失败: {exc}"}
