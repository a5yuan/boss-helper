# 子系统：投递统计

每个子系统一份文档。改动该目录下代码前必须读完本文件。

## 职责

记录投递、AI 调用、采集、筛选四类事件，并把它们聚合成可回看的统计页（`/stats`）。

**不负责**：不做任何实际投递动作，不参与采集，不写 `tracking.json`。事件只读，不驱动业务逻辑——事件写失败不能影响主流程。

## 不变量

- 事件流 append-only：一条事件写入后永不修改、永不删除。
- 事件按平台分文件（`output/{platform}/events.jsonl`），跨平台聚合在读取时做，不在写入时做。
- 写事件失败只记日志，绝不向上抛异常——统计是旁路，不能拖垮投递。
- 不存 JD 正文、招呼语全文、完整岗位 JSON。事件里只留指针（`job_id`）和数值。
- `drafted` 不计入「已投递」（见 ADR-0003）。

## 依赖方向

```
stats  ← 允许被 server/app.py 依赖（提供 /api/stats）
stats  → 允许依赖 src/storage（读事件文件）
stats  ↛ 不依赖 collector / adapters / ai（只消费它们写的事件）
```

写入侧相反：`src/ai/apply.py`、`src/ai/client.py`、`src/collector.py` 依赖 `src/storage/events.py`，反向不成立。

## 关键文件

| 文件 | 作用 |
|---|---|
| `src/storage/events.py` | `record()` 写入、`load()` 读取 |
| `src/storage/stats.py` | 聚合：分桶、成功率、费用、日历热力图 |
| `scripts/backfill_events.py` | 回填脚本（幂等） |
| `server/stats.html` | 统计页（静态，手写 SVG） |
| `server/app.py` `/api/stats` | 聚合接口 |
| `output/{platform}/events.jsonl` | 事件流 |

## 接口

```
GET /api/stats?range=today|24h|7d|30d|all&platform=all|boss|zhaopin
```

分桶在服务端做完，前端只画图。分桶粒度跟着区间走：`today` / `24h` 按小时，
其余按天。

返回结构：

```json
{
  "ok": true,
  "range": "7d",
  "platform": "all",
  "granularity": "day",
  "platforms": ["boss", "zhaopin"],
  "buckets": [{"key": "2026-11-25", "label": "11-25",
               "submitted": 1, "drafted": 0, "skipped": 0,
               "collects": 3, "screens": 3,
               "ai_calls": 0, "ai_duration_ms": 0,
               "by_platform": {"boss": {"submitted": 1, "drafted": 0, "skipped": 0}}}],
  "totals": {"submitted": 1, "drafted": 0, "skipped": 0, "failed": 0,
             "attempts": 1, "success_rate": 1.0,
             "today_submitted": 0, "today_drafted": 0,
             "avg_duration_ms": null,
             "ai_calls": 0, "collects": 32, "screens": 19,
             "tokens_in": 0, "tokens_out": 0, "cost": null},
  "heatmap": {"start": "2026-05-27", "end": "2026-11-25", "cells": [...]},
  "event_count": 70,
  "bad_lines": 0
}
```

## 统计口径

- **总投递数**只算 `submitted`。`drafted` 单独一个数（ADR-0003）。
- **成功率** = （submitted + drafted）/ 真正动过手的次数。
  闸门拦下的（`skipped: daily_limit` / `already_applied` / `unsupported:*`）
  从没碰过平台，不进分母——它们不是失败。
- **AI 花费**需要 `ai.pricing` 单价表（`{模型: {input: 元/千token, output: ...}}`）。
  没配就返回 `null`，页面显示 token 数——不编金额。
- **平均耗时**取 `apply` 事件的 `duration_ms` 均值。

## 回填

```
.venv/Scripts/python scripts/backfill_events.py            # 全部平台
.venv/Scripts/python scripts/backfill_events.py --dry-run  # 只看会写多少
```

从 `output/{platform}/jobs_*.json` 生成 `collect`、从 `ai_plan_*.json` 生成 `screen`。
**投递类不回填**——当时没记，编不出来。

幂等靠去重键：回填来的事件用 `event + file`（一个文件一条事件），
运行时记的事件用 `ts + event + job_id`。任务书写的是 `ts + event + file`，
但 `jobs_*.json` 是累积文件，同一个文件多次采集后 `ts` 会变，用 `ts` 做键
会让同一份文件每次回填都多一条。

## 写入点

谁写什么事件：

| 位置 | 事件 | 关键字段 |
|---|---|---|
| `src/ai/apply.py:run_apply` | `apply` | `status`（submitted / drafted / skipped）、`duration_ms` |
| `src/ai/apply.py:run_apply` | `send_message` | `length`、`sent` |
| `src/ai/dispatch.py:dispatch` | `apply` | BOSS 填草稿，**`status` 恒为 `drafted`** |
| `src/ai/client.py:_post` | `ai_call` | `kind`、`model`、`tokens_in`、`tokens_out` |
| `src/collector.py:run_collection` | `collect` | `count`、`skipped`、`excluded`、`file` |
| `src/ai/pipeline.py:build_plan` | `screen` | `count`、`planned`、`skipped`、`excluded`、`file` |

- `run_apply` 在三种情况下写 `apply` 事件：闸门拦下（`skipped`）、投递被确认
  （`submitted`）、投递没被确认（`skipped`，**不能记成 submitted**）。
- BOSS 的草稿走 `dispatch`，不在 `run_apply` 里——`run_apply` 只处理
  `apply_then_chat`（智联）。两条路径都写 `apply` 事件，但 `status` 不同。
- token 数从响应 `usage` 里取，取不到就留空，不编。

## 事件字段

公共四字段：`ts`（ISO 到秒）、`platform`、`event`、`ok`。

| event | 附加字段 |
|---|---|
| `apply` | `job_id` `company` `title` `status`(submitted/drafted/skipped) `reason` `duration_ms` |
| `send_message` | `job_id` `length` `sent` `duration_ms` |
| `ai_call` | `kind`(screen/greeting) `model` `tokens_in` `tokens_out` `duration_ms` |
| `collect` | `count` `skipped` `excluded` `file` |
| `screen` | `count` `planned` `skipped` `excluded` `file` |

## 已知陷阱

- 历史数据只有 2 条真实投递事件。`collect` / `screen` 从已有的 42 个 `jobs_*.json` 和 25 个 `ai_plan_*.json` 回填；投递类不回填（当时没有记录，编不出来）。
- 时间区域选「今天」时柱状图按小时分桶，选「7天/30天」按天分桶。粒度跟着区间走，否则要么只有一根柱子要么挤成一片。
- 空数据时保留坐标轴和网格，只显示「暂无数据」，否则看起来像加载失败。

## 测试方式

- `python -m unittest tests.test_events`：写入、读取、坏行跳过、写失败不影响调用方。
- `python -m unittest tests.test_stats_api`：区间过滤、平台过滤、分桶粒度。
- 页面本身无自动化测试，改动后用 `/stats` 手工看一眼三种图和空数据状态。

`tests/test_session_events.py` 是另一回事：它测的是 Session 的 WebSocket 事件流
（多任务 drain / 快照），与统计事件流无关，只是名字撞了。
