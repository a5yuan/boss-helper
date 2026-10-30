"""城市名 ↔ BOSS 城市编码。

BOSS 搜索 URL 形如 https://www.zhipin.com/web/geek/jobs?query=AI&city=101280600，
其中 city 是 BOSS 内部城市数据库 ID（无公式可算）。BOSS 前端通过
GET /wapi/zpCommon/data/city.json 拿到完整「城市名→编码」树。

策略：
- 仓库内置一份常用城市映射（开箱即用，无需联网）。
- 提供 refresh_from_browser()：基于用户已登录的浏览器页面，在页内同源 fetch
  city.json，解析后缓存到 data/city_map.json，下次优先读缓存。
"""
import json
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_PATH = os.path.join(PROJECT_DIR, "data", "city_map.json")

# 内置常用城市（label=中文名, value=BOSS 城市编码字符串）。
# 与中国天气网城市码一致，BOSS 沿用该体系。用户可通过 refresh 拉取完整列表覆盖。
COMMON_CITIES = [
    {"label": "全国", "value": "100010000"},
    {"label": "北京", "value": "101010100"},
    {"label": "上海", "value": "101020100"},
    {"label": "广州", "value": "101280100"},
    {"label": "深圳", "value": "101280600"},
    {"label": "杭州", "value": "101210100"},
    {"label": "成都", "value": "101270100"},
    {"label": "南京", "value": "101190100"},
    {"label": "武汉", "value": "101200100"},
    {"label": "西安", "value": "101110100"},
    {"label": "苏州", "value": "101190400"},
    {"label": "天津", "value": "101030100"},
    {"label": "重庆", "value": "101040100"},
    {"label": "长沙", "value": "101250100"},
    {"label": "郑州", "value": "101180100"},
    {"label": "东莞", "value": "101281600"},
    {"label": "厦门", "value": "101230200"},
    {"label": "青岛", "value": "101120200"},
    {"label": "合肥", "value": "101220100"},
    {"label": "福州", "value": "101230100"},
    {"label": "济南", "value": "101120100"},
    {"label": "宁波", "value": "101210400"},
    {"label": "大连", "value": "101070200"},
    {"label": "无锡", "value": "101190200"},
    {"label": "佛山", "value": "101280800"},
    {"label": "沈阳", "value": "101070100"},
    {"label": "昆明", "value": "101290100"},
    {"label": "南昌", "value": "101240100"},
    {"label": "哈尔滨", "value": "101050100"},
]


def flatten_city_tree(zp_data):
    """把 city.json 的 zpData.cityList 树展平为 [{label, value}]（省+市两级，去重）。"""
    items = []
    seen = set()

    def walk(nodes, depth):
        for node in nodes or []:
            code = node.get("code")
            name = node.get("name")
            if code and name and str(code) not in seen:
                seen.add(str(code))
                items.append({"label": name, "value": str(code)})
            # 仅下钻到「市」级（省 depth0 -> 市 depth1），不收区县（depth2，非有效 city 参数）
            if depth < 1:
                walk(node.get("subLevelModelList"), depth + 1)

    city_list = (zp_data or {}).get("cityList") or []
    walk(city_list, 0)
    return items


def get_cities():
    """返回城市列表：缓存优先，缺失时回退内置常用城市。"""
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return COMMON_CITIES


def save_cities(items):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def refresh_from_browser(browser_type="chrome"):
    """基于已打开的 BOSS 页面在页内 fetch city.json，解析并缓存。

    返回 (cities, error)：成功时 error 为 None。
    """
    from src.core.browser import BrowserManager

    bm = BrowserManager.quick_connect(browser_type)
    if not bm:
        return None, "未找到已打开并登录的 BOSS 页面，请先在浏览器登录 BOSS 后重试"

    try:
        res = bm.evaluate(
            "fetch('/wapi/zpCommon/data/city.json').then(r => r.text())",
            await_promise=True,
        )
        data = bm.get_value(res)  # 字符串会被 get_value 自动 json.loads
        if isinstance(data, str):
            data = json.loads(data)
        zp_data = data.get("zpData") if isinstance(data, dict) else None
        items = flatten_city_tree(zp_data)
        if not items:
            return None, "city.json 解析为空，可能页面未登录或接口结构变化"
        save_cities(items)
        return items, None
    except Exception as exc:  # noqa: BLE001
        return None, f"获取 city.json 失败: {exc}"
    finally:
        bm.disconnect()
