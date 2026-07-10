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
AUTH_SECRET_KEY=change-me-to-a-random-secret
AUTH_TOKEN_TTL_SECONDS=604800
AUTH_COOKIE_SECURE=false
AUTH_RATE_LIMIT_MAX_ATTEMPTS=20
AUTH_RATE_LIMIT_WINDOW_SECONDS=900
```

If the model is not configured or the provider call fails, the service falls back to deterministic mock responses so local development and deployment checks still work.
`AUTH_SECRET_KEY` signs login cookies. Use a stable random value in production; changing it logs out existing users.
Auth register/login endpoints are rate-limited per client and email by `AUTH_RATE_LIMIT_MAX_ATTEMPTS` within `AUTH_RATE_LIMIT_WINDOW_SECONDS`.

When running through Docker Compose, create a local `docker-compose.override.yml` from the project root if you want containers to read this `.env` file:

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
docker compose --profile worker up --build
```

The override file is intentionally ignored by Git because it can point containers at local secret files.

Optional integration placeholders:

```bash
MESSAGE_QUEUE_URL=amqp://user:password@rabbitmq:5672/
RPC_TIMEOUT_SECONDS=5
WORKER_RECONNECT_INITIAL_SECONDS=2
WORKER_RECONNECT_MAX_SECONDS=30
```

`MESSAGE_QUEUE_URL` enables RabbitMQ event publishing. `RPC_TIMEOUT_SECONDS` is the shared timeout budget for queue and future runtime-to-service calls.
The worker reconnect settings control exponential backoff when PostgreSQL or RabbitMQ is not ready, or when the queue connection drops.

When `MESSAGE_QUEUE_URL` is configured, the runtime publishes small domain events to the durable RabbitMQ topic exchange `travel.events`. Queue failures are logged but do not fail the user request.

Current events:

- `trip.plan.created`
- `trip.plan.updated`
- `trip.plan.deleted`
- `user.profile.updated`
- `agent.conversation.updated`
- `agent.conversation.deleted`
- `agent.conversation.summarize.requested`
- `agent.conversation.summary.created`
- `user.data.imported`

Conversation summaries are generated through `app.workers.conversation_summarizer.ConversationSummarizerWorker`. The HTTP API can call this worker synchronously, or queue an asynchronous job when RabbitMQ is configured.

RabbitMQ consumer support is available through `python -m app.worker_main`, but it is not started by the normal API process. The consumer listens to `agent.conversation.summarize.requested`, skips `manual_api` events that the HTTP API already handled, and processes asynchronous summary jobs. The API stores job status in `conversation_summary_jobs`; the consumer moves jobs through `QUEUED`, `RUNNING`, `SUCCEEDED`, and `FAILED`. Failed or invalid messages are rejected into the consumer dead-letter queue.
If RabbitMQ or PostgreSQL is unavailable at startup, the worker keeps retrying with exponential backoff instead of exiting.

Run the worker locally only when both RabbitMQ and PostgreSQL are configured:

```bash
python -m app.worker_main
```

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
- `conversation_summaries`
- `conversation_summary_jobs`
- `trip_plans`
- `users`
- `user_profiles`

Conversation APIs are scoped by the signed-in user when a valid session cookie or Bearer token is present. Without a valid session, the runtime keeps the existing anonymous `X-User-Id` fallback for local development.

## API

Create an account:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"email":"you@example.com","password":"ChangeMe123!","displayName":"Traveler"}'
```

Sign in:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"email":"you@example.com","password":"ChangeMe123!"}'
```

Get the current signed-in user:

```bash
curl http://localhost:8000/api/v1/auth/me \
  -b cookies.txt
```

Update account display name:

```bash
curl -X PATCH http://localhost:8000/api/v1/auth/me \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"displayName":"Traveler"}'
```

Change password:

```bash
curl -X PATCH http://localhost:8000/api/v1/auth/password \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"currentPassword":"ChangeMe123!","newPassword":"NewChangeMe123!"}'
```

Export signed-in user data:

```bash
curl http://localhost:8000/api/v1/me/export \
  -b cookies.txt
```

Import a previously exported data file into the current signed-in account:

```bash
curl -X POST http://localhost:8000/api/v1/me/import \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  --data-binary @travel-agent-data.json
```

Delete the current account and owned app data:

```bash
curl -X DELETE http://localhost:8000/api/v1/auth/me \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"currentPassword":"ChangeMe123!","confirmation":"DELETE"}'
```

Sign out:

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -b cookies.txt
```

Authenticated requests are scoped by the signed-in user's httpOnly cookie. If no valid login cookie or Bearer token is present, the runtime keeps the existing anonymous `X-User-Id` fallback for local development.
Application user passwords are stored only as PBKDF2-SHA256 hashes in `users.password_hash`. Service credentials such as PostgreSQL and RabbitMQ are managed separately through Docker Compose environment variables locally and Kubernetes Secrets on VPS. User data export returns account metadata, traveler profile, conversations, summaries, and saved trip plans, but never returns password hashes or session tokens. User data import accepts that export format, ignores exported account identity fields, and restores data into the currently signed-in account. Account deletion requires the current password and confirmation text, then deletes only that user's account, profile, conversations, summaries, summary jobs, and saved trip plans.

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

Generate or refresh a conversation summary:

```bash
curl -X POST http://localhost:8000/api/v1/conversations/{conversationId}/summary
```

Queue an asynchronous conversation summary job:

```bash
curl -X POST http://localhost:8000/api/v1/conversations/{conversationId}/summary-jobs
```

This endpoint returns `202 Accepted` only when `MESSAGE_QUEUE_URL` is configured and the event was published to RabbitMQ. Without RabbitMQ, use the synchronous `/summary` endpoint.

Get the latest asynchronous summary job status:

```bash
curl http://localhost:8000/api/v1/conversations/{conversationId}/summary-jobs/latest
```

Get the latest conversation summary:

```bash
curl http://localhost:8000/api/v1/conversations/{conversationId}/summary
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
