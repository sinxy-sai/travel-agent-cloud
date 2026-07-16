# travel-gateway

Python/FastAPI gateway service for the Kubernetes-native microservice route.

Current responsibilities:

- Public API entrypoint for the frontend.
- Proxies `/api/*` and `/health` to `agent-runtime`.
- Proxies `/mcp` and `/tools/*` to `travel-mcp`.
- Exposes `/gateway/health` with upstream status for `agent-runtime` and `travel-mcp`.
- Keeps business logic out of the gateway.

Local development:

```powershell
cd services/travel-gateway
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:TRAVEL_MCP_URL="http://localhost:8100"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Kubernetes route:

```text
Ingress -> travel-gateway -> agent-runtime
                         -> travel-mcp
```

Future split points:

- `/api/v1/auth/*` can move from `agent-runtime` to `travel-auth`.
- `/api/v1/trip-plans/*` can move to `travel-trip`.
- Agent orchestration can move behind `travel-agent`, while `agent-runtime` remains the Python agent execution boundary.
