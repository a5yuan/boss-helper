# 事件用按平台分文件的 JSONL，不用 sqlite

投递统计页需要回看历史事件。选 JSONL（`output/{platform}/events.jsonl`，append-only，一行一条）而不是 sqlite，理由是数据量小（一天几十条，十年十几 MB）、写入只需一次追加、没有 schema 迁移负担；代价是聚合要在 Python 里做，查询不能走 SQL。考虑到页面是按时间段整体读取、不做复杂关联查询，这个代价可以接受。

## Considered Options

- **复用 `apply_audit.log`**：已有该文件且格式接近，但字段固定为投递相关（6 个），无法承载 `ai_call` / `collect` / `screen` 这些类型。改造它会破坏现有审计语义，所以新建一份并迁移旧数据。
- **sqlite**：聚合快、支持索引，但要引入 schema、迁移、并发写锁（多平台多线程同时写），对一个"一天几十行"的场景属于过度设计。

## Consequences

统计页每次打开会全量读一次事件文件并在内存聚合。数据量到十万行级别时需要重新评估（届时可以按月切文件，仍然不需要数据库）。
