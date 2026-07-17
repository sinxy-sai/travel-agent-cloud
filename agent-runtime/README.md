# Travel Agent Runtime

`agent-runtime` 是旅行 Agent 的编排和执行核心。它不再承载登录注册、用户资料、账户导入导出、会话列表、行程列表等面向用户的数据边界；这些能力已经迁入独立微服务：

- `services/travel-auth`：认证、用户资料、OAuth、邮箱验证、账户导入导出。
- `services/travel-agent`：会话、聊天历史、摘要任务和 worker。
- `services/travel-trip`：行程持久化、版本、收藏、删除、导出。
- `services/travel-mcp`：高德/FastMCP 旅行工具服务。

## 当前职责

runtime 保留的职责：

- 执行 LangGraph/LangChain 旅行规划 workflow。
- 调用旅行工具 Provider：`mock` 或 `fastmcp`。
- 生成行程、异步行程 job、SSE job events。
- 处理内部聊天回复。
- 处理行程修订和单日重生成。
- 在迁移期提供最小 fallback 持久化，避免下游服务不可用时核心 Agent 完全不可用。

runtime 不再负责：

- 公开 `/api/v1/auth/*`、`/api/v1/me/*`。
- 公开 `/api/v1/conversations/*`。
- 公开 `/api/v1/trip-plans/*`。
- 邮件发送、GitHub OAuth、MinIO 导出文件管理。
- RabbitMQ 摘要 worker。

## 接口边界

公开健康与诊断接口：

- `GET /health`
- `GET /api/v1/agent/status`
- `GET /api/v1/agent/tools`
- `GET /api/v1/agent/diagnostics`

内部服务接口，需要 `X-Travel-Internal-Token`：

- `POST /internal/v1/trip-plan`
- `POST /internal/v1/trip-plan-jobs`
- `GET /internal/v1/trip-plan-jobs/{job_id}`
- `GET /internal/v1/trip-plan-jobs/{job_id}/events`
- `POST /internal/v1/agent/chat`
- `POST /internal/v1/trip-plans/{trip_plan_id}/revise`
- `POST /internal/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate`

前端和外部客户端不应直接调用 runtime 的内部接口，应统一走 `travel-gateway`。

## 环境变量

最小配置示例见 `.env.example`。核心变量：

```text
APP_NAME=Travel Agent Runtime
APP_ENV=local
ALLOWED_ORIGINS=http://localhost:5173
DATABASE_URL=postgresql://travel_agent:travel_agent_dev@postgres:5432/travel_agent_cloud
MESSAGE_QUEUE_URL=amqp://travel_agent:travel_agent_dev@rabbitmq:5672/
AUTH_SECRET_KEY=change-me-to-a-random-secret
INTERNAL_SERVICE_TOKEN=change-me-internal-service-token
AGENT_ENGINE=langgraph
TRAVEL_TOOL_PROVIDER=fastmcp
FASTMCP_BASE_URL=http://travel-mcp:8100/mcp
TRAVEL_TRIP_URL=http://travel-trip:8200
```

说明：

- `AUTH_SECRET_KEY` 只用于校验 `travel-auth` 签发并由内部服务转发的 token。
- `DATABASE_URL` 只服务于 runtime 的最小 fallback 存储；真实用户会话和行程数据由对应微服务负责。
- `MESSAGE_QUEUE_URL` 用于发布领域事件；摘要消费 worker 已迁到 `services/travel-agent`。
- 邮件、OAuth、MinIO、用户资料、导入导出相关环境变量不属于 runtime。

## 本地运行

推荐通过仓库根目录的 Docker Compose 启动：

```bash
docker compose up -d --build
```

启用摘要 worker 时运行：

```bash
docker compose --profile worker up -d --build
```

该 worker 使用 `services/travel-agent` 镜像，不再使用 `agent-runtime` 代码。

## 验证

从仓库根目录运行：

```bash
python -m compileall agent-runtime/app
./scripts/smoke-test.ps1 http://localhost:5173
```

smoke test 应通过 gateway 验证完整用户路径，不应直接以 runtime 的 `:8000` 端口验证旧公共 API。
