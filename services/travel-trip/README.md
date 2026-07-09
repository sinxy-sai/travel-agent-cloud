# travel-trip

Trip management service. Planned responsibilities include itinerary persistence, favorites, exported files, and user trip history.

Planned communication:

- Provides trip CRUD APIs through `travel-gateway`.
- Exposes internal trip metadata APIs to `travel-agent` through Spring Cloud OpenFeign.
- Owns trip persistence once trip management is moved out of `agent-runtime`.
- Publishes RabbitMQ events such as `trip.plan.created`, `trip.plan.deleted`, and `trip.plan.export.requested`.
- Uses MinIO for generated files and PostgreSQL for authoritative trip data.
