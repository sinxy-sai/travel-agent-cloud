# travel-gateway

`travel-gateway` 是 Kubernetes 原生微服务路线中的 Python/FastAPI 网关服务。

## 当前职责

- 作为前端访问后端的公共 API 入口。
- 将 `/api/*` 和 `/health` 代理到 `agent-runtime`。
- 将 `/api/v1/trip-plan*` 和 `/api/v1/trip-plans*` 优先代理到 `travel-trip`。
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

## Kubernetes 路由

```text
Ingress -> travel-gateway -> agent-runtime
                         -> travel-mcp
```

## 后续拆分点

- `/api/v1/auth/*` 后续可以从 `agent-runtime` 迁移到 `travel-auth`。
- `/api/v1/trip-plans/*` 已先接入 `travel-trip` 门面服务，后续迁移真实行程持久化逻辑。
- Agent 编排入口后续可以迁移到 `travel-agent`，但 LangGraph/LangChain 执行引擎仍可以留在 `agent-runtime`。
