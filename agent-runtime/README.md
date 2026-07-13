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
Set `REDIS_URL` to make auth rate limiting shared across runtime replicas. If it is empty, the runtime uses the existing in-process limiter:

```bash
REDIS_URL=redis://localhost:6379/0
REDIS_KEY_PREFIX=travel-agent-cloud
```

The health response includes `redisRateLimitEnabled` so deployments can confirm whether Redis-backed limiting is active.

Configure MinIO-compatible object storage to archive authenticated user data exports:

```bash
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=travel_agent
MINIO_SECRET_KEY=change-me
MINIO_BUCKET=travel-agent-exports
MINIO_SECURE=false
```

The health response includes `objectStorageEnabled`. Export downloads are proxied through the authenticated API, so MinIO does not need a public endpoint.

Email verification and password reset use `EMAIL_PROVIDER=mock` by default. Mock mode returns `devToken` and `actionUrl` in API responses for local testing. To send real email, switch to SMTP:

```bash
EMAIL_PROVIDER=smtp
EMAIL_FROM=your-address@qq.com
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USERNAME=your-address@qq.com
SMTP_PASSWORD=your-qq-smtp-authorization-code
SMTP_USE_SSL=true
SMTP_STARTTLS=false
PUBLIC_APP_URL=http://localhost:5173
EMAIL_VERIFICATION_TOKEN_TTL_SECONDS=86400
PASSWORD_RESET_TOKEN_TTL_SECONDS=1800
```

Gmail SMTP uses an app password:

```bash
EMAIL_PROVIDER=smtp
EMAIL_FROM=your-address@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=your-google-app-password
SMTP_USE_SSL=false
SMTP_STARTTLS=true
PUBLIC_APP_URL=https://your-domain.example
```

Email verification and password reset tokens are generated as random one-time tokens. Only SHA-256 token hashes are stored in `auth_tokens`; the plaintext token is shown only in mock mode or inside the email link.
Account data export and import endpoints require a verified email address. Unverified accounts can still sign in, update profile details, plan trips, chat, request verification emails, and reset passwords.

GitHub OAuth can be enabled with a GitHub OAuth App. Set the OAuth App callback URL to the backend callback endpoint, for example `http://localhost:8000/api/v1/auth/oauth/github/callback` during local development:

```bash
GITHUB_OAUTH_CLIENT_ID=your-github-oauth-client-id
GITHUB_OAUTH_CLIENT_SECRET=your-github-oauth-client-secret
GITHUB_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/oauth/github/callback
OAUTH_HTTP_TIMEOUT_SECONDS=10
```

GitHub OAuth uses a signed `state` value plus an httpOnly state cookie. The runtime requests `read:user user:email` and only creates or links accounts when GitHub returns a verified primary email. The app never receives or stores the GitHub account password. OAuth-created accounts start without a project password; users can use the password setup/reset email flow to add one before password-protected actions such as deleting the account or unlinking the only OAuth identity.

