# 子系统：CDP 浏览器控制

## 职责

`src/core/browser.py` 负责启动 / 复用 Chrome / Edge、通过 HTTP `/json` 发现标签页、建立 CDP WebSocket、发送命令、提取返回值、把窗口带到前台。

它**不负责**页面里执行什么逻辑——那是 `src/js/` 和 `collector.py` 的事。

## 不变量

- 常规数据读取只用 `Runtime.evaluate`；另有 `Page.bringToFront`（前台化）和 `Input.dispatchMouseEvent`（`native_click`）。不 enable 任何 CDP Domain。
- `send_cdp` 必须有整体 deadline；每 2 秒切片 `recv` 以响应 `stop_check`。**分片超时不是失败，继续等。**
- `connect_ws` 成功后 `settimeout(None)`；命令期间临时设置切片超时，`finally` 恢复。
- `disconnect()` 只关 WebSocket，不关浏览器；`close()` 仅在 `_owns_browser` 时杀进程。
- 标签页选择只考虑 `type == "page"`；`shared_worker` 的 URL 也可能含 `geek-chat`，必须排除。
- 端口文件写入失败不影响主流程。

## 依赖方向

```
src.collector / server.app / src.core.cities
        → src.core.browser
src.core.browser → src.config, requests, websocket-client, src.utils.window
src.core.browser → server.tracer（仅函数内延迟 import）
```

不得 import `collector` / `extractor`。

## 关键文件

| 文件 | 作用 |
|---|---|
| `src/core/browser.py` | `BrowserManager`：连接、启动、发现页面、CDP 收发、前台化 |
| `src/config.py` | 浏览器路径 / 端口文件 / profile 目录 |
| `src/utils/window.py` | Win32 前台化兜底 |
| `.cdp_port_chrome` / `.cdp_port_edge` | 最近一次使用的调试端口 |

## 已知陷阱

- **端口文件过期**：`try_connect_existing` 先读端口文件，失败再扫 9222–9229；旧文件不会自动删，不要假设它一定有效。
- **导航后 WebSocket 失效**：页面跳转会销毁 target，原 WS 的响应永远不来；`send_cdp` 超时后由调用方重连。
- **2 秒切片异常**：`WebSocketTimeoutException` 必须与整体 deadline 区分（55e1d30）。
- **`find_boss_page` 评分**：`/web/geek/` +5、`jobs` +2、登录页 −8；新增页面类型时更新评分，否则可能连到登录页。
- **`bring_to_front` 双保险**：CDP `Page.bringToFront` 在部分窗口管理器无效，补 Win32 `SetForegroundWindow`；最大化窗口不能调 `SW_RESTORE`。
- **`get_value` 会自动 `json.loads` 字符串**：JS 返回值是 JSON 字符串时，调用方拿到的是 dict，不要再 `json.loads` 一次。

## 测试方式

```bash
# 确认端口和标签页
cat .cdp_port_chrome
curl http://127.0.0.1:<port>/json
```

或在 Python 里：

```python
from src.core.browser import BrowserManager
bm = BrowserManager.quick_connect("chrome")
print(bm.evaluate("document.title"))
bm.disconnect()
```
