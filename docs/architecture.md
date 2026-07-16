# 架构说明

Travel Agent Cloud 当前从一个可部署核心开始：

```text
frontend -> travel-gateway -> agent-runtime -> PostgreSQL
                    -> travel-trip -> agent-runtime
                                 -> travel-mcp
                                 -> Redis / RabbitMQ / MinIO
```

## 当前 Agent Runtime API

```text
GET    /health
GET    /api/v1/me/profile
PATCH  /api/v1/me/profile
POST   /api/v1/trip-plan
POST   /api/v1/chat
GET    /api/v1/conversations
GET    /api/v1/conversations/{conversationId}
PATCH  /api/v1/conversations/{conversationId}
GET    /api/v1/conversations/{conversationId}/summary
POST   /api/v1/conversations/{conversationId}/summary
POST   /api/v1/conversations/{conversationId}/summary-jobs
GET    /api/v1/conversations/{conversationId}/summary-jobs/latest
DELETE /api/v1/conversations/{conversationId}
GET    /api/v1/trip-plans
GET    /api/v1/trip-plans/{tripPlanId}
PATCH  /api/v1/trip-plans/{tripPlanId}
DELETE /api/v1/trip-plans/{tripPlanId}
GET    /api/v1/trip-plans/{tripPlanId}/export
```

## 目标微服务结构

```text
frontend
  -> travel-gateway
      -> travel-auth
      -> travel-trip
      -> travel-agent
          -> agent-runtime
      -> travel-mcp

travel-auth / travel-trip / travel-agent / agent-runtime
  -> PostgreSQL / Redis / MinIO / RabbitMQ
```

## 服务通信

- 前端流量统一进入 `travel-gateway`。
- 对外 HTTP API 使用 `/api/v1` 下的 REST 风格。
- Python/FastAPI 服务之间优先使用 HTTP REST。
- `agent-runtime` 通过 MCP 风格 JSON-RPC 调用 `travel-mcp`。
- gRPC 暂时保留，不作为当前默认方案；只有出现明确的低延迟或双向流式需求时再引入。

## 消息队列

RabbitMQ 是当前默认消息队列，用于领域事件和后台任务。

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

当前异步摘要流程：

```text
POST /api/v1/conversations/{conversationId}/summary-jobs
  -> PostgreSQL conversation_summary_jobs status=QUEUED
  -> RabbitMQ agent.conversation.summarize.requested
  -> agent-runtime-worker
  -> PostgreSQL conversation_summary_jobs status=RUNNING/SUCCEEDED/FAILED
  -> ConversationSummarizerWorker
```

## 队列规则

- 生产者发布小型 JSON 事件，字段使用 camelCase。
- 消费者必须幂等，因为队列消息可能重试。
- 业务数据仍以 PostgreSQL 为准，消息只携带 ID 和必要上下文。
- 长耗时任务必须持久化状态，并提供查询接口供前端轮询。
- Secret 只能通过 `.env` 或 Kubernetes Secret 注入，不能提交到仓库。

## 支撑基础设施

```text
PostgreSQL, Redis, RabbitMQ, MinIO, pgvector, Docker Compose, K3s, Ingress, GitHub Actions
```

API 规范见 [api-guidelines.md](api-guidelines.md)，服务通信细节见 [service-communication.md](service-communication.md)。
