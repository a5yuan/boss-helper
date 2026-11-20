"""进程级前台锁：屏幕只有一个，需要真实前台的操作必须串行。

两个平台同时采集时，窗口焦点是进程级全局状态，不是每个浏览器标签页
各有一份。下面这一段操作必须整段独占：

    bring_to_front -> 坐标点击 -> 真实按键 / insertText -> blur

只要另一个平台在中间插进来，它会把窗口切走，前一个平台的坐标点击就
落到错误的窗口上。所以所有这类操作都持同一把锁。

反过来，纯 CDP / JS 的读取和点击不需要前台，**不持这把锁**，否则两个
平台的采集会被白白串起来，失去并发意义。

用法：

    from src.focus_lock import foreground

    with foreground():
        page.bring_to_front()
        page.native_click(x, y)
        ...
"""
import threading
from contextlib import contextmanager

# 进程内唯一。用 RLock 是为了允许同一线程嵌套持有（例如 fill_chat_input
# 内部再调用辅助函数），不同线程之间仍然严格串行。
_FOREGROUND_LOCK = threading.RLock()


@contextmanager
def foreground():
    """持有前台锁，退出（含异常）时释放。

    只包住真正需要抢占窗口焦点的代码段；locate / 读长度这类只读 JS
    放在锁外面。
    """
    with _FOREGROUND_LOCK:
        yield
