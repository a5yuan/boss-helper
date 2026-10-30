# 子系统：复核队列与投递跟踪

## 职责

把采集结果变成可逐条处理的队列：`server/review.html`（`/review`）+ `src/tracking.py`（状态库）+ `server/app.py` 的 `/api/tracking`、`/api/focus`、`/api/greet`。

不负责采集；它只读 `jobs_*.json`，并在浏览器里定位 / 填招呼语。

入口：桌面端顶部「复核队列」按钮通过 `_PickApi.open_review` 在系统浏览器打开；浏览器/开发模式下也可直接访问 `/review`（Vite dev 已代理）。页面顶部可切换历史采集文件。

## 不变量

- **主键是 `encryptJobId`**：`track_key` 和前端 `keyOf` 都是 `encrypt_job_id || security_id`。`securityId` 每次页面加载都会变，不能单独持久化（55e1d30）。
- **状态机**：`new → shortlisted / skipped / applied`，合法值由 `VALID_STATUS` 约束；未知状态抛 `ValueError`。
- **`tracking.json` 原子写**：`tmp + os.replace`；默认路径 `output/tracking.json`。
- **focus 顺序**：先按 `security_id` 在当前页面点卡片；点不到才用 `encrypt_job_id` 打开 `job_detail/<eid>.html`。
- **greet 只填不发送**：把文本写进最后一个可见 `textarea` / `contenteditable`，发送留给人工。
- **采集运行时拒绝浏览器操作**：`_with_browser` 在 `session.running` 时返回错误。
- **页面默认读最新文件，可切换历史文件**：`/api/results` 不带参数时取排序后的第一个 `jobs_*.json`；带 `date=<文件名>` 时取匹配文件。

## 依赖方向

```
server/review.html → /api/results, /api/tracking, /api/focus, /api/greet
server/app.py → src.tracking, src.core.browser, src.utils.browser_behavior, src.config
src.tracking → src.config（延迟 import）
```

`src/tracking.py` 不依赖 FastAPI / 浏览器。

## 关键文件

| 文件 | 作用 |
|---|---|
| `server/review.html` | 独立复核页：筛选、快捷键、详情、动作 |
| `src/tracking.py` | `Tracker`：读 / 写 `tracking.json` |
| `server/app.py` | `track_key`、`_job_files`、`_find_job`、`_with_browser`、`/api/focus`、`/api/greet` |
| `src/utils/browser_behavior.py` | `click_job`：Vue 点击优先，DOM 兜底 |
| `output/tracking.json` | 状态库（不入库） |

## 快捷键

`↑/↓` 或 `j/k` 移动，`A` 已投，`L` 收藏，`S` 跳过，`Enter` 浏览器定位，`G` 填招呼语。输入框聚焦时不触发。

## 已知陷阱

- **旧数据缺 `encrypt_job_id`**：只能在同一页面会话内用 `security_id` 定位，刷新后失效；前端会显示"无ID / 旧数据"提示，重新采集可修复。
- **URL 回退会离开列表页**：`job_detail/<eid>.html` 打开后，原搜索结果页状态丢失；需要回列表时用浏览器后退。
- **`prefer_chat=True`**：`/api/greet` 优先连最后一个 URL 含 `chat` 的 `type=page` 标签；没有聊天页时退回普通 BOSS 页，可能找不到输入框。
- **`shared_worker` 陷阱**：它的 URL 也可能含 `geek-chat`，`_with_browser` 已用 `type == "page"` 排除；新增页面选择逻辑时别退回去。
- **默认招呼语**用岗位 `title` + 前两个 `skills`；改模板时保持"只填不发送"。
- **状态按 ID 存**：同一岗位在不同 `jobs_*.json` 里重复出现时，状态会共享（这是期望行为）；切换文件不会重置状态。
- **历史文件切换只影响列表**：`/api/tracking` 始终返回全局状态库；`/api/focus`、`/api/greet` 会在所有采集文件里查找岗位。

## 测试方式

1. 跑一次采集，确认 `output/jobs_*.json` 有 `encrypt_job_id`。
2. 打开 `http://127.0.0.1:8848/review`，或点桌面端「复核队列」。
3. 用顶部文件下拉切换历史文件，确认列表和统计随之变化。
4. 依次按 `A` / `L` / `S`，刷新页面确认状态仍在。
5. 按 `Enter`：卡片在页面上应点击并切前台；不在页面上应打开详情页。
6. 按 `G`：浏览器聊天输入框出现招呼语，未自动发送。
7. 重启后端，确认 `/api/tracking` 仍返回之前的状态。
