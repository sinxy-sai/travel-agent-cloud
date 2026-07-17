# Travel Agent Runtime

`agent-runtime` 是旅行 Agent 的执行核心。它只负责运行 LangGraph/LangChain workflow、调用 LLM 和旅行工具，并返回生成结果。

它不再拥有数据库，不保存会话，不保存行程，也不负责用户、认证、导入导出或摘要 worker。

## 服务边界

runtime 负责：

- 生成行程计划。
- 生成聊天回复。
- 根据已有行程修订完整计划。
- 根据已有行程重生成单日计划。
- 暴露 Agent 状态、工具目录和诊断信息。
- 调用 `mock` 或 `fastmcp` 旅行工具 Provider。

runtime 不负责：

- 登录注册、邮箱验证、OAuth、账户导入导出。
- 会话、消息、摘要任务和摘要 worker。
- 行程持久化、版本、收藏、删除、导出。
- PostgreSQL/MinIO/Redis 数据边界。

对应职责归属：

- `services/auth`：认证、用户资料、OAuth、邮箱验证、账户导入导出。
- `services/agent`：会话、聊天历史、摘要任务和 worker。
- `services/trip`：行程持久化、版本、收藏、删除、导出。
- `services/mcp`：高德/FastMCP 旅行工具服务。
- `services/gateway`：对外统一 API 和 `/health` 聚合。

## 接口

公开诊断接口：

- `GET /health`
- `GET /api/v1/agent/status`
- `GET /api/v1/agent/tools`
- `GET /api/v1/agent/diagnostics`

内部执行接口，需要 `X-Travel-Internal-Token`：

- `POST /internal/v1/trip-plan`
- `POST /internal/v1/agent/chat`
- `POST /internal/v1/trip-plans/{trip_plan_id}/revise`
- `POST /internal/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate`

`/internal/v1/trip-plan-jobs/*` 仍保留为 runtime 局部执行 job 能力；对外的可保存行程 job 由 `services/trip` 承担。

前端和外部客户端不应直接调用 runtime，应统一走 `travel-gateway`。

## 环境变量

最小配置见 `.env.example`。核心变量：

```text
APP_NAME=Travel Agent Runtime
APP_ENV=local
ALLOWED_ORIGINS=http://localhost:5173
AUTH_SECRET_KEY=change-me-to-a-random-secret
INTERNAL_SERVICE_TOKEN=change-me-internal-service-token
AGENT_ENGINE=langgraph
TRAVEL_TOOL_PROVIDER=fastmcp
FASTMCP_BASE_URL=http://travel-mcp:8100/mcp
```

说明：

- `AUTH_SECRET_KEY` 只用于校验 `travel-auth` 签发并由内部服务转发的 token。
- RabbitMQ、数据库、MinIO、Redis、邮件、OAuth、用户资料、导入导出相关环境变量不属于 runtime。

## 本地运行

推荐从仓库根目录启动：

```bash
docker compose up -d --build
```

启用摘要 worker：

```bash
docker compose --profile worker up -d --build
```

该 worker 使用 `services/agent` 镜像，不使用 `agent-runtime` 代码。

## 验证

```bash
python -m compileall agent-runtime/app
./scripts/smoke-test.ps1 http://localhost:5173
```

完整用户路径应通过 gateway 验证，不应直接以 runtime 的 `:8000` 端口验证旧公共 API。
