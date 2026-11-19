"""按站点名解析适配器。

引擎只认 ``site`` 字符串，不 import 任何具体平台类。新增平台时注册一个
factory（签名 ``(page, click_timing) -> PlatformAdapter``）即可，
collector 不需要改。
"""
from typing import Any, Callable

# 未显式指定 site 时使用的平台
DEFAULT_SITE = "boss"

_FACTORIES: dict[str, Callable[..., Any]] = {}


def register_adapter(site: str, factory: Callable[..., Any]) -> None:
    _FACTORIES[site] = factory


def create_adapter(site: str | None = None, page=None, click_timing=None):
    key = site or DEFAULT_SITE
    factory = _FACTORIES.get(key)
    if factory is None and key == DEFAULT_SITE:
        from src.adapters.boss import BossAdapter
        factory = BossAdapter
    if factory is None:
        raise ValueError(f"未知平台: {key}")
    return factory(page, click_timing)
