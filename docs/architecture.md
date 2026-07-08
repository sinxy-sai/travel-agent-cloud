# Architecture

Travel Agent Cloud starts with a small deployable core:

```text
frontend -> agent-runtime
```

Current Agent Runtime contract:

```text
POST /api/v1/trip-plan
POST /api/v1/chat
GET  /api/v1/conversations
GET  /api/v1/conversations/{conversationId}
```

The target microservice architecture is:

```text
frontend
  -> travel-gateway
  -> travel-auth
  -> travel-agent
  -> agent-runtime
  -> travel-trip
```

Supporting infrastructure:

```text
MySQL, Redis, RabbitMQ, MinIO, vector database, K3s, Ingress, GitHub Actions
```

API conventions are documented in [api-guidelines.md](api-guidelines.md).
