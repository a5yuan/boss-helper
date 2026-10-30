# AGENTS.md — 路由表

本文件**不写规则**，只回答一个问题：**干这件事之前，先读哪份文档。**

读之前不要动手。读完之后，如果发现路由表里没有覆盖你当前的任务，先把该文档补上，再干活。

## 路由表

| 你要做的事 | 先读 | 读完的判定标准 |
|---|---|---|
| 改采集主流程 / 轮询 / 登录态 / 翻页 | `docs/subsystems/collector.md` | 能说清一次采集的完整生命周期和停止/暂停边界 |
| 改 CDP 连接、标签页选择、超时、点击 | `docs/subsystems/browser-cdp.md` | 知道允许用哪些 CDP 命令，超时和断连怎么降级 |
| 改 FastAPI 接口 / Session / 启动器 / Vue 前端 | `docs/subsystems/server-api.md` | 知道单任务约束、事件流和 dev/prod 两种启动方式 |
| 改 `/review` 复核队列、投递状态、定位、招呼语 | `docs/subsystems/review-queue.md` | 知道 encryptJobId 与 securityId 的区别，以及状态机 |
| 写新代码 / 重构 | `docs/code-standards.md` | 命名、依赖方向、错误处理、验证要求已明确 |
| 审查代码或 PR | `docs/code-standards.md` + `docs/review-checklist.md` | 能逐条对照，而不是凭感觉 |
| 审查外部贡献者提交的 PR | `CODE_OF_CONDUCT.md`、`LICENSE`（额外规则**尚未编写**，首次收到外部 PR 时补 `docs/contributors.md`） | 知道 CLA / 测试 / 变更说明的要求 |
| 修 bug / 复现问题 | `docs/debugging.md` + 对应 `docs/subsystems/` | 能按文档给出本地复现步骤 |
| 加调试追踪 / 看调用链 | `.agents/skills/tracelink/SKILL.md` | 知道 span、scope、exporter 的接法 |
| 合规检查 / 术语审查 | `.agents/workflows/compliance-check.md`、`LEGAL.md`、`docs/zhipin-robots.md` | 知道禁用词和 0 目标请求的边界 |
| 发布 / 改版本号 / 打包 exe | `docs/release.md` | 知道版本号三处来源和发布前检查 |
| 了解产品用法 / 目录结构 | `README.md`、`使用说明.txt` | — |
| 不确定该读什么 | 本文件「兜底」 | — |

## 每晚复盘

每天把当天所有 commit 过一遍，产出写入 `LESSONS.md`。复盘关注三个场景：

1. 哪些修复之后又返工了
2. 哪些压根不该合并
3. 哪些验证做得太糙

提示词见 `prompts/nightly-review.md`。

## 兜底

- 找不到对应文档：**先写文档，再写代码**。空缺本身就是问题。
- 两份文档冲突：以 `docs/code-standards.md` 为准，并提 issue 修正另一份。
- `LESSONS.md` 与 `docs/` 冲突：`docs/` 是当前标准，`LESSONS.md` 是历史证据；若冲突说明某条教训尚未晋升，按 `docs/` 执行并记录原因。

## 文档地图

```
CLAUDE.md                        ← 入口，只有指针
AGENTS.md                        ← 本文件，路由
LESSONS.md                       ← 错题本（夜间复盘追加）
docs/
  code-standards.md              ← 硬性标准
  review-checklist.md            ← 审查清单
  debugging.md                   ← 复现与定位
  release.md                     ← 发布与打包
  zhipin-robots.md               ← 目标站点 robots 快照（已有）
  subsystems/
    _template.md                 ← 新子系统文档模板
    collector.md                 ← 采集主流程
    browser-cdp.md               ← CDP 浏览器控制
    server-api.md                ← FastAPI / Session / GUI 启动器 / 前端
    review-queue.md              ← 复核队列与投递跟踪
prompts/
  nightly-review.md              ← 夜间复盘提示词
.agents/
  skills/tracelink/              ← TraceLink 追踪接入说明（已有）
  workflows/compliance-check.md  ← 合规术语扫描（已有）
```
