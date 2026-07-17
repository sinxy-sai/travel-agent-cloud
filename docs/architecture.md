# 架构说明

Travel Agent Cloud 正在从可部署单体演进为 Kubernetes 原生 Python/FastAPI 微服务系统。

```text
frontend
  -> travel-gateway
      -> travel-auth  -> PostgreSQL
      -> travel-trip  -> PostgreSQL
      -> travel-agent -> PostgreSQL / agent-runtime
      -> travel-mcp
      -> agent-runtime -> PostgreSQL / Redis / RabbitMQ / MinIO / travel-mcp
```

## 服务职责

- `travel-gateway`：统一 API 入口，保持前端只需要访问一个后端地址。
- `travel-auth`：用户认证、session、profile、安全事件、邮箱 token、OAuth identity、GitHub OAuth 回调。
- `travel-trip`：行程持久化、版本、恢复、收藏、删除和导出。
- `travel-agent`：会话数据边界、同步摘要和 Agent API 门面。
- `travel-mcp`：旅行工具数据源，当前主要封装高德 Web 服务和 fallback。
- `agent-runtime`：Agent 执行核心，负责 LangGraph/LangChain 编排、聊天回复、行程生成和异步 worker。

## 当前仍由 agent-runtime 承担的接口类型

- Agent 执行：`/api/v1/chat`、`/api/v1/agent/*`。
- 行程执行：`/api/v1/trip-plan`、行程 AI 修订、单日重生成。
- 异步任务：会话摘要 job、worker 消费。
- 迁移期聚合：账户导入导出和导出文件。

外部访问优先经过 `travel-gateway`。即使某个路径仍由 `agent-runtime` 实际处理，也应该先由对应领域服务承接路由，便于后续逐步迁移。

## 服务通信

- 前端流量统一进入 `travel-gateway`。
- 对外 HTTP API 使用 `/api/v1` 下的 REST 风格。
- Python/FastAPI 服务之间优先使用 HTTP REST。
- `agent-runtime` 通过 MCP 风格 JSON-RPC 调用 `travel-mcp`。
- RabbitMQ 用于领域事件和后台任务。
- gRPC 暂时保留，不作为当前默认方案。

## 消息队列

候选事件：

- `trip.plan.created`
- `trip.plan.updated`
- `trip.plan.deleted`
- `trip.plan.export.requested`
- `agent.conversation.updated`
- `agent.conversation.deleted`
- `agent.conversation.summarize.requested`
- `agent.conversation.summary.created`
- `user.profile.updated`

队列规则：

- 事件字段使用 camelCase。
- 消费者必须幂等。
- 消息只携带 ID 和必要上下文，业务数据仍以 PostgreSQL 为准。
- 长耗时任务必须持久化状态，并提供查询接口给前端轮询。

## 基础设施

```text
PostgreSQL, Redis, RabbitMQ, MinIO, Docker Compose, K3s, Ingress
```

## 代码组织原则

- `services/common` 只放跨服务基础设施代码，例如 HTTP 代理、header 转发、健康检查和通用错误结构。
- 业务规则留在各自服务内，避免共享包变成隐形单体。
- 新服务应拥有自己的路由、配置、模型、README、Dockerfile 和部署清单。

API 规范见 [api-guidelines.md](api-guidelines.md)，服务通信细节见 [service-communication.md](service-communication.md)。
