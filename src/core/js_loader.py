"""注入 JS 加载器：从 src/js/*.js 读取脚本，支持占位符替换。

约定：JS 文件中用 '__SID__' 作为 securityId 占位符、__EXTRA__ 作为可选片段占位符。
调用处通过 subs 字典做字符串替换，例如：
    load_js("read_panel.js", {"'__SID__'": f"'{sid_e}'", "__EXTRA__": extra})
"""
from pathlib import Path
from functools import lru_cache

_JS_DIR = Path(__file__).resolve().parent.parent / "js"


@lru_cache(maxsize=None)
def _read(name: str) -> str:
    return (_JS_DIR / name).read_text(encoding="utf-8")


def load_js(name: str, subs: dict | None = None, **kwsubs: str) -> str:
    """读取 JS 文件并做占位符替换。

    subs/kwsubs 中的 key 为待替换文本，value 为替换内容。
    """
    code = _read(name)
    mapping: dict = {}
    if subs:
        mapping.update(subs)
    if kwsubs:
        mapping.update(kwsubs)
    for key, val in mapping.items():
        code = code.replace(key, val)
    return code
