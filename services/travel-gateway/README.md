# travel-gateway

`travel-gateway` 是前端和外部客户端访问后端的统一入口。本地使用 Docker Compose 编排，VPS/K3s 部署时由 Ingress 进入 gateway，再由 gateway 路由到后端微服务。

## 当前职责

- 对外暴露统一 API 入口。
- 聚合 `/health`，返回系统整体健康状态和各服务 upstream 状态。
- 将 `/api/v1/auth/*` 和 `/api/v1/me/*` 路由到 `travel-auth`。
- 将 `/api/v1/chat`、`/api/v1/agent/*` 和 `/api/v1/conversations/*` 路由到 `travel-agent`。
- 将 `/api/v1/trip-plan*` 和 `/api/v1/trip-plans*` 路由到 `travel-trip`。
- 将 `/mcp` 和 `/tools/*` 路由到 `travel-mcp`。
- 为内部服务调用注入 `X-Travel-Internal-Token`。
- 统一透传或生成 `X-Request-ID`，并返回基础安全响应头。

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

为兼容前端和 smoke test，gateway 仍保留旧顶层字段：

- `databaseEnabled`
- `messageQueueEnabled`
- `redisRateLimitEnabled`
- `objectStorageEnabled`
- `githubOAuthEnabled`
- `agentEngine`
- `agentEngineCapabilities`
- `travelToolsProvider`

这些字段现在来自各微服务的 health 汇总，而不是由 `agent-runtime` 代表全局状态。

`/gateway/health` 也返回同一份聚合结果，保留给内部调试使用。

## 本地运行

```powershell
cd services/travel-gateway
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:TRAVEL_AUTH_URL="http://localhost:8300"
$env:TRAVEL_TRIP_URL="http://localhost:8200"
$env:TRAVEL_AGENT_URL="http://localhost:8400"
$env:TRAVEL_MCP_URL="http://localhost:8100"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

通常推荐在仓库根目录直接使用 Docker Compose：

```powershell
docker compose up -d --build
```

## Kubernetes 路由

```text
Ingress -> travel-gateway -> travel-auth
                         -> travel-agent
                         -> travel-trip
                         -> agent-runtime
                         -> travel-mcp
```
