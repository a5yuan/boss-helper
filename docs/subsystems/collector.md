# 子系统：采集主流程

## 职责

`src/collector.py` 编排一次完整的采集：连接 / 启动浏览器 → 确认登录 → 导航到目标页 → 循环「提取列表 → 点击卡片 → 读详情 → 写文件」。

它**不负责** CDP 传输（`browser.py`）、平台页面操作（`src/adapters/boss.py` + `src/js/`）、输出格式（`writer.py`）。

入口：`run_collection(...)`。CLI 由 `main.py` 调用，GUI 由 `server/session.py` 在子线程调用。

## 不变量

- **0 目标请求**：除用户可见的 `location.href` 导航外，不向目标平台域名发请求。
- **运行资源按 `platform + browser_type` 隔离**：profile 在 `profiles/{platform}/{browser_type}`，端口文件 `.cdp_port_{platform}_{browser_type}`，输出与 tracking 在 `output/{platform}/`。BOSS 兼容旧 profile（`profiles/{browser}_profile`）和旧端口文件，避免登录态失效。
- **一次运行一个 `BrowserManager` + 一个 `OutputWriter`**；writer 在内存里按 `(title, company)` 查重。
- **`securityId` 只在当前页面会话有效**；`processed_sids` 只用于本轮去重，不能持久化。
- **停止 / 暂停在循环边界检查**；任何长等待必须走 `_interruptible_sleep`。
- **薪资 `****` 或为空触发熔断**：暂停并等用户处理登录 / 刷新，不写入坏数据。
- **关键词路线必须有 query**；关闭关键词搜索时 `query` 被清空，走手动路线。
- **失败不静默**：读详情失败计入 `fail_count`，继续下一条；不因单条失败退出整轮。
- **公司离线不采集**：点击卡片 / 读详情之前先读公司行 `a.boss-info`，公司不在线直接跳过；在线状态读不出时按未知放行，照常采集。
- **速度档位只改本地等待**：`slow / normal / fast` 只影响点击后的延时、详情滚动和间隔休息，不改变读取方式、不增加任何请求。`speed` 显式传入时优先于 `safe_mode` / `fast`。

## 依赖方向

```
main.py / server.session → src.collector
src.collector → src.adapters.base, src.adapters.registry,
                src.core.browser, src.utils.browser_behavior,
                src.utils.salary, src.storage.writer, src.control, src.config
src.adapters.registry → importlib("src.adapters.<site>")（首次按 site 发现）
src.adapters.boss → src.core.js_loader, src.utils.chat_input, src.core.browser（仅异常类型）
src.collector → server.tracer（仅函数内延迟 import）
```

不允许 `src.core.*` 反向 import `collector`；平台相关页面操作只能放在适配器里。
`src.collector` 不 import 任何具体平台类，只通过 `site` 字符串向 registry 要适配器。

## 关键文件

| 文件 | 作用 |
|---|---|
| `src/collector.py` | 主流程、登录等待、导航、循环、熔断、进度；平台策略只做调度 |
| `src/adapters/base.py` | `PlatformAdapter` 契约、页面门面、结果形状 |
| `src/adapters/registry.py` | `site` → `import src.adapters.<site>`，平台自注册；新增平台只建目录，不改公共文件 |
| `src/adapters/boss.py` | BOSS 页面操作：选页 / 登录探针 / 检索 URL / 列表 / 在线 / 点击 / 滚动 / 详情 / 聊天 / 招呼语 |
| `src/utils/browser_behavior.py` | 随机浏览间隔、`SPEED_PROFILES` 速度档位（滚动与点击都在适配器） |
| `src/utils/salary.py` | 薪资解析与区间匹配 |
| `src/storage/writer.py` | `jobs_YYYY-MM-DD[_tag].json/.md` 增量写 + 内存查重 |
| `src/control.py` | Console / GUI 控制器（日志、进度、暂停、等待用户） |
| `src/js/extract_list.js` | 从 Vue 组件树取 securityId 列表 |
| `src/js/read_panel.js` | 从 `$data.currentJob` / `$data.jobDetail` 取详情 |
| `src/js/read_company_online.js` | 按 `securityId` 定位卡片，读公司行与在线图标，返回探针 JSON |
| `src/utils/company_online.py` | 探针三态归类 `online / offline / unknown` 与一行证据格式化 |

## 平台契约（`PlatformAdapter`）

引擎只通过下面这组方法接触页面。适配器构造时注入一个 `Page` 门面
（`evaluate / get_value / bring_to_front / native_click / send_cdp`），
不得碰端口、进程、标签页发现或文件。所有方法返回带 `ok` 的字典，
不得向上抛异常；`StopError` 例外，必须继续冒泡。

