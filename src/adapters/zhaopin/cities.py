"""BOSS 城市码 → 智联招聘城市码。

运行参数里的 ``city_code`` 沿用 BOSS 城市编码（如杭州 ``101210100``），
智联搜索页的 ``jl`` 参数用的是另一套数字 id（如杭州 ``653``）。
这里只在已知映射里转换，查不到就返回 ``None``，由调用方省略 ``jl``
回落到站点默认城市。
"""
from src.core.cities import COMMON_CITIES

# BOSS 城市码 → 城市名（与 src.core.cities 共用一份数据源）
BOSS_CODE_TO_NAME = {str(c["value"]): c["label"] for c in COMMON_CITIES}

# 城市名 → 智联 jl 编码。只收录实测过的：653 = 杭州。
ZHAOPIN_CITY_CODES_BY_NAME = {
    "杭州": "653",
}


def resolve_city_code(city_code):
    """把 BOSS 城市码解析成智联 ``jl`` 编码，解析不了返回 ``None``。

    1. 已是 1–4 位纯数字：视为智联 id，原样返回；
    2. BOSS 码能查到城市名，且该城市在映射表里：返回对应编码；
    3. 其余返回 ``None``。
    """
    code = str(city_code or "").strip()
    if code.isdigit() and 1 <= len(code) <= 4:
        return code
    name = BOSS_CODE_TO_NAME.get(code)
    if name and name in ZHAOPIN_CITY_CODES_BY_NAME:
        return ZHAOPIN_CITY_CODES_BY_NAME[name]
    return None
