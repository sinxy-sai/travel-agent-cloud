# travel-agent

Planned Python/FastAPI agent facade service.

This is not a running service yet. LangGraph/LangChain execution currently lives in `agent-runtime`.

Future responsibilities:

- User-facing agent request facade behind `travel-gateway`.
- Quota, audit, ownership, and request policy checks before agent execution.
- Calls to `agent-runtime` for LangGraph/LangChain execution.
- Calls to `travel-trip` for persisted trip metadata after the trip service split.
- RabbitMQ jobs for non-blocking agent tasks.

Migration rule:

- Keep `agent-runtime` as the execution engine until planning behavior is stable.
- Add this facade only when quota/audit/service ownership logic becomes large enough to justify a separate deployable service.
