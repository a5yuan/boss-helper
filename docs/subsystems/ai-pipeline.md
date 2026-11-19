# 子系统：AI 筛选与招呼语

## 职责

把 `jobs_*.json` 里已采集的岗位变成一份**可执行的投递计划**：

1. `screen`：用 LLM 按简历给每条岗位打分、判定 `apply / maybe / skip`、写理由；
2. `greeting`：针对判为 `apply` 的岗位，结合 JD 与简历生成招呼语（80~120 字）；
3. `dispatch`：按计划逐条打开详情页 → 点「立即沟通」→ 把招呼语填进输入框 → 最后跳到聊天页。

产物：`output/ai_plan_<date>_<tag>.json`。

## 不变量

- **只填不发送**：`dispatch` 只把文本写进输入框，发送永远由人点。`fill_greeting.js` 不得触发发送。
- **LLM 只读文本**：发给模型的只有岗位字段和简历文本，不带 cookie、不带 securityId。
- **按方向选简历**：`ai.resumes` 配多份简历 + 关键词，按「标题 3 / 技能 2 / JD 1」打分选一份；
  平局或零命中走 `default_resume`。计划里每条都记 `resume` 字段，方便事后核对。
- **不进仓库的密钥**：`ai.api_key` 只写在 `config.yaml`（已 gitignore）或环境变量 `BOSS_AI_API_KEY`。
- **计划先落盘再执行**：`dispatch` 只读 plan 文件，不重新调模型；人不改计划就不执行。
- **节奏可配**：`ai.fill_gap_min` / `ai.fill_gap_max`（默认 5~10s）控制条间隔，
  `ai.fill_settle`（默认 2s）控制填完到切下一条的等待；CLI 用 `--gap-min/--gap-max` 覆盖。
  单条实际耗时 ≈ 页面加载 4s + 点击 1s + 填字 0.5s + settle + 间隔。
- **失败不中断**：单条失败计入 `failed`，继续下一条；全部结束后仍要跳到聊天页。
- **投前看活跃度**：点「立即沟通」之前先读详情页 `.job-boss-info` 的活跃描述
  （`刚刚活跃 / 在线 / N天前活跃 / N月前活跃`），超过 `ai.max_inactive_days`（默认 3 天）
  直接跳过——对方看不到，还可能被自动回复筛掉。读不出来时放行并记日志。
- **不重复联系**：已有 `tracking.json` 记录的岗位直接跳过，绝不重复点。
- **每日额度可选**：`ai.daily_limit` 默认 0（不限）；设成正数时按当天
  `applied / shortlisted` 计数截断。
- **LLM 全局限流**：`src/ai/client.py` 只有一个模块级 `BoundedSemaphore`，容量取
  `ai.concurrency`；限的是真正发出的 `requests.post`，不按 `LLMClient` 实例各算一份。

## 依赖方向

```
src.ai.pipeline → src.ai.client, src.ai.screen, src.ai.dispatch, src.config
src.ai.dispatch → src.adapters.boss, src.core.browser, src.core.js_loader, src.runtime, src.tracking
src.ai.* 不得 import server.*；API 层在 server.app 里调用它们
```

## 关键文件

| 文件 | 作用 |
|---|---|
| `src/ai/client.py` | OpenAI 兼容 chat 客户端，JSON 输出解析与重试 |
| `src/ai/resume.py` | 读简历（md/txt）+ `ResumeLibrary` 关键词路由，多份简历按方向选 |
| `src/ai/screen.py` | 打分 + 判定 + 理由 + 招呼语，提示词在这里 |
| `src/ai/pipeline.py` | 计划编排：读采集结果 → 调模型 → 写 `ai_plan_*.json`，带缓存复用 |
| `src/ai/activity.py` | 招聘者活跃描述解析（`parse_active_days` / `is_offline`） |
| `src/ai/dispatch.py` | 浏览器侧执行：开详情 → 点沟通 → 填字 → 跳聊天页 |
| `src/js/fill_greeting.js` | 把 `__TEXT__` 写进最后一个可见输入框（只填不发） |
| `src/ai/__main__.py` | CLI：`screen` / `dispatch` 两个子命令 |

