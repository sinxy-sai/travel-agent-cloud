# Architecture

Travel Agent Cloud starts with a small deployable core:

```text
frontend -> agent-runtime
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

