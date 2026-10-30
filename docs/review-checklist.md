# 审查清单

逐条打勾。任何一条不通过，先修再合并。审查前先读 `docs/code-standards.md`。

## 合规

- [ ] Python 侧没有新增对 zhipin.com 的 HTTP 请求（搜 `requests.`、`httpx`、`urllib`）
- [ ] 页面内 `fetch` 只在 CDP `Runtime.evaluate` 上下文执行
- [ ] 新增文案 / 注释没有敏感词（按 `.agents/workflows/compliance-check.md` 扫一遍）
- [ ] 没有引入绕过登录 / 验证码 / 风控的能力

## 标识与数据

- [ ] 持久化用 `encrypt_job_id`；`security_id` 没有被单独写进 tracking 主键
- [ ] 状态值在 `VALID_STATUS` 内
- [ ] `tracking.json` 写入是原子写（`tmp + os.replace`）
- [ ] 新采集字段在 `DetailPanelReader.read_detail`、`webui/src/api.ts:Job`、`/review` 三处都能取到（或明确只给其中一处用）
- [ ] 旧数据（缺 `encrypt_job_id`）有降级提示，不会静默失败

## CDP / 浏览器

- [ ] 新增 CDP 命令走 `send_cdp` / `evaluate`，没有直接 `ws.recv()`
- [ ] 有整体超时；超时按"取数失败"降级，不让线程崩
- [ ] 页面导航 / 登录跳转后重新定位标签页（`_reconnect_boss` / `find_boss_page`）
- [ ] 选标签页时排除了 `type != "page"`（`shared_worker` 的 URL 也含 `geek-chat`）
- [ ] `disconnect()` 与 `close()` 的语义没有被混用

## 采集主流程

- [ ] 停止 / 暂停在循环边界被检查；长睡眠用 `_interruptible_sleep`
- [ ] 薪资 `****` 熔断逻辑没有被绕过
- [ ] 查重口径（`title + company`）变化时，说明了重复岗位的影响
- [ ] 输出文件名前缀 / tag 规则没有被破坏（`_append_location_tag`）

## 复核队列

- [ ] `/api/focus` 的 click → URL 回退顺序保留
- [ ] `/api/greet` 只填输入框，不点击发送
- [ ] 采集任务运行时，focus / greet 返回明确错误，而不是并发操作浏览器
- [ ] 快捷键不会被输入框抢走（`e.target.tagName === 'INPUT'` 分支）

## 服务与前端

- [ ] 新接口返回 JSON，失败是 `{ok:false,error}`；同步接口没有长时间阻塞事件循环（浏览器操作会占线程池，需说明）
- [ ] WS 事件类型与 `webui/src/stores/engine.ts:handleEvent` 对齐
- [ ] 前端 `npm --prefix webui run build` 通过（含 `vue-tsc --noEmit`）
- [ ] dev 模式 Vite 代理路径（`/api`、`/ws`、`/__debug_log`）没有遗漏

## 验证

- [ ] 提交说明里有可复现的手动验证步骤
- [ ] 至少验证了失败路径（浏览器没开、未登录、页面无卡片、旧数据）
- [ ] 行为变化已写进 `CHANGELOG.md`
