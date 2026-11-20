"""进程级前台锁：屏幕只有一个，需要真实前台的操作必须串行。

两个平台同时采集时，窗口焦点是进程级全局状态，不是每个浏览器标签页
各有一份。下面这一段操作必须整段独占：

    bring_to_front -> 坐标点击 -> 真实按键 / insertText -> blur

只要另一个平台在中间插进来，它会把窗口切走，前一个平台的坐标点击就
落到错误的窗口上。所以所有这类操作都持同一把锁。

纯 CDP / JS 的定位和采集读取不需要前台，放在锁外，否则两个平台的采集
会被白白串起来。例外是同一次前台事务里的收尾检查：填字后读回长度、
点开会话后判断输入框是否就绪，这两步必须和前面的写入或点击待在同一个
临界区，中途不能把前台让出去。

用法：

    from src.focus_lock import foreground

    with foreground():
        page.bring_to_front()
        page.native_click(x, y)
        ...
"""
import threading
from contextlib import contextmanager

# 进程内唯一。用 RLock 而不是 Lock：同一线程重复进入不会自锁，给把临界区
# 拆进辅助函数留了余地；不同线程之间仍然严格串行。
_FOREGROUND_LOCK = threading.RLock()


@contextmanager
def foreground():
    """持有前台锁，退出（含异常）时释放。

    只包住真正需要抢占窗口焦点的代码段。定位和纯采集读取放在锁外；
    同一次前台事务的收尾检查（读长度、判断输入框就绪）留在锁内。
    """
    with _FOREGROUND_LOCK:
        yield
