"""按站点名解析适配器。

约定：每个平台以 ``src.adapters.<site>`` 导入（模块或包），导入时调用
``register_adapter`` 自报工厂。新增平台只建目录，不改任何公共文件。
"""
import importlib
from typing import Any, Callable

from src.config import DEFAULT_PLATFORM

# 未显式指定 site 时使用的平台
DEFAULT_SITE = DEFAULT_PLATFORM

_FACTORIES: dict[str, Callable[..., Any]] = {}


def register_adapter(site: str, factory: Callable[..., Any]) -> None:
    _FACTORIES[site] = factory


def create_adapter(site: str | None = None, page=None, click_timing=None):
    key = site or DEFAULT_SITE
    factory = _FACTORIES.get(key)
    if factory is None:
        module_name = f"src.adapters.{key}"
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            # 平台目录不存在才是"未知平台"；模块内部的依赖缺失照常抛出
            if exc.name == module_name:
                raise ValueError(f"未知平台: {key}") from exc
            raise
        factory = _FACTORIES.get(key)
    if factory is None:
        raise ValueError(f"平台 {key} 没有注册适配器（{module_name} 未调用 register_adapter）")
    return factory(page, click_timing)
