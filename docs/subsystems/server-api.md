# 子系统：服务、会话与桌面启动器

## 职责

- `server/app.py`：FastAPI REST + WebSocket + 静态前端托管 + `/review` 页面。
- `server/session.py`：任务注册表，每个 `task_id` 一个 daemon 线程跑 `run_collection`。
- `server/tracer.py`：TraceLink 单例与 Receiver 配置。
- `run_gui.py`：进程编排（uvicorn 子线程、Vite、pywebview 窗口、端口发现、启动日志）。
- `webui/`：Vue 3 + Vite + Pinia 前端。

不负责采集算法和 CDP 细节。

## 不变量

- **同一平台同一时刻只有一个采集任务**：`Session.running_for(platform)` 为真时 `start` 抛 `RuntimeError`；不同平台可以并存。
- **引擎与 UI 只通过 `GuiController.events` 队列通信**；WS 每 0.15s 把所有 controller 的队列 drain 一遍，每条事件追加 `task_id`。
- **任务结束后从 `tasks` 移除**，controller 留在 `_terminal` 里 300 秒（最多 8 条），供前端轮询收尾。
- **API 失败返回 `{ok: false, error}`**，不把 traceback 直接抛给前端。
- **dev 模式**：Vite 代理 `/api`、`/ws`、`/review`、`/__debug_log`、`/__debug_panel` 到后端；**prod 模式**：`server/static/` 挂在 `/`。
- **`/review` 不依赖 Vue 构建产物**，直接返回 `server/review.html`。
- **GUI 模式没有控制台**：stdout / stderr 必须重定向到 `startup.log`。

## 依赖方向

```
run_gui.py → server.app (uvicorn) → server.session → src.collector
server.app → src.config, src.core.cities, src.runtime, src.tracking, src.core.browser
webui → /api, /ws（HTTP/WS，不 import Python）
```

`server.app` 在模块底部延迟 import `src.tracking`；新增重模块时沿用延迟 import，避免启动变慢 / 循环依赖。

## 关键文件

| 文件 | 作用 |
|---|---|
| `server/app.py` | 全部 REST / WS 路由、`/review`、静态托管 |
| `server/session.py` | `Session` 单例、启动 / 停止 / 暂停 / ack |
| `server/tracer.py` | TraceLink 配置（scope、endpoint、开关） |
| `run_gui.py` | 模式选择、端口、Vite、pywebview、`--stop` |
| `webui/src/api.ts` | 前端 API 封装与类型 |
| `webui/src/stores/engine.ts` | Pinia 引擎状态、WS 事件处理、参数持久化 |
| `webui/vite.config.ts` | dev 代理与 build 输出到 `server/static` |

## 接口一览

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/platforms` | 已注册平台（`name` + `display_name`），默认平台排第一；导入 `src/adapters` 下的模块触发自注册，不按平台名写分支 |
| GET / POST | `/api/config` | 浏览器路径、输出目录 |
| GET / POST | `/api/start-params` | 运行参数持久化（白名单，含 `speed`: `slow` / `normal` / `fast`、`site` 平台） |
| POST | `/api/start-params/reset` | 重置默认 |
| GET | `/api/cities` | 城市列表（缓存优先） |
| POST | `/api/cities/refresh` | 页内 fetch `city.json` |
| POST | `/api/start` / `stop` / `pause` / `resume` | 任务控制；start 返回 `task_id`（`site` 或别名 `platform` 指定平台），其余可用 `task_id` 指定目标任务，缺省为当前任务 |
| GET | `/api/status` | 运行状态、进度、待办动作；可用 `task_id` 查指定任务 |
| POST | `/api/ack` | 用户完成扫码 / 确认；可用 `task_id` 指定目标任务 |
| GET | `/api/results` | 最新（或指定日期）岗位 JSON；`platform` 指定平台输出目录，不传时沿用 `output_dir` / 默认平台 |
| WS | `/ws` | 日志 / 进度 / 状态 / need_action 事件流；连接时先推所有任务快照（快照事件带 `task_id` 与 `platform`），之后一条连接转发所有平台 |
| GET / POST | `/api/tracking` | 投递状态；可用 `platform`（读为查询参数，写为 body 字段）指定平台，缺省为默认平台 |
| POST | `/api/focus` | 浏览器定位，并默认点击「立即沟通」打开聊天窗；`platform` 指定平台，不传时用岗位记录 / 默认平台 |
| POST | `/api/greet` | 填招呼语；`platform` 同上 |
| GET | `/review` | 复核队列页面 |
| GET | `/api/ai/plan` | 读某个采集文件对应的 AI 计划（`exists=false` 表示还没筛过） |
| POST | `/api/ai/screen` | 跑 AI 筛选并生成 `ai_plan_*.json`（采集运行中拒绝） |
| POST | `/api/ai/greeting` | 保存单条招呼语的编辑 |
| POST | `/api/ai/fill` | 后台线程批量填充（点沟通 + 填字，不发送），返回 `task_id` |
| GET | `/api/ai/fill/status` | 批量填充进度与日志；可用 `task_id`，缺省为最近一次 |
| GET / DELETE | `/__debug_log` | 调试日志读写 |
| GET / POST | `/api/debug/*` | 调试开关、scope、面板 |

## 已知陷阱

- **WS 是轮询式 drain**：两个客户端同时连接会互相抢事件；不要假设多标签页都能收到完整日志。
- **同步路由会占线程池**：`/api/focus`、`/api/greet` 内部同步操作浏览器（含 `time.sleep`），并发请求会排队。
- **`_with_browser` 在采集运行时直接拒绝**：这是有意的，不要改成并发连接同一个浏览器。
- **终态记录只保留 300 秒**：`/api/status` 在这段时间内仍返回最后一次进度和 state，前端据此显示"已停止"。
- **`current_task_id` 指向最后一次 `start` 的任务**：不传 `task_id` 的 status / stop 走的仍是它；多平台并行时前端必须按 `task_id` 取状态。
- **快照只推活任务**：有活任务时，终态任务不会出现在连接快照里；已停止的标签页刷新后会消失，活页面里仍保留。快照不带日志，刷新后日志从空开始。
- **`/api/platforms` 有进程内缓存**：新装或删掉平台目录后要重启服务才会刷新列表。
- **状态按 `task_id` 索引**：`/api/focus`、`/api/greet` 只在同平台任务运行时拒绝，不会因为别的平台任务在跑就拒绝。
- **`StaticFiles` 挂在 `/`**：新增路由必须在 mount 之前注册，否则会被静态托管吞掉；`/review` 就是靠这一点在 mount 之前注册的。
- **Vite 构建 `outDir` 是 `../server/static`**：`build_exe.py` 又拷 `webui/dist`，两处产物要一致。
- **端口**：dev 模式自动找空闲端口并写 `.env.local`；prod 固定 `BOSS_BACKEND_PORT`。

## 测试方式

```bash
python run_gui.py --dev --no-window
curl http://127.0.0.1:8848/api/status
curl http://127.0.0.1:8848/api/results
```

前端改动：`npm --prefix webui run build`（含 `vue-tsc --noEmit`）。
