# travel-auth

Planned Python/FastAPI authentication service.

This is not a running service yet. Authentication currently lives in `agent-runtime`.

Future responsibilities:

- Register, login, logout, email verification, password reset, and OAuth callbacks.
- JWT/session issuing and validation.
- Redis-backed rate limiting and session state where needed.
- User profile and account lifecycle events through RabbitMQ.

Migration rule:

- Keep the current `agent-runtime` API contract stable.
- Move endpoints behind `travel-gateway` route by route.
- Do not duplicate password/session logic in two running services at the same time.
