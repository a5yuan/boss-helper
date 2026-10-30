# 调试与复现

## 先看哪里

| 现象 | 先看 |
|---|---|
| 双击 exe 没反应 | exe 同目录 `startup.log` |
| 源码启动失败 | 终端输出 + 项目根 `startup.log` |
| 采集卡住 / 日志停更 | `.tracelink/trace.ndjson`，按 scope 过滤 |
| 接口 4xx/5xx | 后端终端 + `server/app.py` 对应路由 |
| 前端白屏 | 浏览器 DevTools + Vite 终端 |
| 找不到浏览器 | `config.yaml` 的 `chrome.path`，或注册表检测日志 |

## 启动方式

```bash
# 桌面 GUI（按 .env 的 BOSS_ENV 决定 dev/prod）
python run_gui.py

# 开发模式（Vite HMR）
python run_gui.py --dev

# 只起服务，不弹窗口
python run_gui.py --dev --no-window

# 构建前端后以 prod 模式运行
python run_gui.py --build

# 停止残留进程（杀 8848 监听）
python run_gui.py --stop

# CLI
python main.py --new -b chrome -n 20
```

端口：dev 模式后端从 `BOSS_DEV_BACKEND_PORT`（默认 8848）起找空闲端口，Vite 从 `BOSS_DEV_VITE_PORT`（默认 5173）起找；启动后写 `.env.local` 供前端代理使用。

## TraceLink

- 开关：`TRACELINK_ENABLED=true`，或 dev 模式自动开（`BOSS_GUI_DEV=1`）。
- 文件：`.tracelink/trace.ndjson`。
- Dashboard：`npm run dashboard`（`npx tracelink dashboard`），Receiver 默认 5174。
- 后端端点：`GET /__debug_log` 读日志，`DELETE /__debug_log` 清空，`GET /api/debug/status` 看 scope。
- 前端日志经 `/__debug_log` 转发到同一 tracer。
- 常用 scope：`collect-start`、`start-collection`、`error`、`stop-collection`。

## CDP

- 端口文件：`.cdp_port_chrome` / `.cdp_port_edge`。
- 端口扫描范围：9222–9229（`try_connect_existing`）。
- 标签页列表：`curl http://127.0.0.1:<port>/json`。
- 常见坑：导航 / 登录后 `webSocketDebuggerUrl` 会变，必须重新 `find_boss_page()`；`shared_worker` 的 URL 也可能含 `geek-chat`，但它不是页面。

## 常见故障

| 故障 | 原因 | 处理 |
|---|---|---|
| 启动即退出 | GUI 模式无控制台，stdout 是 NULL | 看 `startup.log` |
| WebSocket 连接超时 | 浏览器已关 / 端口失效 | 重新采集或 `--new` |
| 日志停在「导航至…」 | 页面跳转销毁了 CDP target | 确认登录；靠 `_reconnect_boss` 重连 |
| 薪资显示 `****` | 登录过期 / 页面未加载完 | 熔断分支：手动刷新页面后继续 |
| 复核定位失败 | 浏览器没在跑 / 采集任务占用 | 先跑一次采集，或停止任务 |
| 8848 被占 | 上次进程未退出 | `python run_gui.py --stop`，或 `--port` |
| 根目录 `npm install` 报错 | preinstall 拦截 | 用 `npm run install-deps` / `npm run add -- <pkg>` |
| 前端构建找不到模块 | 未装依赖 / 路径别名 | `npm --prefix webui install`，检查 `@` 别名 |

## 复现步骤模板

提交 bug 修复时按这个写：

```
环境：Windows / Chrome 版本 / dev 或 prod / 浏览器是否已登录
步骤：1. ... 2. ... 3. ...
预期：...
实际：...
证据：trace 片段 / startup.log / 接口响应 / 截图
```

## 测试现状

仓库目前没有自动化测试。修复 bug 时至少提供：

- 一个能稳定触发原问题的操作序列；
- 修复后用同样序列的结果；
- 如果改的是 `/review` 或 tracking，重启服务后确认状态仍在。

建立 `tests/` 后，在本文件补上运行命令。
