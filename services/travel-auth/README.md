# travel-auth

Authentication service. Planned responsibilities include login, JWT issuing, Sa-Token integration, and Redis-backed sessions.

Planned communication:

- Provides REST APIs consumed through `travel-gateway`.
- Exposes internal user/session validation APIs for Java services through Spring Cloud OpenFeign.
- Stores sessions and login state in Redis.
- Publishes user lifecycle events to RabbitMQ, such as `user.profile.updated`, after real account binding is implemented.
