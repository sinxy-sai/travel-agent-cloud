# travel-trip

Planned Python/FastAPI trip management service.

This is not a running service yet. Trip persistence and export APIs currently live in `agent-runtime`.

Future responsibilities:

- Trip plan CRUD, history, version restore, favorites, and search.
- Export metadata and generated file ownership.
- PostgreSQL as authoritative storage.
- MinIO for generated markdown, image, and PDF export artifacts.
- RabbitMQ events such as `trip.plan.created`, `trip.plan.updated`, and `trip.plan.export.requested`.

Migration rule:

- First keep `travel-gateway` as the public entrypoint.
- Then move trip endpoints out of `agent-runtime` when their data model is stable.
- Agent planning should call this service only through internal HTTP APIs after the split.
