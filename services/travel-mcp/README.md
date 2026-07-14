# travel-mcp

Local MCP-compatible travel tool server for Agent Runtime development.

This service exposes a minimal JSON-RPC endpoint at `/mcp` with `tools/list`
and `tools/call`. It returns deterministic Amap-style stub data for:

- `travel.search_attractions`
- `travel.search_hotel`
- `travel.search_meals`
- `travel.plan_routes`
- `travel.get_weather`
- `travel.estimate_budget`

The service is intentionally stateless and does not persist user data. Replace
the stub handlers with real Amap/FastMCP tool calls later while keeping the
tool names and response schemas stable.

Local run:

```powershell
cd services/travel-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

Agent Runtime config for local host mode:

```text
TRAVEL_TOOL_PROVIDER=fastmcp
FASTMCP_BASE_URL=http://localhost:8100/mcp
```

Agent Runtime config for Docker Compose network mode:

```text
TRAVEL_TOOL_PROVIDER=fastmcp
FASTMCP_BASE_URL=http://travel-mcp:8100/mcp
```