| 分组 | 方法 | 返回 | 谁负责 |
|---|---|---|---|
| 身份 | `site` / `display_name` | 字符串 | 适配器 |
| 选页 | `owns_url(url)` / `pick_target(targets)` | bool / `Tab \| None` | 适配器过滤归属并打分；传输层 `list_pages` 只拉 `/json` |
| 站点入口 | `home_url()` / `login_url()` / `reload()` | URL / `{ok, reason}` | 适配器 |
| 滚动 | `scroll_list()` / `scroll_detail()` / `scroll_position()` | `{ok}` / `{ok}` / `{scrollTop}` | 适配器执行，引擎决定何时调用 |
| 登录 | `probe_login()` | `{state, source}`，`state` 为 `in/login/unknown` | 适配器探测，引擎决定重试/扫码循环 |
| 检索 | `search_url(criteria)` / `matches_criteria(url, criteria)` | URL / bool | 适配器 |
| 等待 | `wait_results(timeout)` | `{ok, state, reason}`，`state` 为 `ready/login/timeout` | 适配器等待，引擎决定重连/重新导航 |
| 列表 | `list_jobs()` | `{ok, jobs: JobCard[], reason}` | 适配器 |
| 公司在线 | `probe_online(job_id)` | `{ok, online, source, reason, evidence}` | 适配器读页面，引擎用 `classify_online` 决策 |
| 点击 | `click_card(job_id)` | `{ok, index, total, reason}` | 适配器 |
| 详情 | `read_detail(job_id)` | 详情字典，至少含 `success`；成功时含 `title/company/salary/location/encrypt_job_id/platform` | 适配器 |
| 聊天 | `open_chat(job_id)` / `open_conversation(hints)` / `chat_input_ready()` / `chat_url()` / `fill_greeting(text)` | `{ok, ...}` | 适配器（dispatch 调用） |

**留在引擎的**：速度档位、条间延时、熔断阈值、重试与登录循环时序、日志格式、
线程生命周期、停止/暂停信号、文件名与输出格式。这些是策略，不属于某个平台。

接入新平台只需要建 `src/adapters/<site>/`（或同名模块），在导入时调用
`register_adapter`。`create_adapter("<site>")` 首次找不到工厂会 import 该模块，
不依赖任何手工注册。

验收方式见 `tests/test_fake_platform.py`：不手工注册零网络适配器，
`run_collection(..., site="fake")` 必须靠自动发现完整跑完并写出合法 JSON；
任何平台 token 回到 `collector.py` 都会被该测试拦下。

## 已知陷阱

- **CDP 分片超时**：`send_cdp` 每 2 秒 `recv` 一次以便响应停止；分片超时异常必须吞掉继续等，否则采集线程崩溃（55e1d30）。
- **页面复用判断**：只有 query / city / salary / jobType / degree / experience 六项全部匹配且已登录，才跳过重载；少一项就会重新导航。改筛选参数时同步改 `BossAdapter.matches_criteria`。
- **导航中被销毁的 target**：登录重定向时 `evaluate` 可能抛异常，`_goto_search` 把异常当作 `login` 处理，触发重新登录流程。
- **`scroll_list` 故意不 await Promise**：滚动 JS 内部发异步 XHR，等 Promise 会在网络慢时卡住 CDP。
- **查重口径是 title + company + 区域**：列表阶段用 `areaDistrict`，详情阶段从 `location`（「城市·区域」）取区域；两边都取不到区域时回退旧口径（视为重复）。详情拿到 `encryptJobId` 后还会精确查一次，防止跨文件重复。
- **手动路线**：`keyword_search=False` 时不会自动导航，依赖用户先在浏览器里搜索 / 滚动。
- **在线标记的 `<!---->`**：公司离线时 `.boss-logo` 里的在线图标渲染成 Vue 注释节点 `<!---->`，DOM 里根本没有 `.boss-online-icon`。因此"图标不存在 + `row_text_len > 0`"才是离线；`row_text_len == 0` 说明公司行还没渲染出来，一律归 `unknown` 放行，不当作离线。
- **速度档位**：`slow` 沿用原安全模式节奏（Vue 滚动等待 600ms、DOM 点击延迟 300ms、点后 0.5s，平均约 4.7s/条，每 12 条休息 8~18s）；`normal` 450/200/0.3s，平均约 2.2s/条、每 25 条休息 4~8s；`fast` 250/100/0.1s，条间 0.3~0.8s、不滚动详情、不休息。改档位只改 `SPEED_PROFILES`，不要在 collector 里散落魔法数字。

## 测试方式

自动化（假平台，无需浏览器或网络）：

```bash
.venv/Scripts/python -m unittest tests.test_fake_platform -v
```

手动：

```bash
python main.py --new -b chrome -n 3

# 或启动服务后调用接口
python run_gui.py --dev --no-window
curl -X POST http://127.0.0.1:8848/api/start \
  -H 'Content-Type: application/json' \
  -d '{"count":3,"keyword_search":true,"query":"AI"}'
```

预期：`output/jobs_<date>_AI.json` 增长，日志出现 `[RUN]` / `-> OK (vue)`，结束时 `ctrl.status("done")`。
