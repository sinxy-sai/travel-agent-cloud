# Agent Runtime

`agent-runtime` 是 Travel Agent Cloud 当前的核心 FastAPI 服务，承载 AI 旅行规划运行时、认证、行程、会话、导出和后台任务入口。

## 本地运行

```powershell
cd agent-runtime
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```powershell
curl http://localhost:8000/health
```

默认情况下，未配置模型或供应商调用失败时，服务会使用确定性的 mock/fallback 响应，保证本地开发和部署检查可继续运行。

## LLM 配置

从 `.env.example` 创建 `.env`，然后配置 OpenAI-compatible API：

```text
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=your-model-name
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=4096
LLM_TIMEOUT_SECONDS=60
```

## 认证配置

```text
AUTH_SECRET_KEY=change-me-to-a-random-secret
AUTH_TOKEN_TTL_SECONDS=604800
AUTH_COOKIE_SECURE=false
AUTH_RATE_LIMIT_MAX_ATTEMPTS=20
AUTH_RATE_LIMIT_WINDOW_SECONDS=900
```

`AUTH_SECRET_KEY` 用于签名登录 cookie。生产环境必须使用稳定随机值；修改它会让已有用户退出登录。

设置 `REDIS_URL` 后，认证限流会跨 runtime 副本共享：

```text
REDIS_URL=redis://localhost:6379/0
REDIS_KEY_PREFIX=travel-agent-cloud
```

`/health` 会返回 `redisRateLimitEnabled`，用于确认 Redis 限流是否生效。

## 对象存储

MinIO 兼容对象存储用于归档已登录用户的数据导出文件：

```text
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=travel_agent
MINIO_SECRET_KEY=change-me
MINIO_BUCKET=travel-agent-exports
MINIO_SECURE=false
```

导出文件通过已认证 API 下载，MinIO 不需要公网暴露。

## 邮箱验证和找回密码

默认 `EMAIL_PROVIDER=mock`。mock 模式会在 API 响应里返回 `devToken` 和 `actionUrl`，方便本地测试。

真实邮箱使用 SMTP：

```text
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

邮箱验证和找回密码 token 是一次性随机 token。数据库只保存 SHA-256 hash；明文 token 只会出现在 mock 响应或邮件链接中。

## GitHub OAuth

本地开发时，GitHub OAuth App callback URL 可以配置为：

```text
http://localhost:8000/api/v1/auth/oauth/github/callback
```

环境变量：

```text
GITHUB_OAUTH_CLIENT_ID=your-github-oauth-client-id
GITHUB_OAUTH_CLIENT_SECRET=your-github-oauth-client-secret
GITHUB_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/oauth/github/callback
OAUTH_HTTP_TIMEOUT_SECONDS=10
```

GitHub OAuth 使用签名 `state` 和 httpOnly state cookie。应用不会接收或存储 GitHub 账号密码。OAuth 创建的账号默认没有项目内密码，用户可通过设置密码或找回密码流程补充密码。

## Docker Compose 读取本地 env

如果希望容器读取 `agent-runtime/.env`，在项目根目录创建本地 override：

```powershell
Copy-Item docker-compose.override.example.yml docker-compose.override.yml
docker compose --profile worker up --build
```

`docker-compose.override.yml` 会被 Git 忽略。

## Agent 和工具配置

常用配置：

```text
MESSAGE_QUEUE_URL=amqp://user:password@rabbitmq:5672/
REDIS_URL=redis://redis:6379/0
REDIS_KEY_PREFIX=travel-agent-cloud
RPC_TIMEOUT_SECONDS=5
AGENT_ENGINE=langgraph
TRAVEL_TOOL_PROVIDER=fastmcp
FASTMCP_BASE_URL=http://travel-mcp:8100/mcp
FASTMCP_AUTH_TOKEN=
FASTMCP_TIMEOUT_SECONDS=8
FASTMCP_ATTRACTIONS_TOOL=travel.search_attractions
FASTMCP_HOTEL_TOOL=travel.search_hotel
FASTMCP_MEALS_TOOL=travel.search_meals
FASTMCP_ROUTES_TOOL=travel.plan_routes
FASTMCP_WEATHER_TOOL=travel.get_weather
FASTMCP_BUDGET_TOOL=travel.estimate_budget
WORKER_RECONNECT_INITIAL_SECONDS=2
WORKER_RECONNECT_MAX_SECONDS=30
```

