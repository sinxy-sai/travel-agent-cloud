# Kubernetes-native Python Microservices Roadmap

The project is moving toward Kubernetes-native Python/FastAPI microservices.
This does not require Spring Boot, Spring Cloud, or gRPC as the default stack.

## Current Running Boundary

```text
frontend
  -> travel-gateway
      -> agent-runtime
      -> travel-mcp

agent-runtime
  -> PostgreSQL
  -> Redis
  -> RabbitMQ
  -> MinIO
  -> travel-mcp
```

## Services

- `travel-gateway`: thin FastAPI reverse proxy and public API entrypoint.
- `agent-runtime`: current auth, trip, chat, export, and agent orchestration API.
- `travel-mcp`: travel tool service, currently AMap-backed with fallback behavior.
- `agent-runtime-worker`: background worker consuming RabbitMQ jobs.
- `travel-auth`: planned FastAPI service for auth once auth boundaries are stable.
- `travel-trip`: planned FastAPI service for trip persistence and export ownership.
- `travel-agent`: planned FastAPI facade for quota, audit, and agent request policy.

## Kubernetes Responsibilities

- Service discovery uses Kubernetes service DNS, for example `http://agent-runtime:8000`.
- Public routing uses Kubernetes Ingress to `travel-gateway`.
- Runtime config uses environment variables and Kubernetes Secrets.
- Async work uses RabbitMQ, not direct in-process calls.
- Shared state uses PostgreSQL, Redis, and MinIO.

## Migration Order

1. Put `travel-gateway` in front of the existing API.
2. Run `travel-mcp` as a first real tool microservice.
3. Keep `agent-runtime` stable while agent planning behavior matures.
4. Split `travel-auth` only after auth flows are stable.
5. Split `travel-trip` after trip/export schemas settle.
6. Add `travel-agent` when quota/audit/policy logic no longer belongs in `agent-runtime`.

## Non-goals For Now

- No Spring Cloud migration.
- No service mesh requirement.
- No gRPC requirement until there is a concrete streaming or low-latency internal API need.
- No early database-per-service split before data ownership is clear.
