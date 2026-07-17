# travel-trip

`travel-trip` 是行程领域服务。

## 当前职责

- 处理登录用户和匿名本地用户的行程历史、详情、编辑、版本、恢复、收藏、删除和 Markdown 导出。
- 通过 `POST /internal/v1/trip-plans` 承接 `agent-runtime` 的生成后保存请求。
- 通过 `PATCH /internal/v1/trip-plans/{tripPlanId}` 承接 `agent-runtime` 的 AI 修订和单日重生成保存请求。
- 对行程生成、异步生成、AI 修订和单日重生成入口使用 runtime internal execution 路径，因为这些仍属于 Agent 执行核心能力。
- 通过 `/health` 暴露自身、数据库和上游 runtime 状态。

## 后续职责

- 把导出文件元数据和图片/PDF 等文件归属校验继续下沉到 `travel-trip`。
- 通过 RabbitMQ 发布 `trip.plan.created`、`trip.plan.updated`、`trip.plan.deleted`、`trip.plan.export.requested` 等事件。
- 在数据边界稳定后，再考虑从共享 PostgreSQL 拆到独立数据库。

## 本地运行

```powershell
cd services/travel-trip
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:DATABASE_URL="postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud"
$env:AUTH_SECRET_KEY="travel-agent-cloud-local-dev-secret"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8200
```

`requirements.txt` 会以 editable 方式安装 `../common`，因此本地运行时需要保留 `services/common` 目录。
