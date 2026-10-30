"""Windows 窗口焦点辅助：CDP 的 bringToFront 在部分情况下不生效，用 Win32 兜底。"""
import ctypes
import sys

if sys.platform == "win32":
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _title(hwnd) -> str:
        n = _user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def focus_chrome_window(hints=("BOSS直聘", "zhipin", "BOSS")) -> bool:
        found = []

        def _cb(hwnd, _lparam):
            if not _user32.IsWindowVisible(hwnd):
                return True
            t = _title(hwnd)
            if not t:
                return True
            low = t.lower()
            if any(h.lower() in low for h in hints):
                found.append(hwnd)
                return False
            return True

        _user32.EnumWindows(_EnumWindowsProc(_cb), 0)
        if not found:
            return False
        hwnd = found[0]
        # 只有最小化时才还原；对最大化窗口调 SW_RESTORE 会把它缩回启动时的尺寸
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        _user32.SetForegroundWindow(hwnd)
        return True

else:
    def focus_chrome_window(hints=("BOSS",)) -> bool:
        return False
