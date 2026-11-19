"""每个平台一套运行资源。

UI 仍是单任务，但平台之间不共享配置路径和 tracking 锁。runtime 由入口
（session / HTTP 接口 / CLI）取用，Tracker 从这里注入，不在业务层 new。
"""
import threading

from src.config import DEFAULT_PLATFORM, get_config
from src.tracking import Tracker


class PlatformRuntime:
    def __init__(self, platform: str, browser_type: str = "chrome"):
        self.platform = platform
        self.browser_type = browser_type
        self.config = get_config(browser_type, platform=platform)
        self.tracker = Tracker(
            path=self.config["tracking_file"],
            legacy_path=self.config.get("legacy_tracking_file"),
        )

    @property
    def output_dir(self) -> str:
        return self.config["output_dir"]


_RUNTIMES: dict[tuple[str, str], PlatformRuntime] = {}
_LOCK = threading.Lock()


def get_runtime(platform: str | None = None, browser_type: str = "chrome") -> PlatformRuntime:
    """按平台缓存 runtime，同一平台的 Tracker 共享一把锁。"""
    key = (platform or DEFAULT_PLATFORM, browser_type)
    with _LOCK:
        runtime = _RUNTIMES.get(key)
        if runtime is None:
            runtime = PlatformRuntime(*key)
            _RUNTIMES[key] = runtime
        return runtime
