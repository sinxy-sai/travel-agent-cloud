# travel-trip

`travel-trip` 是行程领域服务，负责行程生成入口、持久化、版本、收藏、删除和导出。

## 当前职责

- 处理登录用户和匿名本地用户的行程历史、详情、编辑、版本、恢复、收藏、删除和 Markdown 导出。
- 处理 `POST /api/v1/trip-plan`，调用 `agent-runtime` 生成行程后保存。
- 处理 `POST /api/v1/trip-plan-jobs`，提供异步行程生成 job 和 SSE 进度。
- 处理 `POST /api/v1/trip-plans/{tripPlanId}/revise`，调用 runtime 生成修订结果并保存新版本。
- 处理 `POST /api/v1/trip-plans/{tripPlanId}/days/{day}/regenerate`，调用 runtime 重生成单日计划并保存新版本。
- 通过 `/health` 暴露自身、数据库和上游 runtime 状态。

## 不负责的能力

- 登录注册、用户资料、OAuth 和账户导入导出：属于 `services/auth`。
- 会话、聊天历史和摘要任务：属于 `services/agent`。
- LangGraph/LangChain、LLM 和旅行工具编排：属于 `agent-runtime`。

## 后续增强

- 当前异步行程 job store 是内存态，生产上可以迁到 PostgreSQL 或 Redis。
- 后续可补充 `trip.plan.created`、`trip.plan.updated`、`trip.plan.deleted`、`trip.plan.export.requested` 等领域事件。
- 共享 PostgreSQL 是 VPS 资源约束下的取舍；服务代码边界已经独立。

## 本地运行

```powershell
cd services/trip
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:DATABASE_URL="postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud"
$env:AUTH_SECRET_KEY="travel-agent-cloud-local-dev-secret"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8200
```

容器环境推荐从仓库根目录启动：

```powershell
docker compose up -d --build travel-trip
```
