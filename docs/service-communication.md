# 服务通信方案

本文档描述 Travel Agent Cloud 的服务间通信选择。

## 当前选型

| 需求 | 方案 | 范围 |
| --- | --- | --- |
| 公共 API | HTTP REST | 前端到 `travel-gateway` |
| Python 服务内部调用 | HTTP REST | `travel-gateway` 到各后端服务 |
| Agent Runtime 调用 | HTTP REST | `travel-agent` 到 `agent-runtime` |
| 旅行工具调用 | MCP 风格 HTTP JSON-RPC | `agent-runtime` 到 `travel-mcp` |
| 异步事件和后台任务 | RabbitMQ | 跨服务事件和后台任务 |
| 未来流式 RPC | gRPC 或 WebSocket | 保留，不是当前默认实现 |

## 为什么使用 RabbitMQ

当前异步工作负载主要是业务事件和后台任务，而不是高吞吐日志分析流。RabbitMQ 更适合目前阶段。

适合使用 RabbitMQ 的场景：

- 会话摘要任务。
- 大文件导出生成。
- 通知或审计事件。
- 可重试的工具执行任务。
- 用户、行程、Agent 事件与下游消费者解耦。

不适合使用 RabbitMQ 的场景：

- 同步用户查询。
- 替代 PostgreSQL 作为事实数据源。
- 传递密钥、JWT、密码或大体积正文。

## HTTP 服务调用

当前 Python/FastAPI 微服务路线优先使用 HTTP REST。这样可以保持服务边界清晰，并且便于在 Docker Compose 和 K3s 中使用服务名 DNS。

典型调用：

- `frontend -> travel-gateway`
- `travel-gateway -> travel-trip`
- `travel-gateway -> agent-runtime`
- `travel-gateway -> travel-mcp`
- 未来 `travel-gateway -> travel-auth`
- 未来 `travel-gateway -> travel-agent`
- 未来 `travel-agent -> agent-runtime`

`agent-runtime` 应始终通过明确 HTTP 契约暴露能力，避免其他服务耦合到 Python 内部实现。

## MCP 风格工具调用

`agent-runtime` 使用 MCP 风格 JSON-RPC 调用旅行工具，例如：

- 景点搜索
- 天气查询
- 路线规划
- 酒店搜索
- 餐食推荐
- 预算估算

工具服务必须返回经过 schema 校验的结构化内容。`agent-runtime` 应把所有工具响应视为不可信输入；工具失败或返回无效数据时，使用 mock/fallback 数据保持公共 API 稳定。

## 事件命名

事件名使用点分隔：

```text
trip.plan.created
trip.plan.updated
trip.plan.deleted
trip.plan.export.requested
agent.conversation.updated
agent.conversation.deleted
agent.conversation.summary.created
agent.conversation.summarize.requested
user.profile.updated
```

事件 payload 字段使用 camelCase：

```json
{
  "eventId": "uuid",
  "eventType": "trip.plan.created",
  "occurredAt": "2026-07-09T10:00:00Z",
  "userId": "anon:example",
  "tripPlanId": "uuid",
  "conversationId": "uuid"
}
```

## 可靠性规则

- 消费者必须幂等。
- 每个事件必须包含 `eventId`、`eventType`、`occurredAt` 和归属用户 `userId`。
- 生产者应发布 ID，而不是完整数据库记录。
- 消费者需要从自己的数据库或归属服务重新读取最新状态。
- 失败任务应退避重试，并最终进入死信队列。
- 日志必须包含 request id 或 event id，方便追踪。

## 安全规则

- 不要把 API key、JWT、密码或供应商密钥放进事件。
- RabbitMQ 凭据本地来自 `.env`，VPS 来自 Kubernetes Secret。
- 管理后台端口 `15672` 只用于本地开发，不应在 VPS 公网暴露。
- 真正用户体系稳定后，服务间调用需要传递内部用户上下文头。

## 当前实现状态

- Docker Compose 已包含 RabbitMQ。
- K3s 默认通过 `deploy/k8s/addons/rabbitmq.yaml` 部署 RabbitMQ。
- `agent-runtime` 支持 `MESSAGE_QUEUE_URL` 和 `RPC_TIMEOUT_SECONDS`。
- 配置 `MESSAGE_QUEUE_URL` 后，`agent-runtime` 会向 `travel.events` topic exchange 发布领域事件。
- `python -m app.worker_main` 是 RabbitMQ consumer 入口。
- `agent-runtime-worker` 会处理异步会话摘要任务，并更新任务状态。
- Docker Compose 通过 `worker` profile 启动 `agent-runtime-worker`。
- K3s 默认通过 Kustomize 部署 `agent-runtime-worker`。
