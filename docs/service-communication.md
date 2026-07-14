# Service Communication Plan

This document defines the service-to-service communication choices for Travel Agent Cloud.

## Selected Stack

| Need | Choice | Scope |
| --- | --- | --- |
| Public API | REST over HTTP | Frontend to Gateway |
| Java internal RPC | Spring Cloud OpenFeign | Gateway, auth, trip, agent services |
| Python Agent Runtime calls | REST over HTTP | Java `travel-agent` to FastAPI `agent-runtime` |
| Travel tool calls | MCP-style JSON-RPC over HTTP | `agent-runtime` to `travel-mcp` / future FastMCP servers |
| Async events and jobs | RabbitMQ | Cross-service events and background jobs |
| Future streaming RPC | gRPC | Reserved, not part of the current implementation |

## Why RabbitMQ

RabbitMQ fits the current product better than Kafka because the first async workloads are business events and background jobs, not high-throughput analytics streams.

Use RabbitMQ for:

- Conversation summarization jobs.
- Large export generation.
- Notification or audit events.
- Retryable tool execution jobs.
- Decoupling profile/trip events from downstream consumers.

Do not use RabbitMQ for:

- Synchronous user-facing reads.
- Replacing PostgreSQL as the source of truth.
- Sending secrets or large payloads.

## Why OpenFeign

OpenFeign fits the Java microservice plan because the project already targets Spring Boot and Spring Cloud.

Use OpenFeign for:

- `travel-gateway -> travel-auth`
- `travel-gateway -> travel-trip`
- `travel-gateway -> travel-agent`
- `travel-agent -> travel-trip` when the agent service needs persisted trip metadata

Use plain REST clients for:

- `travel-agent -> agent-runtime`
- `agent-runtime -> travel-mcp` while the local tool server is an MCP-compatible HTTP stub

The Python Agent Runtime should stay behind an explicit HTTP contract. That keeps the AI runtime replaceable and avoids coupling Java services directly to Python internals.

Use MCP-style JSON-RPC for:

- `agent-runtime -> travel-mcp` travel tools such as attraction search, weather, route planning, hotels, meals, and budget estimates.

The tool server must return schema-validated structured content. Agent Runtime treats all tool responses as untrusted and falls back to mock values when a tool call fails or returns invalid data.

## Event Naming

Use dot-separated event names:

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

Event payloads use camelCase fields:

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

## Reliability Rules

- Consumers must be idempotent.
- Each event must include `eventId`, `eventType`, `occurredAt`, and the owning `userId`.
- Producers should publish IDs, not full database records.
- Consumers must fetch fresh state from their own database or the owning service.
- Failed jobs should retry with backoff and eventually move to a dead-letter queue.
- Logs must include request ID or event ID for traceability.

## Security Rules

- Do not put API keys, JWTs, passwords, or provider secrets in events.
- RabbitMQ credentials come from `.env` locally and Kubernetes Secret on VPS.
- Management UI port `15672` is for local development only; do not expose it publicly on VPS.
- Service-to-service calls must preserve user identity through an internal user context header once real auth is implemented.

## Current Implementation Status

- Docker Compose includes RabbitMQ for local development.
- K3s deploys RabbitMQ through `deploy/k8s/addons/rabbitmq.yaml` as part of the default Kustomize deployment.
- Agent Runtime exposes `MESSAGE_QUEUE_URL` and `RPC_TIMEOUT_SECONDS` settings.
- Agent Runtime publishes domain events to the `travel.events` topic exchange when `MESSAGE_QUEUE_URL` is configured.
- Agent Runtime has a reusable synchronous conversation summarizer worker at `app/workers/conversation_summarizer.py`.
- `POST /api/v1/conversations/{conversationId}/summary` now emits `agent.conversation.summarize.requested` before generating and persisting the summary.
- `POST /api/v1/conversations/{conversationId}/summary-jobs` creates a persisted `conversation_summary_jobs` row, publishes `agent.conversation.summarize.requested` with `summaryJobId`, and returns `202 Accepted` only after RabbitMQ accepts the event.
- `GET /api/v1/conversations/{conversationId}/summary-jobs/latest` returns the newest persisted job status for frontend polling.
- A RabbitMQ consumer entrypoint exists at `python -m app.worker_main`.
- The consumer updates job status from `QUEUED` to `RUNNING`, then `SUCCEEDED` or `FAILED`.
- Docker Compose exposes the consumer as the `agent-runtime-worker` service behind the `worker` profile.
- Docker Compose exposes the local `travel-mcp` tool server behind the `tools` profile for FastMCP/Amap integration development.
- K3s deploys the consumer through `deploy/k8s/addons/agent-runtime-worker.yaml` as part of the default Kustomize deployment.
