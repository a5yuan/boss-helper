# 子系统：采集主流程

## 职责

`src/collector.py` 编排一次完整的采集：连接 / 启动浏览器 → 确认登录 → 导航到目标页 → 循环「提取列表 → 点击卡片 → 读详情 → 写文件」。

它**不负责** CDP 传输（`browser.py`）、页面 DOM / Vue 解析（`extractor.py` + `src/js/`）、输出格式（`writer.py`）。

入口：`run_collection(...)`。CLI 由 `main.py` 调用，GUI 由 `server/session.py` 在子线程调用。

## 不变量

- **0 目标请求**：除用户可见的 `location.href` 导航外，不向 zhipin.com 发请求。
- **一次运行一个 `BrowserManager` + 一个 `OutputWriter`**；writer 在内存里按 `(title, company)` 查重。
- **`securityId` 只在当前页面会话有效**；`processed_sids` 只用于本轮去重，不能持久化。
- **停止 / 暂停在循环边界检查**；任何长等待必须走 `_interruptible_sleep`。
- **薪资 `****` 或为空触发熔断**：暂停并等用户处理登录 / 刷新，不写入坏数据。
- **关键词路线必须有 query**；关闭关键词搜索时 `query` 被清空，走手动路线。
- **失败不静默**：读详情失败计入 `fail_count`，继续下一条；不因单条失败退出整轮。

## 依赖方向

```
main.py / server.session → src.collector
src.collector → src.core.browser, src.core.extractor,
                src.utils.browser_behavior, src.utils.salary,
                src.storage.writer, src.control, src.config
src.collector → server.tracer（仅函数内延迟 import）
```

不允许 `src.core.*` 反向 import `collector`。

## 关键文件

| 文件 | 作用 |
|---|---|
| `src/collector.py` | 主流程、登录探测、导航、循环、熔断、进度 |
| `src/core/extractor.py` | `VueExtractor.extract` 取列表；`DetailPanelReader.read_detail` 读详情 |
| `src/utils/browser_behavior.py` | 点击卡片、滚动、随机浏览间隔 |
| `src/utils/salary.py` | 薪资解析与区间匹配 |
| `src/storage/writer.py` | `jobs_YYYY-MM-DD[_tag].json/.md` 增量写 + 内存查重 |
| `src/control.py` | Console / GUI 控制器（日志、进度、暂停、等待用户） |
| `src/js/extract_list.js` | 从 Vue 组件树取 securityId 列表 |
| `src/js/read_panel.js` | 从 `$data.currentJob` / `$data.jobDetail` 取详情 |

## 已知陷阱

- **CDP 分片超时**：`send_cdp` 每 2 秒 `recv` 一次以便响应停止；分片超时异常必须吞掉继续等，否则采集线程崩溃（55e1d30）。
- **页面复用判断**：只有 query / city / salary / jobType / degree / experience 六项全部匹配且已登录，才跳过重载；少一项就会重新导航。改筛选参数时同步改 `page_reuse_check`。
- **导航中被销毁的 target**：登录重定向时 `evaluate` 可能抛异常，`_goto_search` 把异常当作 `login` 处理，触发重新登录流程。
- **`auto_scroll_list` 故意不 await Promise**：滚动 JS 内部发异步 XHR，等 Promise 会在网络慢时卡住 CDP。
- **查重口径是 title + company**：同名同公司的不同城市岗位会被误判为重复；改口径前评估历史数据。
- **手动路线**：`keyword_search=False` 时不会自动导航，依赖用户先在浏览器里搜索 / 滚动。

## 测试方式

无自动化测试。手动：

```bash
python main.py --new -b chrome -n 3

# 或启动服务后调用接口
python run_gui.py --dev --no-window
curl -X POST http://127.0.0.1:8848/api/start \
  -H 'Content-Type: application/json' \
  -d '{"count":3,"keyword_search":true,"query":"AI"}'
```

预期：`output/jobs_<date>_AI.json` 增长，日志出现 `[RUN]` / `-> OK (vue)`，结束时 `ctrl.status("done")`。
