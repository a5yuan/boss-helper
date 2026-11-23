# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `tracking.py` 的 `os.replace` 在 Windows 遇到读句柄占用时不再裸崩：清理临时文件并抛 `TrackingError`，接口返回 `{ok:false,error}`
- 采集在列表到底且连续无新卡片时不再死循环：连续 2 轮无新岗位触发刷新，最多刷新 2 次后正常结束，进度显示已处理数量

### Added

- 智联 JS 探针的真执行测试：`tests/js/` 用零依赖 DOM shim + `node --test` 跑 `src/js/zhaopin_*.js`，`tests/test_js_probes.py` 把结果并进 `python -m unittest`；没有 node 时跳过。新增探针必须有对应测试文件
- 投递能力契约（`delivery_mode`）：`prefill_chat`（BOSS，只填不发）/ `apply_then_chat`（智联，投递后进聊天发一条）/ `unsupported`；引擎 `src/ai/apply.py` 按能力分支，不按站点名分支。智联投递受 `apply.enabled`、`apply.send_message`、`apply.daily_limit` 三道闸控制（默认全关），投前查 `hasAppliedPosition`/`applyType` 幂等，成功后 tracking 记 `applied`，每次动作追加 `output/zhaopin/apply_audit.log`；新增只读体检 `python -m src.ai apply-check --site zhaopin --job-id <number>`。BOSS 行为不变
- 智联招聘（`zhaopin`）只读采集适配器：从 SSR `__INITIAL_STATE__.positionList` 读首屏 20 条与完整 JD，城市码实测 653 = 杭州；投递侧返回 `unsupported:`；`config.yaml` 支持 `zhaopin:` 平台段覆盖浏览器 / profile / 输出目录 / 端口文件
- `/api/ai/plan`、`/api/ai/screen`、`/api/ai/greeting`、`/api/ai/fill` 接受可选 `platform`，AI 计划按平台读写（`output/{platform}/ai_plan_*.json`）；复核页在非默认平台可用「AI 筛选」「AI 批量填」与招呼语编辑
- `/api/focus`、`/api/greet` 接受可选 `platform`（请求体）：复核页切到非默认平台后，「定位并沟通」「填招呼语」作用在该平台的浏览器上；不传时仍按岗位记录 / 默认平台。目标平台浏览器未启动时返回「<平台> 尚未启动，先跑一次采集」
- 平台目录 `GET /api/platforms`：从已注册适配器发现平台名与显示名；`/api/results` 支持 `platform`，`/api/tracking` 读写支持 `platform`
- 前端多任务视图：按平台分标签、每个任务独立的进度 / 日志 / 确认框；单任务时不显示标签栏，外观与之前一致
- 任务注册表（`server/session.py`）：同一平台只允许一个任务，不同平台可以同时采集；`/api/start` 支持 `platform` 别名
- WebSocket 事件流追加 `task_id`，连接建立时推送所有任务的快照；任务结束后保留 300 秒终态记录供前端收尾
- 进程级前台锁（`src/focus_lock.py`）：两个平台同时采集时，填招呼语、点「立即沟通」等需要真实窗口焦点的段串行执行；纯 CDP / JS 读取与点击不持锁
- 单条 `/ws` 连接转发所有平台的采集事件，每条事件带 `task_id`；连接建立时先推所有任务的 status / progress / need_action 快照
- AI 筛选与招呼语管线（`src/ai/`）：按简历给岗位打分、判定投递价值、按 JD 生成招呼语
- 简历库按岗位方向自动选择（`ai.resumes` + 关键词权重：标题 3 / 技能 2 / JD 1）
- 复核页集成：「AI 筛选」「AI 批量填」按钮，详情区显示分数/理由/不匹配点与可编辑招呼语
- `/api/ai/plan`、`/api/ai/screen`、`/api/ai/greeting`、`/api/ai/fill`、`/api/ai/fill/status`
- `ai.daily_limit`（默认 0 = 不限）：每日点「立即沟通」的可选上限；已联系过的岗位自动跳过
- `ai.max_inactive_days`（默认 3）：投前读招聘者活跃状态，超期直接跳过
- `ai.auto_after_collect`：采集结束后自动执行 `off` / `screen` / `fill`
- `ai.fill_gap_min` / `fill_gap_max` / `fill_settle`：填充节奏可调，默认 5~10s + 2s
- 修复填充后草稿丢失：改用 CDP `Input.insertText` 真实输入，并在导航前 blur 触发草稿保存
- `dispatch --force-refill`：跳过「已联系过」过滤，只用于补回丢失的草稿

