# 代码标准

本文件是**硬性标准**，不是建议。写代码、审代码前必读。

来源：`LESSONS.md` 中被 ≥3 个独立日期命中的教训晋升而来；接入模板时，也把仓库既有且不可协商的约定固化在这里（见文末说明）。新增规则仍按 Seen 门槛晋升，不要随手往这里加。

## 合规（最高优先级）

- **不得在 Python 侧向 zhipin.com 发起任何 HTTP 请求。** 数据只能来自浏览器已渲染的页面，通过 CDP `Runtime.evaluate` 读取 Vue / DOM 状态。
- 页面内同源 `fetch` 只能在浏览器上下文执行（如 `src/core/cities.py:refresh_from_browser`），且必须由用户动作触发、失败时降级。
- 代码、注释、日志、UI 文案不得出现合规扫描列出的敏感词。新增文案前按 `.agents/workflows/compliance-check.md` 扫一遍。
- 不实现绕过登录、绕过验证码、伪装请求头、代理池等能力。验证码出现时暂停并等用户手动完成。

## 命名

- Python：模块 / 函数 / 变量 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE_CASE`。
- 注释、日志、文档用中文，与现有代码一致；代码标识符用英文。
- 岗位字段名沿用采集输出的键（`encrypt_job_id`、`security_id`、`salary`…），不要为"更规范"改名——前端、`/review`、`tracking.json` 都依赖这些键。

## 标识与状态

- 跨页面 / 跨会话持久化的岗位标识用 `encrypt_job_id`；`security_id` 只用于同一页面会话内的卡片定位。
- 投递状态只允许 `new / shortlisted / skipped / applied`（`src/tracking.py:VALID_STATUS`）。
- 写 `tracking.json` 必须走 `tmp + os.replace` 原子写。
- 写 `config.yaml` 只允许白名单字段（`save_start_params` 的 `allowed` 集合），不要整块覆盖用户配置。

## 依赖方向

```
main.py / run_gui.py / server/*  →  src/collector.py  →  src/core/*, src/utils/*, src/storage/*
src/*  →  server.tracer（只在函数内延迟 import）
```

- `src/` 不得在模块顶层 import `server.*`；需要 tracer 时在函数内 import，避免循环依赖。
- `src/core/browser.py` 只负责 CDP 传输，不得 import `collector`。
- 新增跨层调用前，先改 `docs/subsystems/*.md` 的依赖图，再改代码。

## 页面脚本

- 可复用、带占位符的注入脚本放 `src/js/*.js`，用 `js_loader.load_js()` 读取并替换占位符。
- 一次性脚本可以内联在 Python 字符串里，但必须带中文注释说明它依赖的页面结构，且失败时返回 `{ok:false, reason}` 而不是抛异常。
- JS 访问 Vue 内部状态必须做防御（`try/catch`、空值判断）；页面结构变化时返回明确失败，不要让 Python 侧 `json.loads` 崩。

## 错误处理

- 对外部系统的调用（CDP、文件、浏览器进程、HTTP）必须有超时和明确的失败分支。
- **新增代码**不要用裸 `except:`；至少 `except Exception` 并记录 tracer。既有裸 `except` 不在顺手重构范围内。
- API 层失败返回 `{"ok": False, "error": "..."}`，不要把异常直接抛给前端。
- 采集线程的异常必须写进 tracer 和 `GuiController.log(level="error")`；GUI 模式没有控制台，否则没有任何线索。

## 并发与生命周期

- 同一时刻只允许一个采集任务（`Session.running`）。
- 采集线程是 daemon 线程；停止 / 暂停通过 `GuiController` 的事件标志，循环边界必须检查。
- 长睡眠用 `_interruptible_sleep`，不要直接 `time.sleep` 大数值。
- `BrowserManager.disconnect()` 只断 WebSocket，不关浏览器；只有 `close()` 在 `_owns_browser` 时才杀进程。

## 依赖管理

- Python 依赖同时写进 `pyproject.toml` 的 `dependencies` 和 `requirements.txt`。
- 前端依赖用根目录 `npm run add -- <pkg>`（根目录 `npm install` 被 preinstall 拦截）。
- 新增依赖要在提交说明里写清：为什么现有依赖不能满足。

## 验证与提交

- **当前没有自动化测试。** 改动必须给出可复现的手动验证步骤：启动命令、操作路径、预期输出（文件 / 接口 / 界面）。步骤写进提交说明或 PR 描述。
- 一个 commit 只做一件事；message 说清"为什么"，diff 说明"是什么"。
- 行为变化同步 `CHANGELOG.md`。
- 提交前至少做一次语法检查：`.venv/Scripts/python -m compileall src server main.py run_gui.py`；前端改动跑 `npm --prefix webui run build`。
- 涉及 `/review` 或 tracking 的改动，必须手动走一遍：采集一次 → 打开 `/review` → `A/L/S/Enter/G` 各按一次 → 重启服务确认状态仍在。

---

## 晋升记录

初始约定在接入模板时从仓库既有实现整理，不占用晋升记录；后续晋升按流程登记。

| 日期 | 规则 | 来源（LESSONS.md 中的 Seen 日期） |
|---|---|---|
| | | |
