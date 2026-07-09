# travel-agent

Java facade service for AI planning requests. It will call `agent-runtime` and enforce user, quota, and audit policies.

Planned communication:

- Provides agent-facing REST APIs through `travel-gateway`.
- Calls `travel-trip` with Spring Cloud OpenFeign when it needs persisted trip metadata.
- Calls Python `agent-runtime` through REST because FastAPI is the runtime boundary.
- Publishes RabbitMQ jobs such as `agent.conversation.summarize.requested` for non-blocking background work.
- Enforces quota, audit, and user ownership before forwarding requests to the AI runtime.
