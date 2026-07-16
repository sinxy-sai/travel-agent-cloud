# travel-trip

`travel-trip` 是规划中的 Python/FastAPI 行程管理服务，目前还不是运行中的服务。行程持久化和导出接口当前仍在 `agent-runtime` 中。

## 未来职责

- 行程 CRUD、历史版本、版本恢复、收藏和搜索。
- 导出文件元数据和文件归属校验。
- 使用 PostgreSQL 作为权威数据源。
- 使用 MinIO 保存 Markdown、图片和 PDF 等导出文件。
- 通过 RabbitMQ 发布 `trip.plan.created`、`trip.plan.updated`、`trip.plan.export.requested` 等事件。

## 迁移原则

- 先保持 `travel-gateway` 作为公共入口。
- 等行程和导出数据模型稳定后，再从 `agent-runtime` 拆出行程接口。
- 拆分后，Agent 规划只通过内部 HTTP API 访问行程服务。