When running through Docker Compose, create a local `docker-compose.override.yml` from the project root if you want containers to read this `.env` file:

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
docker compose --profile worker up --build
```

The override file is intentionally ignored by Git because it can point containers at local secret files.

Optional integration placeholders:

```bash
MESSAGE_QUEUE_URL=amqp://user:password@rabbitmq:5672/
REDIS_URL=redis://redis:6379/0
REDIS_KEY_PREFIX=travel-agent-cloud
RPC_TIMEOUT_SECONDS=5
AGENT_ENGINE=basic
TRAVEL_TOOL_PROVIDER=mock
WORKER_RECONNECT_INITIAL_SECONDS=2
WORKER_RECONNECT_MAX_SECONDS=30
```

`MESSAGE_QUEUE_URL` enables RabbitMQ event publishing. `REDIS_URL` enables distributed auth rate limiting. `RPC_TIMEOUT_SECONDS` is the shared timeout budget for queue and future runtime-to-service calls. `AGENT_ENGINE=basic` selects the current built-in itinerary/chat engine. `AGENT_ENGINE=langgraph` runs the dependency-free graph-shaped workflow skeleton and reports `langgraph:workflow-skeleton` in `/health`; it defines chat, trip draft, enrichment, validation, and day-regeneration nodes before the real LangGraph dependency is introduced. `/health` also returns `agentEngineCapabilities` with the supported user-facing abilities and workflow node names for debugging. `GET /api/v1/agent/status` returns the same capabilities plus a privacy-safe `lastRunTrace` that records only operation and node names, not user prompts. Later LangGraph or DeepAgent engines should implement the same engine interface without changing the public chat and trip plan APIs. `TRAVEL_TOOL_PROVIDER=mock` enables the local deterministic POI, hotel, meal, weather, and budget provider. Later FastMCP-backed providers should implement the same travel tool interface without changing the public trip plan API.
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
- `auth.oauth_logged_in`
- `auth.identity_linked`
- `auth.identity_unlinked`
- `user.data_exported`
- `user.data.imported`
- `user.anonymous_data.imported`

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
- `auth_tokens`
- `auth_identities`
- `users`
- `user_profiles`
- `user_security_events`

Conversation, profile, summary, and trip plan APIs are scoped by the signed-in user when a valid session cookie or Bearer token is present. Without a valid session, the runtime keeps the existing anonymous `X-User-Id` fallback for local development. If both are present, the signed-in account always wins.

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

Request a new verification email for the signed-in account:

```bash
curl -X POST http://localhost:8000/api/v1/auth/email-verification/request \
  -b cookies.txt
```

Confirm email verification with the token from the email link:

```bash
curl -X POST http://localhost:8000/api/v1/auth/email-verification/confirm \
  -H "Content-Type: application/json" \
  -d '{"token":"token-from-email"}'
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

Request password reset by email. The response is intentionally generic so callers cannot discover whether an email is registered:

```bash
curl -X POST http://localhost:8000/api/v1/auth/password-reset/request \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com"}'
```

Confirm password reset with the token from the email link:

```bash
curl -X POST http://localhost:8000/api/v1/auth/password-reset/confirm \
  -H "Content-Type: application/json" \
  -d '{"token":"token-from-email","newPassword":"NewChangeMe123!"}'
```

List active and revoked login sessions:

```bash
curl http://localhost:8000/api/v1/auth/sessions \
  -b cookies.txt
```

Revoke one session by id:

```bash
curl -X DELETE http://localhost:8000/api/v1/auth/sessions/session-id \
  -b cookies.txt
```

Sign out every other active session while keeping the current session:

```bash
curl -X POST http://localhost:8000/api/v1/auth/sessions/revoke-all \
  -b cookies.txt
```

List recent account security activity:

```bash
curl "http://localhost:8000/api/v1/auth/security-events?page=1&pageSize=10" \
  -b cookies.txt
```

Export signed-in user data:

```bash
curl http://localhost:8000/api/v1/me/export \
  -b cookies.txt
```

Archive the same export JSON in MinIO, then download it through the authenticated API:

```bash
curl -X POST http://localhost:8000/api/v1/me/export-files \
  -b cookies.txt

curl http://localhost:8000/api/v1/me/export-files/export-id \
  -b cookies.txt \
  -o travel-agent-data.json
```

Import a previously exported data file into the current signed-in account:

```bash
curl -X POST http://localhost:8000/api/v1/me/import \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  --data-binary @travel-agent-data.json
```

Check whether the current browser has anonymous data that can be copied into the signed-in account:

```bash
curl http://localhost:8000/api/v1/me/anonymous-data/summary \
  -H "X-User-Id: anon:local-browser-id" \
  -b cookies.txt
```

Import the current browser's anonymous data into the signed-in account. The source anonymous id is read from `X-User-Id`; conversations and trip plans are copied with new ids so the anonymous records remain untouched:

