"""桌面 GUI / 服务器入口：子线程启动 uvicorn(FastAPI)，主线程打开 pywebview 窗口（或纯服务器模式）。

用法：
    python run_gui.py                     # 根据 .env 中的 BOSS_ENV 决定 dev/prod 模式
    python run_gui.py --dev              # 强制开发模式
    python run_gui.py --dev --port 5175  # 指定前端端口为 5175
    python run_gui.py --dev --no-window  # 仅启动服务，不弹客户端窗口（同 --no-open / --no-gui）
    python run_gui.py --build            # 构建前端（npm run build），并以 prod 模式运行
    python run_gui.py --stop             # 停止所有 boss run_gui 进程，释放端口
"""
import argparse
import ctypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

# ============================================================================
# exe 启动期 stdout/stderr 重定向
# ============================================================================
# 当 PyInstaller 打成 console=False 的 GUI 程序时，进程没有控制台，
# stdout/stderr 是 NULL 句柄。任何 print() 或异常 traceback 一旦走到
# 这两个流就会抛 ValueError，连锁导致启动失败（这就是"双击打不开"的真因）。
#
# 解决：把 stdout/stderr 重定向到 exe 同目录的 startup.log。
# 这样 GUI 模式下也能看到 print 输出和异常 traceback，方便排查。
# ============================================================================
def _setup_log_redirect():
    if getattr(sys, "frozen", False):
        # exe 所在目录：dist\BOSS直聘助手\
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        log_path = os.path.join(exe_dir, "startup.log")
    else:
        # 源码运行：当前目录
        log_path = os.path.join(os.getcwd(), "startup.log")

    try:
        # 每次启动覆盖旧日志，避免历史噪音干扰
        log_file = open(log_path, "w", encoding="utf-8", errors="replace")
        sys.stdout = log_file
        sys.stderr = log_file
        # 让后续 print() 立即刷盘（不要等缓冲区满）
        sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None
        sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, "reconfigure") else None
        print(f"[startup] pid={os.getpid()} argv={sys.argv} cwd={os.getcwd()} executable={sys.executable}")
        print(f"[startup] frozen={getattr(sys, 'frozen', False)} __file__={__file__}")
    except Exception as e:
        # 兜底：重定向失败也不要让启动挂掉
        pass

_setup_log_redirect()

# 版本号（必须放在 uvicorn 之前，让启动日志第一行就能看到）
try:
    from src import __version__ as _APP_VERSION, APP_NAME as _APP_NAME  # noqa: E402
except Exception:
    _APP_VERSION = "0.0.0"
    _APP_NAME = "BOSS直聘助手"
print(f"[startup] {_APP_NAME} v{_APP_VERSION}")

import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 环境变量加载（手动解析 .env，不依赖 python-dotenv）
# ---------------------------------------------------------------------------

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def _load_env() -> dict[str, str]:
    defaults = {
        "BOSS_ENV": "prod",
        "BOSS_BACKEND_PORT": "8848",
        "BOSS_DEV_BACKEND_PORT": "8848",
        "BOSS_DEV_VITE_PORT": "5173",
        "BOSS_OUTPUT_DIR": "output/",
    }
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    defaults[k.strip()] = v.strip()
    return defaults

_tenv = _load_env()

# 将所有加载的环境变量和默认值注入到 os.environ，供子线程和模块使用
for k, v in _tenv.items():
    os.environ.setdefault(k, v)

def _env(key: str, default: str = "") -> str:
    return _tenv.get(key, default)


# ---------------------------------------------------------------------------
# WebView2 配置
# ---------------------------------------------------------------------------

os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--disable-extensions "
    "--disable-component-extensions-with-background-pages "
    "--disable-features=WebContentsForceDark",
)

HOST = "127.0.0.1"
WIN_W, WIN_H = 1280, 820
ENV_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")


class _Server(uvicorn.Server):
    def install_signal_handlers(self):
        pass


