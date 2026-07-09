# travel-gateway

Spring Cloud Gateway service. It will provide the public API entrypoint for frontend, auth, trip, and agent services.

Planned communication:

- Public REST entrypoint for the frontend.
- Routes requests to `travel-auth`, `travel-trip`, and `travel-agent`.
- Uses Spring Cloud Gateway filters for auth context propagation, request IDs, and rate limiting.
- Does not publish RabbitMQ events directly unless the event is about gateway-level audit or abuse detection.