```bash
curl -X POST http://localhost:8000/api/v1/me/anonymous-data/import \
  -H "X-User-Id: anon:local-browser-id" \
  -b cookies.txt
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
Application user passwords are stored only as PBKDF2-SHA256 hashes in `users.password_hash`. JWTs include a `sid` claim for new logins; the runtime checks `auth_sessions` so logout and explicit revocation can invalidate a session before the token expires. Existing tokens without `sid` remain accepted until their natural expiry for deployment compatibility. Session records store a hashed client identifier and sanitized User-Agent, never raw JWTs. Service credentials such as PostgreSQL, RabbitMQ, MinIO, and SMTP are managed separately through Docker Compose environment variables locally and Kubernetes Secrets on VPS. User data export returns account metadata, traveler profile, conversations, summaries, and saved trip plans, but never returns password hashes, session tokens, or email action tokens. MinIO export objects are stored below a per-user prefix and are only downloaded through an authenticated ownership-scoped endpoint. User data import accepts the export format, ignores exported account identity fields, and restores data into the currently signed-in account. Anonymous data import copies the current browser's anonymous workspace into the signed-in account and records `user.anonymous_data_imported`; the frontend checks `/anonymous-data/summary` after login and prompts the user before importing. Account security activity records successful account events and stores only a hashed client identifier plus non-sensitive details. Password reset completion writes `auth.password_reset_completed` and revokes older sessions; account deletion requires the current password and confirmation text, then deletes only that user's account, object-storage exports, profile, conversations, summaries, summary jobs, sessions, security events, and saved trip plans.

Create a structured trip plan:

```bash
curl -X POST http://localhost:8000/api/v1/trip-plan \
  -H "Content-Type: application/json" \
  -d '{
    "destination": "Chengdu",
    "days": 3,
    "budget": "moderate",
    "interests": "local food, city walk",
    "startDate": "2026-08-01",
    "endDate": "2026-08-03",
    "transportation": "walking and metro",
    "accommodation": "comfortable hotel",
    "preferences": ["local food", "city walk"],
    "freeTextInput": "Keep mornings relaxed and avoid packed schedules."
  }'
```

The response includes `savedTripPlanId`, which can be used immediately with the saved trip plan APIs.
The trip plan contract is additive and still accepts the original `destination`, `days`, `budget`, and `interests` fields. New responses may also include `weatherInfo`, `budget`, per-day `hotel`, `attractions`, and `meals`; these are currently mock/LLM-enriched fields and are reserved for later LangChain/LangGraph/FastMCP tool orchestration.
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

Edit a saved trip plan using its current `version`:

```bash
curl -X PATCH http://localhost:8000/api/v1/trip-plans/{tripPlanId} \
  -H "Content-Type: application/json" \
  -d '{
    "plan": {
      "title": "Edited Chengdu itinerary",
      "summary": "A relaxed food-focused city break.",
      "days": [
        {
          "day": 1,
          "theme": "Historic center",
          "morning": "Visit Wenshu Monastery",
          "afternoon": "Walk through the old streets",
          "evening": "Try a local hotpot restaurant"
        }
      ],
      "tips": ["Reserve popular restaurants in advance"]
    },
    "expectedVersion": 1
  }'
```

Content edits increment `version`. A request using an outdated `expectedVersion` returns HTTP `409` with code `TRIP_PLAN_VERSION_CONFLICT`; reload the saved plan before retrying. Favorite-only updates do not require `expectedVersion`.

Regenerate one day of a saved trip plan. Only the target day is replaced; the rest of the itinerary is preserved:

```bash
curl -X POST http://localhost:8000/api/v1/trip-plans/{tripPlanId}/days/2/regenerate \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Make this day slower and add a local food stop",
    "expectedVersion": 2
  }'
```

Day regeneration also increments `version` and returns HTTP `409` with code `TRIP_PLAN_VERSION_CONFLICT` when `expectedVersion` is stale.

Delete a saved trip plan:

```bash
curl -X DELETE http://localhost:8000/api/v1/trip-plans/{tripPlanId}
```

Export a saved trip plan as Markdown:

```bash
curl http://localhost:8000/api/v1/trip-plans/{tripPlanId}/export
```

If `DATABASE_URL` is configured, conversations and trip plans are persisted to PostgreSQL. Without `DATABASE_URL`, the service uses in-memory storage for local development.