def _find_free_port(host: str, start: int, tries: int = 20) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"{host} 上 {start}~{start + tries} 端口均被占用")


def _start_server(port: int):
    from server.app import app

    config = uvicorn.Config(app, host=HOST, port=port, log_level="warning")
    _Server(config).run()


def _wait_ready(port: int, timeout=15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://{HOST}:{port}/api/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.25)
    return False


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _write_env_local(backend_port: int, vite_port: int):
    webui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webui")
    env_path = os.path.join(webui_dir, ".env.local")
    content = f"VITE_BACKEND_URL=http://127.0.0.1:{backend_port}\nVITE_PORT={vite_port}\n"
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)


def _wait_port(host: str, port: int, timeout=40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.3)
    return False


def _start_vite(vite_port: int):
    if _port_open(HOST, vite_port):
        print(f"[-] 端口 {vite_port} 已被占用，Vite 无法启动")
        return None

    npm = shutil.which("npm")
    if not npm:
        print("[-] 未找到 npm，请先安装 Node.js 或手动运行 `npm run dev`")
        return None

    webui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webui")
    print(f"[*] 正在启动 Vite 开发服务器（端口 {vite_port}）...")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(
        [npm, "run", "dev"],
        cwd=webui_dir,
        shell=(os.name == "nt"),
        creationflags=creationflags,
    )


def _kill_proc_tree(proc: "subprocess.Popen | None"):
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc.terminate()
    except Exception:
        pass


def _force_light_webview2():
    try:
        from webview.platforms import edgechromium
    except Exception:
        return

    _orig = getattr(edgechromium.EdgeChrome, "on_webview_ready", None)
    if _orig is None:
        return

    def patched(self, sender, args):
        _orig(self, sender, args)
        try:
            from Microsoft.Web.WebView2.Core import CoreWebView2PreferredColorScheme
            sender.CoreWebView2.Profile.PreferredColorScheme = (
                CoreWebView2PreferredColorScheme.Light
            )
        except Exception:
            pass

    edgechromium.EdgeChrome.on_webview_ready = patched


def _center_xy(webview, w: int, h: int):
    try:
        screens = webview.screens
        if screens:
            sw, sh = screens[0].width, screens[0].height
            return max(0, int((sw - w) / 2)), max(0, int((sh - h) / 2))
    except Exception:
        pass
    return None, None


class _PickApi:
    def __init__(self):
        self._window = None
        self._webview = None

    # ── 文件选择 ───────────────────────────────────────────────
    def pick_folder(self):
        try:
            res = self._window.create_file_dialog(self._webview.FOLDER_DIALOG)
            if res:
                return res[0]
        except Exception:
            pass
        return ""

    def pick_file(self):
        try:
            res = self._window.create_file_dialog(
                self._webview.OPEN_DIALOG, allow_multiple=False
            )
            if res:
                return res[0]
        except Exception:
            pass
        return ""

    def save_file(self, filename: str, content: str) -> str:
        try:
            from server.tracer import tracer
            tracer.entry("PickApi:save_file", f"请求保存文件: {filename}", {"filename": filename})
            res = self._window.create_file_dialog(
                self._webview.SAVE_DIALOG,
                save_filename=filename,
                file_types=("CSV Files (*.csv)", "All Files (*.*)")
            )
            if res:
                save_path = res[0]
                with open(save_path, "w", encoding="utf-8-sig") as f:
                    f.write(content)
                tracer.entry("PickApi:save_file_success", f"文件成功保存至: {save_path}", {"path": save_path})
                return save_path
            else:
                tracer.entry("PickApi:save_file_cancelled", f"用户取消了保存文件: {filename}")
        except Exception as e:
            try:
                from server.tracer import tracer
                tracer.entry("PickApi:save_file_error", f"保存文件失败: {str(e)}", {"error": str(e)}, scope="error")
            except Exception:
                pass
            print(f"[PickApi] save_file error: {e}")
        return ""

    # ── 通知 ───────────────────────────────────────────────────
    def flash_taskbar(self, count=6):
        """任务栏图标闪烁（Windows 原生，无需额外依赖）。"""
        try:
            from src.notify import flash_taskbar as _flash
            _flash(count=count)
        except Exception:
            pass

    def stop_flash(self):
        """停止任务栏闪烁。"""
        try:
            from src.notify import stop_flash_taskbar
            stop_flash_taskbar()
        except Exception:
            pass

    def play_sound(self, kind="alert"):
        """通过 Web Audio API 在前端播放提示音。
        kind: 'alert' | 'done' | 'error'
        前端会拦截 window.pywebview.api.play_sound() 并播放对应音频。
        """
        # 这里通过 evaluate_js 让前端播放声音（前端已注册全局回调）
        try:
            self._window.evaluate_js(
                f"window.__playSound && window.__playSound({repr(kind)})"
            )
        except Exception:
            pass