- 采集前跳过公司不在线的岗位：读 `.boss-logo` 内的 `.boss-online-icon`，缺失即离线，不点击卡片、不读详情（`src/js/read_company_online.js` + `src/utils/company_online.py` + `BossAdapter.probe_online`）
- 采集速度档位 `slow` / `normal` / `fast`：调整点击前后等待、条间延时与间隔休息，不改变读取方式；前端「采集速度」下拉可选
- `click_vue.js` / `click_dom.js` 的点击等待改为 `__SCROLL_WAIT__` / `__CLICK_DELAY__` 占位符，由速度档位注入
- 复核队列定位后自动点击「立即沟通」打开聊天窗（`/api/focus` 新增 `open_chat`，默认开启；只点按钮、不发送消息）
- 假平台契约测试（`tests/test_fake_platform.py`）：零网络适配器跑通完整采集，并用 token 扫描拦住平台知识回流 `collector.py`
- 平台适配器自动发现：`create_adapter("<site>")` 按约定 import `src.adapters.<site>`，平台导入时自注册；新增平台不再需要改任何公共文件
- 运行资源按平台隔离：profile / 端口文件 / 输出目录 / tracking 都带 `platform` 维度；新增 `src/runtime.py` 持有每平台的 Tracker
- BOSS 迁移兼容：继续使用 `profiles/{browser}_profile` 与 `.cdp_port_{browser}`，首次读取时把旧 `output/tracking.json` 复制到 `output/boss/tracking.json`

### Changed

- 采集输出每条岗位新增 `platform` 字段（当前为 `boss`）；其余字段与旧输出一致
- 页面操作收敛到 `src/adapters/boss.py`：collector 与 dispatch 只调用适配器，不再直接写 BOSS 选择器
- 平台契约补齐：首页/登录 URL、刷新、列表与详情滚动都进适配器；`run_collection` 新增 `site` 参数，经 `src/adapters/registry.py` 解析适配器，引擎不再 import 具体平台类
- `BrowserManager` 的选页方法收敛为 `list_pages()`，平台归属与打分交给 `BossAdapter.owns_url` / `pick_target`
- 采集统计新增 `offline` / `online_unknown`：进度面板显示「离线跳过」「状态未知」，总结里「跳过」改为「(重复/薪资)」并单列离线与未知条数
- `/api/focus` 返回新增 `chat` 字段，报告沟通按钮是否点到；`Enter` 按钮文案改为「定位并沟通」
- `config.yaml` 的 `start_params` 新增 `speed`；旧配置按 `fast` / `safe_mode` 自动推导，不会强制改回慢速
- 采集输出目录改为 `output/{platform}/`（BOSS 为 `output/boss/`）；历史文件仍留在 `output/`，但新采集与复习队列只看新目录
- `config.yaml` 的 `start_params` 新增 `site`（默认 `boss`）
- `dispatch` 不再自己 new Tracker：由 runtime 注入，同一平台共享状态锁与每日配额
- 采集结束后 AI 钩子使用本次采集返回的确切文件，不再 glob 最新 `jobs_*.json`；`plan_path_for` 改为跟随源文件目录
- CDP 选页去平台化：`BrowserManager.list_pages` 返回全部 target，归属判断由适配器 `owns_url` 负责
- 启动后校验端口与页面归属，找不到本平台页面就关闭进程退出；二级平台不再扫描 9222-9229
- LLM 调用改为模块级全局限流：容量取 `ai.concurrency`，所有 `LLMClient` 共享，不再按实例各算一份
- 单槽状态按 `task_id` 索引：`Session` 与 `_ai_fill` 不再用全局单例；`/api/focus`、`/api/greet` 只拒绝同平台任务
- `/api/start` 与 `/api/ai/fill` 返回 `task_id`，`stop/pause/resume/ack/status` 与填充状态查询可带 `task_id`，缺省当前任务

---

## [0.2.0] - 2026-10-30

### Added

- 复核队列 `/review`：关键词/薪资/排除词筛选，↑↓ 切换，A 已投 / L 收藏 / S 跳过 / Enter 定位 / G 填招呼语
- 岗位列表新增「复核队列」入口（桌面端在系统浏览器打开）
- 复核页支持切换历史采集文件
- 最小单元测试：薪资解析、投递状态、查重口径
- agent 文档体系（`CLAUDE.md` / `AGENTS.md` / `LESSONS.md` / `docs/` / `prompts/`）

### Changed

- 查重口径从 `title + company` 扩展为 `title + company + 区域`，详情拿到 `encryptJobId` 后再精确查一次
- 复核历史文件时，`/api/focus` 与 `/api/greet` 会在所有采集文件中查找岗位
- 版本号统一为 `0.2.0`（`src/__version__.py` / `pyproject.toml` / `webui/package.json`）

### Fixed

- 薪资解析支持「8千-1.2万」这类两端单位不同的写法

---

## [1.0.0] - 2026-06-22

### Highlights

- Stable release of BOSS-Helper as a CDP-based browser assistant
- Desktop GUI (pywebview) and CLI modes
- Vue component tree extraction for job card data
- Detail panel reader via `$data.currentJob` / `$data.jobDetail`
- Configurable browse pacing for natural interaction rhythm
- JSON + Markdown output with deduplication

### Architecture

- Pure CDP communication via `Runtime.evaluate` (single command pattern)
- Login state detection: `bst` cookie → `ka=header-username` DOM fallback
- Interruptible sleep for responsive stop handling
- Full-chain debug tracer (NDJSON + human-readable logs)
- Auto port discovery for dev mode (backend + Vite)

---

## [0.1.0] - 2026-01-01

- Initial release (BOSS 直聘 V14)