## 采集后自动执行

`ai.auto_after_collect` 控制采集结束后是否自动接上 AI：

| 值 | 行为 |
|---|---|
| `off`（默认） | 什么都不做，等人在复核页点按钮 |
| `screen` | 只跑筛选生成计划，不点任何东西 |
| `fill` | 筛选 + 逐条点沟通并填招呼语（只填不发，但会产生真实沟通记录） |

钩子在 `server/session.py:ai_after_collect`，跑在采集线程里，用同一个
`GuiController` 输出日志，所以界面「实时日志」能看到 `[AI]` 开头的行。
它接收本次采集返回的 `json` 路径，不再 glob 最新文件；Tracker 由
`src/runtime.py` 注入，配额按平台算。任务被手动停止时不会触发。

## 复核页集成

`/review` 顶部两个按钮：

- **AI 筛选** → `POST /api/ai/screen`，给当前采集文件生成计划；列表显示分数，详情区显示判定 / 理由 / 不匹配点 / 可编辑招呼语
- **AI 批量填** → `POST /api/ai/fill`，后台线程逐条「定位 → 点沟通 → 填字」，前端轮询 `/api/ai/fill/status`

填充结束不刷新页面（刷新会清空输入框），草稿由平台自己保存。

## 已知陷阱

- **点「立即沟通」本身就是一次沟通**：对方招聘者会收到通知，有些人还挂着自动回复
  按学历 / 年限先筛一遍（实测收到过「不好意思，不太合适哦」）。不存在"只填不发就不算联系"。
- **securityId 会随页面加载失效**：`dispatch` 一律用 `encrypt_job_id` 拼详情页 URL，不依赖列表卡片。
- **点沟通可能开新标签**：点完要按 URL 含 `chat` 找 `type=page` 的标签重连，`shared_worker` 必须排除。
- **聊天输入框是 contenteditable，不是 textarea**：判断"输入框就绪"必须同时查 `textarea` 和 `[contenteditable="true"]` 且尺寸 > 40×8；只查 textarea 会把搜索结果页的隐藏输入框当成聊天框。
- **「立即沟通」外层有 `div.btn-startchat-wrap`**：`element.click()` 点的是壳子，不触发跳转；必须用 CDP `Input.dispatchMouseEvent` 点坐标（`locate_chat_button.js` 只定位、不点击）。
- **草稿是失焦时才存的**：填完直接 `location.href` 跳走，草稿会丢（回来是空的）。
  必须先在页面上 blur 一次再导航；实测 blur 后 2s 再切就稳了。
- **输入要走真实通道**：`innerText` + 手工 `dispatch(input)` 不更新 BOSS 的 Vue 状态，
  草稿同样存不住。用 CDP 的 `Input.insertText`（先 Ctrl+A 清空）。
- **填完别立刻导航**：平台存草稿有延迟，填完等 2.5s 再走，否则草稿丢失；已在聊天页时收尾不要再 `location.href` 一次。
- **详情页返回空 JD**：BOSS 对未登录 / 频繁访问会返回脱敏内容；`screen` 遇到 `jd` 为空应直接判 `skip` 并在理由里写明，不要硬编招呼语。

## 测试方式

```bash
# 1) 只筛选，不碰浏览器（可反复跑，有缓存）
.venv/Scripts/python -m src.ai screen --file output/jobs_2026-11-17_RAG_杭州.json --limit 3

# 2) 看计划
cat output/ai_plan_2026-11-17_RAG_杭州.json

# 3) 执行（真实点沟通，串行）
.venv/Scripts/python -m src.ai dispatch --plan output/ai_plan_2026-11-17_RAG_杭州.json --max 3
```

预期：`screen` 输出每条的分/判定/理由；`dispatch` 每条打印 `>>> 填好了`，结束时浏览器停在 `/web/geek/chat`。
