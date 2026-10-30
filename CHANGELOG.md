# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