def _find_all_boss_procs() -> list[int]:
    try:
        out = subprocess.check_output(
            ["powershell", "-Command",
             "Get-NetTCPConnection -LocalPort 8848 -State Listen "
             "-ErrorAction SilentlyContinue | "
             "Select-Object -ExpandProperty OwningProcess"],
            text=True,
        )
        return [int(x) for x in out.strip().splitlines() if x.strip().isdigit()]
    except Exception:
        return []


def _stop_all():
    pids = _find_all_boss_procs()
    if not pids:
        print("[-] 未找到正在运行的 boss 实例（端口 8848 无监听）")
        return
    print(f"[*] 正在终止 {len(pids)} 个进程: {pids}")
    killed = []
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                killed.append(pid)
        except Exception:
            pass
    # 等待端口释放
    time.sleep(1)
    remaining = _find_all_boss_procs()
    if remaining:
        print(f"[!] 仍有进程残留 PIDs: {remaining}，请手动 `netstat -ano | findstr :8848` 查看")
    else:
        print("[+] 所有 boss 进程已终止，端口已释放")


def _build_frontend():
    """Build webui/dist，复制到 server/static/（仅 prod 模式需要）。"""
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("未找到 npm，请先安装 Node.js")
    webui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webui")
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server", "static")
    print("[*] Building frontend...")
    subprocess.run([npm, "run", "build"], cwd=webui_dir, check=True)
    if os.path.exists(static_dir):
        shutil.rmtree(static_dir)
    dist_src = os.path.join(webui_dir, "dist")
    shutil.copytree(dist_src, static_dir)
    print(f"[+] 前端已构建到 server/static/")


def main():
    try:
        _main_impl()
    except Exception as e:
        # GUI 模式无控制台，必须把异常写进日志，否则用户看不到任何线索
        import traceback
        traceback.print_exc()
        print(f"[FATAL] main 启动失败: {type(e).__name__}: {e}")
        # 暂停 5 秒给用户/AI 时间看日志（双击不会一闪而过）
        time.sleep(5)


