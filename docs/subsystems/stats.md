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
| `server/stats.html` | 统计页（静态，手写 SVG） |
| `server/app.py` `/api/stats` | 聚合接口 |
| `output/{platform}/events.jsonl` | 事件流 |

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
