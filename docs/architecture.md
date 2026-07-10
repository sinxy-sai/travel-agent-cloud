# Architecture

Travel Agent Cloud starts with a small deployable core:

```text
frontend -> agent-runtime -> PostgreSQL
```

Current Agent Runtime contract:

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
DELETE /api/v1/conversations/{conversationId}
GET    /api/v1/trip-plans
GET    /api/v1/trip-plans/{tripPlanId}
PATCH  /api/v1/trip-plans/{tripPlanId}
DELETE /api/v1/trip-plans/{tripPlanId}
GET    /api/v1/trip-plans/{tripPlanId}/export
```

Target microservice architecture:

```text
frontend
  -> travel-gateway
      -> travel-auth
      -> travel-trip
      -> travel-agent
          -> agent-runtime

travel-auth/travel-trip/travel-agent
  -> PostgreSQL / Redis / MinIO / pgvector
  -> RabbitMQ
```

## Service Communication

- Public frontend traffic enters through `travel-gateway`.
- External HTTP APIs follow REST conventions under `/api/v1`.
- Java microservices call each other with Spring Cloud OpenFeign.
- Gateway-to-Agent Runtime and Java-to-Agent Runtime calls use REST first because the Python runtime already exposes FastAPI contracts.
- gRPC is reserved for future low-latency or bidirectional streaming use cases, such as live agent trace streaming or tool execution streams.

## Message Queue

RabbitMQ is the default message queue for the project.

Initial event and job candidates:

- `trip.plan.created`: created after a trip plan is saved.
- `trip.plan.updated`: created after a trip plan metadata update, such as favorite changes.
- `trip.plan.deleted`: created after a saved trip plan is deleted.
- `trip.plan.export.requested`: queued when exporting large files or generating attachments.
- `agent.conversation.updated`: created after conversation metadata changes.
- `agent.conversation.deleted`: created after a conversation is deleted.
- `agent.conversation.summary.created`: created after a conversation summary is generated or refreshed.
- `agent.conversation.summarize.requested`: queued to summarize long conversations.
- `user.profile.updated`: emitted when user preferences change.

Queue rules:

- Producers publish small JSON events with stable camelCase field names.
- Consumers must be idempotent because queue delivery can be retried.
- Business data remains in PostgreSQL; queue messages carry IDs and minimal context.
- Secrets are injected through Kubernetes Secret or local `.env`, never committed.

Supporting infrastructure:

```text
PostgreSQL, Redis, RabbitMQ, MinIO, pgvector, K3s, Ingress, GitHub Actions
```

API conventions are documented in [api-guidelines.md](api-guidelines.md). Service communication details are documented in [service-communication.md](service-communication.md).