def _main_impl():
    parser = argparse.ArgumentParser(description="BOSS 助手 GUI")
    parser.add_argument("--dev", action="store_true", help="强制开发模式（忽略 .env 中的 BOSS_ENV）")
    parser.add_argument("--build", action="store_true", help="构建前端（npm run build），同时以 prod 模式运行")
    parser.add_argument("--stop", action="store_true", help="停止所有 boss run_gui 进程，释放端口")
    parser.add_argument("--port", type=int, help="指定前端/主服务端口 (Vite port)")
    parser.add_argument("--backend-port", type=int, help="指定后端 API 端口")
    parser.add_argument("--no-window", action="store_true", help="不打开桌面客户端窗口（纯服务器模式）")
    parser.add_argument("--no-open", action="store_true", help="同 --no-window，不自动打开桌面客户端窗口")
    parser.add_argument("--no-gui", action="store_true", help="同 --no-window，不自动打开桌面客户端窗口")
    args = parser.parse_args()

    if args.stop:
        _stop_all()
        return

    no_window = args.no_window or args.no_open or args.no_gui

    # 判断模式：--build > --dev > .env
    is_build = args.build
    is_dev = args.dev or (not is_build and _env("BOSS_ENV", "prod") == "dev")

    if is_build:
        _build_frontend()
        os.environ.pop("BOSS_GUI_DEV", None)
        backend_port = args.backend_port or int(_env("BOSS_BACKEND_PORT", "8848"))
        vite_proc = None
    elif is_dev:
        os.environ["BOSS_GUI_DEV"] = "1"
        start_backend = args.backend_port or int(_env("BOSS_DEV_BACKEND_PORT", "8848"))
        start_vite = args.port or int(_env("BOSS_DEV_VITE_PORT", "5173"))
        backend_port = _find_free_port(HOST, start_backend)
        vite_port = _find_free_port(HOST, start_vite)
        vite_proc = None
    else:
        os.environ.pop("BOSS_GUI_DEV", None)
        backend_port = args.backend_port or args.port or int(_env("BOSS_BACKEND_PORT", "8848"))
        vite_proc = None

    threading.Thread(target=_start_server, args=(backend_port,), daemon=True).start()
    if not _wait_ready(backend_port):
        print(f"[-] 后端在 http://{HOST}:{backend_port} 启动超时")
        return

    if is_dev:
        _write_env_local(backend_port, vite_port)
        vite_proc = _start_vite(vite_port)
        if not _wait_port(HOST, vite_port):
            print(f"[-] Vite 在 {HOST}:{vite_port} 启动超时，请检查 webui/ 依赖是否已 `npm install`")
            _kill_proc_tree(vite_proc)
            return
        url = f"http://{HOST}:{vite_port}"
        print(f"[*] dev 模式：后端 {backend_port}，Vite {vite_port}（HMR 已就绪）")
    else:
        mode = "build" if is_build else "prod"
        url = f"http://{HOST}:{backend_port}"
        print(f"[*] {mode} 模式：后端 {backend_port}")

    if no_window:
        print(f"[+] 服务器模式已就绪（无桌面窗口）")
        if is_dev:
            print(f"    ➜  前端 Dev 地址: {url}")
            print(f"    ➜  后端 API 地址: http://{HOST}:{backend_port}")
        else:
            print(f"    ➜  Web 服务地址: {url}")
        print("    按 Ctrl+C 可停止服务...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] 正在停止服务...")
        finally:
            _kill_proc_tree(vite_proc)
            try:
                from server.session import session
                session.stop()
            except Exception:
                pass
        return

    import webview

    _force_light_webview2()

    pick_api = _PickApi()
    pick_api._webview = webview

    x, y = _center_xy(webview, WIN_W, WIN_H)
    window = webview.create_window(
        "BOSS 直聘助手",
        url,
        width=WIN_W,
        height=WIN_H,
        x=x,
        y=y,
        min_size=(1024, 680),
        text_select=True,
        js_api=pick_api,
    )
    pick_api._window = window

    def _on_loaded():
        try:
            window.evaluate_js(
                "document.addEventListener('contextmenu', e => e.preventDefault());"
            )
        except Exception:
            pass

        # 注入系统窗口句柄，让通知模块能闪烁任务栏
        try:
            from src.notify import set_window_hwnd
            hwnd = ctypes.windll.user32.GetActiveWindow()
            set_window_hwnd(hwnd)
        except Exception:
            pass

    def _on_closing():
        try:
            from server.session import session
            session.stop()
        except Exception:
            pass
        _kill_proc_tree(vite_proc)

    window.events.loaded += _on_loaded
    window.events.closing += _on_closing
    webview.start()


if __name__ == "__main__":
    main()
