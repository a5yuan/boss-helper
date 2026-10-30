"""Windows 系统通知：任务栏图标闪烁 + 音频提示。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

# ─── FlashWindowEx ────────────────────────────────────────────────────────────
class FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",    wintypes.UINT),
        ("hwnd",      wintypes.HWND),
        ("dwFlags",   wintypes.DWORD),
        ("uCount",    wintypes.UINT),
        ("dwTimeout", wintypes.DWORD),
    ]

FLASHW_STOP        = 0
FLASHW_CAPTION     = 0x00000001
FLASHW_TRAY        = 0x00000002
FLASHW_ALL         = FLASHW_CAPTION | FLASHW_TRAY
FLASHW_TIMER       = 0x00000004
FLASHW_TIMERNOFG   = 0x0000000C   # 直到用户激活窗口才停止

_user32 = ctypes.windll.user32
_flash = _user32.FlashWindowEx


def _flash_window(hwnd: int | None, *, count: int = 6, stop: bool = False) -> bool:
    """让窗口任务栏图标闪烁（win32gui 句柄）。"""
    if not hwnd:
        return False
    flags = FLASHW_STOP if stop else FLASHW_ALL | FLASHW_TIMERNOFG
    fi = FLASHWINFO(
        cbSize   = ctypes.sizeof(FLASHWINFO),
        hwnd     = hwnd,
        dwFlags  = flags,
        uCount   = count,
        dwTimeout = 0,
    )
    return bool(_flash(ctypes.byref(fi)))


# ─── pywebview 窗口句柄获取（注入到 window 对象） ───────────────────────────
_pywebview_hwnd: int | None = None


def set_window_hwnd(hwnd: int):
    """由 run_gui.py 在 pywebview 窗口创建后调用，传入系统窗口句柄。"""
    global _pywebview_hwnd
    _pywebview_hwnd = hwnd


def flash_taskbar(count: int = 6):
    """触发任务栏图标闪烁（用户点击 pywebview 窗口即可停止）。"""
    _flash_window(_pywebview_hwnd, count=count)


def stop_flash_taskbar():
    """停止闪烁。"""
    _flash_window(_pywebview_hwnd, stop=True)
