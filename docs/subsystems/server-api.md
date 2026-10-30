# 子系统：服务、会话与桌面启动器

## 职责

- `server/app.py`：FastAPI REST + WebSocket + 静态前端托管 + `/review` 页面。
- `server/session.py`：单任务会话，把 `run_collection` 放进 daemon 线程。
- `server/tracer.py`：TraceLink 单例与 Receiver 配置。
- `run_gui.py`：进程编排（uvicorn 子线程、Vite、pywebview 窗口、端口发现、启动日志）。
- `webui/`：Vue 3 + Vite + Pinia 前端。

不负责采集算法和 CDP 细节。

## 不变量

- **同一时刻只有一个采集任务**：`Session.running` 为真时 `start` 抛错。
- **引擎与 UI 只通过 `GuiController.events` 队列通信**；WS 每 0.15s `drain()` 一次。
- **API 失败返回 `{ok: false, error}`**，不把 traceback 直接抛给前端。
- **dev 模式**：Vite 代理 `/api`、`/ws`、`/__debug_log`、`/__debug_panel` 到后端；**prod 模式**：`server/static/` 挂在 `/`。
- **`/review` 不依赖 Vue 构建产物**，直接返回 `server/review.html`。
- **GUI 模式没有控制台**：stdout / stderr 必须重定向到 `startup.log`。

## 依赖方向

```
run_gui.py → server.app (uvicorn) → server.session → src.collector
server.app → src.config, src.core.cities, src.tracking, src.core.browser
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
| GET / POST | `/api/config` | 浏览器路径、输出目录 |
| GET / POST | `/api/start-params` | 运行参数持久化（白名单） |
| POST | `/api/start-params/reset` | 重置默认 |
| GET | `/api/cities` | 城市列表（缓存优先） |
| POST | `/api/cities/refresh` | 页内 fetch `city.json` |
| POST | `/api/start` / `stop` / `pause` / `resume` | 任务控制 |
| GET | `/api/status` | 运行状态、进度、待办动作 |
| POST | `/api/ack` | 用户完成扫码 / 确认 |
| GET | `/api/results` | 最新（或指定日期）岗位 JSON |
| WS | `/ws` | 日志 / 进度 / 状态 / need_action 事件流 |
| GET / POST | `/api/tracking` | 投递状态 |
| POST | `/api/focus` | 浏览器定位 |
| POST | `/api/greet` | 填招呼语 |
| GET | `/review` | 复核队列页面 |
| GET / DELETE | `/__debug_log` | 调试日志读写 |
| GET / POST | `/api/debug/*` | 调试开关、scope、面板 |

## 已知陷阱

- **WS 是轮询式 drain**：两个客户端同时连接会互相抢事件；不要假设多标签页都能收到完整日志。
- **同步路由会占线程池**：`/api/focus`、`/api/greet` 内部同步操作浏览器（含 `time.sleep`），并发请求会排队。
- **`_with_browser` 在采集运行时直接拒绝**：这是有意的，不要改成并发连接同一个浏览器。
- **`session.controller` 在任务结束后仍保留**：`/api/status` 会继续返回最后一次进度和 state，前端据此显示"已停止"。
- **`StaticFiles` 挂在 `/`**：新增路由必须在 mount 之前注册，否则会被静态托管吞掉。
- **Vite 构建 `outDir` 是 `../server/static`**：`build_exe.py` 又拷 `webui/dist`，两处产物要一致。
- **端口**：dev 模式自动找空闲端口并写 `.env.local`；prod 固定 `BOSS_BACKEND_PORT`。

## 测试方式

```bash
python run_gui.py --dev --no-window
curl http://127.0.0.1:8848/api/status
curl http://127.0.0.1:8848/api/results
```

前端改动：`npm --prefix webui run build`（含 `vue-tsc --noEmit`）。
