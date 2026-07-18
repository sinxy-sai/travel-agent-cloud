# travel-gateway

`travel-gateway` 是前端和外部客户端访问后端的统一入口。本地由 Docker Compose 编排，VPS/K3s 部署时由 Ingress 或前端 Nginx 进入 gateway，再按路径转发到后端微服务。

## 当前职责

- 对外暴露统一 API 入口。
- 聚合 `/health`，返回系统整体健康状态和各 upstream 状态。
- 将 `/api/v1/auth/*` 和 `/api/v1/me/*` 路由到 `travel-auth`。
- 将 `/api/v1/chat`、`/api/v1/agent/*` 和 `/api/v1/conversations/*` 路由到 `travel-agent`。
- 将 `/api/v1/trip-plan*`、`/api/v1/trip-plan-jobs*` 和 `/api/v1/trip-plans*` 路由到 `travel-trip`。
- 将 `/mcp` 和 `/tools/*` 路由到 `travel-mcp`。
- 为内部服务调用注入 `X-Travel-Internal-Token`。
- 统一透传或生成 `X-Request-ID`，并返回基础安全响应头。
- 可选启用 Redis 固定窗口限流。

## 健康检查

对外统一检查：

```text
GET /health
HEAD /health
```

`/health` 由 gateway 自己返回，不再代理到 `agent-runtime`。响应会聚合：

- `agentRuntime`
- `travelAuth`
- `travelTrip`
- `travelAgent`
- `travelMcp`

为兼容前端和 smoke test，gateway 保留旧顶层字段：

- `databaseEnabled`
- `messageQueueEnabled`
- `redisRateLimitEnabled`
- `objectStorageEnabled`
- `githubOAuthEnabled`
- `agentEngine`
- `agentEngineCapabilities`
- `travelToolsProvider`

其中 `redisRateLimitEnabled` 表示 gateway 已启用 Redis 限流并且能连通 Redis。

`/gateway/health` 和 `/metrics` 不参与限流，适合作为容器健康检查和 Prometheus 抓取入口。

## 环境变量

本地配置文件放在 `services/gateway/.env`，模板为 `services/gateway/.env.example`。

常用变量：

- `AGENT_RUNTIME_URL`
- `TRAVEL_AUTH_URL`
- `TRAVEL_TRIP_URL`
- `TRAVEL_AGENT_URL`
- `TRAVEL_MCP_URL`
- `INTERNAL_SERVICE_TOKEN`
- `GATEWAY_REQUEST_TIMEOUT_SECONDS`
- `ALLOWED_ORIGINS`
- `REDIS_RATE_LIMIT_ENABLED`
- `REDIS_URL`
- `GATEWAY_RATE_LIMIT_MAX_REQUESTS`
- `GATEWAY_RATE_LIMIT_WINDOW_SECONDS`

## 本地运行

```powershell
cd services/gateway
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:TRAVEL_AUTH_URL="http://localhost:8300"
$env:TRAVEL_TRIP_URL="http://localhost:8200"
$env:TRAVEL_AGENT_URL="http://localhost:8400"
$env:TRAVEL_MCP_URL="http://localhost:8100"
$env:AGENT_RUNTIME_URL="http://localhost:8000"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

容器环境推荐从仓库根目录启动：

```powershell
docker compose up -d --build travel-gateway
```

## 路由关系

```text
Ingress / frontend nginx
  -> travel-gateway
      -> travel-auth
      -> travel-agent
      -> travel-trip
      -> agent-runtime
      -> travel-mcp
```
