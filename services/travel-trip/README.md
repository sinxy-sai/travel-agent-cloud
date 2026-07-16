# travel-trip

`travel-trip` 是 Python/FastAPI 行程管理服务。

当前阶段它已经作为独立服务运行，但内部仍以门面方式代理到 `agent-runtime` 的行程接口。这样可以先建立服务边界、镜像、健康检查、网关路由和 K3s 部署形态，再逐步迁移真实行程持久化逻辑。

## 当前职责

- 承接 `travel-gateway` 转发过来的行程 API。
- 代理 `/api/v1/trip-plan`、`/api/v1/trip-plan-jobs/*` 和 `/api/v1/trip-plans/*` 到 `agent-runtime`。
- 通过 `/health` 暴露自身和 upstream 状态。
- 通过 `X-Travel-Service-Boundary: travel-trip` 标记内部服务边界，便于后续日志和排查。

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

## 本地运行

```powershell
cd services/travel-trip
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8200
```
