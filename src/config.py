import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

def _dt(fn: str, msg: str, data: dict = None, scope="config"):
    """写入 tracer 追踪日志。"""
    try:
        from server.tracer import tracer
        tracer.internal(f"config.py:{fn}", msg, data or {}, scope=scope)
    except Exception:
        pass

def _find_chrome():
    """自动检测 Chrome 路径"""
    # Windows 平台下优先尝试从注册表读取安装路径，支持自定义盘符
    if sys.platform == "win32":
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                        path, _ = winreg.QueryValueEx(key, "")
                        if path and os.path.isfile(path):
                            _dt("_find_chrome", "从 Windows 注册表成功检测到 Chrome 路径", {"path": path})
                            return path
                except WindowsError:
                    continue
        except Exception as e:
            _dt("_find_chrome", "注册表检测发生异常", {"error": str(e)}, scope="error")

    _dt("_find_chrome", "注册表未检测到 Chrome，开始尝试默认路径检测")
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome", "/usr/bin/chromium-browser",
    ]
    for path in candidates:
        if os.path.isfile(path):
            _dt("_find_chrome", "从候选路径检测到 Chrome", {"path": path})
            return path
            
    res = shutil.which("chrome") or shutil.which("google-chrome") or ""
    _dt("_find_chrome", "最终检测到的 Chrome 路径", {"path": res})
    return res

def _find_edge():
    """自动检测 Edge 路径"""
    # Windows 平台下优先尝试从注册表读取安装路径，支持自定义盘符
    if sys.platform == "win32":
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as key:
                        path, _ = winreg.QueryValueEx(key, "")
                        if path and os.path.isfile(path):
                            _dt("_find_edge", "从 Windows 注册表成功检测到 Edge 路径", {"path": path})
                            return path
                except WindowsError:
                    continue
        except Exception as e:
            _dt("_find_edge", "注册表检测发生异常", {"error": str(e)}, scope="error")

    _dt("_find_edge", "注册表未检测到 Edge，开始尝试默认路径检测")
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            _dt("_find_edge", "从候选路径检测到 Edge", {"path": path})
            return path
            
    res = shutil.which("msedge") or ""
    _dt("_find_edge", "最终检测到的 Edge 路径", {"path": res})
    return res

# 动态判断运行环境是否为打包后的 exe
if getattr(sys, "frozen", False):
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    CONFIG_PATH = os.path.join(EXE_DIR, "config.yaml")
else:
    CONFIG_PATH = os.path.join(PROJECT_DIR, "config.yaml")


def _default_output_dir():
    """开发模式及源码模式默认项目内 output/；打包模式默认可执行文件同级目录的 output/。"""
    if getattr(sys, "frozen", False):
        EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
        return os.path.join(EXE_DIR, "output")
    return os.path.join(PROJECT_DIR, "output")


def _read_yaml():
    if os.path.exists(CONFIG_PATH):
        try:
            import yaml
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


def load_config(browser_type="chrome"):
    """加载 config.yaml，缺失项用默认值"""
    cfg = _read_yaml()

    # 根据浏览器类型决定默认值
    if browser_type == "edge":
        default_path = _find_edge()
        profile_name = "edge_profile"
    else:
        default_path = _find_chrome()
        profile_name = "chrome_profile"

    browser_cfg = cfg.get(browser_type, cfg.get("chrome", {})) # 兼容旧版 chrome 配置项
    output_cfg = cfg.get("output", {})

    output_dir = output_cfg.get("dir", "") or _default_output_dir()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception:
        pass

    browser_path = browser_cfg.get("path", "") or default_path
    _dt("load_config", "已加载配置", {
        "browser_type": browser_type,
        "config_path_val": browser_cfg.get("path", ""),
        "resolved_path": browser_path
    })

    return {
        "browser_path": browser_path,
        "profile_dir": browser_cfg.get("profile_dir", "") or os.path.join(PROJECT_DIR, "profiles", profile_name),
        "output_dir": output_dir,
        "port_file": os.path.join(PROJECT_DIR, f".cdp_port_{browser_type}"),
        "humanize": cfg.get("humanize", {}),
    }


def save_config(browser_type="chrome", browser_path=None, output_dir=None):
    """把浏览器路径 / 输出目录写回 config.yaml（仅更新传入的非空项）。"""
    _dt("save_config", "收到保存配置请求", {
        "browser_type": browser_type,
        "browser_path": browser_path,
        "output_dir": output_dir
    })
    try:
        import yaml
    except Exception as e:
        _dt("save_config", "导入 yaml 失败", {"error": str(e)}, scope="error")
        return False
    cfg = _read_yaml()
    if browser_path is not None:
        cfg.setdefault(browser_type, {})["path"] = browser_path
        _dt("save_config", f"已更新 {browser_type} 路径配置", {"path": browser_path})
    if output_dir:
        cfg.setdefault("output", {})["dir"] = output_dir
        _dt("save_config", "已更新输出目录配置", {"dir": output_dir})
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        _dt("save_config", "成功写入 config.yaml")
        return True
    except Exception as e:
        _dt("save_config", "写入 config.yaml 失败", {"error": str(e)}, scope="error")
        return False


# ── StartParams 持久化 ──────────────────────────────────────────────────────────

def load_start_params() -> dict:
    """从 config.yaml 读取已保存的运行参数，缺失字段用默认值。"""
    cfg = _read_yaml()
    saved = cfg.get("start_params", {})
    defaults = {
        "count": 20,
        "browser_type": "chrome",
        "safe_mode": True,
        "fast": False,
        "new_chrome": False,
        "tag": None,
        "keyword_search": True,
        "query": "",
        "city_code": None,
        "city_name": None,
        "salary_min": None,
        "salary_max": None,
        "tag_sync": True,
        "onboarding_completed": False,
        "job_type": "",
        "degrees": [],
        "experience": [],
        "salary_fuzzy": False,
    }
    result = defaults.copy()
    for k, v in saved.items():
        if k in result:
            result[k] = v
    return result


def save_start_params(params: dict) -> bool:
    """把运行参数写入 config.yaml（保留其他区段不动）。"""
    try:
        import yaml
    except Exception:
        return False
    cfg = _read_yaml()
    # 只写已知字段，避免污染
    allowed = {
        "count", "browser_type", "safe_mode", "fast", "new_chrome",
        "tag", "keyword_search", "query", "city_code", "city_name",
        "salary_min", "salary_max", "tag_sync", "onboarding_completed",
        "job_type", "degrees", "experience", "salary_fuzzy",
    }
    filtered = {k: v for k, v in params.items() if k in allowed}
    cfg["start_params"] = filtered
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        return True
    except Exception:
        return False


# 提供一个便捷函数来获取配置，而不是直接导出静态 CONFIG
def get_config(browser_type="chrome"):
    return load_config(browser_type)

# 默认导出 chrome 配置以保持向后兼容
CONFIG = get_config("chrome")
