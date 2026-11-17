# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- AI 筛选与招呼语管线（`src/ai/`）：按简历给岗位打分、判定投递价值、按 JD 生成招呼语
- 简历库按岗位方向自动选择（`ai.resumes` + 关键词权重：标题 3 / 技能 2 / JD 1）
- 复核页集成：「AI 筛选」「AI 批量填」按钮，详情区显示分数/理由/不匹配点与可编辑招呼语
- `/api/ai/plan`、`/api/ai/screen`、`/api/ai/greeting`、`/api/ai/fill`、`/api/ai/fill/status`
- `ai.daily_limit`（默认 20）：每日点「立即沟通」的硬上限；已联系过的岗位自动跳过
- `ai.max_inactive_days`（默认 3）：投前读招聘者活跃状态，超期直接跳过

- 采集速度档位 `slow` / `normal` / `fast`：调整点击前后等待、条间延时与间隔休息，不改变读取方式；前端「采集速度」下拉可选
- `click_vue.js` / `click_dom.js` 的点击等待改为 `__SCROLL_WAIT__` / `__CLICK_DELAY__` 占位符，由速度档位注入
- 复核队列定位后自动点击「立即沟通」打开聊天窗（`/api/focus` 新增 `open_chat`，默认开启；只点按钮、不发送消息）

### Changed

- `/api/focus` 返回新增 `chat` 字段，报告沟通按钮是否点到；`Enter` 按钮文案改为「定位并沟通」
- `config.yaml` 的 `start_params` 新增 `speed`；旧配置按 `fast` / `safe_mode` 自动推导，不会强制改回慢速

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
