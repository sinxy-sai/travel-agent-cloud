# travel-gateway

`travel-gateway` 是 Kubernetes 原生微服务路线中的 Python/FastAPI 网关服务。

## 当前职责

- 作为前端访问后端的公共 API 入口。
- 将 `/api/*` 和 `/health` 代理到 `agent-runtime`。
- 将 `/api/v1/auth/*` 和 `/api/v1/me/*` 优先代理到 `travel-auth`。
- 将 `/api/v1/trip-plan*` 和 `/api/v1/trip-plans*` 优先代理到 `travel-trip`。
- 将 `/api/v1/chat`、`/api/v1/agent/*` 和 `/api/v1/conversations/*` 优先代理到 `travel-agent`。
- 将 `/mcp` 和 `/tools/*` 代理到 `travel-mcp`。
- 通过 `/gateway/health` 返回 `agent-runtime` 和 `travel-mcp` 的 upstream 状态。
- 不承载业务逻辑，只做路由、入口治理和后续可扩展的横切能力。

## 本地运行

```powershell
cd services/travel-gateway
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:TRAVEL_MCP_URL="http://localhost:8100"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

`requirements.txt` 会以 editable 方式安装 `../common`，因此本地运行时要保持 `services/common` 目录存在。

## Kubernetes 路由

```text
Ingress -> travel-gateway -> agent-runtime
                         -> travel-mcp
```

## 后续拆分点

- `/api/v1/auth/*` 和 `/api/v1/me/*` 已先接入 `travel-auth` 门面服务，后续迁移真实认证存储逻辑。
- `/api/v1/trip-plans/*` 已先接入 `travel-trip` 门面服务，后续迁移真实行程持久化逻辑。
- `/api/v1/chat`、`/api/v1/agent/*` 和 `/api/v1/conversations/*` 已先接入 `travel-agent` 门面服务，后续迁移配额、审计和请求策略逻辑。