说明：

- `MESSAGE_QUEUE_URL` 启用 RabbitMQ 事件发布。
- `REDIS_URL` 启用分布式认证限流。
- `AGENT_ENGINE=basic` 使用内置基础引擎。
- `AGENT_ENGINE=langgraph` 使用 LangGraph 工作流；安装可选依赖后会使用编译后的 `StateGraph`。
- `TRAVEL_TOOL_PROVIDER=mock` 使用确定性本地工具数据。
- `TRAVEL_TOOL_PROVIDER=fastmcp` 通过 `FASTMCP_BASE_URL` 调用 `travel-mcp`。
- FastMCP 工具失败或返回无效 schema 时，runtime 会 fallback 到 mock 值，保持公共 API 稳定。

`/health` 会返回 `agentEngine`、`agentEngineCapabilities` 和 `travelToolsProvider`。`GET /api/v1/agent/status` 还会返回隐私安全的运行 trace、工具调用汇总和质量评分汇总，不包含用户 prompt、生成内容、用户 ID、API key 或供应商 payload。

## RabbitMQ 事件和 Worker

配置 `MESSAGE_QUEUE_URL` 后，runtime 会向 `travel.events` topic exchange 发布小型领域事件。

当前事件包括：

- `trip.plan.created`
- `trip.plan.revised`
- `trip.plan.updated`
- `trip.plan.deleted`
- `trip.plan.version.restored`
- `agent.conversation.updated`
- `agent.conversation.deleted`
- `agent.conversation.summarize.requested`
- `agent.conversation.summary.created`
- `auth.oauth_logged_in`
- `auth.identity_linked`
- `auth.identity_unlinked`
- `user.profile.updated`
- `user.data_exported`
- `user.data.imported`
- `user.anonymous_data.imported`

worker 入口：

```powershell
python -m app.worker_main
```

该进程消费 `agent.conversation.summarize.requested`，处理异步摘要任务，并将任务状态从 `QUEUED` 更新为 `RUNNING`、`SUCCEEDED` 或 `FAILED`。如果 RabbitMQ 或 PostgreSQL 暂不可用，worker 会指数退避重连。

## 可观测性

每个 HTTP 响应包含：

- `X-Request-ID`：自动生成或透传传入的 `X-Request-ID`。
- `X-Process-Time-Ms`：后端请求处理耗时，单位毫秒。

日志写入 stdout，方便容器采集。通过 `LOG_LEVEL=DEBUG|INFO|WARNING|ERROR` 控制日志级别。

## 持久化

默认使用内存存储。配置 `DATABASE_URL` 后启用 PostgreSQL：

```text
DATABASE_URL=postgresql://travel_agent:password@localhost:5432/travel_agent_cloud
```

服务启动时会创建当前所需表：

- `conversations`
- `messages`
- `conversation_summaries`
- `conversation_summary_jobs`
- `trip_plans`
- `trip_plan_versions`
- `auth_tokens`
- `auth_identities`
- `users`
- `user_profiles`
- `user_security_events`

已登录请求以 httpOnly cookie 或 Bearer token 识别用户。没有有效登录时，本地开发仍支持匿名 `X-User-Id` fallback；两者同时存在时，以登录账号为准。

## 常用 API 示例

注册：

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"email":"you@example.com","password":"ChangeMe123!","displayName":"Traveler"}'
```

登录：

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"email":"you@example.com","password":"ChangeMe123!"}'
```

获取当前登录用户：

```bash
curl http://localhost:8000/api/v1/auth/me -b cookies.txt
```

创建结构化行程：

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

发送聊天消息：

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"I want a relaxed 3-day Chengdu food trip","mode":"TRIP_PLANNING"}'
```

查询行程列表：

```bash
curl "http://localhost:8000/api/v1/trip-plans?page=1&pageSize=20"
```

导出 Markdown：

```bash
curl http://localhost:8000/api/v1/trip-plans/{tripPlanId}/export
```

完整接口契约以 `app/main.py` 和 `app/schemas.py` 为准；公共 API 风格见根目录的 `docs/api-guidelines.md`。
