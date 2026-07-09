# Agent Runtime

FastAPI service for the AI travel planning runtime.

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

The runtime uses mock responses by default. To connect an OpenAI-compatible chat completion API, create `.env` from `.env.example` and set:

```bash
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=your-model-name
```

If the model is not configured or the provider call fails, the service falls back to deterministic mock responses so local development and deployment checks still work.

Optional integration placeholders:

```bash
MESSAGE_QUEUE_URL=amqp://user:password@rabbitmq:5672/
RPC_TIMEOUT_SECONDS=5
```

`MESSAGE_QUEUE_URL` is reserved for later RabbitMQ producers/consumers. `RPC_TIMEOUT_SECONDS` is the shared timeout budget for future runtime-to-service calls.

## Observability

Every HTTP response includes:

- `X-Request-ID`: generated automatically, or propagated from the incoming `X-Request-ID` header.
- `X-Process-Time-Ms`: backend request processing time in milliseconds.

Request logs are written to stdout for container collection. Set `LOG_LEVEL=DEBUG`, `INFO`, `WARNING`, or `ERROR` to control runtime verbosity.

## Persistence

The runtime uses in-memory conversation storage by default. Set `DATABASE_URL` to enable SQL-backed storage:

```bash
DATABASE_URL=postgresql://travel_agent:password@localhost:5432/travel_agent_cloud
```

When database storage is enabled, the service creates the current tables on startup:

- `conversations`
- `messages`
- `trip_plans`

Conversation APIs are scoped by `X-User-Id`. This is an anonymous-user boundary for the current milestone, not a replacement for real authentication.

## API

Create a structured trip plan:

```bash
curl -X POST http://localhost:8000/api/v1/trip-plan \
  -H "Content-Type: application/json" \
  -d '{"destination":"Chengdu","days":3,"budget":"moderate","interests":"local food, city walk"}'
```

The response includes `savedTripPlanId`, which can be used immediately with the saved trip plan APIs.
Pass `conversationId` in the request body to attach the generated trip plan to an existing planning conversation.

Send a chat message:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"I want a relaxed 3-day Chengdu food trip","mode":"TRIP_PLANNING"}'
```

Get the current user profile:

```bash
curl http://localhost:8000/api/v1/me/profile \
  -H "X-User-Id: smoke-test-user"
```

Update traveler preferences:

```bash
curl -X PATCH http://localhost:8000/api/v1/me/profile \
  -H "Content-Type: application/json" \
  -H "X-User-Id: smoke-test-user" \
  -d '{"displayName":"Smoke Test Traveler","homeCity":"Beijing","preferredBudget":"moderate","travelStyle":"relaxed city walks","interests":["local food","museums"]}'
```

List conversations:

```bash
curl "http://localhost:8000/api/v1/conversations?page=1&pageSize=20"
```

Search conversations:

```bash
curl "http://localhost:8000/api/v1/conversations?page=1&pageSize=20&query=Chengdu"
```

Get a conversation:

```bash
curl http://localhost:8000/api/v1/conversations/{conversationId}
```

Rename a conversation:

```bash
curl -X PATCH http://localhost:8000/api/v1/conversations/{conversationId} \
  -H "Content-Type: application/json" \
  -d '{"title":"Chengdu planning thread"}'
```

Delete a conversation:

```bash
curl -X DELETE http://localhost:8000/api/v1/conversations/{conversationId}
```

List saved trip plans:

```bash
curl "http://localhost:8000/api/v1/trip-plans?page=1&pageSize=20"
```

Filter saved trip plans:

```bash
curl "http://localhost:8000/api/v1/trip-plans?page=1&pageSize=20&favoriteOnly=true&query=Chengdu"
```

Get a saved trip plan:

```bash
curl http://localhost:8000/api/v1/trip-plans/{tripPlanId}
```

Favorite or unfavorite a saved trip plan:

```bash
curl -X PATCH http://localhost:8000/api/v1/trip-plans/{tripPlanId} \
  -H "Content-Type: application/json" \
  -d '{"favorite":true}'
```

Delete a saved trip plan:

```bash
curl -X DELETE http://localhost:8000/api/v1/trip-plans/{tripPlanId}
```

Export a saved trip plan as Markdown:

```bash
curl http://localhost:8000/api/v1/trip-plans/{tripPlanId}/export
```

If `DATABASE_URL` is configured, conversations and trip plans are persisted to PostgreSQL. Without `DATABASE_URL`, the service uses in-memory storage for local development.
